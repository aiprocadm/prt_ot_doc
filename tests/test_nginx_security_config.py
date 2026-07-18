from __future__ import annotations

from pathlib import Path


def test_nginx_api_cookie_and_rate_limit_hardening_present() -> None:
    config_path = Path("proxy/nginx.conf")
    content = config_path.read_text(encoding="utf-8")

    assert "limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;" in content
    assert "limit_req zone=api_limit burst=20 nodelay;" in content
    assert 'proxy_cookie_path / "/; SameSite=Lax; Secure";' in content
