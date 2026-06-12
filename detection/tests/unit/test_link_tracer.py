"""S2b LinkTracer 단위 테스트 (Story 3-7) — fetch/캐시/메신저/SSRF/실패 격리.

httpx.MockTransport + fakeredis로 외부 네트워크·실제 Redis 0건.
"""

from __future__ import annotations

import fakeredis
import httpx
import pytest

import detection.src.agents.link_fetch_guard as guard_mod
from detection.src.agents.link_tracer import MAX_LINKS_PER_POST, LinkTracer


@pytest.fixture
def redis_client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def allow_public_dns(monkeypatch: pytest.MonkeyPatch):
    """SSRF 가드의 DNS 해석을 공인 IP로 고정 (가드 통과시키기)."""
    monkeypatch.setattr(guard_mod, "_resolve_all_ips", lambda host: ["93.184.216.34"])


def _tracer(redis_client, handler, transport_calls=None) -> LinkTracer:
    def _wrapped(request: httpx.Request) -> httpx.Response:
        if transport_calls is not None:
            transport_calls.append(str(request.url))
        return handler(request)

    return LinkTracer(redis_client, transport=httpx.MockTransport(_wrapped))


def _html_handler(content: bytes, status: int = 200):
    """text/html 응답을 돌려주는 MockTransport 핸들러 팩토리."""
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=content, headers={"content-type": "text/html"})
    return _handler


def test_messenger_link_not_fetched(redis_client) -> None:
    calls: list[str] = []
    tracer = _tracer(redis_client, lambda r: httpx.Response(200), calls)
    evidence = tracer.trace(["https://discord.gg/abcd1234"])
    assert len(evidence) == 1
    assert evidence[0].kind == "messenger"
    assert evidence[0].fetch_status == "skipped:messenger"
    assert calls == []  # fetch 0회


def test_web_fetch_detects_distribution(redis_client, allow_public_dns) -> None:
    html = (
        b"<html><head><title>Free Hack Download</title></head>"
        b"<body>crack download \xea\xb0\x80\xea\xb2\xa9 5000</body></html>"
    )
    tracer = _tracer(redis_client, _html_handler(html))
    [ev] = tracer.trace(["https://evil.example/hack"])
    assert ev.kind == "web"
    assert ev.fetch_status == "ok"
    assert ev.page_title == "Free Hack Download"
    assert ev.is_distribution_site is True
    assert ev.indicators


def test_application_content_type_aborts_as_file_link(redis_client, allow_public_dns) -> None:
    def _binary(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"MZ\x90\x00binary",
            headers={"content-type": "application/octet-stream"},
        )

    tracer = _tracer(redis_client, _binary)
    [ev] = tracer.trace(["https://evil.example/hack.exe"])
    assert ev.kind == "file_direct_link"
    assert ev.is_distribution_site is True
    assert "abort:content_type" in ev.fetch_status


def test_ssrf_blocked_private_ip(redis_client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guard_mod, "_resolve_all_ips", lambda host: ["10.0.0.1"])
    tracer = _tracer(redis_client, lambda r: httpx.Response(200))
    [ev] = tracer.trace(["https://internal.example/x"])
    assert ev.kind == "blocked"
    assert "blocked:" in ev.fetch_status


def test_redirect_to_private_ip_blocked(redis_client, monkeypatch: pytest.MonkeyPatch) -> None:
    # 첫 hop 공인, redirect 대상이 사설 IP → 차단.
    def _dns(host: str) -> list[str]:
        return {"good.example": ["93.184.216.34"], "evil.internal": ["192.168.0.10"]}.get(host, [])

    monkeypatch.setattr(guard_mod, "_resolve_all_ips", _dns)
    tracer = _tracer(
        redis_client,
        lambda r: httpx.Response(302, headers={"location": "https://evil.internal/secret"}),
    )
    [ev] = tracer.trace(["https://good.example/start"])
    assert ev.kind == "blocked"
    assert ev.fetch_status == "blocked:redirect_target"


def test_cache_hit_skips_second_fetch(redis_client, allow_public_dns) -> None:
    calls: list[str] = []
    html = b"<html><title>Page</title><body>hello</body></html>"
    tracer = _tracer(redis_client, _html_handler(html), calls)

    first = tracer.trace(["https://good.example/p"])
    second = tracer.trace(["https://good.example/p"])

    assert len(calls) == 1  # 두 번째는 캐시 hit — fetch 0회
    assert first[0].fetch_status == "ok"
    # 캐시 히트 시 원본 fetch_status 보존 ("cached"로 덮어쓰지 않음 — blocked:... 등 증거 유실 방지).
    assert second[0].fetch_status == "ok"
    assert second[0].kind == first[0].kind


def test_http_error_isolated_as_error(redis_client, allow_public_dns) -> None:
    tracer = _tracer(redis_client, _html_handler(b"nope", status=404))
    [ev] = tracer.trace(["https://good.example/missing"])
    assert ev.kind == "error"
    assert "http_404" in ev.fetch_status


def test_fetch_exception_isolated(redis_client, allow_public_dns) -> None:
    def _boom(r: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    tracer = _tracer(redis_client, _boom)
    [ev] = tracer.trace(["https://good.example/down"])
    assert ev.kind == "error"
    assert ev.fetch_status.startswith("error:")


def test_caps_links_per_post(redis_client, allow_public_dns) -> None:
    calls: list[str] = []
    html = b"<html><title>p</title><body>x</body></html>"
    tracer = _tracer(redis_client, _html_handler(html), calls)
    urls = [f"https://good.example/{i}" for i in range(10)]
    evidence = tracer.trace(urls)
    assert len(evidence) == MAX_LINKS_PER_POST  # 최대 3개만
    assert len(calls) == MAX_LINKS_PER_POST


def test_too_many_redirects_returns_error(redis_client, allow_public_dns) -> None:
    # 매 hop 마다 302를 반환하면 _MAX_REDIRECTS+1 회 후 error:too_many_redirects.
    hop = {"n": 0}

    def _always_redirect(request: httpx.Request) -> httpx.Response:
        hop["n"] += 1
        return httpx.Response(302, headers={"location": f"https://good.example/hop{hop['n']}"})

    tracer = _tracer(redis_client, _always_redirect)
    [ev] = tracer.trace(["https://good.example/start"])
    assert ev.kind == "error"
    assert ev.fetch_status == "error:too_many_redirects"


def test_blocked_url_is_cached(redis_client, monkeypatch: pytest.MonkeyPatch) -> None:
    # SSRF 차단 결과가 캐시에 저장되어 두 번째 호출은 fetch 없이 캐시에서 반환.
    monkeypatch.setattr(guard_mod, "_resolve_all_ips", lambda host: ["10.0.0.1"])
    calls: list[str] = []
    tracer = _tracer(redis_client, lambda r: httpx.Response(200), calls)

    first = tracer.trace(["https://internal.example/x"])
    second = tracer.trace(["https://internal.example/x"])

    assert first[0].kind == "blocked"
    assert second[0].kind == "blocked"
    assert calls == []  # HTTP transport 호출 0회 — 첫 번째도 SSRF 가드에서 차단됨


def test_cache_get_exception_treated_as_miss(
    redis_client, allow_public_dns, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Redis.get 이 예외를 던지면 캐시 miss로 강등하고 fetch를 계속해야 한다.
    html = b"<html><title>p</title><body>content</body></html>"
    tracer = _tracer(redis_client, _html_handler(html))

    def _failing_get(key):
        raise Exception("redis connection lost")

    monkeypatch.setattr(redis_client, "get", _failing_get)

    [ev] = tracer.trace(["https://good.example/page"])
    assert ev.kind == "web"
    assert ev.fetch_status == "ok"


def test_proxy_env_used(redis_client, allow_public_dns, monkeypatch: pytest.MonkeyPatch) -> None:
    # transport가 주입되면 proxy보다 우선 — 여기선 proxy env가 설정돼도 transport 경로로 동작 검증.
    monkeypatch.setenv("LINK_TRACE_PROXY", "http://proxy.example:8080")
    html = b"<html><title>p</title><body>x</body></html>"
    tracer = _tracer(redis_client, lambda r: httpx.Response(200, content=html, headers={"content-type": "text/html"}))
    [ev] = tracer.trace(["https://good.example/p"])
    assert ev.kind == "web"
