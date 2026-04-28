
const formSnapshots = new WeakMap();
const SETTINGS_FORM_SELECTOR = '#form-wifi, #form-ap, #form-mqtt, #form-params, #form-led';
const LED_ROLES = ['alive', 'measurement', 'config_ap', 'config_sta', 'network', 'error', 'factory_reset'];
const LED_PALETTE = [
  {name: 'Red',     hex: '#ff0000'},
  {name: 'Orange',  hex: '#ff5900'},
  {name: 'Yellow',  hex: '#ffc400'},
  {name: 'Green',   hex: '#1aff00'},
  {name: 'Teal',    hex: '#00ffd2'},
  {name: 'Cyan',    hex: '#0095ff'},
  {name: 'Blue',    hex: '#003cff'},
  {name: 'Violet',  hex: '#6811ff'},
  {name: 'Pink',    hex: '#ff007c'},
];
let ledPreviewTimer = null;


function setSelectValue(field, value, {silent = false} = {}) {
  const input = field.querySelector('input[type=hidden]');
  const labelEl = field.querySelector('.select-value');
  const options = field.querySelectorAll('.select-options li');
  let chosen = null;
  options.forEach(o => {
    const isSel = o.dataset.value === value;
    o.setAttribute('aria-selected', isSel ? 'true' : 'false');
    if (isSel) chosen = o;
  });
  if (input) input.value = value;
  if (labelEl) {
    if (chosen && chosen.children.length > 0) {
      labelEl.innerHTML = chosen.innerHTML;
    } else {
      labelEl.textContent = (chosen && (chosen.dataset.label || chosen.textContent.trim())) || value || '';
    }
  }
  if (!silent && input) {
    input.dispatchEvent(new Event('input', {bubbles: true}));
    input.dispatchEvent(new Event('change', {bubbles: true}));
  }
}

function closeAllSelects(except) {
  document.querySelectorAll('.select-field.is-open').forEach(f => {
    if (f === except) return;
    f.classList.remove('is-open');
    const list = f.querySelector('.select-options');
    const trigger = f.querySelector('.select-trigger');
    if (list) list.hidden = true;
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
  });
}

function initSelectField(field) {
  const trigger = field.querySelector('.select-trigger');
  const list = field.querySelector('.select-options');
  if (!trigger || !list) return;

  trigger.addEventListener('click', event => {
    event.stopPropagation();
    const isOpen = field.classList.toggle('is-open');
    list.hidden = !isOpen;
    trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    if (isOpen) closeAllSelects(field);
  });

  list.addEventListener('click', event => {
    const li = event.target.closest('li[data-value]');
    if (!li || li.getAttribute('aria-disabled') === 'true') return;
    setSelectValue(field, li.dataset.value);
    field.classList.remove('is-open');
    list.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    trigger.blur();
  });

  trigger.addEventListener('keydown', event => {
    if (event.key === 'Escape' && field.classList.contains('is-open')) {
      field.classList.remove('is-open');
      list.hidden = true;
      trigger.setAttribute('aria-expanded', 'false');
    }
  });
}

document.addEventListener('click', () => {
  closeAllSelects(null);
  closeLedPalettes(null);
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeAllSelects(null);
    closeLedPalettes(null);
  }
});
document.querySelectorAll('.select-field').forEach(initSelectField);

const wifiTrigger = document.querySelector('#form-wifi .select-field[data-field=ssid] .select-trigger');
if (wifiTrigger) {
  wifiTrigger.addEventListener('click', () => {
    const field = wifiTrigger.closest('.select-field');
    if (field && field.classList.contains('is-open')) {
      startWifiScan();
    }
  });
}

function collectFormData(form) {
  const data = {};
  for (const el of form.querySelectorAll('input, select')) {
    if (!el.name) continue;
    if (el.type === 'checkbox') {
      data[el.name] = el.checked;
      continue;
    }
    let v = el.value;
    if (el.name === 'mqtt_interval_minutes') {
      data.mqtt_interval = Number(v) * 60;
      continue;
    }
    if (el.type === 'number' || el.type === 'range') {
      v = v === '' ? null : Number(v);
    }
    if (v !== null && v !== '') data[el.name] = v;
  }
  return data;
}

function snapshotForm(form) {
  formSnapshots.set(form, JSON.stringify(collectFormData(form)));
}

function formChanged(form) {
  return formSnapshots.get(form) !== JSON.stringify(collectFormData(form));
}

function setSubmitEnabled(form, enabled) {
  const button = form.querySelector('button[type=submit]');
  if (button) button.disabled = !enabled;
}

function formatMinutes(minutes) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours
    ? `${hours} h${rest ? ` ${rest} min` : ''}`
    : `${minutes} min`;
}

function updateIntervalLabel(inputSelector, labelId, fallbackMinutes) {
  const input = document.querySelector(inputSelector);
  const label = document.getElementById(labelId);
  if (!input || !label) return;
  const minutes = Number(input.value) || fallbackMinutes;
  label.textContent = formatMinutes(minutes);
  updateRangeFill(input);
}

function updateIntervalWarning(inputSelector, warningId, message) {
  const input = document.querySelector(inputSelector);
  const warning = document.getElementById(warningId);
  if (!input || !warning) return;
  const minutes = Number(input.value) || 15;
  warning.textContent = minutes < 15 ? message : '';
}

function updateMqttIntervalLabel() {
  updateIntervalLabel('#form-params [name=mqtt_interval_minutes]', 'mqtt-interval-label', 5);
  updateIntervalWarning(
    '#form-params [name=mqtt_interval_minutes]',
    'mqtt-interval-warning',
    'Below 15 min: data is published more often, increasing network use and power consumption.'
  );
}


function updateRangeFill(input) {
  const min = Number(input.min) || 0;
  const max = Number(input.max) || 100;
  const value = Number(input.value) || min;
  const percent = ((value - min) / (max - min)) * 100;
  input.style.setProperty('--range-fill', `${percent}%`);
}

function updateLedControls() {
  LED_ROLES.forEach(role => {
    const input = document.querySelector(`#form-led [name=${role}_brightness]`);
    const label = document.querySelector(`#form-led [data-led-brightness=${role}]`);
    if (!input || !label) return;
    label.textContent = `${Number(input.value) || 0}%`;
    updateRangeFill(input);
  });
  syncLedPalettes();
}

function renderLedPalettes() {
  document.querySelectorAll('#form-led .color-picker').forEach(picker => {
    const role = picker.dataset.ledRole;
    const trigger = picker.querySelector('.color-trigger');
    const palette = picker.querySelector('.color-palette');
    const input = document.querySelector(`#form-led [name=${role}_color]`);
    if (!trigger || !palette || !input) return;
    palette.innerHTML = LED_PALETTE.map(color =>
      `<button type="button" class="color-swatch" style="--swatch:${color.hex}" data-color="${color.hex}" aria-label="${role} ${color.name}"></button>`
    ).join('');
    trigger.addEventListener('click', event => {
      event.stopPropagation();
      closeLedPalettes(picker);
      const isOpen = picker.classList.toggle('is-open');
      palette.hidden = !isOpen;
    });
    palette.addEventListener('click', event => {
      event.stopPropagation();
      const button = event.target.closest('.color-swatch');
      if (!button) return;
      input.value = button.dataset.color;
      input.dispatchEvent(new Event('input', {bubbles: true}));
      syncLedPalettes();
      picker.classList.remove('is-open');
      palette.hidden = true;
      previewLedRole(role);
    });
  });
  syncLedPalettes();
}

function closeLedPalettes(except) {
  document.querySelectorAll('#form-led .color-picker.is-open').forEach(picker => {
    if (picker === except) return;
    picker.classList.remove('is-open');
    const palette = picker.querySelector('.color-palette');
    if (palette) palette.hidden = true;
  });
}

function syncLedPalettes() {
  LED_ROLES.forEach(role => {
    const input = document.querySelector(`#form-led [name=${role}_color]`);
    if (!input) return;
    const picker = document.querySelector(`#form-led .color-picker[data-led-role=${role}]`);
    if (picker) picker.style.setProperty('--selected-color', input.value);
    document.querySelectorAll(`#form-led .color-picker[data-led-role=${role}] .color-swatch`).forEach(button => {
      button.classList.toggle('is-selected', button.dataset.color.toLowerCase() === input.value.toLowerCase());
    });
  });
}

function previewLedRole(role) {
  const color = document.querySelector(`#form-led [name=${role}_color]`);
  const brightness = document.querySelector(`#form-led [name=${role}_brightness]`);
  if (!color || !brightness) return;
  clearTimeout(ledPreviewTimer);
  ledPreviewTimer = setTimeout(() => {
    fetch('/api/led/preview', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({color: color.value, brightness: Number(brightness.value) || 0}),
    }).catch(() => {});
  }, 120);
}

function restoreLedPreview() {
  if (navigator.sendBeacon) {
    const blob = new Blob(['{}'], {type: 'application/json'});
    navigator.sendBeacon('/api/led/restore', blob);
    return;
  }
  fetch('/api/led/restore', {method: 'POST', keepalive: true}).catch(() => {});
}

function duplicateLedColor() {
  const seen = {};
  for (const role of LED_ROLES) {
    const input = document.querySelector(`#form-led [name=${role}_color]`);
    if (!input) continue;
    const color = input.value.toLowerCase();
    if (seen[color]) return {color, first: seen[color], second: role};
    seen[color] = role;
  }
  return null;
}

function watchForm(form) {
  const update = () => {
    if (form.id === 'form-params') {
      updateMqttIntervalLabel();
    }
    if (form.id === 'form-led') {
      updateLedControls();
      const active = document.activeElement;
      const role = active && active.name && active.name.endsWith('_brightness')
        ? active.name.replace('_brightness', '')
        : null;
      if (role) previewLedRole(role);
    }
    setSubmitEnabled(form, formChanged(form));
  };
  form.addEventListener('input', update);
  form.addEventListener('change', update);
}


let wifiScanInFlight = false;   // запобігаємо паралельним стартам

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function rssiBarsSVG(rssi) {
  let bars;
  if (rssi >= -55) bars = 3;
  else if (rssi >= -70) bars = 2;
  else if (rssi >= -85) bars = 1;
  else bars = 0;
  const dots = [];
  for (let i = 0; i < 3; i++) {
    const cx = 2 + i * 4;        // 2, 6, 10
    const filled = i < bars;
    if (filled) {
      dots.push(`<circle cx="${cx}" cy="6" r="1.5" fill="currentColor"/>`);
    } else {
      dots.push(`<circle cx="${cx}" cy="6" r="1.4" fill="none" stroke="currentColor" stroke-width=".7" opacity=".4"/>`);
    }
  }
  return `<svg class="ssid-bars" viewBox="0 0 12 12" aria-hidden="true">${dots.join('')}</svg>`;
}

const LOCK_SVG = `<svg class="ssid-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>`;

function renderWifiOptions(field, networks) {
  const list = field.querySelector('.select-options');
  if (!networks.length) {
    list.innerHTML = '<li role="option" aria-disabled="true">No networks found</li>';
    return;
  }
  list.innerHTML = networks.map(n => {
    const meta = n._saved
      ? '<span class="ssid-meta">saved</span>'
      : `<span class="ssid-meta">${rssiBarsSVG(n.rssi)}${n.secured ? LOCK_SVG : ''}</span>`;
    const ssid = escapeHtml(n.ssid);
    return `<li role="option" data-value="${ssid}" data-label="${ssid}">
      <span class="ssid-name">${ssid}</span>
      ${meta}
    </li>`;
  }).join('');
  const currentValue = field.querySelector('input[type=hidden]').value;
  if (currentValue) {
    setSelectValue(field, currentValue, {silent: true});
  }
}

async function startWifiScan() {
  if (wifiScanInFlight) return;
  wifiScanInFlight = true;

  const field = document.querySelector('#form-wifi .select-field[data-field=ssid]');
  if (!field) { wifiScanInFlight = false; return; }
  const list = field.querySelector('.select-options');

  list.innerHTML = '<li role="option" aria-disabled="true">Scanning... (~5s, AP briefly offline)</li>';

  try {
    await fetch('/api/wifi/scan/start', {method: 'POST', cache: 'no-store'});
  } catch (e) {
  }

  const field2 = field;        // alias для closure
  const startedAt = Date.now();
  const maxWaitMs = 30000;     // 30с safety net
  const list2 = list;

  const poll = async () => {
    if (Date.now() - startedAt > maxWaitMs) {
      list2.innerHTML = '<li role="option" aria-disabled="true">Scan timed out</li>';
      wifiScanInFlight = false;
      return;
    }
    try {
      const r = await fetch('/api/wifi/scan/result', {cache: 'no-store'});
      if (r.ok) {
        const state = await r.json();
        if (state.status === 'done') {
          const currentSsid = field2.querySelector('input[type=hidden]').value;
          const networks = (state.networks || []).slice();
          if (currentSsid && !networks.some(n => n.ssid === currentSsid)) {
            networks.push({ssid: currentSsid, rssi: -100, secured: true, _saved: true});
          }
          renderWifiOptions(field2, networks);
          wifiScanInFlight = false;
          return;
        }
        if (state.status === 'error') {
          list2.innerHTML = `<li role="option" aria-disabled="true">Scan error: ${escapeHtml(state.error || 'unknown')}</li>`;
          wifiScanInFlight = false;
          return;
        }
      }
    } catch (_) {
    }
    setTimeout(poll, 1000);
  };
  setTimeout(poll, 4000);
}


const WIFI_TEST_RESULT_MESSAGES = {
  ok:                    'Wi-Fi password is correct. Router connection works.',
  wrong_password:        'Wrong password',
  no_ap:                 'Could not connect. Check network name, signal, and password.',
  fail:                  'Connection failed',
  timeout:               'Connection timed out',
};

function setWifiButtonsBusy(form, busy) {
  form.querySelectorAll('button').forEach(button => {
    button.disabled = busy;
  });
  if (!busy) {
    setSubmitEnabled(form, formChanged(form));
  }
}

async function checkWifiCredentials(form) {
  const field = document.querySelector('#form-wifi .select-field[data-field=ssid]');
  const ssidInput = field && field.querySelector('input[type=hidden]');
  const passwordInput = document.querySelector('#form-wifi [name=password]');
  const statusEl = document.getElementById('status-wifi');

  const ssid = ssidInput ? ssidInput.value : '';
  const password = passwordInput ? passwordInput.value : '';

  if (!ssid) {
    setStatus(statusEl, 'Choose a Wi-Fi network first', 'err');
    return null;
  }

  setWifiButtonsBusy(form, true);
  setStatus(statusEl, 'Checking Wi-Fi... browser will lose Wi-Fi ~15s, do not close this tab.');

  try {
    const start = await fetch('/api/wifi/test', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ssid, password}),
      cache: 'no-store',
    });
    if (!start.ok) {
      setStatus(statusEl, await start.text() || 'Could not start Wi-Fi check', 'err');
      setWifiButtonsBusy(form, false);
      return null;
    }
  } catch (_) {
  }

  const startedAt = Date.now();
  const maxWaitMs = 30000;

  return await new Promise(resolve => {
    const poll = async () => {
    if (Date.now() - startedAt > maxWaitMs) {
      setStatus(statusEl, 'Wi-Fi check timed out -- try again', 'err');
      setWifiButtonsBusy(form, false);
      resolve(null);
      return;
    }
    try {
      const r = await fetch('/api/wifi/test/result', {cache: 'no-store'});
      if (r.ok) {
        const state = await r.json();
        if (state.status === 'done') {
          const msg = WIFI_TEST_RESULT_MESSAGES[state.result] || `Unknown result: ${state.result}`;
          const kind = state.result === 'ok' ? 'ok' : 'err';
          setStatus(statusEl, msg, kind);
          resolve(state);
          return;
        }
        if (state.status === 'error') {
          setStatus(statusEl, `Test error: ${state.error || 'unknown'}`, 'err');
          setWifiButtonsBusy(form, false);
          resolve(null);
          return;
        }
      }
    } catch (_) {
    }
    setTimeout(poll, 1000);
    };
    setTimeout(poll, 4000);
  });
}

async function saveWifiAfterValidation(form) {
  if (!formChanged(form)) return;

  const statusEl = document.getElementById('status-wifi');
  const state = await checkWifiCredentials(form);
  if (!state || state.result !== 'ok') {
    setWifiButtonsBusy(form, false);
    return;
  }

  const validationKind = 'ok';
  const validationMessage = WIFI_TEST_RESULT_MESSAGES[state.result];
  const data = collectFormData(form);
  setStatus(statusEl, `${validationMessage} Saving...`, validationKind);

  try {
    const r = await fetch('/api/settings/wifi', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data),
    });
    const text = await r.text();
    if (r.ok) {
      const pw = form.querySelector('input[name=password]');
      if (pw) pw.value = '';
      snapshotForm(form);
      setSubmitEnabled(form, false);
      setStatus(statusEl, 'Wi-Fi saved. Password is correct.', validationKind);
    } else {
      setStatus(statusEl, 'Error: ' + text, 'err');
    }
  } catch (e) {
    setStatus(statusEl, 'Network error while saving: ' + e, 'err');
  } finally {
    setWifiButtonsBusy(form, false);
  }
}

function setStatus(el, text, kind) {
  if (!el) return;
  el.textContent = text || '';
  el.className = 'form-status' + (kind ? ' ' + kind : '');
}

function setFormValue(formId, name, value) {
  const input = document.querySelector(`#${formId} [name=${name}]`);
  if (input) input.value = value;
}

function setFormChecked(formId, name, checked) {
  const input = document.querySelector(`#${formId} [name=${name}]`);
  if (input) input.checked = Boolean(checked);
}


async function loadSettings() {
  try {
    const r = await fetch('/api/settings');
    if (!r.ok) return;
    const s = await r.json();

    const currentSsid = (s.wifi_settings && s.wifi_settings.ssid) || '';
    const ssidInput = document.querySelector('#form-wifi [name=ssid]');
    if (ssidInput) ssidInput.value = currentSsid;
    const ssidField = document.querySelector('#form-wifi .select-field[data-field=ssid]');
    if (ssidField) {
      const labelEl = ssidField.querySelector('.select-value');
      if (labelEl) labelEl.textContent = currentSsid || 'Choose network';
      const list = ssidField.querySelector('.select-options');
      if (list && !list.children.length) {
        list.innerHTML = '<li role="option" aria-disabled="true">Tap to scan...</li>';
      }
    }

    if (s.mqtt_settings) {
      setFormValue('form-mqtt', 'department', s.department || 'kpi');
      setFormValue('form-mqtt', 'room', s.room || 'kronos');
      setFormValue('form-mqtt', 'server', s.mqtt_settings.server || '');
      setFormValue('form-mqtt', 'port', s.mqtt_settings.port || 1883);
      setFormValue('form-mqtt', 'user', s.mqtt_settings.user || '');
      setFormChecked('form-mqtt', 'ssl', s.mqtt_settings.ssl);
    }
    if (s.ap_settings) {
      setFormValue('form-ap', 'ssid', s.ap_settings.ssid || 'thsensor');
    }
    const unitsField = document.querySelector('#form-params .select-field[data-field=units]');
    if (unitsField) setSelectValue(unitsField, s.units || 'metric', {silent: true});
    setFormValue('form-params', 'ntp_server', s.ntp_server || '');
    const intervalSec = s.mqtt_interval || 300;
    setFormValue('form-params', 'mqtt_interval_minutes',
      Math.max(1, Math.min(720, Math.round(intervalSec / 60))));
    updateMqttIntervalLabel();

    if (s.led_settings) {
      LED_ROLES.forEach(role => {
        const cfg = s.led_settings[role];
        if (!cfg) return;
        const color = document.querySelector(`#form-led [name=${role}_color]`);
        const brightness = document.querySelector(`#form-led [name=${role}_brightness]`);
        if (color) color.value = cfg.color || color.value;
        if (brightness) brightness.value = cfg.brightness ?? brightness.value;
      });
      updateLedControls();
    }

    document.querySelectorAll(SETTINGS_FORM_SELECTOR).forEach(form => {
      snapshotForm(form);
      setSubmitEnabled(form, false);
    });
  } catch (e) {
    console.error('Failed to load settings:', e);
  }
}

async function submitForm(form, endpoint, statusElId) {
  if (!formChanged(form)) return false;

  const statusEl = document.getElementById(statusElId);
  const data = collectFormData(form);

  statusEl.textContent = form.id === 'form-mqtt' ? 'Checking MQTT...' : 'Saving...';
  statusEl.className = 'form-status';

  try {
    const r = await fetch(endpoint, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data),
    });
    const text = await r.text();
    if (r.ok) {
      let parsed;
      try { parsed = JSON.parse(text); } catch { parsed = {message: text}; }
      statusEl.textContent = parsed.message || 'OK';
      statusEl.className = 'form-status ok';
      const pw = form.querySelector('input[name=password]');
      if (pw) pw.value = '';
      snapshotForm(form);
      setSubmitEnabled(form, false);
      return true;
    } else {
      statusEl.textContent = text || 'Error';
      statusEl.className = 'form-status err';
      return false;
    }
  } catch (e) {
    statusEl.textContent = 'Network error: ' + e;
    statusEl.className = 'form-status err';
    return false;
  }
}

document.getElementById('form-wifi').addEventListener('submit', e => {
  e.preventDefault();
  saveWifiAfterValidation(e.target);
});

document.getElementById('form-mqtt').addEventListener('submit', e => {
  e.preventDefault();
  submitForm(e.target, '/api/settings/mqtt', 'status-mqtt');
});

document.getElementById('form-ap').addEventListener('submit', e => {
  e.preventDefault();
  submitForm(e.target, '/api/settings/ap', 'status-ap');
});

document.getElementById('form-params').addEventListener('submit', e => {
  e.preventDefault();
  submitForm(e.target, '/api/settings/parameters', 'status-params');
});

document.getElementById('form-led').addEventListener('submit', async e => {
  e.preventDefault();
  const dup = duplicateLedColor();
  if (dup) {
    setStatus(
      document.getElementById('status-led'),
      `Duplicate LED color: ${dup.first} and ${dup.second} both use ${dup.color}`,
      'err'
    );
    return;
  }
  if (await submitForm(e.target, '/api/settings/led', 'status-led')) {
    restoreLedPreview();
  }
});

const formPassword = document.getElementById('form-password');
const pwStatusEl   = document.getElementById('status-password');

function setPwStatus(text, kind) {
  pwStatusEl.textContent = text || '';
  pwStatusEl.className = 'form-status' + (kind ? ' ' + kind : '');
}

function showPwStep(step) {
  formPassword.dataset.step = step;
  formPassword.querySelector('.pw-step-current').hidden = step !== 'current';
  formPassword.querySelector('.pw-step-new').hidden     = step !== 'new';
  formPassword.querySelectorAll('.pw-toggle.visible').forEach(b => {
    b.classList.remove('visible');
    const i = b.parentElement.querySelector('input');
    if (i) i.type = 'password';
  });
  updatePwButtons();
  if (step === 'new') {
    formPassword.querySelector('[name=new_password]').focus();
  } else {
    formPassword.querySelector('[name=current_password]').focus();
  }
}

function updatePwButtons() {
  if (pwBusy) return;  // під час запиту тримаємо disabled з іншого джерела
  const step = formPassword.dataset.step || 'current';
  const curBtn = formPassword.querySelector('.pw-step-current button[type=submit]');
  const newBtn = formPassword.querySelector('.pw-step-new button[type=submit]');
  if (step === 'current') {
    const v = formPassword.querySelector('[name=current_password]').value;
    if (curBtn) curBtn.disabled = !v;
  } else {
    const p1 = formPassword.querySelector('[name=new_password]').value;
    const p2 = formPassword.querySelector('[name=new_password2]').value;
    if (newBtn) newBtn.disabled = !p1 || !p2;
  }
}

formPassword.addEventListener('input', updatePwButtons);

let verifiedCurrentPw = '';
let pwBusy = false;

function setPwBusy(busy) {
  pwBusy = busy;
  formPassword.querySelectorAll('button[type=submit]').forEach(b => { b.disabled = busy; });
}

function resetPwForm() {
  verifiedCurrentPw = '';
  formPassword.querySelectorAll('input').forEach(i => { i.value = ''; });
  showPwStep('current');
}

formPassword.addEventListener('submit', async event => {
  event.preventDefault();
  if (pwBusy) return;                        // захист від подвійного submit
  const step = formPassword.dataset.step || 'current';

  if (step === 'current') {
    const currentPw = formPassword.querySelector('[name=current_password]').value;
    if (!currentPw) { setPwStatus('Enter current password', 'err'); return; }
    setPwStatus('Checking...');
    setPwBusy(true);
    try {
      const r = await fetch('/api/settings/password/verify', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({current_password: currentPw}),
      });
      if (r.ok) {
        verifiedCurrentPw = currentPw;
        setPwStatus('');
        showPwStep('new');
      } else {
        setPwStatus(await r.text() || 'Invalid password', 'err');
      }
    } catch (e) {
      setPwStatus('Network error: ' + e, 'err');
    } finally {
      setPwBusy(false);
    }
    return;
  }

  const p1 = formPassword.querySelector('[name=new_password]').value;
  const p2 = formPassword.querySelector('[name=new_password2]').value;
  if (p1.length < 8) { setPwStatus('Password must be at least 8 characters', 'err'); return; }
  if (p1 !== p2)     { setPwStatus('Passwords do not match', 'err'); return; }
  if (!verifiedCurrentPw) {
    setPwStatus('Please verify current password first', 'err');
    showPwStep('current');
    return;
  }

  setPwStatus('Saving...');
  setPwBusy(true);
  try {
    const r = await fetch('/api/settings/password', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        current_password: verifiedCurrentPw,
        new_password: p1,
        new_password2: p2,
      }),
    });
    const text = await r.text();
    if (r.ok) {
      let msg = 'Password changed';
      try { msg = (JSON.parse(text).message) || msg; } catch {}
      resetPwForm();
      setPwStatus(msg, 'ok');
    } else {
      setPwStatus(text || 'Failed to change password', 'err');
    }
  } catch (e) {
    setPwStatus('Network error: ' + e, 'err');
  } finally {
    setPwBusy(false);
  }
});

document.getElementById('form-logout').addEventListener('submit', async event => {
  event.preventDefault();
  restoreLedPreview();
  try {
    await fetch('/api/logout', {method: 'POST'});
  } catch (_) {
  }
  if (window.parent && window.parent !== window) {
    window.parent.postMessage({type: 'close-settings-modal'}, '*');
  } else {
    window.location.href = '/';
  }
});

function initThemeSwitcher() {
  let saved = 'ocean';
  try { saved = localStorage.getItem('ui-theme') || 'ocean'; } catch (_) {}
  let selected = saved;

  const statusEl = document.getElementById('status-theme');
  const saveBtn  = document.getElementById('btn-save-theme');

  function syncSaveBtn() {
    if (saveBtn) saveBtn.disabled = (selected === saved);
  }

  document.querySelectorAll('.theme-swatch').forEach(btn => {
    if (btn.dataset.theme === saved) btn.classList.add('is-active');
    btn.addEventListener('click', () => {
      document.querySelectorAll('.theme-swatch').forEach(b => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      selected = btn.dataset.theme;
      applyTheme(selected);   // прев'ю без збереження
      if (statusEl) setStatus(statusEl, '');
      syncSaveBtn();
    });
  });

  if (saveBtn) {
    saveBtn.addEventListener('click', () => {
      applyTheme(selected, true);   // тепер зберігаємо
      saved = selected;
      syncSaveBtn();
      try { window.parent.postMessage({ type: 'theme-changed', theme: selected }, '*'); } catch (_) {}
      const label = document.querySelector(`.theme-swatch[data-theme="${selected}"] .theme-name`);
      setStatus(statusEl, `${label ? label.textContent : selected} saved`, 'ok');
      setTimeout(() => setStatus(statusEl, ''), 2000);
    });
  }
}

renderLedPalettes();
initThemeSwitcher();
document.querySelectorAll(SETTINGS_FORM_SELECTOR).forEach(watchForm);
loadSettings();
window.restoreLedPreview = restoreLedPreview;
window.addEventListener('pagehide', restoreLedPreview);

setInterval(() => {
  fetch('/api/ping', {cache: 'no-store'}).catch(() => {});
}, 30000);
