"""Link Fetch Guard 단위 테스트 (Story 3-7, AC #7) — SSRF 차단 ≥8건.

DNS 해석은 monkeypatch로 격리 — 외부 네트워크 호출 0건.
"""

from __future__ import annotations

import pytest

import detection.src.agents.link_fetch_guard as guard_mod
from detection.src.agents.link_fetch_guard import (
    is_disallowed_content_type,
    validate_url,
)


@pytest.fixture
def fake_dns(monkeypatch: pytest.MonkeyPatch):
    """hostname → 지정 IP 목록으로 해석되도록 _resolve_all_ips 패치."""
    mapping: dict[str, list[str]] = {}

    def _fake(hostname: str) -> list[str]:
        return mapping.get(hostname, [])

    monkeypatch.setattr(guard_mod, "_resolve_all_ips", _fake)
    return mapping


def test_private_ip_10_block(fake_dns) -> None:
    fake_dns["internal.example"] = ["10.0.0.5"]
    decision = validate_url("http://internal.example/path")
    assert not decision.allowed
    assert "blocked ip" in decision.reason


def test_private_ip_192_168_block(fake_dns) -> None:
    fake_dns["router.example"] = ["192.168.1.1"]
    assert not validate_url("https://router.example").allowed


def test_loopback_ipv4_literal_block() -> None:
    assert not validate_url("http://127.0.0.1/admin").allowed


def test_loopback_ipv6_literal_block() -> None:
    assert not validate_url("http://[::1]/admin").allowed


def test_aws_metadata_endpoint_block() -> None:
    # 169.254.169.254 — link-local, 클라우드 메타데이터 탈취 벡터.
    assert not validate_url("http://169.254.169.254/latest/meta-data/").allowed


def test_cgnat_shared_address_block() -> None:
    # 100.64.0.0/10 — is_private=False 함정. 명시 차단돼야.
    assert not validate_url("http://100.64.1.1/x").allowed


def test_ipv4_mapped_ipv6_loopback_block() -> None:
    # ::ffff:127.0.0.1 — is_loopback이 mapped에서 False라 ipv4_mapped 언랩 후 차단.
    assert not validate_url("http://[::ffff:127.0.0.1]/x").allowed


def test_disallowed_scheme_block() -> None:
    assert not validate_url("ftp://example.com/file").allowed
    assert not validate_url("file:///etc/passwd").allowed
    assert not validate_url("gopher://example.com").allowed


def test_disallowed_port_block(fake_dns) -> None:
    fake_dns["api.example"] = ["93.184.216.34"]  # 공인 IP
    assert not validate_url("http://api.example:8080/internal").allowed


def test_public_ip_allowed(fake_dns) -> None:
    fake_dns["good.example"] = ["93.184.216.34"]  # 공인 IP (example.com)
    decision = validate_url("https://good.example/page")
    assert decision.allowed
    assert decision.resolved_ips == ("93.184.216.34",)


def test_mixed_resolution_blocks_if_any_private(fake_dns) -> None:
    # DNS rebinding 류: 공인 + 사설 IP가 섞이면 차단 (가장 보수적).
    fake_dns["evil.example"] = ["93.184.216.34", "10.1.2.3"]
    assert not validate_url("https://evil.example").allowed


def test_dns_resolution_failure_block(fake_dns) -> None:
    # 해석 실패(레코드 없음) → 차단.
    assert not validate_url("https://nonexistent.invalid").allowed


def test_content_type_application_disallowed() -> None:
    assert is_disallowed_content_type("application/octet-stream")
    assert is_disallowed_content_type("application/zip; charset=binary")
    assert is_disallowed_content_type("application/x-msdownload")


def test_content_type_text_allowed() -> None:
    assert not is_disallowed_content_type("text/html; charset=utf-8")
    assert not is_disallowed_content_type("text/plain")
    assert not is_disallowed_content_type(None)


def test_content_type_xhtml_xml_allowed() -> None:
    # application/xhtml+xml 은 허용 목록의 유일한 application/* 타입.
    assert not is_disallowed_content_type("application/xhtml+xml")
    assert not is_disallowed_content_type("application/xhtml+xml; charset=utf-8")


def test_empty_string_blocked() -> None:
    decision = validate_url("")
    assert not decision.allowed
    assert decision.reason == "empty url"


def test_non_string_blocked() -> None:
    decision = validate_url(None)  # type: ignore[arg-type]
    assert not decision.allowed
    assert decision.reason == "empty url"


def test_no_hostname_blocked() -> None:
    decision = validate_url("http:///path")
    assert not decision.allowed
    assert "hostname" in decision.reason


def test_bracketed_ipv4_returns_invalid_url() -> None:
    # Python 3.14+: urlsplit("http://[127.0.0.1]/") raises ValueError — guard가 GuardDecision(False) 반환.
    decision = validate_url("http://[127.0.0.1]/")
    assert not decision.allowed
    assert decision.reason == "invalid url"


def test_http_on_https_port_blocked(fake_dns) -> None:
    fake_dns["api.example"] = ["93.184.216.34"]
    decision = validate_url("http://api.example:443/")
    assert not decision.allowed
    assert "port not allowed" in decision.reason


def test_https_on_http_port_blocked(fake_dns) -> None:
    fake_dns["api.example"] = ["93.184.216.34"]
    decision = validate_url("https://api.example:80/")
    assert not decision.allowed
    assert "port not allowed" in decision.reason


def test_explicit_default_port_allowed(fake_dns) -> None:
    # http:80 과 https:443 은 스킴 기본 포트이므로 명시해도 허용.
    fake_dns["good.example"] = ["93.184.216.34"]
    assert validate_url("http://good.example:80/").allowed
    assert validate_url("https://good.example:443/").allowed
