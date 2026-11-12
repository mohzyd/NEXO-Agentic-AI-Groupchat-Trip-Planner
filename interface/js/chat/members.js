(function (C) {
  const SIZE = 38;      // circle diameter in px (keep in sync with .av in header.css)
  const OVERLAP = 12;   // how far each circle tucks under the next

  const palette = C.store.get('chat.colors.v2', {});
  let hueSeed = C.store.get('chat.hueSeed', null);
  let assigned = C.store.get('chat.colorN.v2', 0);

  if (hueSeed == null) {
    hueSeed = Math.floor(Math.random() * 360);
    C.store.set('chat.hueSeed', hueSeed);
  }

  function colorOf(id) {
    if (!palette[id]) {
      // Golden-angle steps keep consecutive members visually distinct
      const hue = Math.round((hueSeed + assigned++ * 137.508) % 360);
      palette[id] = `hsl(${hue} 78% 55%)`;
      C.store.set('chat.colors.v2', palette);
      C.store.set('chat.colorN.v2', assigned);
    }
    return palette[id];
  }

  function initials(name) {
    const [first = '?', second] = name.trim().split(/\s+/);
    return (first[0] + (second ? second[0] : first[1] || first[0])).toUpperCase();
  }

  let list = [];
  const get = id => list.find(member => member.id === id);

  const box = document.getElementById('members');
  let shownIds = new Set();

  function setMembers(members) {
    list = members.map(member => ({
      id: member.id,
      name: member.name || 'Guest',
      active: true
    }));
    render();
  }

  function render() {
    const active = list.filter(member => member.active);
    const step = SIZE - OVERLAP;
    const fit = Math.max(1, Math.floor((box.clientWidth - SIZE) / step) + 1);
    const overflow = active.length > fit;
    const visible = overflow ? active.slice(0, fit - 1) : active;   // last slot is the "+N" circle

    box.style.setProperty('--overlap', `${OVERLAP}px`);
    box.replaceChildren();

    const nowShown = new Set();
    visible.forEach(member => {
      const circle = C.el('div', 'av' + (shownIds.has(member.id) ? '' : ' pop'), initials(member.name));
      circle.style.setProperty('--c', colorOf(member.id));
      circle.title = member.name;
      circle.setAttribute('aria-label', member.name);
      box.append(circle);
      nowShown.add(member.id);
    });

    if (overflow) {
      const hidden = active.length - visible.length;
      const more = C.el('div', 'av more', `${hidden}+`);
      more.title = `${hidden} more active`;
      box.append(more);
    }
    shownIds = nowShown;
  }

  C.members = { get, colorOf, initials, render, setMembers };
  new ResizeObserver(render).observe(box);
})(window.Chat);
