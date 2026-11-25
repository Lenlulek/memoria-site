const bindCdekPoints = (() => {
  const endpoint = "https://functions.yandexcloud.net/d4ek0k6sut0uou7s9f0g";
  let leaflet;
  let disposeMap;

  function loadMapLibrary() {
    if (window.L) return Promise.resolve(window.L);
    if (!leaflet) {
      leaflet = new Promise((resolve, reject) => {
        const base = "https://unpkg.com/leaflet@1.9.4/dist/leaflet";
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = base + ".css";
        css.integrity = "sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=";
        css.crossOrigin = "anonymous";
        document.head.append(css);
        const script = document.createElement("script");
        script.src = base + ".js";
        script.integrity = "sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=";
        script.crossOrigin = "anonymous";
        script.onload = () => resolve(window.L);
        script.onerror = reject;
        css.onerror = reject;
        document.head.append(script);
      });
    }
    return leaflet;
  }

  async function lookup(action, params) {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({action, ...params}),
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) throw new Error("CDEK lookup failed");
    const data = await response.json();
    if (!Array.isArray(data)) throw new Error("Invalid CDEK response");
    return data;
  }

  function setOptions(select, caption, options) {
    select.replaceChildren(new Option(caption, ""), ...options);
    select.hidden = options.length === 0;
  }

  return (panel, cityInput, delivery, update) => {
    const button = panel.querySelector("button");
    const [cities, offices] = panel.querySelectorAll("select");
    const status = panel.querySelector("[role=status]");
    const mapHost = document.createElement("div");
    mapHost.hidden = true;
    mapHost.style.cssText = "height:clamp(220px,40dvh,340px);border-radius:10px;overflow:hidden;isolation:isolate";
    mapHost.setAttribute("aria-label", "Карта пунктов выдачи СДЭК");
    panel.insertBefore(mapHost, offices);
    let markers = new Map();
    let map;
    let revision = 0;

    function resetMap() {
      if (map) map.remove();
      map = null;
      markers.clear();
      mapHost.hidden = true;
    }

    if (disposeMap) disposeMap();
    const observer = new MutationObserver(() => {
      if (!panel.isConnected) dispose();
    });
    observer.observe(document.body, {childList: true, subtree: true});
    function dispose() {
      observer.disconnect();
      revision++;
      resetMap();
      if (disposeMap === dispose) disposeMap = null;
    }
    disposeMap = dispose;

    async function displayMap(points, current) {
      const mapped = points.flatMap(point => {
        const {latitude, longitude} = point.location;
        return Number.isFinite(latitude) && Number.isFinite(longitude)
          ? [{point, coordinates: [latitude, longitude]}] : [];
      });
      if (!mapped.length) return;
      try {
        const L = await loadMapLibrary();
        if (current !== revision || !panel.isConnected) return;
        mapHost.hidden = false;
        map = L.map(mapHost, {scrollWheelZoom: false});
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(map);
        for (const {point, coordinates} of mapped) {
          const label = document.createElement("span");
          label.textContent = point.location.address;
          const marker = L.marker(coordinates, {title: point.location.address}).addTo(map);
          marker.bindPopup(label);
          marker.on("click", () => {
            offices.value = point.code;
            selectPoint();
          });
          markers.set(point.code, marker);
        }
        map.fitBounds(mapped.map(entry => entry.coordinates), {padding: [18, 18], maxZoom: 14});
      } catch {
        resetMap();
      }
    }

    function clearPoint() {
      delivery.point = "";
      delivery.pointCode = "";
      update();
    }

    function showError() {
      status.textContent = "Не удалось загрузить пункты СДЭК. Попробуйте ещё раз или выберите Ozon.";
    }

    async function loadOffices(cityCode) {
      const current = ++revision;
      clearPoint();
      resetMap();
      setOptions(offices, "", []);
      if (!cityCode) {
        status.textContent = "Выберите город из списка.";
        return;
      }
      status.textContent = "Загружаем пункты выдачи…";
      try {
        const points = await lookup("fittingPoints", {city_code: cityCode});
        if (current !== revision || !panel.isConnected) return;
        const eligible = points.filter(point => point.code && point.location?.address &&
          point.is_dressing_room === true && point.allowed_cod === true);
        const options = eligible.map(point => new Option(point.location.address, point.code));
        setOptions(offices, "Выберите пункт выдачи", options);
        status.textContent = options.length ? "Выберите удобный адрес." :
          "В этом городе не нашлось пунктов СДЭК с примеркой и оплатой при получении.";
        void displayMap(eligible, current);
      } catch {
        if (current === revision) showError();
      }
    }

    cityInput.addEventListener("input", () => {
      revision++;
      resetMap();
      status.textContent = "";
      setOptions(cities, "", []);
      setOptions(offices, "", []);
      clearPoint();
    });

    button.addEventListener("click", async () => {
      const city = cityInput.value.trim();
      if (city.length < 2) {
        status.textContent = "Введите название города.";
        cityInput.focus();
        return;
      }
      const current = ++revision;
      clearPoint();
      resetMap();
      setOptions(cities, "", []);
      setOptions(offices, "", []);
      status.textContent = "Ищем город…";
      try {
        const results = await lookup("cities", {city});
        if (current !== revision || !panel.isConnected) return;
        const options = results.filter(item => item.code && item.city).map(item =>
          new Option([item.city, item.region].filter(Boolean).join(", "), item.code));
        setOptions(cities, "Уточните город", options);
        if (options.length === 1) {
          cities.value = options[0].value;
          await loadOffices(cities.value);
        } else {
          status.textContent = options.length ? "Выберите город из списка." :
            "Город не найден. Проверьте написание.";
        }
      } catch {
        if (current === revision) showError();
      }
    });

    cities.addEventListener("change", () => loadOffices(cities.value));
    function selectPoint() {
      if (!offices.value) {
        clearPoint();
        return;
      }
      delivery.city = cities.selectedOptions[0].textContent;
      cityInput.value = delivery.city;
      delivery.point = offices.selectedOptions[0].textContent;
      delivery.pointCode = offices.value;
      status.textContent = "Выбран пункт " + delivery.pointCode + ": " + delivery.point;
      update();
    }
    offices.addEventListener("change", () => {
      selectPoint();
      const marker = markers.get(offices.value);
      if (marker) {
        map.setView(marker.getLatLng(), Math.max(map.getZoom(), 14));
        marker.openPopup();
      }
    });
  };
})();
