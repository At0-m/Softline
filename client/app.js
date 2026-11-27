// Состояния экрана поиска: загрузка, результат, нет прямого совпадения, сбой.
(function () {
  const form = document.getElementById('search-form');
  const input = document.getElementById('search-input');
  const chips = document.querySelectorAll('[data-demo-query]');
  const stateBox = document.getElementById('state-box');

  // Гард устаревших ответов: быстрый повторный ввод не затирается старым ответом.
  let requestSeq = 0;

  function clearBox() {
    stateBox.innerHTML = '';
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // --- Состояние 1: загрузка ---
  function showLoading() {
    clearBox();
    const box = el('div', 'state state--loading');
    box.appendChild(el('div', 'spinner'));
    box.appendChild(el('p', 'state__text', 'Идёт поиск…'));
    stateBox.appendChild(box);
  }

  // --- Состояние 2 и 3: результат / нет прямого совпадения ---
  function showResult(data) {
    clearBox();
    const box = el('div', 'state state--result');

    // Цель: продукт или категория.
    if (data.target) {
      const target = el('div', 'target');
      const label =
        (data.target.type === 'category' ? 'Подборка: ' : 'Первая цель: ') + data.target.label;
      const a = el('a', 'target__link', label);
      a.href = data.target.url;
      a.target = '_blank';
      a.rel = 'noopener';
      target.appendChild(a);
      box.appendChild(target);
    }

    // Нет прямых совпадений — успешный ответ: пометка + альтернативы ниже.
    if (!data.counts || data.counts.direct === 0) {
      box.appendChild(
        el('p', 'notice notice--no-direct', 'Прямого совпадения не найдено. Показываем ближайшие альтернативы.')
      );
    }

    const ctx = {
      categoryUrl: data.target && data.target.type === 'category' ? data.target.url : null,
      byId: Object.fromEntries((data.items || []).map((i) => [i.id, i]))
    };
    const rendered = CardComponents.renderItems(data.items || [], ctx);
    box.appendChild(rendered.node);

    // Счётчик: только карточки, без заголовков секций. При shortfall — реальное число.
    const counter = el('p', 'counter');
    const distinct = data.counts ? data.counts.distinct : rendered.cardCount;
    counter.textContent =
      'Показано товаров: ' + rendered.cardCount + ' (различных: ' + distinct + ')';
    box.appendChild(counter);

    if (data.shortfall) {
      box.appendChild(
        el('p', 'notice notice--shortfall', 'Подборка меньше четырёх позиций. Причина: ' + (data.reason || 'не указана'))
      );
    }

    const meta = el('p', 'meta');
    meta.textContent =
      'Маршрут: ' + (data.route || '—') +
      (data.route === 'fallback' && data.reason ? ' (' + data.reason + ')' : '') +
      ' · запрос ' + (data.request_id || '—') +
      ' · снимок ' + (data.index_version || '—') +
      ' · ' + (data.latency_ms != null ? data.latency_ms + ' мс' : '—');
    box.appendChild(meta);

    stateBox.appendChild(box);
  }

  // --- Состояние 4: технический сбой ---
  function showError(err) {
    clearBox();
    const box = el('div', 'state state--error');
    box.appendChild(el('h2', 'state__title', 'Технический сбой'));
    box.appendChild(el('p', 'state__text', err.message || 'Поиск временно недоступен. Повторите запрос.'));
    const retry = el('button', 'retry-btn', 'Повторить поиск');
    retry.type = 'button';
    retry.addEventListener('click', () => runSearch());
    box.appendChild(retry);
    stateBox.appendChild(box);
  }

  function runSearch() {
    const query = input.value.trim();
    if (!query) {
      showError(new Error('Введите непустой поисковый запрос.'));
      return;
    }
    const seq = ++requestSeq;
    showLoading();
    SearchClient.search(query)
      .then((data) => {
        if (seq !== requestSeq) return; // ответ устарел
        showResult(data);
      })
      .catch((err) => {
        if (seq !== requestSeq) return;
        showError(err);
      });
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    runSearch();
  });

  chips.forEach((chip) => {
    chip.addEventListener('click', () => {
      input.value = chip.dataset.demoQuery;
      runSearch();
    });
  });

  // Стартовое состояние: подсказка до первого запроса.
  function showIdle() {
    clearBox();
    const box = el('div', 'state state--idle');
    box.appendChild(el('p', 'state__text', 'Введите запрос или выберите демо-пример выше.'));
    stateBox.appendChild(box);
  }

  showIdle();
})();
