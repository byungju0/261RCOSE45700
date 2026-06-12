"""S1 TriageAgent — 저비용 1차 분류 + 게임 맥락 자가 추론 + escalation 신호 (Story 3-7).

gpt-4o-mini로 전 게시글에 적용하는 트리아지. `LLMClient.run_structured`로 OpenAI 플러밍을
재사용한다(신규 wrapper 없음). 7필드 스키마를 strict json_schema로 강제하고, type enum·
confidence 범위를 방어적으로 재검증한다(`llm_classifier` 가드 패턴 동일).

게임 맥락(game_context)은 게시글 본문에서 자가 추론한다 — 사이트→게임 라우팅 제거(FR12-C).
공용 도메인 가이드(은어·오탐 규칙)는 system prompt에 항상 주입된다.
"""

from __future__ import annotations

import os

from detection.src.agents.contracts import TriageResult
from detection.src.pipeline.llm_client import build_system_prompt
from shared.interfaces.llm import ALLOWED_DETECTION_TYPES
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_logger = get_logger(__name__)

_DEFAULT_TRIAGE_MODEL = "gpt-4o-mini"

# 트리아지 추가 지침 — 베이스 분류 프롬프트(9-type/confidence 루브릭) 위에 얹는다.
_TRIAGE_INSTRUCTION = (
    "\n\n[트리아지 단계 지침]\n"
    "당신은 저비용 1차 분류기입니다. 위 기준으로 type/confidence/reason_ko/translated_text_ko를 산출하고,\n"
    "추가로 다음을 판단하세요:\n"
    "- game_context: 게시글이 어느 게임/생태계에 관한 것인지 본문에서 자가 추론해 짧게 적으세요 "
    "(예: '리니지M(TW)', '블레이드앤소울', '게임 무관 크랙 포럼', '불명'). 사이트 정보는 주어지지 않습니다.\n"
    "- needs_image: 첨부 이미지를 함께 봐야 정확히 판단할 수 있으면 true (핵 UI 스크린샷·배너 등 암시).\n"
    "- needs_link_trace: 본문의 외부 링크가 배포/거래 경로일 가능성이 있어 추적이 필요하면 true.\n"
    "명백히 무관한 정상 게시글(type=기타, 높은 확신)이면 needs_image/needs_link_trace는 false로 두세요."
)

TRIAGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": sorted(ALLOWED_DETECTION_TYPES)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "game_context": {"type": "string"},
        "reason_ko": {"type": "string"},
        "translated_text_ko": {"type": ["string", "null"]},
        "needs_image": {"type": "boolean"},
        "needs_link_trace": {"type": "boolean"},
    },
    "required": [
        "type", "confidence", "game_context", "reason_ko",
        "translated_text_ko", "needs_image", "needs_link_trace",
    ],
    "additionalProperties": False,
}


class TriageAgent:
    """S1 — gpt-4o-mini 트리아지. LLMClient의 OpenAI 플러밍 재사용."""

    def __init__(self, llm_client, model: str | None = None) -> None:
        self._llm = llm_client
        self._model = model or os.environ.get("TRIAGE_MODEL", _DEFAULT_TRIAGE_MODEL)

    @property
    def model(self) -> str:
        return self._model

    def run(self, text: str) -> TriageResult:
        """정규화 텍스트로 트리아지 수행. type/confidence 방어적 재검증."""
        system_prompt = build_system_prompt() + _TRIAGE_INSTRUCTION
        parsed, in_tok, out_tok, cost = self._llm.run_structured(
            system_prompt=system_prompt,
            user_text=text,
            schema=TRIAGE_SCHEMA,
            schema_name="tracker_triage",
            model=self._model,
        )

        type_value = parsed.get("type")
        if type_value not in ALLOWED_DETECTION_TYPES:
            raise ValueError(f"invalid triage type: {type_value}")
        confidence = parsed.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
            raise ValueError(f"triage confidence out of range: {confidence}")

        return TriageResult(
            type=str(type_value),
            confidence=float(confidence),
            game_context=str(parsed.get("game_context", "")),
            reason_ko=str(parsed.get("reason_ko", "")),
            translated_text_ko=parsed.get("translated_text_ko"),
            needs_image=bool(parsed.get("needs_image", False)),
            needs_link_trace=bool(parsed.get("needs_link_trace", False)),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
        )
