// Register service worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
}

// Prevent accidental double-tap firing +1 twice; small guard on click
document.addEventListener('htmx:beforeRequest', function (evt) {
  const btn = evt.detail.elt;
  if (btn && btn.tagName === 'BUTTON') {
    btn.disabled = true;
    setTimeout(() => { btn.disabled = false; }, 350);
  }
});
