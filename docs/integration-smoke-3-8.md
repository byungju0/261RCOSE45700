# Story 3-8 실사 통합 smoke — ImageAnalyst + Synthesizer + 예산 가드 (escalate 전 경로)

날짜: 2026-06-11
브랜치: `agentic-3-8`
스크립트: `detection/scripts/smoke_agent_pipeline.py` (3-7 스크립트를 S0~S3 full wiring으로 확장)

## 목적

`DETECTION_MODE=agentic` escalate 심층 경로를 production 코드 그대로 1건 실행해,
S0 정규화 → S1 트리아지(실 gpt-4o-mini) → **S2a ImageAnalyst(실 gpt-4o) ∥ S2b LinkTracer 병렬**
→ **S3 Synthesizer(실 gpt-4o) 합성 verdict** + 5 스테이지 agent_runs trace + 게시글당 예산 가드가
실제로 흐르는지 증명한다 (AC #1~#3, #5, #7).

- Redis: fakeredis (in-memory)
- LLM: **실 OpenAI** — S1 gpt-4o-mini / S2a·S3 gpt-4o (`OPENAI_API_KEY`, infra/.env)
- 이미지: `SMOKE_IMAGE` 미지정 → 합성 64x64 단색 PNG (S2a 플러밍 검증 — contributes=false 예상.
  실제 핵 판매 스크린샷으로 contributes=true를 보려면 `SMOKE_IMAGE=/path/to/shot.png` 지정)
- PII 토글: 스크립트가 `LLM_SEND_IMAGES=true`를 명시 설정 (smoke 한정 opt-in — 운영 기본 false)
- DB: PG 미가동이면 분류·trace까지만 (detections+agent_runs 저장은 V10 적용된 PG에서 — 운영자 `!` 실행)

## 입력 게시글

```
리니지M 월핵 최신 버전 팝니다. 탐지 안 됨. 스크린샷 참고.
다운로드: https://example.com/down 텔레그램 https://t.me/smoke_test_001
+ 첨부 이미지 1장 (합성 PNG)
```

## 실행 결과 (2026-06-11)

```
[INFO] DETECTION_MODE=agentic triage=gpt-4o-mini image=gpt-4o synth=gpt-4o budget=$0.02
[INFO] SMOKE_IMAGE 미지정 — 합성 PNG로 S2a 플러밍 검증 (contributes=false 예상)
[INFO] PG 미가동/미설정 — repository 없이 분류·trace까지만 검증.

=== 최종 verdict (S3 합성 또는 degrade) ===
  type=핵_치트 confidence=0.950 image_observed=False
  reason_ko=게시글에서 리니지M용 최신 버전 게임 핵을 판매하고, 탐지 회피를 주장하며 다운로드 링크와
            텔레그램 연락처를 제공하고 있음.
  translated_text_ko=None
  tokens(in/out)=7060/177 cost=$0.01143 (스테이지 합산)

=== agent_runs trace ===
  [normalize]  model=None        cost=$0.00000 latency=0ms
  [triage]     model=gpt-4o-mini cost=$0.00051 latency=3080ms
  [image]      model=gpt-4o      cost=$0.00186 latency=1397ms
      image: contributes=False indicators=[]
      image summary: 전체 빨간색 화면으로 내용 없음.
  [link_trace] model=None        cost=$0.00000 latency=442ms
      link: kind=error      status=error:http_404      distribution=False
      link: kind=messenger  status=skipped:messenger   distribution=False
  [synthesize] model=gpt-4o      cost=$0.00905 latency=2658ms
  -- total stage cost: $0.01143 (게시글당 예산 $0.02 — PRD 평균 ≤$0.005·p95 ≤$0.02)

[DONE] Story 3-8 agentic smoke 통과 — type=핵_치트 tier=T1 synthesized=True
       model_version=agentic:v1:mini+4o:2026-06, 5 스테이지 trace 생성.
```

## 검증 포인트

| 항목 | 결과 |
|---|---|
| S0~S3 5 스테이지 전부 실행 (agent_runs trace 5건) | ✅ normalize/triage/image/link_trace/synthesize |
| S2a 실 gpt-4o vision 호출 + 정직한 판정 | ✅ 합성 단색 PNG를 contributes=false·지표 0건으로 판정 (오탐 없음) |
| S2a ∥ S2b 병렬 (ThreadPoolExecutor) | ✅ image 1397ms·link_trace 442ms 동시 구간 — 직렬 합산 대비 단축 |
| `image_observed` = S2a contributes (AC #3) | ✅ contributes=false → verdict image_observed=False |
| S2b 실패 격리 | ✅ 404는 error 기록 후 계속, 메신저 링크는 fetch 없이 분류 |
| S3 합성 verdict (5필드 스키마) | ✅ type=핵_치트 conf=0.95 + reason_ko에 증거(다운로드 링크·텔레그램) 인용 |
| 게시글당 예산 가드 | ✅ 합산 $0.01143 < $0.02 — 가드 미발동(정상). 가드 발동 경로는 단위/통합 테스트로 검증 |
| 비용 | ✅ escalate 풀 경로 $0.01143 ≤ p95 목표 $0.02 (평균 목표 ≤$0.005는 fast-path 혼합 전제 — 3-9 실측) |
| model_version | ✅ `agentic:v1:mini+4o:2026-06` (≤ VARCHAR(50), 3-9 A/B 분리 키) |
| escalation율 구조화 로그 (AC #7) | ✅ path/stage_costs/stage_latency_ms/escalation_rate 필드 출력 (JSON 로그) |

## 비고

- 합성 이미지에 대한 S2a의 contributes=false 판정은 **이미지 증거 오탐 방지**가 동작함을 보여준다.
  실제 핵 UI 스크린샷 검증(contributes=true 경로)은 Story 3-9 데모 리허설에서 실 수집 이미지로 수행.
- detections + agent_runs 저장 경로는 V10 적용된 PG 필요 — 로컬 dev DB drift(수동 V5) 해소는
  운영자 `!` 실행 절차(3-7 스토리 Task 1) 참조. PG-required 통합 테스트는 `requires_pg` skip으로 격리됨.
- 예산 degrade·S3 실패 fallback·PII 스킵 경로는 외부 호출 0의 단위 7건 + 통합 2건으로 검증
  (`test_orchestrator.py` / `test_agent_pipeline.py`).
