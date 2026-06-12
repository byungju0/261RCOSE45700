"""Stage 간 데이터 계약 — 멀티 에이전트 파이프라인 (Story 3-7).

오케스트레이터(`orchestrator.py`)가 각 에이전트 출력을 다음 단계로 넘길 때 쓰는 dataclass.
`AgentRunTrace`는 RDS `agent_runs` 1행(Flyway V10)에 1:1 대응한다.

LLM 산출 최종 verdict는 기존 `shared.interfaces.llm.LLMResponse`(5필드 + 토큰/비용)를
그대로 재사용한다 — single 모드와 출력 계약을 공유하기 위함(AC #13). 본 모듈은 그 verdict로
가기까지의 중간 산출물만 정의한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# agent_runs.stage 허용 값 — V10 주석과 일치. normalize/link_trace는 LLM 미사용(model=NULL).
AGENT_STAGES: frozenset[str] = frozenset({
    "normalize", "triage", "image", "link_trace", "synthesize",
})

# LinkEvidence.kind — 링크 1건의 처리 결과 분류.
LINK_KINDS: frozenset[str] = frozenset({
    "web",              # 정상 http(s) 페이지를 fetch해 분석
    "messenger",        # discord/telegram/kakao 등 초대링크 — fetch 없이 메타데이터만
    "file_direct_link",  # application/* 응답 — 바이트 폐기, "배포 파일 직링크" 증거만
    "blocked",          # SSRF 가드 차단 (사설 IP/비허용 스킴·포트 등)
    "error",            # 타임아웃/네트워크 오류/4xx·5xx — fetch_status에 상세
})


@dataclass
class NormalizedPost:
    """S0 normalizer 출력 — 정규화 텍스트 + 추출 링크."""

    text: str
    links: list[str] = field(default_factory=list)
    removed_char_count: int = 0  # 정규화로 줄어든 길이(근사 — 1:1 변형문자 치환은 미집계, 디버깅용)


@dataclass
class TriageResult:
    """S1 triage_agent(gpt-4o-mini) 출력 — 1차 분류 + 게임 자가 추론 + escalation 신호.

    `type`/`confidence`/`reason_ko`/`translated_text_ko`는 최종 verdict 5필드로 그대로 승격될 수
    있다(fast path / degrade). `game_context`는 자가 추론값(로깅·디버깅용 — detections에는 미저장).
    `needs_image`/`needs_link_trace`는 escalation 분기 신호.
    """

    type: str
    confidence: float
    game_context: str
    reason_ko: str
    translated_text_ko: str | None
    needs_image: bool
    needs_link_trace: bool
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class LinkEvidence:
    """S2b link_tracer 출력 — 링크 1건의 추적 증거."""

    url: str
    kind: str  # LINK_KINDS 중 하나
    fetch_status: str  # "ok" | "cached" | "skipped:messenger" | "blocked:<reason>" | "error:<detail>"
    page_title: str | None = None
    is_distribution_site: bool = False
    indicators: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.kind not in LINK_KINDS:
            raise ValueError(f"invalid LinkEvidence.kind: {self.kind!r} — 허용: {sorted(LINK_KINDS)}")


@dataclass
class AgentRunTrace:
    """agent_runs 1행 — 스테이지별 trace/비용 (RDS V10).

    `output`은 JSONB 컬럼으로 직렬화되는 임의 dict (스테이지 출력 전문 — LinkEvidence 목록 등).
    `model`이 None이면 LLM 미사용 스테이지(normalize / link_trace fetch).
    """

    stage: str
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int | None = None
    output: dict | None = None

    def __post_init__(self) -> None:
        if self.stage not in AGENT_STAGES:
            raise ValueError(f"invalid AgentRunTrace.stage: {self.stage!r} — 허용: {sorted(AGENT_STAGES)}")
