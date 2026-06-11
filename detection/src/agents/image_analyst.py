"""S2a ImageAnalyst — 첨부 이미지 판독 에이전트 (Story 3-8, FR16-NEW-1).

escalate ∧ 이미지 존재 시 gpt-4o로 핵 UI/사설서버 배너/워터마크/연락처를 판독하여
`ImageEvidence`를 산출한다. `LLMClient.run_structured(image_blocks=...)`로 OpenAI 플러밍을
재사용한다(신규 wrapper 없음 — TriageAgent 패턴).

PII 가드: `LLM_SEND_IMAGES`(기본 false) 토글을 single 모드와 동일하게 적용 — false면
`enabled=False`이고 `run()`은 LLM 호출 없이 None을 반환한다 (PRD 이미지 PII 법무 미확정 대응).
도메인 가이드는 주입하지 않는다 — 이미지 판독에 게임 은어 사전은 불요(토큰 절약),
판독 결과의 해석은 S3 Synthesizer 몫.
"""

from __future__ import annotations

import os

from detection.src.agents.contracts import AgentResponseError, ImageEvidence
from detection.src.pipeline.llm_client import build_image_blocks
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_logger = get_logger(__name__)

_DEFAULT_IMAGE_ANALYST_MODEL = "gpt-4o"


def _env_bool(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


_IMAGE_INSTRUCTION = (
    "당신은 NC AI 게임 보안 분석가입니다. 게시글에 첨부된 이미지를 판독하여 불법 정황 증거를 수집하세요.\n"
    "다음 항목을 중점적으로 확인합니다:\n"
    "- 핵/치트 UI: ESP·aimbot 오버레이, 치트 메뉴, 인젝터 화면 등\n"
    "- 사설서버 배너·홍보 이미지, 서버 접속 화면\n"
    "- 워터마크·로고: 핵 판매 사이트/제작팀 워터마크\n"
    "- 연락처: 디스코드/텔레그램/카카오/QQ ID, QR 코드, 가격표\n\n"
    "출력 필드:\n"
    "- illegal_indicators: 발견한 불법 정황을 짧은 한국어 구절 목록으로 (없으면 빈 배열)\n"
    "- extracted_text: 이미지 속 텍스트를 그대로 추출 (언어 불문, 없으면 빈 문자열)\n"
    "- summary_ko: 이미지가 보여주는 내용을 1-2문장 한국어로 요약\n"
    "- contributes: 이 이미지가 게시글의 불법성 판단에 의미 있게 기여하면 true, "
    "무관한 이미지(풍경·밈·일반 스크린샷)면 false"
)

IMAGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "illegal_indicators": {"type": "array", "items": {"type": "string"}},
        "extracted_text": {"type": "string"},
        "summary_ko": {"type": "string"},
        "contributes": {"type": "boolean"},
    },
    "required": ["illegal_indicators", "extracted_text", "summary_ko", "contributes"],
    "additionalProperties": False,
}


class ImageAnalyst:
    """S2a — gpt-4o 이미지 판독. LLMClient의 OpenAI 플러밍 재사용."""

    def __init__(self, llm_client, model: str | None = None) -> None:
        self._llm = llm_client
        self._model = (model or os.environ.get("IMAGE_ANALYST_MODEL", _DEFAULT_IMAGE_ANALYST_MODEL)).strip()
        self._enabled = _env_bool("LLM_SEND_IMAGES", "false")

    @property
    def model(self) -> str:
        return self._model

    @property
    def enabled(self) -> bool:
        """PII 가드 — LLM_SEND_IMAGES=false면 S2a 전체 비활성 (orchestrator가 skip trace 기록)."""
        return self._enabled

    def run(self, text: str, images: list[str]) -> ImageEvidence | None:
        """이미지 판독 수행. 비활성/이미지 없음/전부 resolve 실패 시 None (LLM 호출 0).

        본문 텍스트를 함께 제공해 이미지-본문 맥락 연결을 돕는다.
        """
        if not self._enabled or not images:
            return None

        image_blocks = build_image_blocks(images)
        if not image_blocks:
            _logger.warning(
                "S2a — resolve 가능한 이미지 없음(스킵): %d개 입력",
                len(images),
                extra={"correlation_id": "", "service": _SERVICE_NAME},
            )
            return None

        parsed, in_tok, out_tok, cost = self._llm.run_structured(
            system_prompt=_IMAGE_INSTRUCTION,
            user_text=text,
            schema=IMAGE_SCHEMA,
            schema_name="tracker_image_analysis",
            model=self._model,
            image_blocks=image_blocks,
        )

        indicators = parsed.get("illegal_indicators")
        if not isinstance(indicators, list):
            # 호출은 성공(과금)했으므로 usage를 실어 raise — orchestrator가 실패 trace에 기록.
            raise AgentResponseError(
                f"invalid image illegal_indicators: {indicators!r}",
                input_tokens=in_tok, output_tokens=out_tok, cost_usd=cost,
            )

        return ImageEvidence(
            illegal_indicators=[str(i) for i in indicators],
            extracted_text=str(parsed.get("extracted_text", "")),
            summary_ko=str(parsed.get("summary_ko", "")),
            contributes=bool(parsed.get("contributes", False)),
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
        )
