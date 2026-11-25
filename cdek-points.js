const bindCdekPoints = (() => {
  const endpoint = "https://functions.yandexcloud.net/d4ek0k6sut0uou7s9f0g";

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
    let revision = 0;

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
      setOptions(offices, "", []);
      if (!cityCode) return;
      status.textContent = "Загружаем пункты выдачи…";
      try {
        const points = await lookup("fittingPoints", {city_code: cityCode});
        if (current !== revision || !panel.isConnected) return;
        const options = points.filter(point => point.code && point.location?.address &&
          point.is_dressing_room === true && point.allowed_cod === true).map(point =>
          new Option(point.location.address, point.code));
        setOptions(offices, "Выберите пункт выдачи", options);
        status.textContent = options.length ? "Выберите удобный адрес." :
          "В этом городе не нашлось пунктов СДЭК с примеркой и оплатой при получении.";
      } catch {
        if (current === revision) showError();
      }
    }

    cityInput.addEventListener("input", () => {
      revision++;
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
    offices.addEventListener("change", () => {
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
    });
  };
})();
