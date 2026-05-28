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
