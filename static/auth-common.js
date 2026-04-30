
function closeModalPage(event) {
  if (typeof window.restoreLedPreview === 'function') {
    window.restoreLedPreview();
  }
  if (window.parent && window.parent !== window) {
    event.preventDefault();
    window.parent.postMessage({ type: 'close-settings-modal' }, '*');
    return false;
  }
  return true;
}

function togglePassword(button) {
  const input = button.parentElement.querySelector('input');
  const visible = input.type === 'password';
  input.type = visible ? 'text' : 'password';
  button.classList.toggle('visible', visible);
}

function setStatus(statusEl, text, kind) {
  statusEl.textContent = text || '';
  statusEl.className = 'form-status' + (kind ? ' ' + kind : '');
}

async function submitAuthForm(form, statusEl, redirectTo, validate) {
  setStatus(statusEl, '');
  if (validate) {
    const err = validate(form);
    if (err) { setStatus(statusEl, err, 'err'); return; }
  }
  try {
    const r = await fetch(form.action, {
      method: 'POST',
      headers: {'Content-Type': 'application/x-www-form-urlencoded'},
      body: new URLSearchParams(new FormData(form)).toString(),
      redirect: 'manual',
    });
    if (r.ok || r.redirected || r.type === 'opaqueredirect' || (r.status >= 300 && r.status < 400)) {
      window.location.href = redirectTo;
    } else {
      setStatus(statusEl, await r.text(), 'err');
    }
  } catch (error) {
    setStatus(statusEl, 'Network error: ' + error, 'err');
  }
}
