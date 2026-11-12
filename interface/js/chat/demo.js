/* Demo content. Delete this file (and its <script> tag) when you connect real data. */
(function (C) {
  const pick = list => list[Math.floor(Math.random() * list.length)];
  const minutesAgo = n => Date.now() - n * 60000;
  const otherMembers = () => C.members.list.filter(member => member.active && member.id !== C.config.me.id);

  // Other members vote on polls
  function simulateVotes(poll) {
    const voters = 2 + Math.floor(Math.random() * 5);
    const window = Math.min(20000, poll.endsAt - Date.now() - 2000);

    for (let i = 0; i < voters; i++) {
      setTimeout(() => {
        if (poll.closed) return;
        pick(poll.options).votes++;
        poll.paint?.();
      }, 1500 + Math.random() * window);
    }
  }
  C.onPollCreated = simulateVotes;

  // Someone sometimes replies to your text messages
  C.onMessageSent = () => {
    if (Math.random() > 0.6) return;
    setTimeout(() => C.addMessage({
      type: 'text',
      from: pick(otherMembers()).id,
      text: pick(['Love it.', 'Makes sense to me.', 'Can you share more?', 'On it 👍', 'Haha, same here', 'Good point!'])
    }), 1200 + Math.random() * 1200);
  };

  const artwork = 'data:image/svg+xml;utf8,' + encodeURIComponent(`
    <svg xmlns="http://www.w3.org/2000/svg" width="480" height="300">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stop-color="#ffb347"/><stop offset=".55" stop-color="#e8467c"/><stop offset="1" stop-color="#3b5bdb"/>
        </linearGradient>
      </defs>
      <rect width="480" height="300" fill="url(#g)"/>
      <circle cx="350" cy="90" r="46" fill="#fff" opacity=".55"/>
      <path d="M0 300V210q120-70 240-10t240-40v140z" fill="#06240f" opacity=".35"/>
    </svg>`);

  C.addMessage({ type: 'text', from: 'u0', text: 'Morning all! The new palette is in the shared board.', at: minutesAgo(9) });
  C.addMessage({ type: 'text', text: 'Looks great. Sending my favorite mockup now.', at: minutesAgo(8) });
  C.addMessage({ type: 'image', src: artwork, alt: 'Mockup', at: minutesAgo(8) });
  C.addMessage({ type: 'text', from: 'u1', text: 'Lunch spot, then? Vote below.', at: minutesAgo(5) });

  const lunchPoll = C.addMessage({
    type: 'poll',
    from: 'u1',
    question: 'Where should we have lunch?',
    options: [
      { text: 'Garden cafe', votes: 2 },
      { text: 'Noodle bar', votes: 1 },
      { text: 'Rooftop grill', votes: 1 }
    ],
    endsAt: Date.now() + 40000,
    closed: false,
    voted: null
  });
  simulateVotes(lunchPoll);

  C.addMessage({ type: 'location', from: 'u2', lat: 38.7223, lng: -9.1393, at: minutesAgo(2) });

  // Members come and go
  setInterval(() => {
    const member = C.members.list[1 + Math.floor(Math.random() * (C.members.list.length - 1))];
    member.active = !member.active;
    C.members.render();
  }, 5000);
})(window.Chat);
