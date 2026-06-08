"""Priority-scored candidates detail fetch probe.

운영 queue/DB 저장 없이 최신 dry-run JSONL 후보를 샘플링해 실제 상세 페이지를
열어본다. 파일 다운로드는 하지 않고 본문/검증 결과/위험 신호 요약만 JSONL로 남긴다.

사용:
    cd /Users/jmac/Desktop/261RCOSE45700/crawler
    CRAWL_DRY_RUN_OUTPUT_DIR=../output \
    CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
      ../.venv/bin/python scripts/detail_priority_probe.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PROJECT_ROOT.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from crawler.src.crawl4ai_crawler import Crawl4AICrawler  # noqa: E402
from crawler.src.preprocessor import content_validator  # noqa: E402
from crawler.src.scheduler.candidate_scoring import score_listing_candidate  # noqa: E402
from crawler.src.scheduler.crawl_scheduler import (  # noqa: E402
    CrawlOptions,
    detail_fetch_concurrency_for_site,
)
from crawler.src.sites.registry import SITES  # noqa: E402
from shared.correlation_id import generate  # noqa: E402
from shared.exceptions.base_exception import CrawlerException  # noqa: E402


_OUTPUT_DIR = Path(os.environ.get("CRAWL_DRY_RUN_OUTPUT_DIR", str(_REPO_ROOT / "output")))
_SESSION_TS = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
_PROBE_OUTPUT = _OUTPUT_DIR / f"detail_probe_{_SESSION_TS}.jsonl"

_MAX_P2 = int(os.environ.get("DETAIL_PROBE_MAX_P2", "80"))
_MAX_52POJIE_P3 = int(os.environ.get("DETAIL_PROBE_52POJIE_P3", "10"))
_MAX_MIXED_P3_PER_SOURCE = int(os.environ.get("DETAIL_PROBE_MIXED_P3", "5"))
_MAX_OTHER_P3_PER_SOURCE = int(os.environ.get("DETAIL_PROBE_OTHER_P3", "2"))
_PROBE_FAST_MODE = os.environ.get("DETAIL_PROBE_FAST_MODE", "").lower() in (
    "1",
    "true",
    "yes",
)
_DELAY_SECONDS = float(os.environ.get(
    "DETAIL_PROBE_DELAY_SECONDS",
    "2",
))
_PROBE_CONCURRENCY = max(
    1,
    int(os.environ.get(
        "DETAIL_PROBE_CONCURRENCY",
        os.environ.get("CRAWL_DETAIL_FETCH_CONCURRENCY", "3"),
    )),
)
_PROBE_BATCH_BY_SITE = os.environ.get(
    "DETAIL_PROBE_BATCH_BY_SITE",
    "false" if _PROBE_FAST_MODE else "true",
).lower() not in (
    "0",
    "false",
    "no",
)
_PROBE_SITE_GROUP_CONCURRENCY = max(
    1,
    int(os.environ.get("DETAIL_PROBE_SITE_GROUP_CONCURRENCY", "1")),
)
_PROBE_SENSITIVE_GROUPS_FIRST = os.environ.get(
    "DETAIL_PROBE_SENSITIVE_GROUPS_FIRST",
    "true",
).lower() not in ("0", "false", "no")
_PROBE_CLOUDFLARE_BACKOFF_SECONDS = max(
    0.0,
    float(os.environ.get(
        "DETAIL_PROBE_CLOUDFLARE_BACKOFF_SECONDS",
        os.environ.get("CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS", "0"),
    )),
)
_PROBE_CLOUDFLARE_BACKOFF_RETRIES = max(
    0,
    int(os.environ.get(
        "DETAIL_PROBE_CLOUDFLARE_BACKOFF_RETRIES",
        os.environ.get("CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES", "0"),
    )),
)
_PROBE_CLOUDFLARE_BACKOFF_SOURCES = {
    item.strip()
    for item in os.environ.get(
        "DETAIL_PROBE_CLOUDFLARE_BACKOFF_SOURCES",
        os.environ.get("CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SOURCES", "dcard,dcard_online"),
    ).split(",")
    if item.strip()
}
_PROBE_SOURCE_COOLDOWN_SECONDS = max(
    0.0,
    float(os.environ.get(
        "DETAIL_PROBE_SOURCE_COOLDOWN_SECONDS",
        os.environ.get("CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS", "0"),
    )),
)
_PROBE_SOURCE_COOLDOWN_SOURCES = {
    item.strip()
    for item in os.environ.get(
        "DETAIL_PROBE_SOURCE_COOLDOWN_SOURCES",
        os.environ.get("CRAWL_DETAIL_SOURCE_COOLDOWN_SOURCES", "dcard,dcard_online"),
    ).split(",")
    if item.strip()
}
_PROBE_CHALLENGE_COOLDOWN_SECONDS = max(
    0.0,
    float(os.environ.get(
        "DETAIL_PROBE_CHALLENGE_COOLDOWN_SECONDS",
        os.environ.get("CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS", "0"),
    )),
)
_DCARD_SESSION_REUSE = os.environ.get("CRAWL_DCARD_SESSION_REUSE", "").lower() in (
    "1",
    "true",
    "yes",
)
_DCARD_SESSION_ID_PREFIX = os.environ.get(
    "CRAWL_DCARD_SESSION_ID_PREFIX",
    "dcard-detail",
)
_DCARD_SESSION_SOURCES = {
    item.strip()
    for item in os.environ.get(
        "CRAWL_DCARD_SESSION_SOURCES",
        "dcard,dcard_online",
    ).split(",")
    if item.strip()
}
_PROBE_SOURCE_CONCURRENCY = os.environ.get("DETAIL_PROBE_SOURCE_CONCURRENCY")
_SENSITIVE_GROUP_SOURCES = {"dcard", "dcard_online", "52pojie"}
_MAX_BODY_CHARS = int(os.environ.get("DETAIL_PROBE_MAX_BODY_CHARS", "1200"))
_SELECTED_ONLY = os.environ.get("DETAIL_PROBE_SELECTED_ONLY", "").lower() in (
    "1",
    "true",
    "yes",
)

_MIXED_SOURCES = {"dcard", "dcard_online", "ptt_mobile_game"}

_SIGNAL_PATTERNS: dict[str, re.Pattern[str]] = {
    "high_risk": re.compile(
        r"핵|치트|매크로|자동사냥|우회|外掛|外挂|輔助|辅助|破解|私服|"
        r"\b(?:hack|cheat|macro|bot|bypass|injector|loader|undetected|hwid|aimbot|esp|wallhack)\b",
        re.IGNORECASE,
    ),
    "contact": re.compile(
        r"텔레그램|디스코드|오픈채팅|카톡|문의|판매|구매|聯絡|联系|出售|购买|"
        r"\b(?:telegram|discord|wechat|weixin|kakao|openchat)\b|qq(?:号|號|群|:|\s+群)",
        re.IGNORECASE,
    ),
    "download": re.compile(
        r"다운로드|다운|첨부|附件|下載|下载|"
        r"\b(?:download|mediafire|mega\.nz|drive\.google|dropbox|github\.com|githubusercontent|release)\b|"
        r"\.(?:exe|dll|apk|zip|rar|7z)\b",
        re.IGNORECASE,
    ),
    "credential": re.compile(
        r"계정|비밀번호|인증|로그인|密碼|密码|帳號|账号|登录|登入|"
        r"\b(?:account|password|login|credential|token|cookie|wallet)\b",
        re.IGNORECASE,
    ),
}


@dataclass(frozen=True)
class ProbeCandidate:
    site_id: str
    board_url: str
    url: str
    title: str
    selected: bool
    has_title_keywords: bool
    keyword_matched: bool
    score: int
    priority_bucket: str
    score_reasons: list[str]
    sample_reason: str


def _latest_dry_run_file(output_dir: Path) -> Path:
    files = sorted(output_dir.glob("dry_run_*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"dry_run_*.jsonl 파일을 찾지 못함: {output_dir}")
    return files[-1]


def _load_candidates(path: Path) -> list[ProbeCandidate]:
    rows: list[ProbeCandidate] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            raw = json.loads(line)
            site_id = raw["site_id"]
            scoring = score_listing_candidate(
                site_id=site_id,
                board_url=raw["board_url"],
                title=raw.get("title") or "",
                keyword_matched=bool(raw.get("keyword_matched")),
                has_title_keywords=bool(raw.get("has_title_keywords")),
            )
            rows.append(
                ProbeCandidate(
                    site_id=site_id,
                    board_url=raw["board_url"],
                    url=raw["url"],
                    title=raw.get("title") or "",
                    selected=bool(raw.get("selected")),
                    has_title_keywords=bool(raw.get("has_title_keywords")),
                    keyword_matched=bool(raw.get("keyword_matched")),
                    score=scoring.score,
                    priority_bucket=scoring.priority_bucket,
                    score_reasons=scoring.reasons,
                    sample_reason="",
                )
            )
    return rows


def _dedupe(candidates: list[ProbeCandidate]) -> list[ProbeCandidate]:
    seen: set[str] = set()
    unique: list[ProbeCandidate] = []
    for cand in candidates:
        if cand.url in seen:
            continue
        seen.add(cand.url)
        unique.append(cand)
    return unique


def _with_reason(cand: ProbeCandidate, reason: str) -> ProbeCandidate:
    return ProbeCandidate(
        site_id=cand.site_id,
        board_url=cand.board_url,
        url=cand.url,
        title=cand.title,
        selected=cand.selected,
        has_title_keywords=cand.has_title_keywords,
        keyword_matched=cand.keyword_matched,
        score=cand.score,
        priority_bucket=cand.priority_bucket,
        score_reasons=cand.score_reasons,
        sample_reason=reason,
    )


def _choose_probe_candidates(
    candidates: list[ProbeCandidate],
    *,
    selected_only: bool = _SELECTED_ONLY,
) -> list[ProbeCandidate]:
    unique = _dedupe(candidates)
    if selected_only:
        selected = [c for c in unique if c.selected]
        selected.sort(
            key=lambda c: (
                c.priority_bucket == "P3",
                -c.score,
                c.site_id,
                c.url,
            )
        )
        return [_with_reason(c, "selected_budget") for c in selected]

    p2 = sorted(
        (c for c in unique if c.priority_bucket == "P2"),
        key=lambda c: (-c.score, c.site_id, c.url),
    )
    chosen: list[ProbeCandidate] = [_with_reason(c, "P2_all") for c in p2[:_MAX_P2]]
    chosen_urls = {c.url for c in chosen}

    def take_p3(site_id: str, limit: int, reason: str) -> None:
        pool = [
            c for c in unique
            if c.priority_bucket == "P3" and c.site_id == site_id and c.url not in chosen_urls
        ]
        pool.sort(key=lambda c: (not c.selected, -c.score, c.url))
        for cand in pool[:limit]:
            chosen.append(_with_reason(cand, reason))
            chosen_urls.add(cand.url)

    take_p3("52pojie", _MAX_52POJIE_P3, "P3_52pojie_sample")
    for site_id in sorted(_MIXED_SOURCES):
        take_p3(site_id, _MAX_MIXED_P3_PER_SOURCE, "P3_mixed_sample")

    other_sources = sorted({
        c.site_id for c in unique
        if c.priority_bucket == "P3"
        and c.site_id not in _MIXED_SOURCES
        and c.site_id != "52pojie"
    })
    for site_id in other_sources:
        take_p3(site_id, _MAX_OTHER_P3_PER_SOURCE, "P3_other_source_sample")

    return chosen


def _extract_signals(text: str) -> dict[str, list[str]]:
    signals: dict[str, list[str]] = {}
    for name, pattern in _SIGNAL_PATTERNS.items():
        hits: list[str] = []
        for match in pattern.finditer(text):
            hit = match.group(0)
            if hit not in hits:
                hits.append(hit)
            if len(hits) >= 10:
                break
        if hits:
            signals[name] = hits
    return signals


def _body_preview(text: str) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:_MAX_BODY_CHARS]


def _parse_probe_source_concurrency(raw: str | None) -> dict[str, int]:
    if not raw:
        return {}
    overrides: dict[str, int] = {}
    for item in raw.split(","):
        if not item.strip() or "=" not in item:
            continue
        site_id, value = item.split("=", 1)
        try:
            overrides[site_id.strip()] = max(1, int(value.strip()))
        except ValueError:
            continue
    return overrides


_PROBE_SOURCE_CONCURRENCY_OVERRIDES = _parse_probe_source_concurrency(
    _PROBE_SOURCE_CONCURRENCY
)


def _probe_concurrency_for_site(site_id: str) -> int:
    base_concurrency = detail_fetch_concurrency_for_site(site_id)
    return _PROBE_SOURCE_CONCURRENCY_OVERRIDES.get(
        site_id,
        min(_PROBE_CONCURRENCY, base_concurrency),
    )


def _can_parallelize_site_group(site_id: str) -> bool:
    return site_id not in _SENSITIVE_GROUP_SOURCES and _probe_concurrency_for_site(site_id) > 1


def _is_cloudflare_challenge_error(exc: Exception) -> bool:
    return "cloudflare js challenge" in str(exc).lower()


def _row_has_cloudflare_challenge(row: dict) -> bool:
    return "cloudflare js challenge" in str(row.get("error", "")).lower()


def _source_cooldown_seconds(site_id: str) -> float:
    if site_id not in _PROBE_SOURCE_COOLDOWN_SOURCES:
        return 0.0
    return _PROBE_SOURCE_COOLDOWN_SECONDS


async def _sleep_after_probe_row(site_id: str, row: dict, *, has_next: bool) -> None:
    if not has_next:
        return
    delay = max(_DELAY_SECONDS, _source_cooldown_seconds(site_id))
    if _row_has_cloudflare_challenge(row):
        delay = max(delay, _PROBE_CHALLENGE_COOLDOWN_SECONDS)
    if delay <= 0:
        return
    print(f"[probe cooldown] {site_id} delay={delay:.1f}s")
    await asyncio.sleep(delay)


def _session_id_for_candidate(cand: ProbeCandidate) -> str | None:
    if not _DCARD_SESSION_REUSE or cand.site_id not in _DCARD_SESSION_SOURCES:
        return None
    normalized_site = cand.site_id.replace("_", "-")
    return f"{_DCARD_SESSION_ID_PREFIX}-{normalized_site}"


async def _probe_one(
    crawler: Crawl4AICrawler,
    cand: ProbeCandidate,
    *,
    session_id: str | None = None,
) -> dict:
    site = SITES[cand.site_id]
    options = CrawlOptions.from_site(site)
    started = datetime.now(UTC)
    attempt = 0
    try:
        while True:
            try:
                result = await crawler.fetch(
                    cand.url,
                    correlation_id=generate(),
                    download_images=False,
                    session_id=session_id,
                    **options.fetch_kwargs(),
                )
                break
            except Exception as exc:
                if (
                    cand.site_id in _PROBE_CLOUDFLARE_BACKOFF_SOURCES
                    and _is_cloudflare_challenge_error(exc)
                    and attempt < _PROBE_CLOUDFLARE_BACKOFF_RETRIES
                ):
                    attempt += 1
                    delay = _PROBE_CLOUDFLARE_BACKOFF_SECONDS * attempt
                    print(
                        "[probe backoff] "
                        f"{cand.site_id} retry={attempt}/{_PROBE_CLOUDFLARE_BACKOFF_RETRIES} "
                        f"delay={delay:.1f}s {cand.url}"
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                raise
        body = result.fit_markdown or result.raw_markdown or ""
        validation = content_validator.validate(cand.site_id, body, cand.url)
        signals = _extract_signals(body)
        elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "site_id": cand.site_id,
            "board_url": cand.board_url,
            "url": cand.url,
            "title": cand.title,
            "selected": cand.selected,
            "priority_bucket": cand.priority_bucket,
            "score": cand.score,
            "score_reasons": cand.score_reasons,
            "sample_reason": cand.sample_reason,
            "ok": True,
            "elapsed_ms": elapsed_ms,
            "body_len": len(body),
            "validator_kind": validation.kind,
            "is_real_user_post": validation.is_real_user_post,
            "validator_reason": validation.reason,
            "signals": signals,
            "signal_count": sum(len(v) for v in signals.values()),
            "crawl_stats": result.crawl_stats,
            "body_preview": _body_preview(body),
        }
    except Exception as exc:
        elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        crawl_stats = exc.crawl_stats if isinstance(exc, CrawlerException) else {}
        return {
            "timestamp": datetime.now(UTC).isoformat(),
            "site_id": cand.site_id,
            "board_url": cand.board_url,
            "url": cand.url,
            "title": cand.title,
            "selected": cand.selected,
            "priority_bucket": cand.priority_bucket,
            "score": cand.score,
            "score_reasons": cand.score_reasons,
            "sample_reason": cand.sample_reason,
            "ok": False,
            "elapsed_ms": elapsed_ms,
            "error": str(exc),
            "crawl_stats": crawl_stats,
        }


def _row_from_result(cand: ProbeCandidate, result, elapsed_ms: int) -> dict:
    body = result.fit_markdown or result.raw_markdown or ""
    validation = content_validator.validate(cand.site_id, body, cand.url)
    signals = _extract_signals(body)
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "site_id": cand.site_id,
        "board_url": cand.board_url,
        "url": cand.url,
        "title": cand.title,
        "selected": cand.selected,
        "priority_bucket": cand.priority_bucket,
        "score": cand.score,
        "score_reasons": cand.score_reasons,
        "sample_reason": cand.sample_reason,
        "ok": True,
        "elapsed_ms": elapsed_ms,
        "body_len": len(body),
        "validator_kind": validation.kind,
        "is_real_user_post": validation.is_real_user_post,
        "validator_reason": validation.reason,
        "signals": signals,
        "signal_count": sum(len(v) for v in signals.values()),
        "crawl_stats": result.crawl_stats,
        "body_preview": _body_preview(body),
    }


def _row_from_error(cand: ProbeCandidate, exc: Exception, elapsed_ms: int) -> dict:
    crawl_stats = exc.crawl_stats if isinstance(exc, CrawlerException) else {}
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "site_id": cand.site_id,
        "board_url": cand.board_url,
        "url": cand.url,
        "title": cand.title,
        "selected": cand.selected,
        "priority_bucket": cand.priority_bucket,
        "score": cand.score,
        "score_reasons": cand.score_reasons,
        "sample_reason": cand.sample_reason,
        "ok": False,
        "elapsed_ms": elapsed_ms,
        "error": str(exc),
        "crawl_stats": crawl_stats,
    }


async def _probe_site_batch(
    crawler: Crawl4AICrawler,
    site_id: str,
    candidates: list[ProbeCandidate],
) -> list[dict]:
    if not candidates:
        return []
    site_concurrency = _probe_concurrency_for_site(site_id)
    if site_concurrency <= 1:
        rows: list[dict] = []
        for idx, cand in enumerate(candidates):
            row = await _probe_one(
                crawler,
                cand,
                session_id=_session_id_for_candidate(cand),
            )
            rows.append(row)
            await _sleep_after_probe_row(
                site_id,
                row,
                has_next=idx < len(candidates) - 1,
            )
        return rows

    site = SITES[site_id]
    options = CrawlOptions.from_site(site)
    started = datetime.now(UTC)
    outcomes = await crawler.fetch_many(
        [c.url for c in candidates],
        correlation_ids=[generate() for _ in candidates],
        download_images=False,
        concurrency=site_concurrency,
        rate_limit_delay=(
            _DELAY_SECONDS,
            max(_DELAY_SECONDS, _DELAY_SECONDS * 2),
        ),
        **options.fetch_kwargs(),
    )
    by_url = {outcome.url: outcome for outcome in outcomes}
    rows: list[dict] = []
    for cand in candidates:
        elapsed_ms = int((datetime.now(UTC) - started).total_seconds() * 1000)
        outcome = by_url.get(cand.url)
        if outcome is None:
            rows.append(
                _row_from_error(
                    cand,
                    CrawlerException(
                        "크롤링 실패: batch outcome missing",
                        correlation_id=generate(),
                    ),
                    elapsed_ms,
                )
            )
        elif outcome.error is not None:
            rows.append(_row_from_error(cand, outcome.error, elapsed_ms))
        elif outcome.result is not None:
            rows.append(_row_from_result(cand, outcome.result, elapsed_ms))
    return rows


def _print_plan(candidates: list[ProbeCandidate], dry_run_path: Path) -> None:
    by_reason = Counter(c.sample_reason for c in candidates)
    by_site = Counter(c.site_id for c in candidates)
    print(f"dry-run input: {dry_run_path}")
    print(f"detail probe output: {_PROBE_OUTPUT}")
    print("probe plan:", " ".join(f"{k}={v}" for k, v in sorted(by_reason.items())))
    print("probe by site:", " ".join(f"{k}={v}" for k, v in sorted(by_site.items())))
    print(
        f"probe concurrency: {_PROBE_CONCURRENCY} fast_mode={_PROBE_FAST_MODE} "
        f"delay={_DELAY_SECONDS:.2f}s batch_by_site={_PROBE_BATCH_BY_SITE} "
        f"group_concurrency={_PROBE_SITE_GROUP_CONCURRENCY} "
        f"sensitive_first={_PROBE_SENSITIVE_GROUPS_FIRST} "
        f"source_cooldown={_PROBE_SOURCE_COOLDOWN_SECONDS:.1f}s "
        f"challenge_cooldown={_PROBE_CHALLENGE_COOLDOWN_SECONDS:.1f}s"
    )


def _print_summary(records: list[dict]) -> None:
    by_bucket = defaultdict(Counter)
    by_site = defaultdict(Counter)
    for row in records:
        bucket = row.get("priority_bucket", "P?")
        site = row["site_id"]
        kind = row.get("validator_kind") if row.get("ok") else "fetch_error"
        has_signal = bool(row.get("signals"))
        by_bucket[bucket]["total"] += 1
        by_bucket[bucket][kind] += 1
        by_bucket[bucket]["signal"] += int(has_signal)
        by_site[site]["total"] += 1
        by_site[site][kind] += 1
        by_site[site]["signal"] += int(has_signal)

    print("bucket summary:")
    print(f"{'bucket':<8} {'total':>5} {'real':>5} {'signal':>6} {'error':>5}")
    for bucket, counts in sorted(by_bucket.items()):
        print(
            f"{bucket:<8} {counts['total']:>5} {counts['real']:>5} "
            f"{counts['signal']:>6} {counts['fetch_error']:>5}"
        )
    print("site summary:")
    print(f"{'site':<28} {'total':>5} {'real':>5} {'signal':>6} {'error':>5}")
    for site, counts in sorted(by_site.items(), key=lambda item: (-item[1]["total"], item[0])):
        print(
            f"{site:<28} {counts['total']:>5} {counts['real']:>5} "
            f"{counts['signal']:>6} {counts['fetch_error']:>5}"
        )


async def main() -> None:
    dry_run_path = Path(os.environ.get("DETAIL_PROBE_INPUT", "")) if os.environ.get("DETAIL_PROBE_INPUT") else _latest_dry_run_file(_OUTPUT_DIR)
    candidates = _choose_probe_candidates(_load_candidates(dry_run_path))
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _print_plan(candidates, dry_run_path)

    crawler = Crawl4AICrawler(headless=True, output_dir="output/_tmp")
    records: list[dict] = []
    with _PROBE_OUTPUT.open("w", encoding="utf-8") as f:
        if _PROBE_BATCH_BY_SITE and _PROBE_CONCURRENCY > 1 and len(candidates) > 1:
            candidates_by_site: dict[str, list[ProbeCandidate]] = defaultdict(list)
            for cand in candidates:
                candidates_by_site[cand.site_id].append(cand)

            async def run_site_batch(site_id: str, batch: list[ProbeCandidate]) -> list[dict]:
                print(
                    f"[site batch] {site_id} count={len(batch)} "
                    f"concurrency={_probe_concurrency_for_site(site_id)}"
                )
                return await _probe_site_batch(crawler, site_id, batch)

            async def write_rows(site_id: str, rows: list[dict]) -> None:
                for row in rows:
                    idx = len(records) + 1
                    print(
                        f"[{idx}/{len(candidates)}] "
                        f"{row.get('priority_bucket')} {site_id} {row.get('url')}"
                    )
                    records.append(row)
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()

            stable_groups = [
                (site_id, batch)
                for site_id, batch in sorted(candidates_by_site.items())
                if _can_parallelize_site_group(site_id)
            ]
            sensitive_groups = [
                (site_id, batch)
                for site_id, batch in sorted(candidates_by_site.items())
                if not _can_parallelize_site_group(site_id)
            ]

            if _PROBE_SENSITIVE_GROUPS_FIRST:
                for site_id, batch in sensitive_groups:
                    await write_rows(site_id, await run_site_batch(site_id, batch))

            if _PROBE_SITE_GROUP_CONCURRENCY > 1 and len(stable_groups) > 1:
                group_semaphore = asyncio.Semaphore(_PROBE_SITE_GROUP_CONCURRENCY)

                async def run_stable_group(site_id: str, batch: list[ProbeCandidate]):
                    async with group_semaphore:
                        return site_id, await run_site_batch(site_id, batch)

                for coro in asyncio.as_completed([
                    run_stable_group(site_id, batch)
                    for site_id, batch in stable_groups
                ]):
                    site_id, rows = await coro
                    await write_rows(site_id, rows)
            else:
                for site_id, batch in stable_groups:
                    await write_rows(site_id, await run_site_batch(site_id, batch))

            if not _PROBE_SENSITIVE_GROUPS_FIRST:
                for site_id, batch in sensitive_groups:
                    await write_rows(site_id, await run_site_batch(site_id, batch))
        elif _PROBE_CONCURRENCY == 1 or len(candidates) <= 1:
            for idx, cand in enumerate(candidates, start=1):
                print(f"[{idx}/{len(candidates)}] {cand.priority_bucket} {cand.site_id} {cand.url}")
                row = await _probe_one(crawler, cand)
                records.append(row)
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                f.flush()
                await _sleep_after_probe_row(cand.site_id, row, has_next=idx < len(candidates))
        else:
            queue: asyncio.Queue[tuple[int, ProbeCandidate]] = asyncio.Queue()
            for idx, cand in enumerate(candidates, start=1):
                queue.put_nowait((idx, cand))

            write_lock = asyncio.Lock()

            async def worker(worker_id: int) -> None:
                while True:
                    try:
                        idx, cand = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    try:
                        print(
                            f"[{idx}/{len(candidates)} w{worker_id}] "
                            f"{cand.priority_bucket} {cand.site_id} {cand.url}"
                        )
                        row = await _probe_one(crawler, cand)
                        async with write_lock:
                            records.append(row)
                            f.write(json.dumps(row, ensure_ascii=False) + "\n")
                            f.flush()
                    finally:
                        queue.task_done()
                    if _DELAY_SECONDS > 0:
                        await asyncio.sleep(_DELAY_SECONDS)

            worker_count = min(_PROBE_CONCURRENCY, len(candidates))
            await asyncio.gather(*(worker(i + 1) for i in range(worker_count)))

    _print_summary(records)


if __name__ == "__main__":
    asyncio.run(main())
