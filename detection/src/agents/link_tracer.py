"""S2b LinkTracer — 위험 링크 1-hop 추적 + 증거 수집 (Story 3-7, FR12-B).

escalate ∧ 링크 존재 시 게시글당 최대 3개 링크를 1-hop fetch(httpx + html2text)하여 배포
사이트 여부를 증거로 수집한다. 파일 다운로드 금지, SSRF 가드 강제, 동일 URL Redis 캐시(7일),
메신저 초대링크는 fetch 없이 메타데이터만.

LLM 미사용 — 규칙 기반 지표 판정(다운로드/판매/연락처 패턴). 비용 $0 (agent_runs model=NULL).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from urllib.parse import urlsplit

import html2text
import httpx

from detection.src.agents.contracts import LinkEvidence
from detection.src.agents.link_fetch_guard import (
    MAX_RESPONSE_BYTES,
    is_disallowed_content_type,
    validate_url,
)
from shared.config.redis_config import REDIS_KEY_LINKTRACE_PREFIX
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_logger = get_logger(__name__)

MAX_LINKS_PER_POST = 3
_CACHE_TTL_SEC = 7 * 24 * 3600  # 7일
_MAX_REDIRECTS = 3

# 메신저 초대 도메인 — fetch 없이 kind=messenger (비공개 채널 유도 메타데이터만).
_MESSENGER_SUFFIXES = (
    "discord.gg",
    "discord.com",
    "t.me",
    "telegram.me",
    "open.kakao.com",
    "line.me",
    "qq.com",
)

# 배포/거래 정황 규칙 기반 지표 (페이지 제목·본문 발췌에서 매칭).
_DISTRIBUTION_KEYWORDS = (
    "download", "다운로드", "下载", "下載",
    "crack", "크랙", "破解", "外掛", "外挂", "辅助", "輔助",
    "hack", "cheat", "핵", "치트", "macro", "매크로", "bot", "봇",
)
_TRADE_KEYWORDS = (
    "가격", "원", "代儲", "代充", "面交", "蝦皮", "충전", "현금",
    "price", "paypal", "kakao", "line id", "微信", "wechat", "discord",
)


def _cache_key(url: str) -> str:
    return REDIS_KEY_LINKTRACE_PREFIX + hashlib.sha256(url.encode("utf-8")).hexdigest()


def _messenger_kind(url: str) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == s or host.endswith("." + s) for s in _MESSENGER_SUFFIXES)


def _detect_indicators(title: str, body: str) -> tuple[bool, list[str]]:
    """제목+본문에서 배포/거래 지표 추출. (is_distribution_site, indicators) 반환."""
    haystack = f"{title}\n{body}".lower()
    indicators: list[str] = []
    has_dist = any(kw.lower() in haystack for kw in _DISTRIBUTION_KEYWORDS)
    has_trade = any(kw.lower() in haystack for kw in _TRADE_KEYWORDS)
    if has_dist:
        indicators.append("배포 관련 표현 발견")
    if has_trade:
        indicators.append("거래/연락처 정황 발견")
    return (has_dist or has_trade), indicators


class LinkTracer:
    """S2b — 1-hop 링크 추적. Redis 캐시 + SSRF 가드 + 바이트 캡."""

    def __init__(self, redis_client, transport=None) -> None:
        self._redis = redis_client
        self._timeout = float(os.environ.get("LINK_TRACE_TIMEOUT_SEC", "5"))
        self._proxy = os.environ.get("LINK_TRACE_PROXY") or None
        # transport: 테스트에서 httpx.MockTransport 주입용 (운영은 None → 기본 transport).
        self._transport = transport

    def trace(self, links: list[str], correlation_id: str = "") -> list[LinkEvidence]:
        """게시글당 최대 MAX_LINKS_PER_POST개 링크 추적. 실패는 격리(예외 전파 금지)."""
        evidence: list[LinkEvidence] = []
        for url in links[:MAX_LINKS_PER_POST]:
            try:
                evidence.append(self._trace_one(url, correlation_id))
            except Exception as exc:  # noqa: BLE001 — 링크 1건 실패가 게시글 분류를 막으면 안 됨
                _logger.warning(
                    "링크 추적 예외 — error로 기록하고 계속: %s", exc,
                    extra={"correlation_id": correlation_id, "service": _SERVICE_NAME, "url": url},
                )
                evidence.append(LinkEvidence(url=url, kind="error", fetch_status=f"error:{type(exc).__name__}"))
        return evidence

    def _trace_one(self, url: str, correlation_id: str) -> LinkEvidence:
        # 1) 메신저 초대링크 — fetch 없이 메타데이터만.
        if _messenger_kind(url):
            return LinkEvidence(
                url=url, kind="messenger", fetch_status="skipped:messenger",
                indicators=["비공개 채널 유도(메신저 초대링크)"],
            )

        # 2) 캐시 조회.
        cached = self._cache_get(url)
        if cached is not None:
            return cached

        # 3) SSRF 가드.
        decision = validate_url(url)
        if not decision.allowed:
            ev = LinkEvidence(url=url, kind="blocked", fetch_status=f"blocked:{decision.reason}")
            self._cache_put(url, ev)
            return ev

        # 4) 1-hop fetch (수동 redirect 루프, 매 hop 재검증).
        ev = self._fetch(url, correlation_id)
        self._cache_put(url, ev)
        return ev

    def _fetch(self, url: str, correlation_id: str) -> LinkEvidence:
        client_kwargs = {"timeout": self._timeout, "follow_redirects": False}
        if self._transport is not None:
            client_kwargs["transport"] = self._transport
        elif self._proxy:
            client_kwargs["proxy"] = self._proxy

        current = url
        with httpx.Client(**client_kwargs) as client:
            for _ in range(_MAX_REDIRECTS + 1):
                # 2차 방어: 매 hop 직전 SSRF 가드 재검증 — DNS rebinding TOCTOU 완화.
                # validate_url()이 1차(trace_one)에서 해석한 IP와 여기서 재해석한 IP가
                # 다를 경우(rebinding 시도) 차단한다.
                decision = validate_url(current)
                if not decision.allowed:
                    return LinkEvidence(url=url, kind="blocked", fetch_status=f"blocked:{decision.reason}")

                with client.stream("GET", current) as resp:
                    # redirect — Location 재검증 후 다음 hop.
                    if resp.is_redirect:
                        location = resp.headers.get("location", "")
                        nxt = str(resp.url.join(location)) if location else ""
                        if not nxt or not validate_url(nxt).allowed:
                            return LinkEvidence(url=url, kind="blocked", fetch_status="blocked:redirect_target")
                        current = nxt
                        continue

                    # application/* — 바이트 폐기, 배포 직링크 증거만.
                    content_type = resp.headers.get("content-type")
                    if is_disallowed_content_type(content_type):
                        return LinkEvidence(
                            url=url, kind="file_direct_link",
                            fetch_status=f"abort:content_type:{content_type}",
                            is_distribution_site=True,
                            indicators=["배포 파일 직링크(application/* 응답)"],
                        )

                    # 에러 응답은 본문 소비 전에 종결 (바이트 낭비 방지).
                    if resp.status_code >= 400:
                        return LinkEvidence(url=url, kind="error", fetch_status=f"error:http_{resp.status_code}")

                    # 본문 streaming + 512KB 캡.
                    chunks: list[bytes] = []
                    total = 0
                    for chunk in resp.iter_bytes():
                        total += len(chunk)
                        if total > MAX_RESPONSE_BYTES:
                            break
                        chunks.append(chunk)
                    raw = b"".join(chunks)
                    return self._build_evidence(url, raw)

        return LinkEvidence(url=url, kind="error", fetch_status="error:too_many_redirects")

    def _build_evidence(self, url: str, raw: bytes) -> LinkEvidence:
        html = raw.decode("utf-8", errors="replace")
        title = _extract_title(html)
        converter = html2text.HTML2Text()
        converter.ignore_links = False
        converter.ignore_images = True
        body = converter.handle(html)[:4000]
        is_dist, indicators = _detect_indicators(title or "", body)
        return LinkEvidence(
            url=url, kind="web", fetch_status="ok",
            page_title=title, is_distribution_site=is_dist, indicators=indicators,
        )

    def _cache_get(self, url: str) -> LinkEvidence | None:
        try:
            raw = self._redis.get(_cache_key(url))
            if raw is None:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            data = json.loads(raw)
            # fetch_status는 원본 그대로 보존 (blocked:private_ip, error:http_404 등).
            # 캐시 히트 여부는 로그로 기록하고, 이유를 덮어쓰지 않는다.
            _logger.debug(
                "linktrace 캐시 hit — kind=%s status=%s",
                data.get("kind"), data.get("fetch_status"),
                extra={"correlation_id": "", "service": _SERVICE_NAME, "url": url},
            )
            return LinkEvidence(**data)
        except Exception as exc:  # noqa: BLE001 — 캐시 장애/손상 엔트리는 miss로 강등, fetch 계속
            _logger.warning(
                "linktrace 캐시 조회 실패 — miss로 처리: %s", exc,
                extra={"correlation_id": "", "service": _SERVICE_NAME, "url": url},
            )
            return None

    def _cache_put(self, url: str, ev: LinkEvidence) -> None:
        payload = json.dumps({
            "url": ev.url, "kind": ev.kind, "fetch_status": ev.fetch_status,
            "page_title": ev.page_title, "is_distribution_site": ev.is_distribution_site,
            "indicators": ev.indicators,
        })
        try:
            self._redis.set(_cache_key(url), payload, ex=_CACHE_TTL_SEC)
        except Exception as exc:  # noqa: BLE001 — 캐시 기록 실패가 수집된 evidence를 잃게 하면 안 됨
            _logger.warning(
                "linktrace 캐시 기록 실패 — 무시하고 계속: %s", exc,
                extra={"correlation_id": "", "service": _SERVICE_NAME, "url": url},
            )


def _extract_title(html: str) -> str | None:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip() or None
