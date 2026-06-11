"""데모 리허설 — "명확 불법 10건 실시간 탐지" 순차 시뮬레이션 (Story 3-9 Task 6).

10건의 게시글을 agentic 파이프라인에 순차 투입해 실시간 탐지를 재현하고, 건별
path/type/tier/cost/latency + 총계(평균 비용·escalation율)를 출력한다.

모드:
  - `DEMO_OFFLINE=true` (기본): LLMMock 에이전트 모드 — 실 OpenAI·실 네트워크·실 PG 0.
    키워드 라우팅으로 10건이 각각 결정론적 verdict를 낸다(리허설 재현성). 데모 당일 인터넷
    없이도 흐름·UI를 시연할 수 있다.
  - `DEMO_OFFLINE=false`: 실 OpenAI 호출(smoke_agent_pipeline와 동일 wiring). 비용 발생.

single 모드 즉시 회귀(데모 당일 정확도 회귀 시 폴백):
    DETECTION_MODE=single  ← 1줄 토글(detection_pipeline.py:63 use_agentic 분기)
  회귀 후 단건 확인: `python detection/scripts/smoke_integration_db.py` (single 경로).
  자세한 절차는 docs/ab-comparison-3-9.md "데모 모드 결정 + single 회귀" 절 참조.

단건 agentic smoke(smoke_agent_pipeline.py)와 중복 회피 — 본 스크립트는 다건 시퀀스 + 집계 전용.

Usage:
    python detection/scripts/demo_rehearsal.py                 # 오프라인(기본)
    DEMO_OFFLINE=false python detection/scripts/demo_rehearsal.py   # 실 OpenAI
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
import zlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import fakeredis  # noqa: E402

from detection.src.agents.image_analyst import ImageAnalyst  # noqa: E402
from detection.src.agents.link_tracer import LinkTracer  # noqa: E402
from detection.src.agents.orchestrator import AgentOrchestrator  # noqa: E402
from detection.src.agents.synthesizer import Synthesizer  # noqa: E402
from detection.src.agents.triage_agent import TriageAgent  # noqa: E402
from detection.src.mocks.llm_mock import LLMMock, load_agent_scenarios  # noqa: E402
from detection.src.pipeline.tier_router import TierRouter  # noqa: E402

# (post_id, 본문, has_image) — 본문은 mock_agent_scenarios.json 키워드를 포함해 라우팅된다.
# 8건 명확 불법(T1~T3, 일부 이미지 첨부) + 2건 정상(T4, fast path).
DEMO_POSTS: list[tuple[str, str, bool]] = [
    ("demo_01", "리니지M 월핵 최신 버전 팝니다. 탐지 안 됨. 텔레그램 @hack_seller", True),
    ("demo_02", "아이온 오토마우스 자동사냥 프로그램 무료 배포합니다. 디스코드 참고", True),
    ("demo_03", "블소 자동사냥 매크로 판매합니다. 영구 라이선스. 카톡 macro_seller", False),
    ("demo_04", "리니지 프리서버 새로 오픈했습니다. 1000% 경험치. 접속 ㄱㄱ", True),
    ("demo_05", "쓰론앤리버티 고레벨 계정 삽니다. 시세 문의 주세요", False),
    ("demo_06", "리니지M 아데나 현금 매입합니다. 최고가 보장", False),
    ("demo_07", "여기저기 홍보 도배 글 올립니다. 외부 사이트 가입하세요", False),
    ("demo_08", "아이온2 리세마라 완성 계정 양도합니다", False),
    ("demo_09", "발록 보스 공략 정리해봤습니다. 패턴 참고하세요", False),
    ("demo_10", "이번 패치노트 요약 공유합니다. 신규 던전 추가", False),
]


def _env_bool(name: str, default: str) -> bool:
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _synthetic_png() -> str:
    """64x64 단색 PNG (Pillow 없이 stdlib) — 오프라인 이미지 플러밍용 로컬 파일(네트워크 0)."""
    width = height = 64
    raw = b"".join(b"\x00" + b"\xc8\x32\x32" * width for _ in range(height))

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )
    tmp = Path(tempfile.gettempdir()) / "demo_3_9_synthetic.png"
    tmp.write_bytes(png)
    return str(tmp)


def _build_orchestrator(offline: bool) -> AgentOrchestrator:
    """오프라인이면 LLMMock 에이전트 모드, 아니면 실 LLMClient (smoke와 동일 wiring)."""
    dedup = fakeredis.FakeRedis(decode_responses=True)
    if offline:
        llm = LLMMock(agent_scenarios=load_agent_scenarios())
    else:
        from detection.src.pipeline.llm_client import LLMClient

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key or api_key.startswith("sk-REPLACE"):
            sys.exit("[FAIL] DEMO_OFFLINE=false인데 OPENAI_API_KEY가 placeholder입니다.")
        llm = LLMClient()

    return AgentOrchestrator(
        TriageAgent(llm),
        LinkTracer(dedup),
        image_analyst=ImageAnalyst(llm),
        synthesizer=Synthesizer(llm),
    )


def _display_path(traces) -> str:
    """trace로부터 표시용 path 추정 — fast_path / escalate(±degrade)."""
    stages = {t.stage for t in traces}
    if not (stages - {"normalize", "triage"}):
        return "fast_path"
    for t in traces:
        if t.stage == "synthesize" and t.output:
            if t.output.get("skipped") == "budget_exceeded":
                return "escalate_budget_degraded"
            if "error" in t.output:
                return "escalate_s3_failed_degraded"
    return "escalate_synthesized"


def main() -> int:
    offline = _env_bool("DEMO_OFFLINE", "true")
    # 오프라인 리허설은 S2a 플러밍까지 보이도록 PII 가드를 스크립트 한정 opt-in (운영 기본 false).
    if offline:
        os.environ["LLM_SEND_IMAGES"] = "true"
    image_enabled = _env_bool("LLM_SEND_IMAGES", "false")

    print(f"[INFO] 데모 리허설 — mode={'OFFLINE(mock)' if offline else 'REAL OpenAI'} "
          f"images={'on' if image_enabled else 'off'} posts={len(DEMO_POSTS)}")
    print("[INFO] single 회귀 폴백: DETECTION_MODE=single (정확도 회귀 시 데모 당일 즉시 전환)\n")

    orchestrator = _build_orchestrator(offline)
    tier_router = TierRouter()
    png = _synthetic_png() if image_enabled else None

    costs: list[float] = []
    escalated = 0
    illegal = 0
    print(f"{'post':<9} {'path':<26} {'type':<22} {'tier':<5} {'cost':>9} {'ms':>6}")
    print("-" * 82)
    for post_id, text, has_image in DEMO_POSTS:
        images = [png] if (has_image and png) else []
        verdict, traces = orchestrator.run(text, correlation_id=f"demo-{post_id}", images=images)
        tier = tier_router.route(verdict.type)
        path = _display_path(traces)
        cost = sum(t.cost_usd for t in traces)
        latency = sum(t.latency_ms or 0 for t in traces)
        costs.append(cost)
        if path != "fast_path":
            escalated += 1
        if tier != "T4":
            illegal += 1
        print(f"{post_id:<9} {path:<26} {verdict.type:<22} {tier:<5} ${cost:>7.5f} {latency:>6}")

    n = len(DEMO_POSTS)
    avg_cost = sum(costs) / n if n else 0.0
    print("-" * 82)
    print(f"\n[집계] {n}건 | 불법 탐지 {illegal}건 | escalation율 {escalated}/{n}={escalated / n:.0%}")
    print(f"[집계] 평균 비용 ${avg_cost:.5f} | 최대 ${max(costs):.5f} | 합계 ${sum(costs):.5f}")
    print(f"[집계] orchestrator escalation율(누적): {orchestrator._escalated}/{orchestrator._posts_total}")
    if offline:
        print("\n[NOTE] 오프라인 평균 비용은 mock fixture 값 — 실 비용 실측은 ab_compare.py(실 OpenAI) 참조.")
        print("[NOTE] 데모는 명확 불법 위주라 escalation율이 높음 — 운영 트래픽(정상 다수)의 평균과 다름.")
    print("\n[DONE] 데모 리허설 완료.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
