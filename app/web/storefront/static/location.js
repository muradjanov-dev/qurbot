/* Shared optional pin for account, checkout and operator enquiries. */
(() => {
  'use strict';
  document.querySelectorAll('[data-location-picker]').forEach(root => {
    const picker = root.querySelector('.location-picker');
    const latInput = root.querySelector('[data-lat]');
    const lngInput = root.querySelector('[data-lng]');
    const address = root.querySelector('[data-address-text]') || root.querySelector('[name="address"]');
    const district = root.querySelector('[data-district]') || root.querySelector('[name="district"]');
    const mapNode = root.querySelector('[data-location-map]');
    const status = root.querySelector('[data-location-status]');
    const suggestion = root.querySelector('[data-location-suggestion]');
    const current = root.querySelector('[data-location-current]');
    const toggle = root.querySelector('[data-location-map-toggle]');
    let map, marker, suggested = '', selectionSerial = 0;

    async function setPin(lat, lng) {
      if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) return;
      const serial = ++selectionSerial;
      latInput.value = String(lat); lngInput.value = String(lng);
      district?.setCustomValidity('');
      if (map) {
        if (marker) marker.setLatLng([lat, lng]);
        else marker = L.marker([lat, lng], {icon: L.divIcon({className: 'location-marker', iconSize: [20, 20]})}).addTo(map);
        map.setView([lat, lng], 16);
      }
      status.textContent = picker.dataset.selected;
      try {
        const response = await fetch(`/api/geocode?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`, {credentials: 'same-origin'});
        const data = await response.json();
        if (serial !== selectionSerial) return;
        if (data.ok && data.address) {
          suggested = data.address;
          if (!address.value.trim()) address.value = suggested;
          else suggestion.hidden = false;
        }
        if (data.ok && data.district_id && district) district.value = String(data.district_id);
        if (data.notice) status.textContent = data.notice;
      } catch (_) { /* The typed address stays available if geocoding fails. */ }
      latInput.dispatchEvent(new Event('input', {bubbles: true}));
    }

    function browserLocation() {
      if (!navigator.geolocation) {status.textContent = picker.dataset.failed; return;}
      navigator.geolocation.getCurrentPosition(
        p => setPin(p.coords.latitude, p.coords.longitude),
        () => {status.textContent = picker.dataset.failed;},
        {enableHighAccuracy: true, timeout: 10000}
      );
    }

    current.addEventListener('click', () => {
      const manager = window.Telegram?.WebApp?.LocationManager;
      if (!manager || !window.Telegram.WebApp.isVersionAtLeast?.('8.0')) {browserLocation(); return;}
      manager.init(() => manager.getLocation(location => {
        if (location) setPin(location.latitude, location.longitude);
        else status.textContent = picker.dataset.failed;
      }));
    });

    toggle.addEventListener('click', () => {
      mapNode.hidden = !mapNode.hidden;
      if (mapNode.hidden) return;
      if (!window.L) {mapNode.hidden = true; status.textContent = picker.dataset.mapFailed; return;}
      if (!map) {
        const lat = Number(latInput.value || root.dataset.defaultLat);
        const lng = Number(lngInput.value || root.dataset.defaultLng);
        map = L.map(mapNode).setView([lat, lng], latInput.value ? 16 : 11);
        L.tileLayer(root.dataset.tileUrl, {attribution: root.dataset.tileAttribution, maxZoom: 19}).addTo(map);
        map.on('click', event => setPin(event.latlng.lat, event.latlng.lng));
        if (latInput.value) setPin(lat, lng);
      }
      setTimeout(() => map.invalidateSize(), 0);
    });
    suggestion.addEventListener('click', () => {
      if (suggested) {address.value = suggested; address.dispatchEvent(new Event('input', {bubbles: true}));}
      suggestion.hidden = true;
    });
    const form = root.tagName === 'FORM' ? root : root.closest('form');
    if (form && district) form.addEventListener('submit', event => {
      if (!latInput.value && !district.value) {
        event.preventDefault();
        district.setCustomValidity(picker.dataset.districtRequired || picker.dataset.failed);
        district.reportValidity();
      }
    });
    district?.addEventListener('change', () => district.setCustomValidity(''));
  });
})();
