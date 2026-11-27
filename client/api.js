// Поисковый клиент. Инкапсулирует только транспорт POST /search, не формат карточек.
// Замена фикстуры на реальный сервис = правка api-config.js, файл не меняется.
(function () {
  const cfg = window.SEARCH_CONFIG || { SEARCH_API_BASE: '' };

  async function search(query) {
    const res = await fetch(cfg.SEARCH_API_BASE + '/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query })
    });

    if (res.status === 400) {
      const body = await res.json().catch(() => ({}));
      const err = new Error(body.error || 'Пустой запрос');
      err.kind = 'bad-request';
      throw err;
    }
    if (!res.ok) {
      throw new Error('Сервер поиска недоступен (HTTP ' + res.status + ')');
    }
    return res.json();
  }

  window.SearchClient = { search };
})();
