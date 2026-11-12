(function (C) {
  const $ = selector => document.querySelector(selector);

  const feed = $('#feed');
  const input = $('#input');
  const sheet = $('#sheet');
  const actions = $('#actions');
  const moreButton = $('#moreBtn');
  const emojiGrid = $('#emojiGrid');
  const gifPane = $('#gifPane');
  const socket = io();
  C.socket = socket;
  const connectionStatus = $('#connectionStatus');
  const joinDialog = $('#joinDialog');
  const joinForm = $('#joinForm');
  const nicknameInput = $('#nicknameInput');
  const passwordLabel = $('#passwordLabel');
  const passwordInput = $('#passwordInput');
  const joinError = $('#joinError');
  const identityKey = `nexo-chat-identity:${C.config.roomID || location.host}`;
  let identity = C.store.get(identityKey, null);
  let roomPassword = '';
  let joined = false;

  C.hydrateIcons();
  $('#chatName').textContent = C.config.name;
  document.title = C.config.name;
  nicknameInput.value = C.store.get('nexo-chat-nickname', '');
  passwordLabel.hidden = !C.config.requiresPassword;
  passwordInput.required = C.config.requiresPassword;
  $('#composer').classList.add('off');
  $('.dock').classList.add('locked');
  passwordInput.closest('label').hidden = !C.config.requiresPassword;

  function setConnectionStatus(text, state) {
    connectionStatus.textContent = text;
    connectionStatus.classList.toggle('connected', state === 'connected');
    connectionStatus.classList.toggle('error', state === 'error');
  }

  function openJoinDialog(message = '') {
    joinError.textContent = message;
    joinError.hidden = !message;
    if (!joinDialog.open) joinDialog.showModal();
    if (C.config.requiresPassword) passwordInput.focus();
    else nicknameInput.focus();
  }

  function sendJoin() {
    const nickname = nicknameInput.value.trim();
    if (!nickname || !socket.connected) return;
    C.store.set('nexo-chat-nickname', nickname);
    socket.emit('join', {
      nickname,
      previousSID: identity && identity.sid,
      recoveryToken: identity && identity.recoveryToken,
      ...(C.config.requiresPassword ? { password: roomPassword } : {})
    });
  }

  joinForm.addEventListener('submit', event => {
    event.preventDefault();
    joinError.hidden = true;
    roomPassword = C.config.requiresPassword ? passwordInput.value : '';
    setConnectionStatus('Joining…');
    sendJoin();
  });
  joinDialog.addEventListener('cancel', event => event.preventDefault());

  socket.on('connect', () => {
    setConnectionStatus('Connected');
    if (identity && identity.sid && (!C.config.requiresPassword || roomPassword)) {
      nicknameInput.value = C.store.get('nexo-chat-nickname', C.config.me.name || 'Guest');
      sendJoin();
    } else {
      openJoinDialog();
    }
  });

  socket.on('identity', data => {
    identity = data;
    C.store.set(identityKey, identity);
    C.config.me = { id: data.userID, name: nicknameInput.value.trim() || 'Guest' };
    joined = true;
    if (C.config.endsAt == null || Date.now() < C.config.endsAt) {
      $('#composer').classList.remove('off');
      $('.dock').classList.remove('locked');
    }
    joinDialog.close();
    passwordInput.value = '';
    setConnectionStatus('Connected', 'connected');
  });

  socket.on('members', members => {
    if (!Array.isArray(members)) return;
    C.members.setMembers(members);
  });

  socket.on('disconnect', () => {
    joined = false;
    $('#composer').classList.add('off');
    $('.dock').classList.add('locked');
    setConnectionStatus('Disconnected', 'error');
  });
  socket.on('connect_error', () => setConnectionStatus('Connection failed', 'error'));

  socket.on('join_error', data => {
    joined = false;
    setConnectionStatus('Could not join', 'error');
    openJoinDialog(data && data.error ? data.error : 'Could not join this chat.');
  });

  socket.on('message_history', messages => {
    if (!Array.isArray(messages)) return;
    feed.replaceChildren();
    messages.forEach(renderServerMessage);
  });

  socket.on('new_message', renderServerMessage);
  socket.on('room_read_only', data => {
    C.config.endsAt = Date.now() - 1;
    tick();
    C.addMessage({ type: 'notice', text: data && data.error ? data.error : 'This chat is read-only.' });
  });
  socket.on('message_error', data => {
    C.addMessage({ type: 'notice', text: data && data.error ? data.error : 'Message could not be sent.' });
  });
  socket.on('ai_error', data => {
    C.addMessage({ type: 'notice', text: data && data.error ? data.error : 'The AI reply could not be generated.' });
  });

  function renderServerMessage(data) {
    if (!data || typeof data !== 'object' || typeof data.type !== 'string') return;

    let payload;
    try {
      payload = JSON.parse(data.message);
    } catch {
      payload = { text: data.message };
    }

    if (data.type === 'poll_update') {
      if (payload && typeof payload === 'object') {
        C.applyPollUpdate({ ...payload, userID: data.userID });
      }
      return;
    }

    if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
      payload = { text: String(payload ?? '') };
    }
    C.addMessage({
      ...payload,
      type: data.type,
      from: data.userID,
      at: Date.parse(data.timestamp) || Date.now()
    });
  }

  C.sendMessage = message => {
    if (!joined || !socket.connected ||
        (C.config.endsAt != null && Date.now() >= C.config.endsAt)) {
      C.addMessage({ type: 'notice', text: 'Connect to the chat before sending messages.' });
      return false;
    }
    const payload = { ...message, id: message.id || C.uid() };
    delete payload.from;
    delete payload.voted;
    delete payload.votesByUser;
    delete payload.paint;
    socket.emit('message', {
      type: message.type,
      message: JSON.stringify(payload)
    });
    return true;
  };

  C.onPollVote = (poll, optionIndex) => {
    C.sendMessage({
      type: 'poll_update',
      pollId: poll.id,
      optionIndex
    });
  };

  /* ---------- Layout: keep feed padding equal to the floating header/footer ---------- */
  const stack = $('#stack');
  const dockWrap = $('#dockWrap');

  function syncLayout() {
    const root = document.documentElement.style;
    root.setProperty('--top-h', `${stack.offsetHeight}px`);
    root.setProperty('--bottom-h', `${dockWrap.offsetHeight}px`);
  }
  new ResizeObserver(syncLayout).observe(stack);
  new ResizeObserver(syncLayout).observe(dockWrap);

  /* ---------- Messages ---------- */
  C.addMessage = function (msg) {
    const type = C.types[msg.type];
    if (!type) return console.warn('Unknown message type:', msg.type);

    msg.id = msg.id || C.uid();
    msg.at = msg.at || Date.now();
    msg.from = msg.from || C.config.me.id;

    const mine = msg.from === C.config.me.id;
    const row = C.el('div', `row ${type.bare ? 'center' : mine ? 'me' : 'other'}`);
    let host = row;

    if (type.bare) {
      row.append(type.render(msg));
    } else {
      host = C.el('div', `bubble glass ${mine ? 'green' : 'gray'}${type.media ? ' media' : ''}`);
      host.append(type.render(msg));

      const sender = mine
        ? { name: 'You' }
        : { name: msg.from === 'nexo-ai' ? 'Nexo AI' : (C.members.get(msg.from) || { name: 'Guest' }).name };
      const meta = C.el('div', 'meta');
      if (!mine) meta.style.setProperty('--c', C.members.colorOf(msg.from));
      meta.append(C.el('span', null, C.fmtTime(msg.at)), C.el('b', null, sender.name));

      row.append(host, meta);
    }

    // Follow new messages only if the reader is already near the bottom (or sent it)
    const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 140;
    feed.append(row);
    if (type.mount) type.mount(host, msg);
    if (mine || nearBottom) requestAnimationFrame(() => feed.scrollTo({ top: feed.scrollHeight }));

    return msg;
  };

  function sendText() {
    const text = input.value.trim();
    if (!text) return;
    if (!C.sendMessage({ type: 'text', text })) return;
    input.value = '';
    input.focus();
  }

  $('#sendBtn').addEventListener('click', sendText);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.isComposing) sendText();
  });

  /* ---------- Actions menu and slide-up sheet ---------- */
  C.closePanels = function () {
    actions.classList.remove('open');
    sheet.classList.remove('open');
    moreButton.setAttribute('aria-expanded', 'false');
  };

  function toggleActions() {
    const willOpen = !actions.classList.contains('open');
    C.closePanels();
    if (willOpen) {
      actions.classList.add('open');
      moreButton.setAttribute('aria-expanded', 'true');
    }
  }

  function openSheet(mode) {
    const alreadyOpen = sheet.classList.contains('open') && sheet.dataset.mode === mode;
    C.closePanels();
    if (alreadyOpen) return;

    sheet.dataset.mode = mode;
    emojiGrid.hidden = mode !== 'emoji';
    gifPane.hidden = mode !== 'gif';
    sheet.classList.add('open');
    if (mode === 'gif') C.gifs.open();
  }

  moreButton.addEventListener('click', event => { event.stopPropagation(); toggleActions(); });
  $('#emojiBtn').addEventListener('click', event => { event.stopPropagation(); openSheet('emoji'); });
  document.addEventListener('click', event => { if (!event.target.closest('.dock')) C.closePanels(); });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') C.closePanels(); });

  /* ---------- Emoji ---------- */
  const EMOJI = '😀 😃 😄 😁 😆 😅 😂 🤣 🙂 😉 😊 😇 🥰 😍 🤩 😘 😋 😛 😜 🤪 🤗 🤔 🫡 🤐 😐 😏 😌 😴 🤤 😎 🤓 🥳 😢 😭 😤 😡 🤯 😱 🥶 🥵 🤒 🙄 😬 🫠 👍 👎 👏 🙌 🙏 🤝 💪 👀 👋 🤞 ✌️ 🫶 ❤️ 🧡 💛 💚 💙 💜 🖤 💔 🔥 ✨ ⭐ 🎉 🎊 💯 ✅ ❌ ⚡ 🌈 ☀️ 🌙 🍕 🍔 🍟 🍩 ☕ 🍻 🎵 🎮 ⚽ 🚀 💡 📌 📎 🎁';

  EMOJI.split(' ').forEach(emoji => {
    const button = C.el('button', null, emoji);
    button.type = 'button';
    button.setAttribute('aria-label', emoji);
    button.addEventListener('click', () => {
      const start = input.selectionStart ?? input.value.length;
      const end = input.selectionEnd ?? start;
      input.setRangeText(emoji, start, end, 'end');   // insert at the caret
      input.focus();
    });
    emojiGrid.append(button);
  });

  /* ---------- Actions: image, GIF, location, poll ---------- */
  const fileInput = $('#imageInput');
  const pollDialog = $('#pollDialog');

  actions.addEventListener('click', event => {
    const action = event.target.closest('[data-act]')?.dataset.act;
    if (!action) return;
    C.closePanels();

    if (action === 'image') fileInput.click();
    if (action === 'gif') openSheet('gif');
    if (action === 'location') C.location.open();
    if (action === 'poll') pollDialog.showModal();
    if (action === 'payment') C.payments.open();
  });

  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    fileInput.value = '';
    if (!file) return;

    if (file.size > 600 * 1024) {
      C.addMessage({
        type: 'notice',
        text: 'Images must be 600 KB or smaller to share in this chat.'
      });
      return;
    }

    const reader = new FileReader();
    reader.onload = () => C.sendMessage({ type: 'image', src: reader.result, alt: file.name });
    reader.onerror = () => C.addMessage({
      type: 'notice',
      text: 'The selected image could not be read.'
    });
    reader.readAsDataURL(file);
  });

  $('#pollCancel').addEventListener('click', () => pollDialog.close());
  $('#pollForm').addEventListener('submit', event => {
    const form = new FormData(event.target);
    const options = String(form.get('opts'))
      .split('\n')
      .map(line => line.trim())
      .filter(Boolean)
      .slice(0, 6);

    if (options.length < 2) {
      event.preventDefault();   // keep the dialog open until there are two options
      return;
    }

    const poll = {
      type: 'poll',
      question: String(form.get('q')).trim(),
      options: options.map(text => ({ text, votes: 0 })),
      endsAt: Date.now() + Number(form.get('sec')) * 1000,
      closed: false,
      voted: null
    };
    C.sendMessage(poll);
    event.target.reset();
  });

  /* ---------- Countdown ---------- */
  const timerLabel = $('#timer');
  const timerPill = $('#timerWrap');
  let timerId;

  function tick() {
    const endsAt = C.config.endsAt;
    if (endsAt == null) {
      timerLabel.textContent = 'Never';
      return;
    }

    const left = endsAt - Date.now();
    if (left <= 0) {
      timerLabel.textContent = 'Ended';
      timerPill.classList.remove('urgent');
      timerPill.classList.add('ended');
      $('#composer').classList.add('off');
      $('.dock').classList.add('locked');
      input.disabled = true;
      input.placeholder = 'This chat has ended';
      C.closePanels();
      clearInterval(timerId);
      return;
    }

    timerLabel.textContent = C.fmtCountdown(left);
    timerPill.classList.toggle('urgent', left < 60000);
  }

  timerId = setInterval(tick, 1000);
  tick();
})(window.Chat);
