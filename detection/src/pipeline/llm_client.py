"""OpenAI Chat Completions 멀티모달 클라이언트 (Story 3-3, 2026-05-27 PIVOT).

SPIKE 3.0(`detection/scripts/spike_llm.py`)의 호출 패턴·schema·system prompt를 production
의미론으로 이식한다. 텍스트/이미지 분리 가능 인터페이스 + json_schema strict mode +
RateLimitError 1회 자동 재시도(Retry-After) + LLM_SEND_IMAGES 토글로 이미지 PII 차단 가능.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any

from detection.src.prompts.registry import get_domain_guide, get_type_guidance
from shared.interfaces.llm import ALLOWED_DETECTION_TYPES, LLMResponse, RateLimitError
from shared.structured_logger import get_logger

try:
    from openai import OpenAI
    from openai import APIConnectionError, APITimeoutError, OpenAIError
    from openai import RateLimitError as OpenAIRateLimitError
except ImportError as exc:  # pragma: no cover — requirements.txt에 openai 명시
    raise ImportError(
        "openai SDK 미설치. detection/requirements.txt 설치 필요."
    ) from exc

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_logger = get_logger(__name__)


# SPIKE 3.0 검증값 — 본 구현에서 그대로 사용.
SYSTEM_PROMPT = (
    "당신은 NC AI 게임 보안 분석가입니다. 주어진 커뮤니티 게시글의 불법성을 판단하세요.\n"
    "다음 type enum 중 하나로 분류:\n"
    "- 핵_치트: 게임 핵·치트 프로그램 자체 (탐지 회피, 무적, 자동 조준 등)\n"
    "- 사설서버: 비공식 게임 서버 운영·홍보\n"
    "- 불법프로그램_배포: 핵 외 매크로·봇·자동화 도구 배포\n"
    "- 계정_거래: 게임 계정 현금 거래\n"
    "- 매크로_판매: 매크로·자동사냥 프로그램 판매\n"
    "- 리세마라: 초기화·리세마라 계정 판매·대행\n"
    "- 현금화: 게임 머니/아이템 현금화·환전\n"
    "- 광고_도배: 무관 광고·스팸\n"
    "- 기타: 위 카테고리에 해당 안 함 (합법 게시글 포함)\n\n"
    "한국어 외 본문 + 이미지 속 외국어 텍스트는 translated_text_ko에 자연스러운 한국어 번역을 포함. 한국어 원문은 null.\n"
    "이미지 첨부가 있고 분류에 의미 있게 기여했으면 image_observed=true.\n"
    "reason_ko는 항상 한국어로 작성. 판단 근거를 1-2문장.\n\n"
    "confidence는 불법 위험도가 아니라 선택한 type 분류의 신뢰도입니다. 다음 기준으로 0.01 단위 숫자를 사용하세요:\n"
    "- 0.95-1.00: 본문에 명시적 판매/배포/거래 문구, 연락처, 가격, 다운로드 링크 등 직접 증거가 여러 개 있음\n"
    "- 0.85-0.94: 핵심 위반 표현이 명확하지만 연락처·가격·링크 같은 보조 증거가 부족함\n"
    "- 0.70-0.84: 위반 가능성이 높지만 맥락 의존적이거나 표현이 우회적임\n"
    "- 0.50-0.69: 애매한 회색 영역. type은 추정하되 reason_ko에 불확실성을 명시\n"
    "- 0.00-0.49: 해당 type 근거가 약함. 합법/무관 게시글이면 type=기타와 낮은 confidence를 사용\n"
    "0.90 또는 0.95를 기본값처럼 반복하지 말고, 근거 강도에 맞춰 다양한 값을 선택하세요."
)


def build_system_prompt(source_id: str | None = None) -> str:
    """조립식 system prompt: 베이스 + 유형 가이드(Stage 2-A) + 공용 도메인 가이드.

    2026-06-11 재정의(Story 3-7, FR12-C): 사이트→게임 라우팅을 제거했다. 게임 맥락은 분류기가
    본문에서 자가 추론하고, 게임 라벨에 종속되지 않는 은어·오탐 지식은 모든 게시글에 동일하게
    주입하는 단일 공용 `domain_guide.md`로 제공한다. `source_id`는 더 이상 프롬프트 선택에
    영향을 주지 않는다 — LLMInterface Protocol 시그니처 호환을 위해 인자만 수용한다.

    안정부(베이스 + 유형 가이드 + 도메인 가이드)는 모든 호출에 공통이므로 OpenAI 프롬프트 캐싱
    prefix가 최대화된다. 파일이 없으면 베이스(SYSTEM_PROMPT)만 반환 — 동작 중립 fallback.
    """
    parts = [SYSTEM_PROMPT]
    type_guidance = get_type_guidance()
    if type_guidance:
        parts.append(type_guidance)
    domain_guide = get_domain_guide()
    if domain_guide:
        parts.append(domain_guide)
    # Stage 2-B (few-shot 예시 주입) — 빈 슬롯. Story 3-5는 코퍼스 파일
    # (detection/src/prompts/examples/{game_key}.jsonl)과 포맷 계약(examples/README.md)만 준비한다.
    # 실제 예시 선택·삽입·토큰 예산 런타임 관리는 별도 미래 스토리 (deferred-work 참조).
    return "\n\n".join(parts)


CLASSIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": sorted(ALLOWED_DETECTION_TYPES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason_ko": {"type": "string"},
        "translated_text_ko": {"type": ["string", "null"]},
        "image_observed": {"type": "boolean"},
    },
    "required": ["type", "confidence", "reason_ko", "translated_text_ko", "image_observed"],
    "additionalProperties": False,
}


def _env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_image_url(image: str) -> str | None:
    """로컬 경로면 base64 인코딩, URL이면 그대로. 읽기 실패 시 None."""
    if image.startswith("data:") or image.startswith("http://") or image.startswith("https://"):
        return image
    if image.startswith("s3://"):
        # presigned URL 변환은 호출자 책임. 본 클라이언트는 그대로 패스하지 않음(OpenAI는 https만 인식).
        _logger.warning(
            "s3:// URL은 사전 presigned 필요 — 본 이미지 스킵",
            extra={"correlation_id": "", "service": _SERVICE_NAME, "image": image},
        )
        return None
    path = Path(image)
    if not path.is_absolute():
        # 프로젝트 루트 기준 상대 경로 허용. detection/src/pipeline → parents[3] == root.
        project_root = Path(__file__).resolve().parents[3]
        path = (project_root / image).resolve()
    if not path.exists():
        _logger.warning(
            "이미지 파일 없음 — 스킵",
            extra={"correlation_id": "", "service": _SERVICE_NAME, "image_path": str(path)},
        )
        return None
    suffix = path.suffix.lstrip(".").lower() or "jpeg"
    if suffix == "jpg":
        suffix = "jpeg"
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        _logger.warning(
            "이미지 읽기 실패 — 스킵: %s", exc,
            extra={"correlation_id": "", "service": _SERVICE_NAME, "image_path": str(path)},
        )
        return None
    return f"data:image/{suffix};base64,{encoded}"


class LLMClient:
    """OpenAI 멀티모달 LLM wrapper. LLMInterface Protocol 구현."""

    def __init__(self, client: OpenAI | None = None) -> None:
        self._model = os.environ.get("LLM_MODEL", "gpt-4o")
        self._timeout = float(os.environ.get("LLM_TIMEOUT_SEC", "30"))
        self._send_images = _env_bool("LLM_SEND_IMAGES", "false")
        self._split_text_image = _env_bool("LLM_SPLIT_TEXT_IMAGE", "false")
        if client is not None:
            self._client = client
        else:
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if not api_key or api_key.startswith("sk-REPLACE"):
                raise RuntimeError(
                    "OPENAI_API_KEY 환경변수가 placeholder입니다. infra/.env 갱신 필요."
                )
            self._client = OpenAI(api_key=api_key, timeout=self._timeout)

    @property
    def model(self) -> str:
        return self._model

    def classify_text_only(self, text: str, source_id: str | None = None) -> LLMResponse:
        """이미지 없이 텍스트만 분류 (fallback 진입점)."""
        return self._call(text, images_payload=[], source_id=source_id)

    def classify(
        self, text: str, images: list[str] | None = None, source_id: str | None = None
    ) -> LLMResponse:
        """기본 진입점. images가 비면 텍스트 only, 채워지면 멀티모달.

        source_id: CrawlEvent.source_id — 게임별 프롬프트 오버레이 선택에 사용 (Stage 1).
        """
        if not images or not self._send_images:
            return self._call(text, images_payload=[], source_id=source_id)

        # 이미지 URL/경로 → OpenAI content block으로 변환.
        image_blocks: list[dict[str, Any]] = []
        for img in images:
            url = _resolve_image_url(img)
            if url is None:
                continue
            image_blocks.append({"type": "image_url", "image_url": {"url": url}})

        if not image_blocks:
            # 모든 이미지가 스킵 — 텍스트 only fallback
            return self._call(text, images_payload=[], source_id=source_id)

        if self._split_text_image:
            # 텍스트 호출 + 이미지 호출 분리 후 merge.
            text_resp = self._call(text, images_payload=[], source_id=source_id)
            image_resp = self._call(text, images_payload=image_blocks, source_id=source_id)
            # 이미지 호출이 image_observed=true이면 우선 적용.
            use_image = image_resp.image_observed
            merged_type = image_resp.type if use_image else text_resp.type
            # confidence는 선택된 브랜치의 값만 사용 — 폐기된 호출의 confidence를 섞으면
            # 선택 근거와 무관한 confidence가 부풀려진다.
            merged_conf = image_resp.confidence if use_image else text_resp.confidence
            return LLMResponse(
                type=merged_type,
                confidence=merged_conf,
                reason_ko=image_resp.reason_ko if use_image else text_resp.reason_ko,
                translated_text_ko=text_resp.translated_text_ko or image_resp.translated_text_ko,
                image_observed=image_resp.image_observed,
                input_tokens=text_resp.input_tokens + image_resp.input_tokens,
                output_tokens=text_resp.output_tokens + image_resp.output_tokens,
                cost_usd=text_resp.cost_usd + image_resp.cost_usd,
            )

        return self._call(text, images_payload=image_blocks, source_id=source_id)

    def _call(
        self,
        text: str,
        *,
        images_payload: list[dict[str, Any]],
        source_id: str | None = None,
    ) -> LLMResponse:
        """단일 OpenAI Chat Completions 호출. 429는 Retry-After 1회 자동 재시도."""
        user_content: list[dict[str, Any]] = [
            {"type": "text", "text": f"게시글:\n{text}"}
        ]
        user_content.extend(images_payload)

        messages = [
            {"role": "system", "content": build_system_prompt(source_id)},
            {"role": "user", "content": user_content},
        ]
        resp = self._create_with_retry(
            messages,
            schema=CLASSIFICATION_SCHEMA,
            schema_name="tracker_classification",
            model=self._model,
        )
        return self._parse_response(resp)

    def _create_with_retry(
        self,
        messages: list[dict[str, Any]],
        *,
        schema: dict[str, Any],
        schema_name: str,
        model: str,
    ) -> Any:
        """OpenAI Chat Completions(json_schema strict) 호출 + 429 Retry-After 1회 재시도.

        분류(5필드)·트리아지(7필드) 등 모든 structured 호출이 공유하는 단일 OpenAI 진입점.
        timeout/connection 에러는 즉시 propagate(RetryHandler 책임), 그 외 OpenAI 에러는 RuntimeError.
        """
        for attempt in (1, 2):
            try:
                return self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": schema_name,
                            "strict": True,
                            "schema": schema,
                        },
                    },
                )
            except OpenAIRateLimitError as exc:
                retry_after = _retry_after_from(exc)
                if attempt == 1:
                    _logger.warning(
                        "OpenAI 429 — Retry-After %ds 후 자동 재시도",
                        retry_after,
                        extra={"correlation_id": "", "service": _SERVICE_NAME},
                    )
                    time.sleep(retry_after)
                    continue
                # 2회차도 429 — RateLimitError로 변환하여 호출자에 통보 (RetryHandler는 catch하지 않음).
                raise RateLimitError(retry_after) from exc
            except (APITimeoutError, APIConnectionError):
                # 1회 retry는 RetryHandler 책임 — 본 메서드는 즉시 propagate.
                raise
            except OpenAIError as exc:
                # 그 외 OpenAI 에러는 즉시 raise (non-retryable로 분류).
                raise RuntimeError(f"OpenAI 호출 실패: {type(exc).__name__}: {exc}") from exc

        # unreachable — 양 분기 모두 return/raise.
        raise RuntimeError("unreachable: _create_with_retry loop exited without return")

    def run_structured(
        self,
        *,
        system_prompt: str,
        user_text: str,
        schema: dict[str, Any],
        schema_name: str,
        model: str,
    ) -> tuple[dict[str, Any], int, int, float]:
        """에이전트용 범용 structured 호출 (텍스트 only). (parsed, in_tok, out_tok, cost) 반환.

        S1 트리아지 등 자체 스키마·모델을 쓰는 에이전트가 OpenAI 플러밍(호출·429 재시도·토큰/비용
        집계)을 재사용하기 위한 진입점 — 신규 OpenAI wrapper 작성 없이 본 클라이언트를 공유한다.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"게시글:\n{user_text}"},
        ]
        resp = self._create_with_retry(
            messages, schema=schema, schema_name=schema_name, model=model
        )
        content = resp.choices[0].message.content or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"OpenAI 응답 JSON 파싱 실패: {exc}") from exc

        from detection.src.rate_limit.cost_cap import estimate_cost_usd
        usage = getattr(resp, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        cost = estimate_cost_usd(model, input_tokens, output_tokens)
        return parsed, input_tokens, output_tokens, cost

    def _parse_response(self, resp: Any) -> LLMResponse:
        content = resp.choices[0].message.content or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"OpenAI 응답 JSON 파싱 실패: {exc}") from exc

        # response_format=json_schema strict가 enforce하지만 방어적으로 검증.
        type_value = parsed.get("type")
        if type_value not in ALLOWED_DETECTION_TYPES:
            raise ValueError(f"invalid type: {type_value}")
        confidence = parsed.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
            raise ValueError(f"confidence out of range: {confidence}")

        usage = getattr(resp, "usage", None)
        input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0

        from detection.src.rate_limit.cost_cap import estimate_cost_usd
        cost = estimate_cost_usd(self._model, input_tokens, output_tokens)

        return LLMResponse(
            type=str(type_value),
            confidence=float(confidence),
            reason_ko=str(parsed.get("reason_ko", "")),
            translated_text_ko=parsed.get("translated_text_ko"),
            image_observed=bool(parsed.get("image_observed", False)),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )


def _retry_after_from(exc: OpenAIRateLimitError) -> int:
    """OpenAI RateLimitError에서 Retry-After 추출. 기본 30s.

    OpenAI는 retry-after-ms(밀리초, 비표준)와 retry-after(초, RFC 7231) 두 헤더를 모두 보낼 수 있다.
    retry-after-ms를 우선 확인하고, 없으면 retry-after를 사용한다. 둘 다 없으면 30s 폴백.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return 30
    headers = getattr(response, "headers", None) or {}
    # 밀리초 헤더 우선 (OpenAI SDK 내부 동작과 동일한 우선순위).
    raw_ms = headers.get("retry-after-ms") or headers.get("Retry-After-Ms")
    if raw_ms is not None:
        try:
            return max(1, int(float(raw_ms) / 1000))
        except (TypeError, ValueError):
            pass
    raw = headers.get("Retry-After") or headers.get("retry-after")
    try:
        return int(float(raw)) if raw is not None else 30
    except (TypeError, ValueError):
        return 30
