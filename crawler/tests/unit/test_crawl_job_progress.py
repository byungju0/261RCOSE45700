from __future__ import annotations

import json
from unittest.mock import MagicMock

from crawler.src.scheduler.crawl_job_progress import (
    CrawlJobProgressStore,
    parse_trigger_command,
)


def test_parse_trigger_command_accepts_json_payload():
    command = parse_trigger_command(
        json.dumps({
            "jobId": "job-1234",
            "correlationId": "cid-1234",
            "requestedAt": "2026-05-28T00:00:00Z",
        })
    )

    assert command.job_id == "job-1234"
    assert command.correlation_id == "cid-1234"
    assert command.requested_at == "2026-05-28T00:00:00Z"


def test_parse_trigger_command_keeps_legacy_string_as_correlation_id():
    command = parse_trigger_command("legacy-cid")

    assert command.job_id == ""
    assert command.correlation_id == "legacy-cid"


def test_parse_trigger_command_keeps_unexpected_json_as_correlation_id():
    command = parse_trigger_command("[\"unexpected\"]")

    assert command.job_id == ""
    assert command.correlation_id == "[\"unexpected\"]"


def test_progress_store_marks_site_progress():
    redis = MagicMock()
    store = CrawlJobProgressStore(redis)

    store.mark_site_complete(
        "job-1234",
        site_id="bahamut",
        completed_sites=3,
        total_sites=8,
    )

    redis.hset.assert_called_once()
    key, = redis.hset.call_args.args
    mapping = redis.hset.call_args.kwargs["mapping"]
    assert key == "crawl:jobs:job-1234"
    assert mapping["status"] == "running"
    assert mapping["completedSites"] == "3"
    assert mapping["totalSites"] == "8"
    assert mapping["percent"] == "38"
    assert mapping["currentSite"] == "bahamut"
    redis.expire.assert_called_once_with("crawl:jobs:job-1234", 6 * 60 * 60)


def test_progress_store_stores_source_run_summary():
    redis = MagicMock()
    store = CrawlJobProgressStore(redis)

    store.store_source_run("52pojie", {
        "lastCheckedAt": "2026-06-13T11:53:14Z",
        "fetched": 5,
        "queued": 0,
        "validatorSkipped": 5,
        "failed": 0,
    })

    redis.set.assert_called_once()
    key, payload = redis.set.call_args.args
    data = json.loads(payload)
    assert key == "crawl:source_runs:52pojie"
    assert data["siteName"] == "52pojie"
    assert data["lastCheckedAt"] == "2026-06-13T11:53:14Z"
    assert data["fetched"] == 5
    assert data["queued"] == 0
    assert data["validatorSkipped"] == 5
    assert data["failed"] == 0
    assert redis.set.call_args.kwargs["ex"] == 7 * 6 * 60 * 60
