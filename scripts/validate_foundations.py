"""Check API Server and Client App foundations against the approved container blueprints."""

from __future__ import annotations

import socket
import sys

import httpx

BASE = "http://localhost:8080"
PAGES = ("/sow", "/plan", "/wsr", "/retrospective")


def _port_closed(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=30)
    health = client.get("/health")
    print("health", health.status_code, health.text[:120])
    if health.status_code != 200:
        return 1
    body = health.json()
    if body.get("status") != "ok":
        print("health payload unexpected", body)
        return 1

    ready = client.get("/ready")
    print("ready", ready.status_code, ready.text[:160])
    if ready.status_code != 200:
        return 1

    for path in PAGES:
        page = client.get(path)
        print("page", path, page.status_code, page.headers.get("content-type"))
        if page.status_code != 200 or "html" not in (page.headers.get("content-type") or ""):
            print(page.text[:200])
            return 1

    if not _port_closed(8000):
        print("API port 8000 is published on the host; Compose should keep it internal")
        return 1
    print("API port 8000 is not published on the host")
    print("Foundation check via client origin: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
