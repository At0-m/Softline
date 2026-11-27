#!/usr/bin/env python3
"""Генератор мини-XLSX фикстуры для smoke-теста match_targets.py.

Создаёт /tmp/opencode/mini_targets.fixture.xlsx (файл вне Git) с двумя
листами-колонками «запрос / целевой URL» на доменах example.com. ФИКСТУРА:
синтетические адреса, не данные партнёра.
"""
import os
import zipfile
from xml.sax.saxutils import escape

OUT = "/tmp/opencode/mini_targets.fixture.xlsx"

ROWS = [
    ("Пример запроса", "Целевой ответ (первый товар в выдаче или категория) "),
    ("точный url", "https://example.com/kripto-pro/abc123-10/"),
    ("криптопро", "https://example.com/kripto-pro/kriptopro-csp/"),
    ("сканер-вс", "https://example.com/npo-echelon/eshelon-skaner-vs/"),
    ("фильтр категории", "https://example.com/kripto-pro/?filter%5Bcategory%5D%5B%5D=2"),
    ("направление", "https://example.com/webinar/"),
    ("", "строка без запроса — должна попасть в пропуски"),
]

SST = "".join(f"<si><t>{escape(v)}</t></si>" for row in ROWS for v in row)
sheet_rows = "".join(
    f'<row r="{i + 1}">'
    + "".join(
        f'<c r="{"AB"[j]}{i + 1}" t="s"><v>{i * 2 + j}</v></c>'
        for j in range(2)
    )
    + "</row>"
    for i, row in enumerate(ROWS)
)

FILES = {
    "[Content_Types].xml": (
        '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    ),
    "_rels/.rels": (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    ),
    "xl/workbook.xml": (
        '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>'
    ),
    "xl/_rels/workbook.xml.rels": (
        '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        "</Relationships>"
    ),
    "xl/sharedStrings.xml": f'<?xml version="1.0"?><sst count="{len(ROWS) * 2}" uniqueCount="{len(ROWS) * 2}" xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{SST}</sst>',
    "xl/worksheets/sheet1.xml": f'<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{sheet_rows}</sheetData></worksheet>',
}

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with zipfile.ZipFile(OUT, "w") as zf:
    for name, body in FILES.items():
        zf.writestr(name, body)
print(f"written {OUT}")
