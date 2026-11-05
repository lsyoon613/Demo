"""Optional authenticated Enamine gateway; no catalog files are transferred to clients."""
from __future__ import annotations

from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import ipaddress
import json
import os
import sqlite3
from urllib.parse import urlsplit

import requests


URL_ENV = "SYNTHESIS_ENAMINE_API_URL"
CLIENT_TOKEN_ENV = "SYNTHESIS_ENAMINE_API_TOKEN"
SERVER_TOKEN_ENV = "SYNTHESIS_ENAMINE_SERVER_TOKEN"
MAX_BODY = 65536


def configured() -> bool:
    return bool(os.environ.get(URL_ENV, "").strip())


def _endpoint() -> tuple[str, str]:
    url = os.environ.get(URL_ENV, "").strip().rstrip("/")
    token = os.environ.get(CLIENT_TOKEN_ENV, "")
    parsed = urlsplit(url)
    try:
        local = ipaddress.ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        local = (parsed.hostname or "").lower() == "localhost"
    if parsed.scheme not in ({"http", "https"} if local else {"https"}) or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise ValueError("원격 Enamine 주소는 HTTPS 기본 URL을 사용하세요 (로컬호스트만 HTTP 허용)")
    if not token:
        raise ValueError(f"원격 Enamine 인증 정보 누락: {CLIENT_TOKEN_ENV}")
    return url, token


def request(path: str, payload: dict, *, timeout: int = 35) -> dict:
    url, token = _endpoint()
    try:
        response = requests.post(url + path, json=payload,
                                 headers={"Authorization": "Bearer " + token}, timeout=(5, timeout))
        if response.status_code != 200:
            raise ValueError(f"원격 Enamine HTTP {response.status_code} · 서버 접속/인증 및 설정 확인")
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("원격 Enamine 응답 형식 오류")
        return result
    except requests.RequestException as exc:
        raise ValueError(f"원격 Enamine 연결 실패: {exc}") from exc


def catalog(smiles: list[str]) -> dict[str, dict]:
    import service
    unique = list(dict.fromkeys(service.canonical(s) for s in smiles))
    if len(unique) > 128:
        raise ValueError("원격 Enamine 구조 조회는 요청당 128개 이내")
    records = request("/v1/catalog", {"smiles": unique})
    if set(records) != set(unique):
        raise ValueError("원격 Enamine 응답 구조 목록 불일치")
    for smiles, record in records.items():
        if not isinstance(record, dict) or record.get("smiles") != smiles or not isinstance(record.get("matches"), list):
            raise ValueError("원격 Enamine 카탈로그 응답 형식 오류")
    return records


def search(target: str, stock: str, time_limit: int, iteration_limit: int) -> list[dict]:
    import service
    routes = request("/v1/search", {"target": target, "stock": stock,
                                    "time_limit": time_limit, "iteration_limit": iteration_limit}, timeout=150)
    if not isinstance(routes.get("routes"), list):
        raise ValueError("원격 Enamine 경로 응답 형식 오류")
    for route in routes["routes"]:
        if not isinstance(route, dict) or route.get("stock") != stock or route.get("target") != target or not isinstance(route.get("steps"), list):
            raise ValueError("원격 Enamine 경로 응답 불일치")
        for step in route["steps"]:
            if (not isinstance(step, dict) or not isinstance(step.get("reactants"), list)
                    or not isinstance(step.get("product"), str)):
                raise ValueError("원격 Enamine 단계 응답 형식 오류")
            service.canonical(step["product"])
            for reactant in step["reactants"]:
                service.canonical(reactant)
    return routes["routes"]


def handler(token: str, search_lock):
    """Create an isolated handler for one server instance (also supports in-process tests)."""
    class Gateway(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass  # Do not log credentials or user-supplied target structures.

        def send_json(self, status: int, value: object):
            data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            supplied = self.headers.get("Authorization", "")
            if not hmac.compare_digest(supplied, "Bearer " + token):
                self.send_json(401, {"error": "unauthorized"})
                return
            if self.path not in ("/v1/catalog", "/v1/search"):
                self.send_json(404, {"error": "not_found"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    raise ValueError("요청 크기 제한 초과")
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError("JSON 객체 필요")
                import service
                if self.path == "/v1/catalog":
                    values = data.get("smiles")
                    if not isinstance(values, list) or len(values) > 128 or any(not isinstance(s, str) or len(s) > 2048 for s in values):
                        raise ValueError("SMILES 목록은 128개 이하")
                    unique = list(dict.fromkeys(service.canonical(s) for s in values))
                    if not service.DB.is_file():
                        self.send_json(503, {"error": "catalog_not_installed"})
                        return
                    with closing(sqlite3.connect(f"file:{service.DB.resolve().as_posix()}?mode=ro", uri=True)) as db:
                        result = {s: service.lookup(s, db) for s in unique}
                else:
                    target = data.get("target")
                    if not isinstance(target, str) or len(target) > 2048 or data.get("stock") != "Enamine (2026-09)":
                        raise ValueError("목표 SMILES 또는 재고 이름 오류")
                    time_limit, iterations = data.get("time_limit"), data.get("iteration_limit")
                    if (type(time_limit) is not int or type(iterations) is not int or
                            not 1 <= time_limit <= 120 or not 1 <= iterations <= 200):
                        raise ValueError("탐색 한도 범위 초과")
                    if not search_lock.acquire(blocking=False):
                        self.send_json(503, {"error": "search_busy"})
                        return
                    try:
                        result = {"routes": service._search_local(service.canonical(target), data["stock"],
                                                                  time_limit, iterations)}
                    finally:
                        search_lock.release()
                self.send_json(200, result)
            except (ValueError, TypeError, json.JSONDecodeError):
                self.send_json(400, {"error": "invalid_request"})
            except Exception:
                self.send_json(503, {"error": "backend_unavailable"})

    return Gateway


def main():
    import argparse
    from threading import Lock
    parser = argparse.ArgumentParser(description="Authenticated private Enamine search/catalog gateway")
    parser.add_argument("--host", default="127.0.0.1", help="Loopback by default; terminate TLS at a private reverse proxy")
    parser.add_argument("--port", type=int, default=9200)
    options = parser.parse_args()
    token = os.environ.get(SERVER_TOKEN_ENV, "")
    if len(token) < 24:
        parser.error(f"Set a random token (at least 24 characters) in {SERVER_TOKEN_ENV}")
    with ThreadingHTTPServer((options.host, options.port), handler(token, Lock())) as server:
        print(f"Enamine gateway listening on {options.host}:{options.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
