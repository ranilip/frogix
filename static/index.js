

const TEMP_UNIT_MAP = { metric: '°C', imperial: '°F', standard: 'K' };

const METRIC_UNIT = {
  temperature: null,   // taken from settings.units
  humidity:    '%',
  pressure:    'hPa',
  co2:         'ppm',
  voc:         'ppb',
  lux:         'lx',
};

const METRIC_CONFIG = {
  temperature: { label: 'Temperature', color: '#00cfaa', icon: 'thermometer' },
  humidity:    { label: 'Humidity',    color: '#00b4d8', icon: 'droplet'     },
  pressure:    { label: 'Pressure',    color: '#a78bfa', icon: 'gauge'       },
  co2:         { label: 'CO₂',         color: '#fb923c', icon: 'leaf'        },
  voc:         { label: 'VOC',         color: '#f472b6', icon: 'wind'        },
  lux:         { label: 'Illuminance', color: '#fbbf24', icon: 'sun'         },
};

const ICONS = {
  thermometer: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M14 14.76V3.5a2.5 2.5 0 0 0-5 0v11.26a4.5 4.5 0 1 0 5 0z"/></svg>`,
  droplet:     `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg>`,
  gauge:       `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>`,
  leaf:        `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 4.48 19 2c1 2 2 4.18 2 8 0 5.5-4.78 10-10 10z"/><path d="M2 21c0-3 1.85-5.36 5.08-6C9.5 14.52 12 13 13 12"/></svg>`,
  wind:        `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M9.59 4.59A2 2 0 1 1 11 8H2m10.59 11.41A2 2 0 1 0 14 16H2m15.73-8.27A2.5 2.5 0 1 1 19.5 12H2"/></svg>`,
  sun:         `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>`,
  default:     `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><circle cx="12" cy="16" r=".5" fill="currentColor"/></svg>`,
};

const STATUS_LABEL = {
  ok:             'connected',
  fail:           'failed',
  no_credentials: 'not configured',
  off:            'off',
  unknown:        '--',
};

const DAY_MS = 24 * 60 * 60 * 1000;
const HOUR_MS = 60 * 60 * 1000;
const QUARTER_MS = 15 * 60 * 1000;


async function fetchJSON(url) {
  try {
    const r = await fetch(url, { cache: 'no-store' });
    return r.ok ? await r.json() : null;
  } catch (_) { return null; }
}

function unitFor(key, tempUnit) {
  const u = METRIC_UNIT[key];
  if (u === null) return TEMP_UNIT_MAP[tempUnit] || '°C';
  return u !== undefined ? u : '';
}

function convertTemperature(celsius, tempUnit) {
  if (typeof celsius !== 'number') return celsius;
  if (tempUnit === 'imperial') return celsius * 9 / 5 + 32;
  if (tempUnit === 'standard') return celsius + 273.15;
  return celsius;
}

function displayValue(key, value, tempUnit) {
  if (typeof value !== 'number') return value;
  const converted = key === 'temperature' ? convertTemperature(value, tempUnit) : value;
  return Math.round(converted * 10) / 10;
}

function formatValue(key, value, tempUnit, digits = 1) {
  const v = displayValue(key, value, tempUnit);
  return typeof v === 'number' ? v.toFixed(digits) : String(v ?? '--');
}

function parseTs(tsStr) {
  if (!tsStr) return NaN;
  const t = Date.parse(tsStr);
  if (!Number.isNaN(t)) return t;

  const m = String(tsStr).match(/T(\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!m) return NaN;
  const d = new Date();
  d.setHours(Number(m[1]), Number(m[2]), Number(m[3] || 0), 0);
  return d.getTime();
}

function formatTimeMs(ms) {
  if (!Number.isFinite(ms)) return '';
  const d = new Date(ms);
  const pad = n => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function currentChartEndMs() {
  return Math.floor(Date.now() / QUARTER_MS) * QUARTER_MS;
}

function snapToQuarterMs(ms) {
  return Math.round(ms / QUARTER_MS) * QUARTER_MS;
}

function msUntilNextQuarter() {
  const now = Date.now();
  return Math.ceil((now + 1000) / QUARTER_MS) * QUARTER_MS - now;
}

function realPointsForLast24(rows, key, units, endMs = currentChartEndMs()) {
  const sourceRows = (rows || [])
    .map(r => ({ v: displayValue(key, r[key], units), rawT: snapToQuarterMs(parseTs(r.ts)) }))
    .filter(p => typeof p.v === 'number' && Number.isFinite(p.rawT))
    .sort((a, b) => a.rawT - b.rawT);

  if (!sourceRows.length) return [];

  const latestRaw = sourceRows[sourceRows.length - 1].rawT;
  const offset = endMs - latestRaw;
  const startMs = endMs - DAY_MS;
  return sourceRows
    .map(p => ({ v: p.v, t: p.rawT + offset, fake: false }))
    .filter(p => p.t >= startMs && p.t <= endMs);
}

function valuesForLast24(rows, key, units) {
  return realPointsForLast24(rows, key, units).map(p => p.v);
}


function buildChart(rows, key, color, W, H, units) {
  const endMs = currentChartEndMs();
  const startMs = endMs - DAY_MS;
  const pts = realPointsForLast24(rows, key, units, endMs);

  const PL = 38, PR = 19, PT = 17, PB = 33;
  const cW = W - PL - PR, cH = H - PT - PB;

  if (pts.length < 2) {
    const point = pts[0];
    const x = point ? (W - PR) : (W / 2);
    const y = point ? (PT + cH / 2) : (H / 2);
    return {
      viewBox: `0 0 ${W} ${H}`,
      inner: `
        ${buildHourlyBands(startMs, endMs, PL, PR, PT, cW, cH, W)}
        ${buildCenterGuide(PL, PT, cW, cH)}
        ${point ? `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.2" fill="${color}"/>
          <text x="${(W - PR).toFixed(1)}" y="${(H - 7).toFixed(1)}"
            text-anchor="middle" fill="#4a6a8a" font-size="9" font-family="system-ui">${formatTimeMs(point.t)}</text>` :
          `<text x="${W / 2}" y="${H / 2}" text-anchor="middle"
            fill="#4a6a8a" font-size="11" font-family="system-ui">No data</text>`}`
    };
  }

  const vals = pts.map(p => p.v);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const range = maxV - minV || 1;

  const toX = t => PL + ((t - startMs) / (endMs - startMs || 1)) * cW;
  const toY = v => PT + (1 - (v - minV) / range) * cH;

  const xyPairs = pts.map(p => [toX(p.t), toY(p.v)]);
  const linePts = xyPairs.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const areaPts = [
    `${PL},${PT + cH}`,
    ...xyPairs.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`),
    `${(PL + cW).toFixed(1)},${(PT + cH).toFixed(1)}`,
  ].join(' ');

  const gid = `g${key}${W | 0}`;

  const yTicks = [maxV, (maxV + minV) / 2, minV];
  const yLabels = yTicks.map((v, i) => {
    const y = PT + (i / 2) * cH;
    return `<line x1="${PL}" y1="${y.toFixed(1)}" x2="${(W - PR).toFixed(1)}" y2="${y.toFixed(1)}"
        stroke="${color}" stroke-width="1" opacity="0.4"/>
      <text x="${(PL - 4).toFixed(1)}" y="${(y + 3.5).toFixed(1)}"
        text-anchor="end" fill="#4a6a8a" font-size="9" font-family="system-ui">${v.toFixed(1)}</text>`;
  }).join('');

  const xLabels = [startMs, startMs + 12 * HOUR_MS, endMs]
    .map((t, idx) => {
      const x = idx === 2 ? PL + cW : toX(t);
      return `<text x="${x.toFixed(1)}" y="${(H - 7).toFixed(1)}"
        text-anchor="${idx === 0 ? 'start' : idx === 2 ? 'end' : 'middle'}"
        fill="#4a6a8a" font-size="9" font-family="system-ui">${formatTimeMs(t)}</text>`;
    }).join('');

  return {
    viewBox: `0 0 ${W} ${H}`,
    inner: `
      <defs>
        <linearGradient id="${gid}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stop-color="${color}" stop-opacity="0.28"/>
          <stop offset="100%" stop-color="${color}" stop-opacity="0.02"/>
        </linearGradient>
      </defs>
      ${buildHourlyBands(startMs, endMs, PL, PR, PT, cW, cH, W)}
      ${buildCenterGuide(PL, PT, cW, cH)}
      ${yLabels}
      <polygon points="${areaPts}" fill="url(#${gid})"/>
      <polyline fill="none" stroke="${color}" stroke-width="1.8"
        stroke-linejoin="round" stroke-linecap="round" points="${linePts}"/>
      ${xLabels}`
  };
}

function buildCenterGuide(PL, PT, cW, cH) {
  const x = PL + cW / 2;
  return `<line x1="${x.toFixed(1)}" y1="${PT}" x2="${x.toFixed(1)}" y2="${PT + cH}"
    stroke="#4a6a8a" stroke-width="1.2" opacity="0.42" stroke-dasharray="4 5"/>`;
}

function buildHourlyBands(startMs, endMs, PL, PR, PT, cW, cH, W) {
  const firstHour = Math.ceil(startMs / HOUR_MS) * HOUR_MS;
  const parts = [];
  for (let t = firstHour, i = 0; t <= endMs; t += HOUR_MS, i++) {
    const x = PL + ((t - startMs) / (endMs - startMs || 1)) * cW;
    if (i % 2 === 0) {
      const nextX = Math.min(W - PR, PL + (((t + HOUR_MS) - startMs) / (endMs - startMs || 1)) * cW);
      parts.push(`<rect x="${x.toFixed(1)}" y="${PT}" width="${Math.max(0, nextX - x).toFixed(1)}" height="${cH}" fill="#ffffff" opacity="0.025"/>`);
    }
    parts.push(`<line x1="${x.toFixed(1)}" y1="${PT}" x2="${x.toFixed(1)}" y2="${PT + cH}" stroke="#d8f3ff" stroke-width="1" opacity="0.10"/>`);
  }
  return parts.join('');
}


let chartObserver = null;
const observedDivs = new Set();

function initChartObserver() {
  if (chartObserver) return;
  if (typeof ResizeObserver === 'undefined') return;

  chartObserver = new ResizeObserver(entries => {
    for (const entry of entries) {
      const div = entry.target;
      redrawChartDiv(div);
    }
  });
}

function redrawChartDiv(div) {
  const key   = div.dataset.key;
  const color = div.dataset.color;
  if (!key || !color) return;
  const W = Math.round(div.clientWidth)  || 300;
  const H = Math.round(div.clientHeight) || 150;
  const rows  = (cachedHistory && cachedHistory.data) || [];
  const units = div.dataset.units || cachedUnits || 'metric';
  const chart = buildChart(rows, key, color, W, H, units);
  const svg   = div.querySelector('svg.metric-chart');
  if (svg) {
    svg.setAttribute('viewBox', chart.viewBox);
    svg.innerHTML = chart.inner;
  }
}

function observeChartDiv(div) {
  if (!chartObserver) initChartObserver();
  if (chartObserver && !observedDivs.has(div)) {
    chartObserver.observe(div);
    observedDivs.add(div);
  }
}

function refreshAllCharts() {
  observedDivs.forEach(div => redrawChartDiv(div));
}


let _renderedKeysSig = null;  // signature of last full card build

function renderCards(readings, history, units) {
  const container = document.getElementById('metric-cards');
  if (!readings) {
    container.innerHTML = `<p style="color:#4a6a8a;padding:1rem">No sensor data available</p>`;
    _renderedKeysSig = null;
    if (chartObserver) { observedDivs.forEach(d => chartObserver.unobserve(d)); observedDivs.clear(); }
    return;
  }

  const sig = `${Object.keys(readings).sort().join(',')}|${units}`;

  if (sig !== _renderedKeysSig) {
    _buildAllCards(container, readings, history, units);
    _renderedKeysSig = sig;
  } else {
    _patchCardValues(container, readings, history, units);
  }
}

function _buildAllCards(container, readings, history, units) {
  if (chartObserver) {
    observedDivs.forEach(div => chartObserver.unobserve(div));
    observedDivs.clear();
  }

  const rows = (history && history.data) || [];

  const html = Object.entries(readings).map(([key, cur]) => {
    const cfg   = METRIC_CONFIG[key] || { label: key, color: '#00cfaa', icon: 'default' };
    const unit  = unitFor(key, units);
    const color = cfg.color;
    const curText = formatValue(key, cur, units, 1);

    const histVals = valuesForLast24(rows, key, units);
    const maxV = histVals.length ? Math.max(...histVals) : null;
    const minV = histVals.length ? Math.min(...histVals) : null;

    const maxHtml = `<div class="stat-row">
        <span class="stat-val" style="color:${color}" data-stat="max">${maxV !== null ? maxV.toFixed(1) + ' ' + unit : ''}</span>
        ${maxV !== null ? `<span class="stat-lbl">Max</span>` : ''}
      </div>`;
    const minHtml = `<div class="stat-row">
        <span class="stat-val" style="color:${color};opacity:.65" data-stat="min">${minV !== null ? minV.toFixed(1) + ' ' + unit : ''}</span>
        ${minV !== null ? `<span class="stat-lbl">Min</span>` : ''}
      </div>`;

    return `
      <div class="metric-card" data-metric="${key}">
        <div class="metric-left">
          <div class="metric-top">
            <div class="metric-icon-wrap"
                 style="background:${color}22;border:1px solid ${color}44;color:${color}">
              ${ICONS[cfg.icon] || ICONS.default}
            </div>
            <div>
              <div class="metric-name">${cfg.label}</div>
              <div class="metric-unit">${unit}</div>
            </div>
          </div>
          <div class="metric-current-block">
            <div class="metric-value" style="color:${color}" data-live="cur">${curText}</div>
            <div class="metric-curr-label">${unit} · Current</div>
          </div>
          <div class="metric-minmax">${maxHtml}${minHtml}</div>
        </div>
        <div class="metric-right" data-key="${key}" data-color="${color}" data-units="${units}">
          <svg class="metric-chart" viewBox="0 0 300 150"
               preserveAspectRatio="xMidYMid meet"></svg>
        </div>
      </div>`;
  }).join('');

  container.innerHTML = html || `<p style="color:#4a6a8a;padding:1rem">No data</p>`;

  container.querySelectorAll('.metric-right[data-key]').forEach(div => observeChartDiv(div));
}

function _patchCardValues(container, readings, history, units) {
  const rows = (history && history.data) || [];

  Object.entries(readings).forEach(([key, cur]) => {
    const card = container.querySelector(`.metric-card[data-metric="${key}"]`);
    if (!card) return;

    const unit = unitFor(key, units);

    const curEl = card.querySelector('[data-live="cur"]');
    if (curEl) curEl.textContent = formatValue(key, cur, units, 1);

    const histVals = valuesForLast24(rows, key, units);
    if (histVals.length) {
      const maxV = Math.max(...histVals);
      const minV = Math.min(...histVals);
      const maxRow = card.querySelector('[data-stat="max"]');
      const minRow = card.querySelector('[data-stat="min"]');
      if (maxRow) {
        maxRow.textContent = `${maxV.toFixed(1)} ${unit}`;
        if (!maxRow.nextElementSibling) {
          const lbl = document.createElement('span');
          lbl.className = 'stat-lbl';
          lbl.textContent = 'Max';
          maxRow.parentElement.appendChild(lbl);
        }
      }
      if (minRow) {
        minRow.textContent = `${minV.toFixed(1)} ${unit}`;
        if (!minRow.nextElementSibling) {
          const lbl = document.createElement('span');
          lbl.className = 'stat-lbl';
          lbl.textContent = 'Min';
          minRow.parentElement.appendChild(lbl);
        }
      }
    }
  });

  container.querySelectorAll('.metric-right[data-key]').forEach(div => {
    div.dataset.units = units;
  });
}


function renderStatus(id, status, labelOverride) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = labelOverride || STATUS_LABEL[status] || status || '--';
}

let _uptimeBase    = 0;
let _uptimeFetchAt = null;

function parseUptimeSecs(str) {
  if (!str) return 0;
  const h = parseInt((str.match(/(\d+)\s*h/)     || [0, 0])[1], 10) || 0;
  const m = parseInt((str.match(/(\d+)\s*m(?!s)/) || [0, 0])[1], 10) || 0;
  const s = parseInt((str.match(/(\d+)\s*s/)      || [0, 0])[1], 10) || 0;
  const total = h * 3600 + m * 60 + s;
  return total || (parseInt(str, 10) || 0);
}

function formatUptime(secs) {
  secs = Math.max(0, secs);
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  return `${h}h ${m}m ${s}s`;
}

function tickUptime() {
  if (_uptimeFetchAt === null) return;
  const el = document.getElementById('uptime');
  if (!el) return;
  const elapsed = Math.floor((Date.now() - _uptimeFetchAt) / 1000);
  el.textContent = formatUptime(_uptimeBase + elapsed);
}

async function refreshSysinfo() {
  if (dashboardPollingPaused) return;
  const d = await fetchJSON('/api/sysinfo');
  if (!d) return;
  const setText = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v || '--'; };
  setText('version', d.version);
  setText('ap_ip',   d.ap_ip);
  setText('sta_ip',  d.sta_ip);
  renderStatus('wifi_status', d.wifi_status, d.wifi_ssid);
  renderStatus('mqtt_status', d.mqtt_status);
  _uptimeBase    = parseUptimeSecs(d.uptime);
  _uptimeFetchAt = Date.now();
  tickUptime();
}


function tickClock() {
  const el = document.getElementById('clock');
  if (!el) return;
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  el.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  tickUptime();
}


let cachedReadings = null, cachedHistory = null, cachedUnits = 'metric';
let dashboardPollingPaused = false;

async function refreshReadings() {
  if (dashboardPollingPaused) return;
  const data = await fetchJSON('/api/readings');
  if (!data) return;
  cachedReadings = data.readings;
  cachedUnits    = data.units || 'metric';
  renderCards(cachedReadings, cachedHistory, cachedUnits);
}

async function refreshHistory() {
  if (dashboardPollingPaused) return;
  const data = await fetchJSON('/api/history');
  if (!data) return;
  cachedHistory = data;
  if (cachedReadings) {
    _patchCardValues(document.getElementById('metric-cards'), cachedReadings, cachedHistory, cachedUnits);
    refreshAllCharts();
  } else {
    renderCards(cachedReadings, cachedHistory, cachedUnits);
  }
}


function initSettingsModal() {
  const openBtn = document.getElementById('open-settings');
  const modal = document.getElementById('settings-modal');
  const frame = document.getElementById('settings-frame');
  if (!openBtn || !modal || !frame) return;
  const setupUrl = openBtn.getAttribute('href') || '/setup';

  const preload = () => {
    if (!frame.getAttribute('src')) frame.src = setupUrl;
  };

  const close = () => {
    dashboardPollingPaused = false;
    modal.classList.remove('is-open');
    modal.setAttribute('aria-hidden', 'true');
    refreshReadings();
    refreshSysinfo();
    refreshHistory();
  };

  const open = event => {
    event.preventDefault();
    dashboardPollingPaused = true;
    preload();
    modal.classList.add('is-open');
    modal.setAttribute('aria-hidden', 'false');
  };

  openBtn.addEventListener('click', open);
  window.addEventListener('message', event => {
    if (event.data && event.data.type === 'close-settings-modal') close();
    if (event.data && event.data.type === 'theme-changed') applyTheme(event.data.theme);
  });
  window.addEventListener('keydown', event => {
    if (event.key === 'Escape' && modal.classList.contains('is-open')) close();
  });

  setTimeout(preload, 1200);
}

initChartObserver();
initSettingsModal();
refreshReadings();
refreshHistory();
refreshSysinfo();
tickClock();

function scheduleQuarterRefresh() {
  setTimeout(async () => {
    if (!dashboardPollingPaused) {
      await refreshReadings();
      await refreshSysinfo();
      await refreshHistory();
    }
    scheduleQuarterRefresh();
  }, msUntilNextQuarter());
}

scheduleQuarterRefresh();
setInterval(tickClock,       1000);

setInterval(() => {
  fetch('/api/ping', {cache: 'no-store'}).catch(() => {});
}, 30000);
