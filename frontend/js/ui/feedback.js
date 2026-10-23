// Toasts and button busy states shared by every studio feature.

export function showToast(title, body, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `<div class="toast-title">${title}</div><div class="toast-body">${body}</div>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

export function setButtonLoading(btn, text) {
  btn._originalText = btn._originalText || btn.textContent;
  btn.textContent = text;
  btn.classList.add('btn-loading');
}

export function clearButtonLoading(btn, text) {
  btn.textContent = text || btn._originalText || 'Done';
  btn.classList.remove('btn-loading');
}
