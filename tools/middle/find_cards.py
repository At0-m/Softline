#!/usr/bin/env python3
"""M1 · Быстрый поиск карточек фида по подстроке названия (владелец: Middle).

Однопроходный потоковый поиск для ручной проверки ID: печатает первые N
совпадений с id, названием, URL, ценой и категорией. Не поисковый канал M2.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profile_feed import open_stream, DEFAULT_FEED  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("needles", nargs="+", help="подстроки названия (без учёта регистра)")
    ap.add_argument("--feed", default=os.environ.get("SOFTLINE_FEED", DEFAULT_FEED))
    ap.add_argument("--limit", type=int, default=5, help="совпадений на подстроку")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    needles = [n.lower() for n in args.needles]
    found: dict[str, list[dict]] = {n: [] for n in needles}
    cat_names: dict[str, str] = {}
    stream, fmt = open_stream(args.feed)
    for _, el in ET.iterparse(stream, events=("end",)):
        if el.tag == "category":
            cid = (el.get("id") or "").strip()
            if cid:
                cat_names[cid] = (el.text or "").strip()
            el.clear()
        elif el.tag == "offer":
            name = (el.findtext("name") or "").strip()
            low = name.lower()
            fields = {ch.tag: (ch.text or "").strip() for ch in el if ch.tag != "param"}
            for n in needles:
                if n in low and len(found[n]) < args.limit:
                    cid = fields.get("categoryId", "")
                    found[n].append({
                        "needle": n, "id": el.get("id"),
                        "name": name, "vendor": fields.get("vendor", ""),
                        "url": fields.get("url", ""),
                        "price": fields.get("price", ""),
                        "currencyId": fields.get("currencyId", ""),
                        "categoryId": cid,
                        "category_name": cat_names.get(cid, ""),
                        "available": el.get("available", ""),
                    })
            el.clear()
    stream.close()
    if args.json:
        print(json.dumps(found, ensure_ascii=False, indent=2))
    else:
        for n, cards in found.items():
            print(f"### {n!r} ({len(cards)})")
            for c in cards:
                print(f"  id={c['id']} avail={c['available']} price={c['price']} {c['currencyId']}")
                print(f"    {c['name'][:100]}")
                print(f"    {c['url']}")
                print(f"    cat={c['categoryId']} → {c['category_name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
