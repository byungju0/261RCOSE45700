"""Link Fetch Guard — SSRF/도메인 정책/바이트 캡 (Story 3-7, 보안 critical).

LinkTracer(S2b)가 외부 링크를 1-hop fetch하기 전·도중에 강제하는 안전 가드. 단위 테스트로
격리 검증한다(AC #7, ≥8건).

강제 항목:
  (a) 스킴 http/https + 포트 80/443만 허용
  (b) hostname DNS 해석 후 **모든** 해석 IP에 대해 사설/loopback/link-local/메타데이터 차단
  (c) redirect 매 hop Location 재검증 (LinkTracer가 hop마다 validate 호출)
  (d) 응답 바이트 상한 (LinkTracer가 streaming 중 enforce — 본 모듈은 상한값 제공)
  (e) content-type allowlist(text/html, text/plain, application/xhtml+xml)에 없으면 즉시 abort

`ipaddress.is_private`의 두 함정을 명시적으로 보완:
  - 100.64.0.0/10 (CGNAT, RFC 6598): is_private=False → 수동 차단
  - IPv4-mapped IPv6 (::ffff:127.0.0.1): is_loopback이 False → ipv4_mapped 언랩 후 재검사
"""

from __future__ import annotations

import ipaddress
import os
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

# 응답 바이트 상한 (기본 512KB). LinkTracer가 streaming 누적 카운터로 적용.
MAX_RESPONSE_BYTES: int = int(os.environ.get("LINK_TRACE_MAX_BYTES", str(512 * 1024)))

_ALLOWED_SCHEMES = {"http", "https"}
_DEFAULT_PORT = {"http": 80, "https": 443}

# CGNAT/공유 주소공간 (RFC 6598) — is_private=False라 수동 차단.
_CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")


@dataclass(frozen=True)
class GuardDecision:
    """가드 판정 결과. allowed=False면 reason에 차단 사유 (구조화 로그·증거용)."""

    allowed: bool
    reason: str = ""
    resolved_ips: tuple[str, ...] = ()


def _ip_is_blocked(ip: ipaddress._BaseAddress) -> bool:
    """사설/loopback/link-local/메타데이터/CGNAT/예약 주소 차단 판정."""
    # IPv4-mapped IPv6는 내부 IPv4로 언랩해 재검사 (is_loopback이 mapped에서 False인 stdlib 동작 보완).
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local      # 169.254.0.0/16 (AWS 메타데이터 169.254.169.254 포함) + fe80::/10
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NET:
        return True
    return False


def _resolve_all_ips(hostname: str) -> list[str]:
    """hostname의 모든 A/AAAA 레코드. 해석 실패 시 빈 리스트."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except OSError:  # gaierror 포함 — 그 외 소켓 계열 실패도 "해석 불가 → 차단"으로 동일 취급
        return []
    ips: list[str] = []
    seen: set[str] = set()
    for info in infos:
        addr = info[4][0]
        # IPv6 scope id(%eth0 등) 제거.
        addr = addr.split("%", 1)[0]
        if addr not in seen:
            seen.add(addr)
            ips.append(addr)
    return ips


def validate_url(url: str) -> GuardDecision:
    """fetch 전 URL 안전성 검증. 스킴·포트·호스트 IP를 모두 통과해야 allowed=True.

    DNS rebinding 완화: hostname을 여기서 해석해 모든 IP를 검사하고, LinkTracer는 동일 IP로
    접속(IP 핀)하도록 resolved_ips를 돌려준다. 핀 접속이 불가한 환경에서도 fetch 직전 본 함수를
    재호출해 재검증한다(2차 방어).
    """
    if not url or not isinstance(url, str):
        return GuardDecision(False, "empty url")

    try:
        parts = urlsplit(url)
    except ValueError:
        return GuardDecision(False, "invalid url")
    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return GuardDecision(False, f"scheme not allowed: {scheme or '(none)'}")

    hostname = parts.hostname
    if not hostname:
        return GuardDecision(False, "no hostname")

    # 포트: 스킴별 기본 포트(http→80, https→443)만 허용. 명시 포트가 스킴 기본과 달라도 차단.
    try:
        port = parts.port if parts.port is not None else _DEFAULT_PORT[scheme]
    except ValueError:
        return GuardDecision(False, "invalid port")
    if port != _DEFAULT_PORT[scheme]:
        return GuardDecision(False, f"port not allowed: {port}")

    # hostname이 이미 IP 리터럴이면 그대로 검사, 아니면 DNS 해석.
    try:
        literal = ipaddress.ip_address(hostname)
        candidate_ips = [str(literal)]
    except ValueError:
        candidate_ips = _resolve_all_ips(hostname)
        if not candidate_ips:
            return GuardDecision(False, f"dns resolution failed: {hostname}")

    for ip_str in candidate_ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return GuardDecision(False, f"unparseable ip: {ip_str}")
        if _ip_is_blocked(ip):
            return GuardDecision(
                False, f"blocked ip: {ip_str}", resolved_ips=tuple(candidate_ips)
            )

    return GuardDecision(True, "ok", resolved_ips=tuple(candidate_ips))


# fetch해서 text로 분석할 수 있는 MIME 타입 허용 목록 (allowlist).
# - text/html: 포럼·블로그·거래사이트 등 실제 배포/거래 콘텐츠의 거의 전부
# - text/plain: Pastebin·GitHub Gist raw URL 등 계정·설정 공유에 사용
# - application/xhtml+xml: 브라우저가 정상 웹 페이지로 렌더링하는 표준 MIME(RFC 2376)
# text/xml, application/xml은 제외 — html2text에서 안전하지만 실제 게임 핵/거래 사이트에서
# 거의 등장하지 않아 허용해도 이득이 없고 공격 면만 넓어진다.
_ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset({
    "text/html",
    "text/plain",
    "application/xhtml+xml",
})


def is_disallowed_content_type(content_type: str | None) -> bool:
    """분석 불가 바이너리/스크립트 타입이면 True (즉시 abort 대상).

    text/javascript, application/octet-stream, application/zip 등 실행·압축 파일은 차단.
    text/html, application/xhtml+xml 등 웹 페이지 타입은 허용.
    Content-Type 미제공(None)은 HTML 가능성 있으므로 허용.
    """
    if not content_type:
        return False
    main = content_type.split(";", 1)[0].strip().lower()
    # allowlist에 없는 타입은 모두 차단 (실행파일·압축·스크립트·바이너리 등 포함).
    return main not in _ALLOWED_CONTENT_TYPES
