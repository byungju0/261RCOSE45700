"""LLMClassifier — 9-type enum 검증 + confidence 범위 + token bucket acquire (Story 3-3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from detection.src.mocks.llm_mock import LLMMock
from detection.src.pipeline.llm_classifier import LLMClassifier
from shared.interfaces.llm import LLMResponse


def test_classifies_clean_text() -> None:
    bucket = MagicMock()
    llm = LLMMock(mode="clean")
    classifier = LLMClassifier(llm, bucket, model_version="openai:gpt-4o:2024-08-06")

    result = classifier.classify("정상적인 게시글")

    assert result.type == "기타"
    assert result.confidence == 0.92
    assert classifier.model_version == "openai:gpt-4o:2024-08-06"
    bucket.acquire.assert_called_once()


def test_classifies_illegal_text() -> None:
    bucket = MagicMock()
    llm = LLMMock(mode="illegal")
    classifier = LLMClassifier(llm, bucket)

    result = classifier.classify("매크로 판매합니다")

    assert result.type == "매크로_판매"
    assert result.confidence == 0.95
    assert result.translated_text_ko is not None


def test_invalid_type_raises_value_error() -> None:
    bucket = MagicMock()
    llm = MagicMock()
    llm.classify.return_value = LLMResponse(
        type="invalid_type", confidence=0.9, reason_ko="...",
        translated_text_ko=None, image_observed=False,
    )
    classifier = LLMClassifier(llm, bucket)

    with pytest.raises(ValueError, match="invalid type: invalid_type"):
        classifier.classify("text")


def test_confidence_above_one_raises_value_error() -> None:
    bucket = MagicMock()
    llm = MagicMock()
    llm.classify.return_value = LLMResponse(
        type="기타", confidence=1.5, reason_ko="...",
        translated_text_ko=None, image_observed=False,
    )
    classifier = LLMClassifier(llm, bucket)

    with pytest.raises(ValueError, match="confidence out of range: 1.5"):
        classifier.classify("text")


def test_confidence_below_zero_raises_value_error() -> None:
    bucket = MagicMock()
    llm = MagicMock()
    llm.classify.return_value = LLMResponse(
        type="기타", confidence=-0.1, reason_ko="...",
        translated_text_ko=None, image_observed=False,
    )
    classifier = LLMClassifier(llm, bucket)

    with pytest.raises(ValueError, match="confidence out of range: -0.1"):
        classifier.classify("text")


def test_images_passed_through_to_llm() -> None:
    bucket = MagicMock()
    llm = MagicMock()
    llm.classify.return_value = LLMResponse(
        type="핵_치트", confidence=0.91, reason_ko="이미지에 핵 광고 확인",
        translated_text_ko=None, image_observed=True,
    )
    classifier = LLMClassifier(llm, bucket)

    classifier.classify("핵 팝니다", images=["s3://bucket/x.jpg"])

    llm.classify.assert_called_once_with("핵 팝니다", ["s3://bucket/x.jpg"], source_id=None)
