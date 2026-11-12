(function (C) {
  C.el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  };

  C.uid = () => Math.random().toString(36).slice(2, 9);

  C.fmtTime = date => new Date(date).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });

  C.fmtCountdown = ms => {
    const total = Math.max(0, Math.floor(ms / 1000));
    const pad = n => String(n).padStart(2, '0');
    const h = Math.floor(total / 3600);
    const m = Math.floor((total % 3600) / 60);
    const s = total % 60;
    return h ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
  };

  // localStorage wrapper that never throws (private mode, quota, etc.)
  C.store = {
    get(key, fallback) {
      try {
        const value = localStorage.getItem(key);
        return value ? JSON.parse(value) : fallback;
      } catch {
        return fallback;
      }
    },
    set(key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
    }
  };

  const ICONS = {
    plus:  '<path d="M12 5v14M5 12h14"/>',
    send:  '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/>',
    smile: '<circle cx="12" cy="12" r="9"/><path d="M8 14s1.5 2 4 2 4-2 4-2M9 9.5h.01M15 9.5h.01"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="m21 16-5-5-9 9"/>',
    pin:   '<path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    gif:   '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10.5 10.2a2 2 0 1 0 0 3.6V12.5H9M13.5 9.5v5M16 14.5v-5h2.5M16 12h2"/>',
    poll:  '<path d="M5 20V10M12 20V4M19 20v-7"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'
  };

  C.icon = name => `
    <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
         stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      ${ICONS[name]}
    </svg>`;

  // Fills every [data-icon="name"] element with its SVG
  C.hydrateIcons = (root = document) => {
    root.querySelectorAll('[data-icon]').forEach(node => {
      node.innerHTML = C.icon(node.dataset.icon);
    });
  };
})(window.Chat);
