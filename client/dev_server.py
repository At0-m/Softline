"""Заглушка контракта для J1. Только локальная разработка UI.

Не является реализацией поиска: раздаёт статические файлы и договорные
тестовые примеры из fixtures/. Реальный бэкенд подключается заменой
SEARCH_API_BASE в client/api-config.js, компоненты карточек не меняются.

Запуск: python3 client/dev_server.py  (по умолчанию http://localhost:5173)
"""

import json
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT.parent / "fixtures"
PORT = int(os.environ.get("PORT", "5173"))

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


def route_query(query: str):
    """Сценарии по ключевым словам. Прочее — исходная фикстура (не изменяется)."""
    if re.search(r"ошибк|сбой", query):
        raise RuntimeError("Заглушка: имитация отказа backend")
    if "мало" in query:
        return "ui-cases/shortfall.json", 0.3
    if "нет совпадений" in query:
        return "ui-cases/no-direct.json", 0.3
    if "дополнение" in query:
        return "ui-cases/complement.json", 0.6
    # задержка, чтобы увидеть состояние загрузки
    return "search-response.json", 0.5


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path != "/search":
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, {"error": "Некорректный JSON"})
        query = body.get("query")
        if not isinstance(query, str) or not query.strip():
            return self._send(400, {"error": "Пустой запрос: укажите поисковую фразу"})
        try:
            rel, delay = route_query(query.strip())
            time.sleep(delay)
            with open(FIXTURES / rel, encoding="utf-8") as fh:
                return self._send(200, json.load(fh))
        except RuntimeError as e:
            return self._send(500, {"error": str(e)})

    def do_GET(self) -> None:
        rel = "index.html" if self.path == "/" else self.path.lstrip("/")
        file = (ROOT / rel).resolve()
        if not str(file).startswith(str(ROOT)) or not file.is_file():
            self.send_response(404)
            self.end_headers()
            return
        data = file.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(file.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args) -> None:
        print("%s %s" % (self.command, self.path))


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"UI-демо J1: http://localhost:{PORT}/ (fixture-only, POST /search — заглушка)")
    server.serve_forever()
