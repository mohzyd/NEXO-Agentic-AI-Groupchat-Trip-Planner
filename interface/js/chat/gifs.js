(function (C) {
  const PAGE_SIZE = 10;
  const MAX_RESULTS = 10;
  const grid = document.getElementById('gifGrid');
  const search = document.getElementById('gifSearch');
  const loadMore = document.getElementById('gifLoadMore');

  const state = {
    query: '',
    offset: 0,
    totalCount: 0,
    loading: false,
    done: false,
    ticket: 0
  };
  let searchTimer;

  function showNote(text) {
    grid.replaceChildren(C.el('p', 'gif-note', text));
  }

  function appendGif(gif) {
    const button = C.el('button');
    button.type = 'button';
    button.title = gif.title;

    const img = C.el('img');
    img.loading = 'lazy';
    img.alt = gif.title || 'GIF';
    img.src = gif.images.fixed_height_small.url;
    button.append(img);

    button.addEventListener('click', () => {
      C.sendMessage({ type: 'gif', src: gif.images.fixed_height.url, alt: gif.title });
      C.closePanels();
    });
    grid.append(button);
  }

  async function load(reset = false) {
    if (!C.config.giphyKey) return showNote('Add your Giphy API key in js/chat/config.js to enable GIFs.');

    if (reset) {
      // A new ticket makes any request still in flight for the old search get ignored
      Object.assign(state, {
        offset: 0,
        totalCount: 0,
        done: false,
        loading: false,
        ticket: state.ticket + 1
      });
      grid.replaceChildren();
      grid.scrollTop = 0;
    }
    if (state.loading || state.done) return;

    state.loading = true;
    loadMore.hidden = true;
    loadMore.disabled = true;
    loadMore.textContent = 'Loading GIFs…';
    const ticket = state.ticket;
    const params = new URLSearchParams({
      api_key: C.config.giphyKey,
      limit: PAGE_SIZE,
      offset: state.offset,
      rating: 'pg'
    });
    if (state.query) params.set('q', state.query);
    const endpoint = state.query ? 'search' : 'trending';

    try {
      const response = await fetch(`https://api.giphy.com/v1/gifs/${endpoint}?${params}`);
      const { data, pagination } = await response.json();
      if (ticket !== state.ticket) return;

      data.forEach(appendGif);
      state.offset += data.length;
      state.totalCount = pagination.total_count;
      state.done = (
        !data.length ||
        state.offset >= state.totalCount ||
        state.offset >= MAX_RESULTS
      );
      loadMore.hidden = state.done;
      loadMore.disabled = false;
      loadMore.textContent = 'Load more GIFs';
      if (!grid.children.length) showNote('No GIFs found.');
    } catch {
      if (ticket === state.ticket) {
        if (!grid.children.length) showNote('Could not load GIFs. Check your connection and key.');
        loadMore.hidden = false;
        loadMore.disabled = false;
        loadMore.textContent = 'Retry loading GIFs';
      }
    } finally {
      if (ticket === state.ticket) state.loading = false;
    }
  }

  loadMore.addEventListener('click', () => load());

  search.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.query = search.value.trim();
      load(true);
    }, 350);
  });

  C.gifs = {
    open() {
      search.focus({ preventScroll: true });
      if (!grid.children.length) load(true);
    }
  };
})(window.Chat);
