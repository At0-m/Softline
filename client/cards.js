// Компоненты карточек и секций. Работают с полями контракта v1 (docs/contract.md)
// и не знают, откуда пришёл ответ: фикстура, заглушка или реальный POST /search.

const CardComponents = (() => {
  const RELATION_LABEL = {
    direct: 'Прямое совпадение',
    alternative: 'Альтернатива',
    complement: 'Дополнение'
  };

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function link(href, cls, text) {
    const a = el('a', cls, text);
    a.href = href;
    a.target = '_blank';
    a.rel = 'noopener';
    return a;
  }

  function formatPrice(price) {
    if (!price || price.amount == null) return null;
    const cur = price.currency === 'RUB' ? '₽' : ' ' + (price.currency || '');
    return price.amount.toLocaleString('ru-RU') + cur;
  }

  // ctx: { categoryUrl } — адрес подборки для ссылки категории.
  function renderCard(item, ctx) {
    ctx = ctx || {};
    const card = el('article', 'card card--' + item.relation);

    const head = el('div', 'card__head');
    const title = link(item.url, 'card__title', item.title);
    head.appendChild(title);
    head.appendChild(el('span', 'badge badge--' + item.relation, RELATION_LABEL[item.relation] || item.relation));
    card.appendChild(head);

    // Категория ведёт на страницу подборки, если адрес известен.
    const cat = el('div', 'card__category');
    if (ctx.categoryUrl) {
      cat.appendChild(link(ctx.categoryUrl, 'card__category-link', item.category));
    } else {
      cat.textContent = item.category;
    }
    card.appendChild(cat);

    // Цена: объект amount/currency или null — нулём пропуск не заменяется.
    card.appendChild(el('div', 'card__price', formatPrice(item.price) || 'Цена не указана'));

    card.appendChild(el('p', 'card__why', item.why));

    if (item.relation === 'complement') {
      card.appendChild(renderComplementNote(item, ctx));
    }

    return card;
  }

  // Дополнение: к какому продукту относится + основание вендора.
  function renderComplementNote(item, ctx) {
    const note = el('div', 'card__complement-note');
    if (item.base_id && ctx.byId && ctx.byId[item.base_id]) {
      note.appendChild(el('span', 'card__base', 'Дополнение к: ' + ctx.byId[item.base_id].title));
    }
    const ev = item.evidence;
    if (ev && ev.source_url) {
      const row = el('div', 'card__evidence');
      row.appendChild(link(ev.source_url, 'card__evidence-link', 'Основание вендора'));
      if (ev.checked_at) row.appendChild(el('span', 'card__evidence-date', 'проверено ' + ev.checked_at));
      if (ev.claim) row.appendChild(el('div', 'card__evidence-claim', ev.claim));
      note.appendChild(row);
    }
    return note;
  }

  const SECTIONS = [
    { relation: 'direct', title: 'Прямые совпадения' },
    { relation: 'alternative', title: 'Альтернативы' },
    { relation: 'complement', title: 'Дополнения' }
  ];

  // Секции карточек по relation. Возвращает контейнер и число карточек
  // (заголовки секций в счётчик не входят).
  function renderItems(items, ctx) {
    const wrap = el('div', 'results');
    let cardCount = 0;
    for (const s of SECTIONS) {
      const list = items.filter((i) => i.relation === s.relation);
      if (!list.length) continue;
      const section = el('section', 'results__section');
      section.appendChild(el('h2', 'results__title', s.title));
      for (const item of list) {
        section.appendChild(renderCard(item, ctx));
        cardCount++;
      }
      wrap.appendChild(section);
    }
    return { node: wrap, cardCount };
  }

  return { renderCard, renderItems };
})();
