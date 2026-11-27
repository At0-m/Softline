# tools/middle · Профиль фида и сопоставление целей (M1)

Владелец: Middle (GLM). Только stdlib Python 3.12. Полный фид, XLSX и выгрузки
каталога в Git не попадают (см. корневой `.gitignore`); входы по умолчанию лежат
в `/home/papito/data/softline/input/`, можно переопределить `--feed`/`--xlsx`
или переменными `SOFTLINE_FEED`/`SOFTLINE_XLSX`.

## Команды M1

```bash
# 1. Профиль фида: формат по магическим байтам, SHA-256 снимка, агрегаты,
#    доли заполнения, примеры карточек. Отчёт в data/out/ (вне Git).
python3 tools/middle/profile_feed.py \
  --feed /home/papito/data/softline/input/Mindbox.yml.gz.xml \
  --out data/out/profile-mindbox.json --examples 5 \
  --feature-url 'kripto-pro' --feature-url 'astralinux' \
  --feature-url 'kaspersky' --feature-url 'echelon'

# 2. Сопоставление целей XLSX с каталогом: точный URL → путь → эвристика
#    по токенам названия (транслитерация + скелет согласных).
python3 tools/middle/match_targets.py \
  --xlsx "/home/papito/data/softline/input/Выборка поисковых запросов.xlsx" \
  --feed /home/papito/data/softline/input/Mindbox.yml.gz.xml \
  --out data/out/targets-match.json

# 3. Ручная проверка карточек по подстроке названия (для подбора реальных ID).
python3 tools/middle/find_cards.py 'криптопро csp' 'сканер-вс' --limit 4

# 4. Smoke-тест на помеченной фикстуре (синтетика, домены example.com).
python3 tools/middle/testdata/make_fixture_xlsx.py
python3 tools/middle/profile_feed.py --feed tools/middle/testdata/mini_feed.fixture.xml
python3 tools/middle/match_targets.py \
  --xlsx /tmp/opencode/mini_targets.fixture.xlsx \
  --feed tools/middle/testdata/mini_feed.fixture.xml --print
```

## Снимок 2026-11-25

* `snapshot_id = 27eaec9e77942c61-2026-11-25_1412`
  (SHA-256 `27eaec9e77942c61d58b3c04dcaa8991c707dc0fcb64a6442a7408d9908cb148`,
  дата из `yml_catalog/@date`).
* Файл `Mindbox.yml.gz.xml` — **не сжат**: по магическим байтам это обычный
  XML UTF-8, `.gz` в имени не соответствует содержимому. Инструмент читает
  gzip только если заголовок `1f 8b`.
* Товарные записи: 136 040; уникальных `offer/@id`: 136 040; пропусков id — 0,
  дублей id — 0, categoryId вне справочника — 0. Повторный прогон байт-в-байт
  совпадает.
* Категории: 9 311 (54 корневых, 9 257 с родителем).
* Цены: 55 771 карточек с ценой > 0; 80 269 с `price="0.00"`; пустых цен нет.

Отчёты прогонов: `data/out/profile-mindbox.json`, `data/out/targets-match.json`.
Handoff Senior: `team/handoff/middle-M1.md`.
