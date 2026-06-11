"""S3 Synthesizer — 증거 통합 최종 판정 에이전트 (Story 3-8).

escalate 경로의 종결자: 게시글 본문 + S1 트리아지 + S2a 이미지 증거 + S2b 링크 증거를
통합하여 기존 5필드 스키마(`CLASSIFICATION_SCHEMA` — 계약 SSOT)로 최종 verdict를 산출한다.

증거 우선순위(AC #4)는 system prompt에 명시: 구체적 증거(fetch로 확인된 배포 페이지·핵 UI
스크린샷) > 본문 추정, 다중 type 신호 시 최상위 Tier type 채택(T1>T2>T3>T4).
`image_observed`는 LLM 자가보고 대신 S2a `contributes`로 결정론적 덮어쓰기(AC #3).
"""

from __future__ import annotations

import os

from detection.src.agents.contracts import (
    AgentResponseError,
    ImageEvidence,
    LinkEvidence,
    TriageResult,
)
from detection.src.pipeline.llm_client import CLASSIFICATION_SCHEMA, build_system_prompt
from detection.src.pipeline.tier_router import TIER_PRIORITY, TYPE_TO_TIER
from shared.interfaces.llm import ALLOWED_DETECTION_TYPES, LLMResponse
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_logger = get_logger(__name__)

_DEFAULT_SYNTHESIZER_MODEL = "gpt-4o"


def _tier_table() -> str:
    """type→Tier 매핑을 프롬프트용 문자열로 — tier_router SSOT에서 렌더링 (하드코딩 금지)."""
    by_tier: dict[str, list[str]] = {}
    for type_value, tier in TYPE_TO_TIER.items():
        by_tier.setdefault(tier, []).append(type_value)
    return " > ".join(
        f"{tier}({', '.join(sorted(by_tier[tier]))})"
        for tier in TIER_PRIORITY
        if tier in by_tier
    )


# 증거 통합 지침 — 베이스 분류 프롬프트(9-type/confidence 루브릭) 위에 얹는다.
_SYNTH_INSTRUCTION = (
    "\n\n[증거 통합 단계 지침]\n"
    "당신은 최종 판정자입니다. 게시글 본문, 1차 트리아지 결과, 이미지/링크 증거를 통합하여\n"
    "최종 type/confidence/reason_ko/translated_text_ko/image_observed를 산출하세요.\n"
    "- 증거 충돌 시 더 구체적 증거를 우선하세요: 실제 fetch로 확인된 배포 페이지"
    "(is_distribution_site=true), 핵 UI 스크린샷(contributes=true) 같은 직접 증거가 본문 표현 추정보다 우선합니다.\n"
    f"- 여러 type 신호가 동시에 있으면 최상위 Tier의 type을 채택하세요. Tier 순서: {_tier_table()}.\n"
    "- reason_ko에 채택한 증거를 1문장 포함하세요 (예: \"링크 추적 결과 다운로드 페이지 확인\").\n"
    "- translated_text_ko는 1차 트리아지의 번역을 기본 유지하되 명백한 오역만 수정하세요. 원문이 한국어면 null.\n"
    "- image_observed는 이미지 증거가 판단에 기여했으면 true."
)


def _serialize_evidence(
    text: str,
    triage: TriageResult,
    image_evidence: ImageEvidence | None,
    link_evidence: list[LinkEvidence],
) -> str:
    """본문 + 증거를 S3 입력 텍스트 블록으로 직렬화."""
    parts = [text]

    parts.append(
        "[1차 트리아지]\n"
        f"type={triage.type} confidence={triage.confidence:.2f} game_context={triage.game_context}\n"
        f"근거: {triage.reason_ko}"
        + (f"\n번역: {triage.translated_text_ko}" if triage.translated_text_ko else "")
    )

    if image_evidence is not None:
        indicators = ", ".join(image_evidence.illegal_indicators) or "(없음)"
        parts.append(
            "[이미지 증거 (S2a)]\n"
            f"contributes={image_evidence.contributes}\n"
            f"불법 지표: {indicators}\n"
            f"추출 텍스트: {image_evidence.extracted_text[:1000]}\n"
            f"요약: {image_evidence.summary_ko}"
        )

    if link_evidence:
        lines = ["[링크 증거 (S2b)]"]
        for ev in link_evidence:
            lines.append(
                f"- url={ev.url} kind={ev.kind} fetch_status={ev.fetch_status} "
                f"배포사이트={ev.is_distribution_site} 지표={ev.indicators} 제목={ev.page_title or '(없음)'}"
            )
            if ev.excerpt:
                lines.append(f"  발췌: {ev.excerpt[:300]}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


class Synthesizer:
    """S3 — gpt-4o 증거 통합. 출력 스키마는 CLASSIFICATION_SCHEMA 그대로(5필드 계약 SSOT)."""

    def __init__(self, llm_client, model: str | None = None) -> None:
        self._llm = llm_client
        self._model = (model or os.environ.get("SYNTHESIZER_MODEL", _DEFAULT_SYNTHESIZER_MODEL)).strip()

    @property
    def model(self) -> str:
        return self._model

    def run(
        self,
        text: str,
        triage: TriageResult,
        image_evidence: ImageEvidence | None,
        link_evidence: list[LinkEvidence],
        model: str | None = None,
    ) -> LLMResponse:
        """증거 통합 최종 verdict 산출. `model`로 예산 fallback 모델 1회 지정 가능 (Task 5).

        반환 LLMResponse의 토큰/비용은 **본 S3 호출분만** — 스테이지 합산은 orchestrator 책임.
        """
        system_prompt = build_system_prompt() + _SYNTH_INSTRUCTION
        user_text = _serialize_evidence(text, triage, image_evidence, link_evidence)

        parsed, in_tok, out_tok, cost = self._llm.run_structured(
            system_prompt=system_prompt,
            user_text=user_text,
            schema=CLASSIFICATION_SCHEMA,
            schema_name="tracker_synthesis",
            model=model or self._model,
        )

        # 호출은 성공(과금)했으므로 검증 실패에 usage를 실어 raise — 실패 trace에 실비용 기록.
        type_value = parsed.get("type")
        if type_value not in ALLOWED_DETECTION_TYPES:
            raise AgentResponseError(
                f"invalid synthesis type: {type_value}",
                input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost,
            )
        confidence = parsed.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
            raise AgentResponseError(
                f"synthesis confidence out of range: {confidence}",
                input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost,
            )

        # image_observed는 S2a contributes로 결정론적 덮어쓰기 (AC #3 — LLM 자가보고 무시).
        image_observed = bool(image_evidence.contributes) if image_evidence is not None else False

        return LLMResponse(
            type=str(type_value),
            confidence=float(confidence),
            reason_ko=str(parsed.get("reason_ko", "")),
            translated_text_ko=parsed.get("translated_text_ko") or triage.translated_text_ko,
            image_observed=image_observed,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
        )
