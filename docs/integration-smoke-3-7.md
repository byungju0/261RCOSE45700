# Story 3-7 실사 통합 smoke — 멀티 에이전트 오케스트레이터 (agentic 모드)

날짜: 2026-06-11
브랜치: `detection/agentic`
스크립트: `detection/scripts/smoke_agent_pipeline.py`

## 목적

`DETECTION_MODE=agentic` 경로를 production 코드 그대로 1건 실행해, S0 정규화 → S1 트리아지
(실 gpt-4o-mini 호출) → ESCALATE → S2b LinkTracer → degrade verdict + 스테이지별 agent_runs
trace가 실제로 흐르는지 증명한다 (AC #12 agentic E2E 데모 성립).

- Redis: fakeredis (in-memory)
- LLM: **실 OpenAI gpt-4o-mini** (`OPENAI_API_KEY`, infra/.env)
- DB: PG 미가동이면 분류·trace까지만 (detections+agent_runs 저장은 V10 적용된 PG에서 — 운영자 `!` 실행)

## 입력 게시글

```
리니지M 월핵 최신 버전 팝니다. 탐지 안 됨.
다운로드: https://example.com/down 텔레그램 https://t.me/smoke_test_001
```

## 실행 결과 (2026-06-11)

```
[INFO] DETECTION_MODE=agentic triage_model=gpt-4o-mini
[INFO] PG 미가동/미설정 — repository 없이 분류·trace까지만 검증.
orchestrator — path=escalate_degrade type=핵_치트 conf=0.950 links=2 needs_image=False

=== 트리아지 verdict (degrade) ===
  type=핵_치트 confidence=0.950 image_observed=False
  reason_ko=게임 핵·치트 프로그램을 판매하고 있으며, 탐지 회피 기능을 언급하고 있어 불법성이
            명확합니다. 판매 링크와 연락처가 포함되어 있어 근거가 확실합니다.
  translated_text_ko=None
  tokens(in/out)=3078/89 cost=$0.00052

=== agent_runs trace ===
  [normalize]  model=None         cost=$0.00000 latency=0ms
  [triage]     model=gpt-4o-mini  cost=$0.00052 latency=2374ms
  [link_trace] model=None         cost=$0.00000 latency=151ms
      link: kind=error      status=error:http_404      distribution=False
      link: kind=messenger  status=skipped:messenger   distribution=False
  -- total stage cost: $0.00052

[DONE] Story 3-7 agentic smoke 통과 — type=핵_치트 tier=T1, 3 스테이지 trace 생성.
```

## 검증 포인트

- **S0 normalize**: 본문에서 외부 링크 2개 추출(example.com/down, t.me/...). LLM 미사용($0).
- **S1 triage (gpt-4o-mini)**: type=핵_치트, conf=0.95, escalate(기타 아님). 실 호출 비용 $0.00052
  — PRD 목표(평균 ≤$0.005, p95 ≤$0.02) 대비 매우 낮음.
- **ESCALATE → S2b LinkTracer**: 링크 존재로 escalate 경로 진입.
  - `https://example.com/down`: 1-hop fetch → HTTP 404 → `kind=error`로 격리(분류 안 막음).
  - `https://t.me/smoke_test_001`: 메신저 도메인 → fetch 없이 `kind=messenger`.
- **degrade**: S3 Synthesizer 부재(Story 3-8)이므로 트리아지 결과가 최종 verdict. image_observed=False.
- **tier 라우팅**: 핵_치트 → T1 (기존 TYPE_TO_TIER 불변).
- **agent_runs trace 3건**(normalize/triage/link_trace) 생성 — V10 적용 시 detections와 동일
  트랜잭션으로 저장된다.

## DB 저장(detections + agent_runs) 검증 절차 (운영자)

로컬 dev DB가 수동 V5 드리프트(flyway 이력 없음, V6~V10 미적용)이므로 V10 적용 후 재실행 필요:

```bash
# 1) 컨테이너/PG 기동 후 마이그레이션 (Claude 직접 적용 차단 → ! 로 실행)
cd api && ./gradlew flywayInfo          # 현재 상태 확인
# flyway 이력 없으면: baseline(V5) 후 V6→V10 적용, 또는 dev DB 재생성 후 V1~V10 전체 (권장)
./gradlew flywayMigrate

# 2) PG 가동 상태에서 smoke 재실행 — detections + agent_runs 저장
DETECTION_MODE=agentic python detection/scripts/smoke_agent_pipeline.py

# 3) 확인
#   SELECT stage, model, cost_usd, latency_ms FROM agent_runs ORDER BY id;
```
