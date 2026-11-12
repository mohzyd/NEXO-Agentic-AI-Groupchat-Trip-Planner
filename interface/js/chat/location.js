/* Location sharing: send your current position, or pick another place. */
(function (C) {
  const $ = selector => document.querySelector(selector);
  const dialog = $('#locDialog');
  const preview = $('#locPreview');
  const search = $('#locSearch');
  const sendButton = $('#locSend');

  let selection = null;          // { lat, lng } or { query }
  let map, marker, geocoder;     // only used when a Google Maps key is set
  let searchTimer;

  const hasKey = () => Boolean(C.config.googleMapsKey);

  function select(value) {
    selection = value;
    sendButton.disabled = !value;
  }

  function sendCurrent() {
    if (!navigator.geolocation) {
      return C.addMessage({ type: 'notice', text: 'Location is not supported in this browser.' });
    }
    navigator.geolocation.getCurrentPosition(
      position => {
        C.sendMessage({
          type: 'location',
          lat: +position.coords.latitude.toFixed(5),
          lng: +position.coords.longitude.toFixed(5)
        });
        dialog.close();
      },
      () => C.addMessage({ type: 'notice', text: 'Location is blocked. Allow access in your browser settings and try again.' }),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  }

  /* ----- With a key: interactive Google map ----- */
  function loadGoogleMaps() {
    if (window.google?.maps) return Promise.resolve();
    return new Promise((resolve, reject) => {
      window.__mapsReady = resolve;
      const script = document.createElement('script');
      script.src = `https://maps.googleapis.com/maps/api/js?key=${C.config.googleMapsKey}&callback=__mapsReady`;
      script.onerror = reject;
      document.head.append(script);
    });
  }

  function dropPin(lat, lng) {
    marker.setPosition({ lat, lng });
    marker.setVisible(true);
    select({ lat: +lat.toFixed(5), lng: +lng.toFixed(5) });
  }

  async function setupMap() {
    try {
      await loadGoogleMaps();
    } catch {
      preview.textContent = 'Google Maps could not load. Check your API key.';
      return;
    }
    map = new google.maps.Map(preview, {
      center: { lat: 20, lng: 0 },
      zoom: 2,
      disableDefaultUI: true,
      zoomControl: true,
      clickableIcons: false
    });
    geocoder = new google.maps.Geocoder();
    marker = new google.maps.Marker({ map, visible: false });
    map.addListener('click', event => dropPin(event.latLng.lat(), event.latLng.lng()));
  }

  function findPlace(text) {
    if (hasKey()) {
      geocoder?.geocode({ address: text }, (results, status) => {
        if (status !== 'OK') return;
        const spot = results[0].geometry.location;
        map.setCenter(spot);
        map.setZoom(15);
        dropPin(spot.lat(), spot.lng());
      });
      return;
    }

    // No key: keyless Google embed previews whatever was typed
    const frame = C.el('iframe');
    frame.title = 'Place preview';
    frame.src = `https://maps.google.com/maps?q=${encodeURIComponent(text)}&z=15&output=embed`;
    preview.replaceChildren(frame);
    select({ query: text });
  }

  function open() {
    search.value = '';
    select(null);
    dialog.showModal();

    if (!hasKey()) {
      preview.replaceChildren();
    } else if (!map) {
      setupMap();
    } else {
      marker.setVisible(false);
    }
  }

  search.addEventListener('input', () => {
    clearTimeout(searchTimer);
    const text = search.value.trim();
    if (!text) return;
    searchTimer = setTimeout(() => findPlace(text), 500);
  });

  $('#locForm').addEventListener('submit', event => event.preventDefault());
  $('#locCurrent').addEventListener('click', sendCurrent);
  $('#locCancel').addEventListener('click', () => dialog.close());
  sendButton.addEventListener('click', () => {
    if (!selection) return;
    C.sendMessage({ type: 'location', ...selection });
    dialog.close();
  });

  C.location = { open };
})(window.Chat);
