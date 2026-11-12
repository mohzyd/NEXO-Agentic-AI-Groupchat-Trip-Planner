/* Message type registry.
 *
 * Add a type with Chat.registerType(name, definition):
 *   render(msg)       -> HTMLElement   builds the content (required)
 *   mount(node, msg)                   runs after insertion: timers, listeners (optional)
 *   media: true                        tighter padding for image-like content (optional)
 *   bare:  true                        no bubble or meta, centered like a notice (optional)
 * Then send one with Chat.addMessage({ type: name, from: memberId, ...yourFields }).
 *
 * TEMPLATE
 * Chat.registerType('sticker', {
 *   media: true,
 *   render(msg) {
 *     const img = Chat.el('img');
 *     img.src = msg.src;
 *     img.alt = msg.alt || 'Sticker';
 *     return img;
 *   }
 * });
 */
(function (C) {
  C.types = {};
  C.registerType = (name, definition) => { C.types[name] = definition; };

  C.registerType('text', {
    render: msg => C.el('div', 'text', msg.text)
  });

  C.registerType('notice', {
    bare: true,
    render: msg => C.el('div', 'notice', msg.text)
  });

  C.registerType('payment_request', {
    render(msg) {
      const card = C.el('div', 'payment-card');
      card.dataset.proposalId = msg.id || '';
      card.append(
        C.el('h3', 'payment-title', msg.title || 'Group payment'),
        C.el('p', 'payment-amount', `${msg.currency || 'USD'} ${msg.target || '0.00'}`),
        C.el('p', 'payment-progress', 'Loading pledge status…'),
        C.el('p', 'payment-status', 'Members pay their own pledge using PayPal Sandbox buyer accounts. No real money is charged.')
      );
      const controls = C.el('div', 'payment-controls');
      const amount = C.el('input', 'payment-pledge-amount');
      amount.type = 'number';
      amount.min = '0.01';
      amount.step = '0.01';
      amount.setAttribute('aria-label', 'Your simulated pledge amount');
      const pledgeButton = C.el('button', 'payment-pledge', 'Pledge');
      pledgeButton.type = 'button';
      const checkoutButton = C.el('button', 'payment-checkout solid', 'Pay my contribution in PayPal Sandbox');
      checkoutButton.type = 'button';
      controls.append(amount, pledgeButton, checkoutButton);
      card.append(controls);
      return card;
    },
    mount(node, msg) {
      C.payments.mountCard(node.querySelector('.payment-card'), msg);
    }
  });

  const imageType = fallbackAlt => ({
    media: true,
    render(msg) {
      const img = C.el('img');
      img.src = msg.src;
      img.alt = msg.alt || fallbackAlt;
      img.loading = 'lazy';
      return img;
    }
  });
  C.registerType('image', imageType('Shared image'));
  C.registerType('gif', imageType('GIF'));

  /* Location: msg has either { lat, lng } or { query } (a searched place name) */
  C.registerType('location', {
    media: true,
    render(msg) {
      const place = msg.query || `${msg.lat},${msg.lng}`;
      const wrap = C.el('div', 'map');

      const frame = C.el('iframe');
      frame.title = 'Shared location';
      frame.loading = 'lazy';
      frame.referrerPolicy = 'no-referrer-when-downgrade';
      frame.src = `https://maps.google.com/maps?q=${encodeURIComponent(place)}&z=15&output=embed`;

      const link = C.el('a', null, 'Open in Google Maps');
      link.href = `https://www.google.com/maps?q=${encodeURIComponent(place)}`;
      link.target = '_blank';
      link.rel = 'noopener';

      wrap.append(frame, link);
      return wrap;
    }
  });

  C.pollResults = poll => {
    const total = poll.options.reduce((sum, option) => sum + option.votes, 0);
    const max = Math.max(...poll.options.map(option => option.votes));
    const winners = max > 0 ? poll.options.filter(option => option.votes === max).map(option => option.text) : [];
    return { total, winners };
  };

  const polls = new Map();

  C.applyPollUpdate = update => {
    const poll = polls.get(update.pollId);
    if (!poll || !Number.isInteger(update.optionIndex) ||
        update.optionIndex < 0 || update.optionIndex >= poll.options.length ||
        typeof update.userID !== 'string') return;

    poll.votesByUser = poll.votesByUser || {};
    if (Object.hasOwn(poll.votesByUser, update.userID)) return;

    poll.votesByUser[update.userID] = update.optionIndex;
    poll.options[update.optionIndex].votes++;
    poll.paint();
  };

  C.registerType('poll', {
    render(poll) {
      const wrap = C.el('div', 'poll');
      wrap.append(C.el('h3', null, poll.question));

      poll.options.forEach(option => {
        const button = C.el('button', 'opt');
        button.type = 'button';
        button.append(C.el('span', null, option.text), C.el('span', 'n', '0'));
        wrap.append(button);
      });

      const footer = C.el('div', 'poll-foot');
      footer.append(C.el('span', 'poll-total'), C.el('span', 'poll-clock'));
      wrap.append(footer);
      return wrap;
    },

    mount(node, poll) {
      poll.votesByUser = poll.votesByUser || {};
      polls.set(poll.id, poll);
      const buttons = [...node.querySelectorAll('.opt')];
      const totalLabel = node.querySelector('.poll-total');
      const clockLabel = node.querySelector('.poll-clock');

      const paint = () => {
        const total = poll.options.reduce((sum, option) => sum + option.votes, 0);
        const max = Math.max(...poll.options.map(option => option.votes));

        buttons.forEach((button, i) => {
          const option = poll.options[i];
          button.style.setProperty('--p', `${total ? (option.votes / total) * 100 : 0}%`);
          button.querySelector('.n').textContent = option.votes;
          button.classList.toggle('mine', poll.votesByUser[C.config.me.id] === i);
          button.classList.toggle('win', poll.closed && max > 0 && option.votes === max);
          button.disabled = poll.closed || Object.hasOwn(poll.votesByUser, C.config.me.id);
        });

        totalLabel.textContent = `${total} vote${total === 1 ? '' : 's'}`;
        clockLabel.textContent = poll.closed ? 'Closed' : `${C.fmtCountdown(poll.endsAt - Date.now())} left`;
      };

      buttons.forEach((button, i) => button.addEventListener('click', () => {
        if (poll.closed || Object.hasOwn(poll.votesByUser, C.config.me.id)) return;
        C.onPollVote?.(poll, i);
      }));

      poll.paint = paint;   // lets other code (e.g. simulated votes) refresh the card

      const timer = setInterval(() => {
        if (!poll.closed && Date.now() >= poll.endsAt) {
          poll.closed = true;
          clearInterval(timer);
          paint();
          C.config.onPollEnd(poll, C.pollResults(poll));   // fires exactly once
        } else {
          paint();
        }
      }, 500);

      paint();
    }
  });
})(window.Chat);
