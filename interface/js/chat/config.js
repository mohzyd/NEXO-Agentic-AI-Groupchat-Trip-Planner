window.Chat = window.Chat || {};

const configElement = document.querySelector('[data-chat-config]');
const serverConfig = configElement
  ? JSON.parse(configElement.dataset.chatConfig)
  : window.NEXO_CHAT_CONFIG || {};

Chat.config = Object.assign({
  name: 'Chat',
  endsAt: null,
  roomID: '',
  requiresPassword: false,
  me: { id: '', name: 'Guest' },
  giphyKey: 'drXVTd5sAOoc7KGkwq22FGa9qWnV06NX',
  googleMapsKey: '',
  onPollEnd(poll, result) {
    let text;
    if (result.total === 0) {
      text = `Poll closed: “${poll.question}” got no votes.`;
    } else if (result.winners.length > 1) {
      text = `Poll closed: “${poll.question}” ended in a tie (${result.winners.join(', ')}).`;
    } else {
      text = `Poll closed: “${poll.question}” — ${result.winners[0]} won.`;
    }
    Chat.addMessage({ type: 'notice', text });
  }
}, serverConfig);
