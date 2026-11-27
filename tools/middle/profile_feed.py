#!/usr/bin/env python3
"""M1 · Потоковое профилирование фида store.softline.ru (YML / Yandex Market Language).

Владелец: Middle. Вход — файл партнёра (вне Git), выход — агрегаты в JSON/NDJSON.
Формат и сжатие определяются по магическим байтам, а не по расширению:
gzip (1f 8b) читается через gzip, иначе файл разбирается как XML напрямую.
Только stdlib. В память попадают агрегаты и словари соответствий, полные записи
не удерживаются: <offer> и <category> выгружаются из дерева итератора.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter

DEFAULT_FEED = "/home/papito/data/softline/input/Mindbox.yml.gz.xml"

# Важные поля карточки по контракту v1 (id, title, url, category, price).
WATCHED_CHILD_FIELDS = (
    "name", "vendor", "vendorCode", "url", "price", "oldprice",
    "currencyId", "categoryId", "picture", "description", "group_id",
)


def detect_format(path: str) -> dict:
    """Формат по содержимому: первые байты решают, есть ли сжатие."""
    with open(path, "rb") as fh:
        head = fh.read(4)
    if head[:2] == b"\x1f\x8b":
        return {"container": "gzip", "body": "xml"}
    if head[:2] == b"PK\x03\x04":
        return {"container": "zip", "body": "unknown"}
    if head[:5] == b"<?xml" or head[:4] == b"<yml" or head[0:1] == b"<":
        return {"container": "none", "body": "xml"}
    return {"container": "unknown", "body": "unknown"}


def open_stream(path: str):
    fmt = detect_format(path)
    if fmt["container"] == "gzip":
        return gzip.open(path, "rb"), fmt
    return open(path, "rb"), fmt


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def text_of(el: ET.Element) -> str:
    return (el.text or "").strip()


class FeedProfiler:
    def __init__(self, max_examples: int, featured_slugs: list[str]) -> None:
        self.max_examples = max_examples
        self.featured_slugs = featured_slugs
        self.stats = {
            "snapshot_date": None,
            "shop": {},
            "categories": {"total": 0, "with_parent": 0, "roots": 0, "empty_name": 0},
            "offers": {
                "records": 0,          # все <offer> в потоке
                "unique_ids": 0,       # уникальных значений offer/@id
                "skipped_no_id": 0,    # нет атрибута id или пустой
                "duplicate_occurrences": 0,  # повторные записи уже виденного id
                "available_true": 0,
                "price_gt_zero": 0,
                "price_zero": 0,
                "price_missing": 0,
                "orphan_category_id": 0,   # categoryId отсутствует в справочнике
            },
            "fill": {f: 0 for f in WATCHED_CHILD_FIELDS},
            "fill_params": 0,          # offer имеет хотя бы один <param>
            "param_name_top": Counter(),
            "duplicate_id_examples": [],
            "orphan_category_examples": [],
            "featured": [],            # карточки по запрошенным подстрокам URL
            "first_examples": [],      # первые карточки потока
        }
        self.category_names: dict[str, str] = {}
        self.category_parent: dict[str, str] = {}
        self.seen_ids: set[str] = set()
        self.url_to_id: dict[str, str] = {}     # полный URL товара -> id
        self.path_to_ids: dict[str, list[str]] = {}
        self.vendor_slugs: Counter = Counter()  # сегмент пути URL товара

    # --- категории ---
    def on_category(self, el: ET.Element) -> None:
        s = self.stats["categories"]
        s["total"] += 1
        cid = el.get("id", "").strip()
        name = text_of(el)
        if not name:
            s["empty_name"] += 1
        parent = el.get("parentId", "").strip()
        if parent:
            s["with_parent"] += 1
            self.category_parent[cid] = parent
        else:
            s["roots"] += 1
        if cid:
            self.category_names[cid] = name

    # --- товары ---
    def on_offer(self, el: ET.Element) -> None:
        s = self.stats["offers"]
        s["records"] += 1
        oid = (el.get("id") or "").strip()
        if not oid:
            s["skipped_no_id"] += 1
        elif oid in self.seen_ids:
            s["duplicate_occurrences"] += 1
            if len(self.stats["duplicate_id_examples"]) < 5:
                self.stats["duplicate_id_examples"].append(oid)
        else:
            self.seen_ids.add(oid)
            s["unique_ids"] += 1

        fields: dict[str, str] = {}
        params: list[tuple[str, str]] = []
        for child in el:
            tag = child.tag
            if tag == "param":
                pname = child.get("name", "").strip()
                params.append((pname, text_of(child)))
            elif tag in WATCHED_CHILD_FIELDS:
                val = text_of(child)
                fields[tag] = val
                if val:
                    self.stats["fill"][tag] += 1

        if el.get("available", "").strip().lower() == "true":
            s["available_true"] += 1

        price_raw = fields.get("price", "")
        try:
            price = float(price_raw) if price_raw else None
        except ValueError:
            price = None
        if price_raw == "":
            s["price_missing"] += 1
        elif price is not None and price > 0:
            s["price_gt_zero"] += 1
        else:
            s["price_zero"] += 1

        if params:
            self.stats["fill_params"] += 1
            for pname, _ in params:
                self.stats["param_name_top"][pname] += 1

        cat_id = fields.get("categoryId", "")
        if cat_id and cat_id not in self.category_names:
            s["orphan_category_id"] += 1
            if len(self.stats["orphan_category_examples"]) < 5:
                self.stats["orphan_category_examples"].append(
                    {"offer_id": oid, "categoryId": cat_id})

        url = fields.get("url", "")
        if url and oid:
            self.url_to_id[url] = oid
            path = url.split("?", 1)[0].rstrip("/").lower()
            self.path_to_ids.setdefault(path, []).append(oid)
            try:
                self.vendor_slugs[path.split("/")[3]] += 1
            except IndexError:
                pass

        card = {
            "id": oid,
            "group_id": el.get("group_id") or fields.get("group_id", ""),
            "available": el.get("available", ""),
            "name": fields.get("name", ""),
            "vendor": fields.get("vendor", ""),
            "url": url,
            "price": price,
            "currencyId": fields.get("currencyId", ""),
            "categoryId": cat_id,
            "category_name": self.category_names.get(cat_id, ""),
            "params": params,
        }
        low_url = url.lower()
        for slug in self.featured_slugs:
            if slug and slug in low_url and not any(
                slug in c["url"].lower() for c in self.stats["featured"]
            ):
                card["featured_by"] = slug
                self.stats["featured"].append(card)
                break
        if len(self.stats["first_examples"]) < self.max_examples:
            self.stats["first_examples"].append(card)

    # --- корень ---
    def on_catalog(self, el: ET.Element) -> None:
        self.stats["snapshot_date"] = el.get("date")

    def run(self, path: str) -> dict:
        stream, fmt = open_stream(path)
        ctx = ET.iterparse(stream, events=("end",))
        t0 = time.time()
        depth_guard = 0
        for event, el in ctx:
            tag = el.tag
            if tag == "offer":
                self.on_offer(el)
                el.clear()
                depth_guard = 0
            elif tag == "category":
                self.on_category(el)
                el.clear()
                depth_guard = 0
            elif tag == "yml_catalog":
                self.on_catalog(el)
            else:
                # периодически освобождаем крупные узлы (categories, offers)
                depth_guard += 1
                if depth_guard > 2000:
                    el.clear()
                    depth_guard = 0
        stream.close()
        self.stats["elapsed_sec"] = round(time.time() - t0, 1)
        self.stats["format"] = fmt
        return self.report()

    def report(self) -> dict:
        s = self.stats
        rec = s["offers"]["records"]
        unique = s["offers"]["unique_ids"]
        fill = {k: {"count": v, "share": round(v / rec, 4) if rec else 0.0}
                for k, v in s["fill"].items()}
        fill["params_any"] = {
            "count": s["fill_params"],
            "share": round(s["fill_params"] / rec, 4) if rec else 0.0,
        }
        return {
            "tool": "profile_feed.py",
            "format": s["format"],
            "snapshot_date": s["snapshot_date"],
            "shop": s["shop"],
            "categories": s["categories"],
            "offers": s["offers"],
            "fill": fill,
            "param_name_top": s["param_name_top"].most_common(25),
            "duplicate_id_examples": s["duplicate_id_examples"],
            "orphan_category_examples": s["orphan_category_examples"],
            "featured": s["featured"],
            "first_examples": s["first_examples"],
            "elapsed_sec": s["elapsed_sec"],
        }

    # для match_targets.py: индексы URL
    def export_catalog(self, path: str, cards: list[dict]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            for c in cards:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--feed", default=os.environ.get("SOFTLINE_FEED", DEFAULT_FEED))
    ap.add_argument("--out", default=None, help="куда записать JSON-отчёт")
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--feature-url", action="append", default=[],
                    help="сохранить карточки, URL которых содержит подстроку (повторяемо)")
    ap.add_argument("--print", action="store_true", help="печатать отчёт в stdout")
    args = ap.parse_args()

    if not os.path.exists(args.feed):
        print(f"feed not found: {args.feed}", file=sys.stderr)
        return 2

    digest = sha256_of(args.feed)
    profiler = FeedProfiler(args.examples, args.feature_url)
    report = profiler.run(args.feed)
    snapshot = f"{digest[:16]}-{(report.get('snapshot_date') or 'nodate').replace(' ', '_').replace(':', '')}"
    report["feed_path"] = args.feed
    report["feed_size_bytes"] = os.path.getsize(args.feed)
    report["sha256"] = digest
    report["snapshot_id"] = snapshot
    report["id_field"] = "offer/@id"
    report["counting_rules"] = {
        "records": "каждый элемент <offer> в потоке",
        "unique_ids": "первая встреча непустого offer/@id",
        "skipped_no_id": "<offer> без атрибута id или с пустым",
        "duplicate_occurrences": "повторное появление уже виденного offer/@id",
    }
    report["indices"] = {
        "offer_urls": len(profiler.url_to_id),
        "offer_paths": len(profiler.path_to_ids),
        "top_vendor_slugs": profiler.vendor_slugs.most_common(15),
        "url_sample_first10": dict(list(profiler.url_to_id.items())[:10]),
    }

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    if args.print or not args.out:
        print(payload)
    print(f"snapshot_id={snapshot}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
