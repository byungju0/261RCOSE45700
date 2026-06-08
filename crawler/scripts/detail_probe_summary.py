"""Summarize detail_priority_probe JSONL output.

사용:
    cd /Users/jmac/Desktop/261RCOSE45700/crawler
    ../.venv/bin/python scripts/detail_probe_summary.py
    ../.venv/bin/python scripts/detail_probe_summary.py ../output/detail_probe_YYYYMMDD_HHMMSS.jsonl
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median


_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "output"


def _latest_probe_file(output_dir: Path = _DEFAULT_OUTPUT_DIR) -> Path:
    files = sorted(output_dir.glob("detail_probe_*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise FileNotFoundError(f"detail_probe_*.jsonl 파일을 찾지 못함: {output_dir}")
    return files[-1]


def _load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON decode 실패: {path}:{line_no}: {exc}") from exc
    return rows


def _kind(row: dict) -> str:
    if not row.get("ok"):
        return "fetch_error"
    return row.get("validator_kind") or "unknown"


def _has_signal(row: dict) -> bool:
    return bool(row.get("signals"))


def _rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{numerator / denominator * 100:.1f}%"


def _summarize_group(rows: list[dict], key_name: str) -> dict[str, Counter]:
    grouped: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        key = row.get(key_name) or "—"
        kind = _kind(row)
        grouped[key]["total"] += 1
        grouped[key][f"kind_{kind}"] += 1
        grouped[key]["real"] += int(kind == "real")
        grouped[key]["signal"] += int(_has_signal(row))
        grouped[key]["error"] += int(kind == "fetch_error")
    return grouped


def _print_group_table(title: str, grouped: dict[str, Counter]) -> None:
    print(title)
    print(
        f"{'key':<30} {'total':>5} {'real':>5} {'real%':>7} "
        f"{'signal':>6} {'sig%':>7} {'error':>5}"
    )
    for key, counts in sorted(grouped.items(), key=lambda item: (-item[1]["total"], item[0])):
        total = counts["total"]
        print(
            f"{key:<30} {total:>5} {counts['real']:>5} {_rate(counts['real'], total):>7} "
            f"{counts['signal']:>6} {_rate(counts['signal'], total):>7} {counts['error']:>5}"
        )
    print()


def _print_kind_breakdown(rows: list[dict]) -> None:
    counts = Counter(_kind(row) for row in rows)
    print("validator kinds")
    for kind, count in counts.most_common():
        print(f"{kind:<14} {count:>5}")
    print()


def _print_signal_breakdown(rows: list[dict]) -> None:
    doc_counts = Counter()
    hit_counts = Counter()
    for row in rows:
        for signal, hits in (row.get("signals") or {}).items():
            doc_counts[signal] += 1
            hit_counts[signal] += len(hits)
    print("signals")
    print(f"{'signal':<14} {'docs':>5} {'hits':>5}")
    for signal, count in doc_counts.most_common():
        print(f"{signal:<14} {count:>5} {hit_counts[signal]:>5}")
    print()


def _print_latency(rows: list[dict]) -> None:
    elapsed = [int(row.get("elapsed_ms") or 0) for row in rows if row.get("elapsed_ms") is not None]
    if not elapsed:
        return
    elapsed_sorted = sorted(elapsed)
    p95_idx = min(len(elapsed_sorted) - 1, int(len(elapsed_sorted) * 0.95))
    print("latency")
    print(
        f"count={len(elapsed)} "
        f"median_ms={int(median(elapsed))} "
        f"p95_ms={elapsed_sorted[p95_idx]} "
        f"max_ms={max(elapsed)}"
    )
    print()


def _classify_fetch_error(row: dict) -> str:
    error = (row.get("error") or "").lower()
    if "cloudflare js challenge" in error:
        return "cloudflare_js_challenge"
    if "http 403" in error and "html content" in error:
        return "cloudflare_or_waf_403_html"
    if "blocked by anti-bot" in error:
        return "anti_bot_blocked"
    if "timeout" in error:
        return "timeout"
    return "other"


def _print_fetch_error_breakdown(rows: list[dict]) -> None:
    fetch_errors = [row for row in rows if _kind(row) == "fetch_error"]
    if not fetch_errors:
        print("fetch error reasons")
        print("- none")
        print()
        return
    counts = Counter(_classify_fetch_error(row) for row in fetch_errors)
    by_site: dict[str, Counter] = defaultdict(Counter)
    for row in fetch_errors:
        by_site[row.get("site_id") or "—"][_classify_fetch_error(row)] += 1

    print("fetch error reasons")
    for reason, count in counts.most_common():
        print(f"{reason:<30} {count:>5}")
    print("fetch error reasons by site")
    for site, site_counts in sorted(by_site.items()):
        parts = " ".join(f"{k}={v}" for k, v in site_counts.most_common())
        print(f"{site:<30} {parts}")
    print()


def _print_problem_samples(rows: list[dict], *, limit: int = 12) -> None:
    print("non-real/error samples")
    shown = 0
    for row in rows:
        kind = _kind(row)
        if kind == "real":
            continue
        title = " ".join((row.get("title") or "").split())
        reason = row.get("validator_reason") or row.get("error") or ""
        print(
            f"- {kind} | {row.get('priority_bucket')} | {row.get('site_id')} | "
            f"{title[:80]} | {reason[:140]}"
        )
        shown += 1
        if shown >= limit:
            break
    if shown == 0:
        print("- none")
    print()


def _print_top_signal_samples(rows: list[dict], *, limit: int = 12) -> None:
    print("signal samples")
    signal_rows = [row for row in rows if _has_signal(row)]
    signal_rows.sort(key=lambda r: (-int(r.get("signal_count") or 0), r.get("site_id") or ""))
    for row in signal_rows[:limit]:
        title = " ".join((row.get("title") or "").split())
        signals = ",".join(sorted((row.get("signals") or {}).keys()))
        print(
            f"- {row.get('priority_bucket')} | {row.get('site_id')} | "
            f"signals={signals} | {title[:90]}"
        )
    if not signal_rows:
        print("- none")
    print()


def summarize(path: Path) -> None:
    rows = _load_rows(path)
    print(f"detail probe file: {path}")
    print(f"rows: {len(rows)}")
    print()
    _print_group_table("bucket summary", _summarize_group(rows, "priority_bucket"))
    _print_group_table("source summary", _summarize_group(rows, "site_id"))
    _print_group_table("sample reason summary", _summarize_group(rows, "sample_reason"))
    _print_kind_breakdown(rows)
    _print_signal_breakdown(rows)
    _print_latency(rows)
    _print_fetch_error_breakdown(rows)
    _print_problem_samples(rows)
    _print_top_signal_samples(rows)


def main(argv: list[str]) -> int:
    try:
        path = Path(argv[1]) if len(argv) > 1 else _latest_probe_file()
        summarize(path)
        return 0
    except Exception as exc:
        print(f"detail probe summary 실패: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
