#!/usr/bin/env python3
"""M1 · Сопоставление эталонных URL из XLSX с каталогом фида (владелец: Middle).

Вход: XLSX с колонками «Пример запроса» / «Целевой ответ», файл фида.
XLSX читается как zip+XML (stdlib), строки без запроса или URL пропускаются
и считаются отдельно. Значимые query-параметры цели сохраняются и декодируются.

Сопоставление — по шагам, каждый шаг помечен в отчёте:
  exact  — полный URL цели совпал с URL товара из фида;
  path   — совпал путь без query (для товара query редок, но проверяется);
  heuristic — слаг цели разбивается на токены и сравнивается с названием
              товара после транслитерации и скелетизации согласных;
              это эвристика M1 для оценки покрытия, не поисковый канал M2.
Классификация цели: product / category (query-фильтр категории) / vendor_page
(одиночный сегмент пути направления). Категорийные URL в фиде отсутствуют —
проверяется существование categoryId из query в справочнике категорий фида.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_feed import detect_format, open_stream  # noqa: E402

DEFAULT_XLSX = "/home/papito/data/softline/input/Выборка поисковых запросов.xlsx"
DEFAULT_FEED = "/home/papito/data/softline/input/Mindbox.yml.gz.xml"

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}
VOWELS = set("aeiou")


def translit(text: str) -> str:
    out = []
    for ch in text.lower():
        out.append(TRANSLIT.get(ch, ch))
    return "".join(out)


def skeleton(token: str) -> str:
    """Согласный скелет токена: регистр/гласные/y→i/k→c не различаются.
    Связывает «криптопро»~«cryptopro», «для»~«dlya», «эшелон»~«eshelon»."""
    t = translit(unicodedata.normalize("NFKD", token).lower())
    t = t.replace("y", "i").replace("k", "c")
    return "".join(ch for ch in t if ch not in VOWELS)


def tokens(text: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", translit(text.lower())) if t]


def token_match(a: str, b: str) -> bool:
    return a == b or (len(a) > 2 and len(b) > 2 and skeleton(a) == skeleton(b))


def read_xlsx(path: str) -> dict:
    """Листы, колонки, строки. Возвращает фактическую структуру и эталоны."""
    with zipfile.ZipFile(path) as zf:
        wb = ET.fromstring(zf.read("xl/workbook.xml"))
        sheets = [(s.get("name"), s.get("sheetId"))
                  for s in wb.iter(NS + "sheet")]
        sst: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root:
                sst.append("".join(t.text or "" for t in si.iter(NS + "t")))
        rows: dict[str, list[str]] = {}
        for name, _sid in sheets:
            sheet_file = f"xl/worksheets/sheet{name.lower()}.xml" if name.lower().startswith("sheet") else None
            if sheet_file is None or sheet_file not in zf.namelist():
                # fallback: первый worksheet
                sheet_file = next(n for n in zf.namelist()
                                  if n.startswith("xl/worksheets/sheet"))
            root = ET.fromstring(zf.read(sheet_file))
            for row in root.iter(NS + "row"):
                cells = []
                for c in row.iter(NS + "c"):
                    v = c.find(NS + "v")
                    val = v.text if v is not None else ""
                    if c.get("t") == "s" and val != "":
                        val = sst[int(val)]
                    cells.append(val)
                rows[row.get("r", str(len(rows) + 1))] = cells
    header = rows.get("1", [])
    refs = []
    skipped = 0
    for rn in sorted(rows, key=lambda r: int(r)):
        if rn == "1":
            continue
        cells = rows[rn]
        query = cells[0].strip() if len(cells) > 0 and cells[0] else ""
        target = cells[1].strip() if len(cells) > 1 and cells[1] else ""
        if query and target:
            refs.append({"row": int(rn), "query": query, "url": target})
        else:
            skipped += 1
    return {"sheets": sheets, "header": header, "refs": refs,
            "skipped_rows": skipped}


def classify_target(url: str) -> tuple[str, dict]:
    parsed = urllib.parse.urlsplit(url)
    params = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    cat_ids = [v for k, v in params
               if "category" in urllib.parse.unquote(k).lower()]
    segments = [s for s in parsed.path.split("/") if s]
    if cat_ids:
        return "category", {"category_ids": cat_ids, "query_params": params,
                            "segments": segments}
    if len(segments) <= 1:
        return "vendor_page", {"query_params": params, "segments": segments}
    return "product", {"query_params": params, "segments": segments}


def match_target(ref: dict, kind: str, info: dict, catalog: dict) -> dict:
    url = ref["url"]
    parsed = urllib.parse.urlsplit(url)
    target_path = parsed.path.rstrip("/").lower()
    res: dict = {
        "row": ref["row"], "query": ref["query"], "url": url,
        "type": kind, "detail": info,
        "match": None, "match_kind": "no_match", "reason": "",
    }
    if kind == "category":
        cat_ids = info["category_ids"]
        known = {c: catalog["category_names"].get(c, "")
                 for c in cat_ids}
        found = [c for c, n in known.items() if n]
        res["match_kind"] = "category_id_resolved" if found else "no_match"
        res["match"] = {"category_id": cat_ids[0] if cat_ids else None,
                        "category_name": known.get(cat_ids[0], "") if cat_ids else ""}
        res["reason"] = (
            "URL категории в фиде отсутствует; categoryId из query-фильтра "
            "проверен по справочнику категорий фида"
            if found else
            "URL категории в фиде отсутствует; categoryId из query "
            "не найден в справочнике категорий — причина пока неизвестна")
        return res

    if kind == "vendor_page":
        seg = info["segments"][0] if info["segments"] else ""
        hit = catalog["vendor_segments"].get(seg, 0)
        res["match_kind"] = "segment_present" if hit else "no_match"
        res["match"] = {"segment": seg, "offer_urls_with_segment": hit}
        res["reason"] = (
            "Страница направления: сегмент пути встречается в URL товаров "
            "фида, но отдельной карточки не имеет"
            if hit else
            "Страница направления: сегмент не встречается в URL товаров фида")
        return res

    # product
    exact = catalog["url_to_id"].get(url)
    if exact:
        res.update(match_kind="exact", match=catalog["cards_by_id"][exact])
        return res
    by_path = catalog["path_to_ids"].get(target_path)
    if by_path:
        res.update(match_kind="path",
                   match=catalog["cards_by_id"][by_path[0]])
        res["reason"] = "совпал путь, query различается"
        return res

    segments = info["segments"]
    vendor_seg, product_seg = segments[0], "-".join(segments[1:])
    want_tokens = tokens(product_seg.replace("-", " "))
    want_sk = {skeleton(t) for t in want_tokens}
    cands = catalog["by_vendor_segment"].get(vendor_seg, [])
    best = None
    for card in cands:
        name_tokens = tokens(card["name"]) + tokens(card.get("vendor", ""))
        got = set()
        for wt in want_tokens:
            if any(token_match(wt, nt) for nt in name_tokens):
                got.add(skeleton(wt))
        if want_sk and got == want_sk:
            best = card
            break
        score = len(got) / max(len(want_sk), 1)
        if score >= 0.5 and (best is None or score > best.get("_score", 0)):
            best = dict(card, _score=score)
    if best:
        best.pop("_score", None)
        res.update(match_kind="heuristic", match=best)
        res["reason"] = (
            "слаг витрины не встречается в URL фида (фид использует hash-id "
            "слаги); найден кандидат по токенам названия после транслитерации")
    else:
        res["reason"] = (
            "слаг витрины не встречается в URL фида; кандидат по токенам "
            "названия не найден — причина пока неизвестна")
    return res


def scan_feed(feed: str, vendor_segments: set[str],
              extra_category_ids: set[str]) -> dict:
    fmt = detect_format(feed)
    stream, _ = open_stream(feed)
    ctx = ET.iterparse(stream, events=("end",))
    cat_names: dict[str, str] = {}
    url_to_id: dict[str, str] = {}
    path_to_ids: dict[str, list[str]] = {}
    vendor_seg_count: Counter = Counter()
    by_vendor: dict[str, list[dict]] = {}
    cards_by_id: dict[str, dict] = {}
    records = unique = 0
    seen: set[str] = set()
    urls_with_query = 0
    for _, el in ctx:
        if el.tag == "category":
            cid = (el.get("id") or "").strip()
            if cid:
                cat_names[cid] = (el.text or "").strip()
            el.clear()
        elif el.tag == "offer":
            records += 1
            oid = (el.get("id") or "").strip()
            if not oid or oid in seen:
                continue
            seen.add(oid)
            unique += 1
            fields = {}
            for child in el:
                if child.tag != "param":
                    fields[child.tag] = (child.text or "").strip()
            url = fields.get("url", "")
            if url:
                if "?" in url:
                    urls_with_query += 1
                path = url.split("?", 1)[0].rstrip("/").lower()
                url_to_id[url] = oid
                path_to_ids.setdefault(path, []).append(oid)
                seg = path.split("/")[3] if path.count("/") >= 3 else ""
                vendor_seg_count[seg] += 1
                if seg in vendor_segments:
                    card = {
                        "id": oid,
                        "name": fields.get("name", ""),
                        "vendor": fields.get("vendor", ""),
                        "url": url,
                        "price": fields.get("price", ""),
                        "currencyId": fields.get("currencyId", ""),
                        "categoryId": fields.get("categoryId", ""),
                        "category_name": cat_names.get(fields.get("categoryId", ""), ""),
                    }
                    by_vendor.setdefault(seg, []).append(card)
                    cards_by_id[oid] = card
            el.clear()
    stream.close()
    missing_cats = sorted(c for c in extra_category_ids if c not in cat_names)
    return {
        "format": fmt, "records": records, "unique_ids": unique,
        "category_names": cat_names, "url_to_id": url_to_id,
        "path_to_ids": path_to_ids,
        "vendor_segments": dict(vendor_seg_count),
        "by_vendor_segment": by_vendor, "cards_by_id": cards_by_id,
        "urls_with_query": urls_with_query,
        "missing_extra_category_ids": missing_cats,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--xlsx", default=os.environ.get("SOFTLINE_XLSX", DEFAULT_XLSX))
    ap.add_argument("--feed", default=os.environ.get("SOFTLINE_FEED", DEFAULT_FEED))
    ap.add_argument("--out", default=None)
    ap.add_argument("--print", action="store_true")
    args = ap.parse_args()

    xlsx = read_xlsx(args.xlsx)
    print(f"sheets={xlsx['sheets']} header={xlsx['header']} "
          f"refs={len(xlsx['refs'])} skipped={xlsx['skipped_rows']}",
          file=sys.stderr)

    parsed_refs = []
    vendor_segments: set[str] = set()
    extra_cats: set[str] = set()
    for ref in xlsx["refs"]:
        kind, info = classify_target(ref["url"])
        if info.get("segments"):
            vendor_segments.add(info["segments"][0])
        extra_cats.update(info.get("category_ids", []))
        parsed_refs.append((ref, kind, info))

    catalog = scan_feed(args.feed, vendor_segments, extra_cats)
    results = [match_target(ref, kind, info, catalog)
               for ref, kind, info in parsed_refs]

    summary = {
        "tool": "match_targets.py",
        "xlsx": {
            "path": args.xlsx,
            "sheets": xlsx["sheets"],
            "header": xlsx["header"],
            "rows_nonempty_refs": len(xlsx["refs"]),
            "rows_skipped": xlsx["skipped_rows"],
        },
        "feed": {
            "path": args.feed, "format": catalog["format"],
            "records": catalog["records"], "unique_ids": catalog["unique_ids"],
            "offer_urls_total": len(catalog["url_to_id"]),
            "offer_urls_with_query": catalog["urls_with_query"],
        },
        "counts": {
            "product_targets": sum(1 for _, k, _ in parsed_refs if k == "product"),
            "category_targets": sum(1 for _, k, _ in parsed_refs if k == "category"),
            "vendor_page_targets": sum(1 for _, k, _ in parsed_refs if k == "vendor_page"),
        },
        "match_counts": dict(Counter(r["match_kind"] for r in results)),
        "missing_extra_category_ids": catalog["missing_extra_category_ids"],
        "results": results,
    }
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    if args.print or not args.out:
        print(payload)
    print("match_counts=" + json.dumps(summary["match_counts"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
