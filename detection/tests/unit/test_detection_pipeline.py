"""DetectionPipeline 단위 테스트 (Story 3-7).

agentic/single 모드 분기, _classification_images 중복 제거, orchestrator=None 폴백 검증.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import detection.src.pipeline.detection_pipeline as pipeline_module
from detection.src.pipeline.detection_pipeline import DetectionPipeline, _classification_images
from shared.models.crawl_event import CrawlEvent


def _make_event(**overrides) -> CrawlEvent:
    base = dict(
        post_id="post-001",
        source_id="test_source",
        site_name="test_site",
        raw_text="게시글 내용",
        language="ko",
        detected_at="2026-06-12T00:00:00Z",
        correlation_id="cid-001",
        image_urls=[],
        s3_image_paths=[],
    )
    base.update(overrides)
    return CrawlEvent(**base)


def _fake_response():
    r = MagicMock()
    r.type = "기타"
    r.confidence = 0.80
    r.reason_ko = "정상"
    r.translated_text_ko = None
    r.image_observed = False
    r.input_tokens = 100
    r.output_tokens = 40
    r.cost_usd = 0.001
    return r


def _make_pipeline(mode: str = "single", orchestrator=None):
    classifier = MagicMock()
    classifier.classify.return_value = _fake_response()
    classifier.model_version = "gpt-4o:v1"
    classifier.model_name = "gpt-4o"

    tier_router = MagicMock()
    tier_router.route.return_value = "tier3"

    cost_cap = MagicMock()
    cost_cap.record.return_value = 0.001

    retry_handler = MagicMock()
    # execute_with_retry의 첫 인자(fn)를 그대로 호출 — 실제 분류 함수 실행.
    retry_handler.execute_with_retry.side_effect = lambda fn, **kw: fn()

    pipeline = DetectionPipeline(
        classifier=classifier,
        tier_router=tier_router,
        cost_cap=cost_cap,
        retry_handler=retry_handler,
        orchestrator=orchestrator,
        mode=mode,
    )
    return pipeline, classifier


def test_agentic_mode_without_orchestrator_falls_back_to_single() -> None:
    pipeline, classifier = _make_pipeline(mode="agentic", orchestrator=None)

    with patch.object(pipeline_module._logger, "warning") as mock_warn:
        with patch("detection.src.pipeline.detection_pipeline.CrawlEvent") as MockEvent:
            MockEvent.from_json.return_value = _make_event()
            pipeline.process("{}")

    assert classifier.classify.called
    # "orchestrator" 언급 경고가 1회 이상 발생해야 함.
    warned_messages = [str(c.args[0]) for c in mock_warn.call_args_list]
    assert any("orchestrator" in m for m in warned_messages)


def test_single_mode_calls_classifier() -> None:
    pipeline, classifier = _make_pipeline(mode="single")

    with patch("detection.src.pipeline.detection_pipeline.CrawlEvent") as MockEvent:
        MockEvent.from_json.return_value = _make_event()
        pipeline.process("{}")

    assert classifier.classify.called


def test_classification_images_deduplicates_preserves_order() -> None:
    event = _make_event(
        image_urls=["http://a.com/1.jpg", "http://b.com/2.jpg"],
        s3_image_paths=["http://a.com/1.jpg", "http://c.com/3.jpg"],
    )
    result = _classification_images(event)
    # 원본 URL 우선, S3 경로 후순위. http://a.com/1.jpg 는 원본에서 먼저 등장 → 1회만.
    assert result == ["http://a.com/1.jpg", "http://b.com/2.jpg", "http://c.com/3.jpg"]


def test_classification_images_excludes_empty_strings() -> None:
    event = _make_event(
        image_urls=["", "http://valid.com/img.jpg", ""],
        s3_image_paths=[],
    )
    assert _classification_images(event) == ["http://valid.com/img.jpg"]


def test_classification_images_empty_event() -> None:
    event = _make_event(image_urls=[], s3_image_paths=[])
    assert _classification_images(event) == []
