# Story 3.8: ImageAnalyst + Synthesizer + 게시글당 예산 가드

Status: done

<!-- 2026-06-11 Epic 3 재정의(Correct Course) 2차 구현 증분. sprint-change-proposal-2026-06-11.md 승인분. Story 3-7 done 직후. -->

## Story

개발자로서,
의심 게시글의 이미지가 분석되고 모든 증거(본문·트리아지·이미지·링크)가 통합되어 최종 판정이 내려지되 게시글당 비용이 통제되기를 원한다,
그래서 정확도를 높이면서도 escalate 게시글의 비용 폭증을 막는다.

> 본 스토리 완료 시 escalate 심층 경로가 완성된다 — 3-7의 "escalate→트리아지 degrade" 임시 종결이 S2a∥S2b 병렬 증거 수집 + S3 증거 통합 verdict로 대체된다. 출력은 기존 5필드 스키마 그대로(detections 계약 불변, Epic 4 무영향).

## Acceptance Criteria

**Given** Story 3-7의 escalate 경로가 동작하는 상태에서
**When** 게시글이 escalate되면

1. **S2a `image_analyst.py`**(gpt-4o)가 이미지 존재 시 핵 UI/사설서버 배너/워터마크/연락처를 판독하여 `ImageEvidence{illegal_indicators[], extracted_text, summary_ko, contributes}`를 산출한다 (FR16-NEW-1)
2. S2a와 S2b(LinkTracer)는 `ThreadPoolExecutor`로 **병렬 실행**된다 (기존 sync 워커 구조 유지, 침습 최소)
3. **S3 `synthesizer.py`**(gpt-4o)가 본문 + 트리아지 + 이미지/링크 증거를 통합하여 기존 `{type, confidence, reason_ko, translated_text_ko, image_observed}` 5필드 스키마를 산출한다 — `image_observed`는 S2a `contributes` 값, `reason_ko`에 채택한 증거를 1문장 포함
4. 증거 충돌 시 더 구체적 증거(다운로드 페이지 확인·핵 UI 스크린샷) 우선 + 다중 type 신호 시 최상위 Tier type 채택을 S3 프롬프트에 명시
5. **게시글당 예산 가드**: `AGENT_POST_BUDGET_USD`(기본 0.02) 초과 시 잔여 stage를 스킵하고 현재까지의 증거로 degrade 종결(S3-mini 또는 트리아지 verdict) — 전수 저장 정책 유지
6. S3 호출 실패 시 트리아지 결과로 degrade 저장(verdict 없는 것보다 1차 분류라도 저장)하고 `agent_runs`에 실패 trace를 기록한다
7. escalation율·스테이지별 비용·latency가 구조화 로그(`correlation_id` 포함)로 남는다 — 50% 초과 지속 시 fast-path 임계 하향 조정 신호
8. 신규 단위/통합 테스트가 mock 에이전트로 escalate 전 경로 + 예산 degrade + S3 실패 fallback을 검증 (외부 호출 0)

[Source: _bmad-output/planning-artifacts/epics.md L751-771 — AC 원문 그대로]

## Tasks / Subtasks

- [x] Task 1: 계약 확장 — `detection/src/agents/contracts.py` (AC: #1, #3)
  - [x] `ImageEvidence{illegal_indicators: list[str], extracted_text: str, summary_ko: str, contributes: bool}` + 토큰/비용 추적 필드(`input_tokens, output_tokens, cost_usd` — `TriageResult` 패턴 동일) dataclass 추가
  - [x] `LinkEvidence`에 **additive** `excerpt: str` 필드(기본 "") 추가 — S2b `_build_evidence()`가 html2text로 이미 추출하는 본문에서 앞 500자 캡처. S3가 title+indicators만으로 판정 불가한 케이스의 증거 소스 (agent_runs.output은 JSONB라 스키마 무영향, 3-7 저장분과 하위호환)
  - [x] `AGENT_STAGES`의 `image`/`synthesize` 값은 3-7에서 이미 등록됨(contracts.py L16-18, V10 주석 일치) — 신규 마이그레이션 불요. **Flyway 변경 0**
- [x] Task 2: `LLMClient.run_structured` 이미지 입력 지원 (AC: #1)
  - [x] `run_structured(...)`에 optional `images: list[str] | None = None` 파라미터 추가 — 기존 `_resolve_image_url()`(L102-135)을 재사용해 user content를 multipart(text + image_url parts)로 구성. 기존 호출자(S1 triage) 무영향(기본값 None)
  - [x] 이미지 전부 resolve 실패 시 텍스트-only로 진행하고 호출 결과에 표식 반환(또는 S2a에서 빈 이미지로 skip 판단) — `classify()`의 기존 fallback 패턴 준수
  - [x] s3:// 키는 기존 동작 유지(경고 후 skip — presigned 변환은 본 스토리 범위 외). 실효 입력은 http(s) `image_urls` + 로컬 경로(base64)
- [x] Task 3: S2a `detection/src/agents/image_analyst.py` (AC: #1)
  - [x] `ImageAnalyst(llm_client, model)` — 모델명 `IMAGE_ANALYST_MODEL` env (기본 `gpt-4o`). `LLMClient.run_structured(images=...)` 위임 호출 (신규 OpenAI wrapper 금지 — TriageAgent 패턴 복제)
  - [x] IMAGE_SCHEMA(json_schema strict): `{illegal_indicators: string[], extracted_text: string, summary_ko: string, contributes: boolean}` — `contributes`는 "이미지가 불법성 판단에 기여하는가" boolean
  - [x] 프롬프트: 핵 UI(ESP/aimbot 오버레이·치트 메뉴)·사설서버 배너·워터마크·연락처(디스코드/텔레그램 ID·QR)·가격표 판독 지시. `domain_guide.md`는 주입하지 않음(이미지 판독은 도메인 은어 불요 — 토큰 절약), 판독 결과 해석은 S3 몫
  - [x] 호출 전 TokenBucket acquire(기존 `llm:rate_limit:classify` 버킷 공유) + 호출 후 `cost_cap.record()` — S1과 동일 규율
  - [x] PII 가드: 기존 `LLM_SEND_IMAGES`(기본 false) 토글을 S2a에도 적용 — false면 S2a 자체를 skip하고 trace에 `{"skipped": "LLM_SEND_IMAGES=false"}` 기록 (PRD L266 법무 미확정 대응, single 모드와 동일 정책)
- [x] Task 4: S3 `detection/src/agents/synthesizer.py` (AC: #3, #4)
  - [x] `Synthesizer(llm_client, model)` — 모델명 `SYNTHESIZER_MODEL` env (기본 `gpt-4o`). 출력 스키마는 **기존 `CLASSIFICATION_SCHEMA`(llm_client.py L84-95) 그대로 재사용** — 5필드 계약의 SSOT 유지, 신규 스키마 정의 금지
  - [x] 입력 조립: 정규화 본문(S0) + TriageResult(type/confidence/game_context/reason_ko) + ImageEvidence(있으면) + LinkEvidence[](있으면 — kind/page_title/is_distribution_site/indicators/excerpt) 를 구조화 텍스트 블록으로 직렬화
  - [x] 시스템 프롬프트에 증거 우선순위 규칙 명시: (a) 구체적 증거(다운로드 페이지 fetch 확인 `is_distribution_site=true`·핵 UI 스크린샷 `contributes=true`) > 본문 추정 (b) 다중 type 신호 충돌 시 최상위 Tier type 채택(T1 > T2 > T3 > T4 — tier_config 순서) (c) `reason_ko`에 채택한 증거 1문장 포함 (d) `translated_text_ko`는 트리아지 산출값을 기본 유지(원문 비한국어 시)
  - [x] 응답의 `image_observed`를 S2a `contributes`로 **덮어쓰기**(S2a 미실행/skip 시 False) — LLM 자가 보고 대신 결정론적 값 (AC #3)
  - [x] type/confidence 방어 검증(ALLOWED_DETECTION_TYPES 9종, [0,1] 클램프) — triage_agent.py L67-96 가드 패턴 재사용
- [x] Task 5: 오케스트레이터 확장 — S2a∥S2b 병렬 + S3 + 예산 가드 (AC: #2, #5, #6)
  - [x] `AgentOrchestrator.__init__`에 `image_analyst`, `synthesizer` 주입(Optional 유지 시 3-7 단독 구성과 하위호환). escalate 분기 재구성: `ThreadPoolExecutor(max_workers=2)`로 S2a(이미지 존재 ∧ LLM_SEND_IMAGES 시)·S2b(링크 존재 시) **병렬 제출** → 양쪽 완료 대기 → 예산 체크 → S3
  - [x] 파이프라인에서 이미지 전달: `detection_pipeline.py`의 single 모드 병합 패턴(`s3_image_paths + image_urls`, L100-109)과 동일하게 agentic 분기에서도 orchestrator로 이미지 리스트 전달
  - [x] **예산 가드(결정론적)**: `AGENT_POST_BUDGET_USD` env(기본 0.02). 각 LLM stage 착수 **직전** 누적 실비용(`sum(trace.cost_usd)`) ≥ 예산이면 잔여 stage 스킵: (a) S2a/S2b 전 초과 → 트리아지 verdict degrade (b) S3 전 초과 → `SYNTH_FALLBACK_MODEL` env(기본 빈 값)가 설정되어 있으면 S3를 해당 모델(gpt-4o-mini)로 1회 시도, 아니면 트리아지 verdict degrade — "S3-mini 또는 트리아지 verdict" AC 문구의 결정론적 구현. degrade여도 **저장은 항상 수행**(전수 저장 정책)
  - [x] **S3 실패 fallback**: Synthesizer 예외(RetryExhausted 포함) 시 트리아지 verdict로 degrade하고 `AgentRunTrace(stage="synthesize", model=모델명, cost_usd=실비용, output={"error": "<클래스명: 요약>"})` 기록 — 실패도 trace로 남김 (AC #6). S2a 실패는 S3를 막지 않음(이미지 증거 없이 진행 — S2b 실패 격리와 동일 원칙)
  - [x] path 값 확장: `fast_path | escalate_synthesized | escalate_budget_degraded | escalate_s3_failed_degraded` — 구조화 로그·테스트 assert 기준
  - [x] `model_version` 갱신: S3 합류로 `agentic:v1:mini+4o:{YYYY-MM}` 형식(변경 제안서 L181 확정값, VARCHAR(50) 이내). 주의 — 3-7의 `agentic:v1:{triage_model}:{YYYY-MM}`에서 변경되므로 (post_id, model_version) 유니크 충돌 없음(신규 값), 3-9 A/B는 본 값 기준
  - [x] `main.py` wiring: ImageAnalyst/Synthesizer 생성 + orchestrator 주입. `DETECTION_MODE=single` 경로 무수정
- [x] Task 6: 구조화 로그 — escalation율·스테이지 비용·latency (AC: #7)
  - [x] 게시글 종결 시 1건 로그: `extra={correlation_id, service, path, stage_costs: {triage: $, image: $, link_trace: $, synthesize: $}, total_cost_usd, stage_latency_ms, escalated: bool}` — 3-7 orchestrator L102-109 로그 확장
  - [x] 오케스트레이터 인스턴스 카운터(`posts_total / escalated / budget_degraded / s3_failed`)로 누적 escalation율을 같은 로그에 포함(`escalation_rate`) — 50% 초과 시 warning 레벨로 "fast-path 임계 하향 검토" 신호 로그 (프로세스 단위 근사로 충분, Prometheus 연동은 Epic 5 backlog)
- [x] Task 7: `llm_mock.py` + fixtures 확장 (AC: #8)
  - [x] `LLMMock.run_structured`가 스키마 모양으로 모드 분기(트리아지 7필드 / 이미지 4필드 / 합성 5필드) 또는 호출 순서 기반 응답 큐 — `tests/fixtures/llm/mock_image_*.json`, `mock_synth_*.json` fixture 추가 (리포 루트 `tests/fixtures/llm/` — 기존 `mock_response_*.json` 위치)
  - [x] 비용 시나리오 mock: 예산 초과를 유발하는 고비용 응답 fixture (예산 degrade 테스트용)
- [x] Task 8: 테스트 (AC: #8 — 외부 네트워크·실제 Redis·실제 OpenAI 0)
  - [x] `tests/unit/test_image_analyst.py`: 스키마 검증 / LLM_SEND_IMAGES=false skip / 이미지 resolve 실패 처리
  - [x] `tests/unit/test_synthesizer.py`: 증거 직렬화(이미지+링크 포함/미포함) / image_observed=contributes 덮어쓰기 / type·confidence 방어 검증 / 5필드 스키마 준수
  - [x] `tests/unit/test_orchestrator.py` 확장: ① escalate 전 경로(S2a∥S2b→S3) verdict·trace 5종 ② 예산 초과 → S2 스킵 degrade ③ 예산 초과(S2 후) → S3 스킵/mini fallback degrade ④ S3 예외 → 트리아지 degrade + 실패 trace ⑤ S2a 단독 실패 시 S3 진행 ⑥ 이미지 없음 → S2b만 ⑦ ThreadPoolExecutor 병렬 경로에서 trace 순서/누락 없음
  - [x] `tests/integration/test_agent_pipeline.py` 확장: escalate→synthesize E2E(fakeredis + LLMMock + MagicMock repo) — agent_runs에 image/synthesize stage 포함 확인, 예산 degrade E2E 1건
  - [x] **출력 계약 불변 회귀**: 3-7의 single vs agentic 계약 테스트가 S3 verdict 경로에서도 동일 5필드+tier/is_illegal을 채움을 확인(케이스 추가)
  - [x] 기준선: 3-7 완료 시점 **118 PASS / 11 skip** + `flake8 src tests --max-line-length=120` clean — 회귀 0 필수
- [x] Task 9: 3-7 리뷰 defer 항목 종결 — S2b mini 요약 fallback 결정 (AC: #3 연계)
  - [x] 3-7 리뷰 defer "규칙 판정 불가 시 gpt-4o-mini 요약 fallback"(link_tracer.py L68-78)을 본 스토리에서 **결정**: S3(gpt-4o)가 LinkEvidence.excerpt(Task 1)를 직접 소비하므로 S2b 단계의 별도 mini 요약 호출은 **불요로 종결 권장**(비용·복잡도 절감, 변경 제안서 S2b 비용 모델의 mini 요약분은 S3로 흡수). 결정과 근거를 본 스토리 Dev Notes/PR에 기록
- [x] Task 10: 실사 smoke + 문서 (AC: #1~#7 데모 성립 확인)
  - [x] `scripts/smoke_agent_pipeline.py` 확장(또는 `smoke_agent_full.py`): 이미지 포함 escalate 게시글 1건 — 실 gpt-4o-mini(S1) + gpt-4o(S2a·S3) 호출, 스테이지별 비용·latency·총비용 출력, 예산 가드 동작 라인 포함. `LLM_SEND_IMAGES=true` 명시 실행 (로컬 이미지 fixture 또는 http URL)
  - [x] `docs/integration-smoke-3-8.md` 캡처 (3-3/3-4/3-7 관례). agent_runs 5 stage 저장은 V10 적용 PG 필요 — 운영자 `!` 실행 절차 3-7 Task 1 노트 참조
  - [x] `.env.example`(detection) + `infra/.env.example`에 신규 env 추가: `AGENT_POST_BUDGET_USD=0.02` / `IMAGE_ANALYST_MODEL=gpt-4o` / `SYNTHESIZER_MODEL=gpt-4o` / `SYNTH_FALLBACK_MODEL=`(선택)

### Review Findings

<!-- 2026-06-11 3-layer 적대적 코드 리뷰(Blind Hunter / Edge Case Hunter / Acceptance Auditor). 0 decision / 12 patch / 3 defer / 12 dismiss. AC 8종 전부 충족 판정(167 PASS/11 skip + flake8 clean 실측 재현). 12 patch 전부 batch-apply 완료 — 신규 AgentResponseError(usage 보존) + 카운터 종결 시점 이동 + S2b 실패 trace + 회귀 테스트 3건 추가. 최종 170 PASS / 11 skip + flake8 clean. -->

- [x] [Review][Patch] **(MAJOR)** S2a/S3 검증 실패 시 실지출 비용이 회계에서 증발 — `run_structured` 성공(과금) 후 응답 검증 raise 시 usage가 소실되어 error trace의 토큰/비용=0 → 예산 가드 누적·cost_cap·detections.cost_usd 모두 누락. 검증 예외에 usage를 실어 orchestrator error trace에 실비용 기록 [image_analyst.py:102-104, synthesizer.py:127-132, orchestrator.py:206-209/279-282]
- [x] [Review][Patch] **(MAJOR)** escalation 카운터가 게시글이 아닌 attempt 단위로 증가 — `_posts_total += 1`이 `run()` 진입 즉시 실행되어 RetryHandler 재시도마다 중복 카운트 → escalation_rate 하향 왜곡(AC #7 경고 신호 신뢰성 훼손). 증분을 종결 시점(`_log_outcome`)으로 이동 [orchestrator.py:113,151]
- [x] [Review][Patch] **(MAJOR)** S2b future 실패 시 link_trace trace 미기록 — S2a는 error trace를 남기는데 S2b except 분기는 warning만(비대칭, 전수 trace 정책 위반). error trace append 추가 [orchestrator.py:304-312]
- [x] [Review][Patch] (MINOR) SYNTH_FALLBACK 경로의 예산 초과 사건이 종결 로그에서 비가시 — fallback 분기는 `_budget_degraded` 미증가·skip 마커 없음(trace output `budget_fallback`만). 누적 카운터/로그 필드 노출 추가 [orchestrator.py:184-191]
- [x] [Review][Patch] (MINOR) `infra/.env.example`에 `IMAGE_ANALYST_MODEL`/`SYNTHESIZER_MODEL` 누락 — Task 10은 양쪽 .env.example 모두 요구 [infra/.env.example]
- [x] [Review][Patch] (MINOR) `model_version[:50]` 무음 절단 — 커스텀 모델명(env 오버라이드) 시 `:{YYYY-MM}` suffix가 잘려 3-9 A/B 키 변별력 상실 가능. 절단 발생 시 warning 로그 [orchestrator.py:104]
- [x] [Review][Patch] (MINOR) `run_structured` 텍스트-only 호출의 wire format이 str→list로 변경 — 기존 호출자(S1) 페이로드 형식 변화 + `test_run_structured_without_blocks_unchanged` 테스트명이 변경 사실과 모순. image_blocks 없으면 기존 str content 유지 [llm_client.py run_structured]
- [x] [Review][Patch] (MINOR) image_analyst 미주입 + 이미지 존재 구성에서 무 trace 무음 누락 — PII skip은 기록하면서 미구성 skip은 미기록(agent_runs만으로 "이미지 없음"과 구분 불가). skip trace 추가 [orchestrator.py:249-250]
- [x] [Review][Patch] (NIT) 예산 skip 마커 `skipped_stages`가 실재하지 않는 stage도 고정 나열 — 이미지/링크 없는 게시글도 image·link_trace 스킵으로 기록(3-9 과대 계상) [orchestrator.py:171]
- [x] [Review][Patch] (NIT) S2a 실패 trace에 latency_ms 미기록 — `_timed`가 예외 시 latency를 소실(S3 실패 trace는 기록, 비대칭). 실패 케이스가 latency 집계에서 체계적 누락 [orchestrator.py:253-256,274-282]
- [x] [Review][Patch] (NIT) Dev Record 테스트 breakdown 수치 스왑 — 실측 synthesizer 11/orchestrator 12인데 "synthesizer 12 + orchestrator 11"로 기재(합계 37은 일치) [본 문서 Debug Log]
- [x] [Review][Patch] (NIT) `mock_synth_illegal.json`의 translated_text_ko가 시나리오와 불일치 — 매크로 판매인데 "대리 레벨업/프리스타일 풋볼" 문구(테스트 미사용, 무해) [tests/fixtures/llm/mock_synth_illegal.json]
- [x] [Review][Defer] agentic 경로 TokenBucket/rate-limit 미적용 — 429 보호는 llm_client 자체 1회 재시도뿐. 3-7부터의 기존 동작이며 Dev Record "[명세 해석]"에 문서화된 이탈(코드 검증 결과 사실) — deferred, pre-existing [agents/*]
- [x] [Review][Defer] RetryHandler 재시도 시 실패 attempt의 LLM 실지출이 cost_cap에 미기록 — `execute_with_retry(orchestrator.run 전체)` 래핑은 3-7 기존 구조(traces 통째 폐기). 재시도 캐시는 deferred-work 기존재 항목과 연결 — deferred, pre-existing [detection_pipeline.py:119-131]
- [x] [Review][Defer] 예산 degrade 마커가 `stage="synthesize"`로 기록 — V10 enum 내 유효하나 3-9에서 "synthesize 행 수 = S3 호출 수" 집계 시 오류. 인수인계 노트 — deferred [orchestrator.py:328-338]

## Dev Notes

### 스코프 경계 — 반드시 지킬 것

| 포함 (3-8) | 제외 (이월처) |
|---|---|
| S2a ImageAnalyst + S2a∥S2b 병렬 | A/B 정확도 비교·비용 실측·fast-path 임계 튜닝 → **3-9** |
| S3 Synthesizer (5필드 verdict) | llm_mock 에이전트 "데모 리허설" 모드·10건 리허설 스크립트 → **3-9** |
| AGENT_POST_BUDGET_USD 예산 가드 + S3 실패 fallback | T1 알림 E2E 검증(기존 시스템) → **3-9** (~~3-10~~은 2026-06-11 2차 폐기 — 3-7 스토리 파일의 "T1 알림 → 3-10" 표기는 무효) |
| escalation율·스테이지 비용 구조화 로그 | Prometheus 메트릭 연동 → Epic 5 backlog |
| LinkEvidence.excerpt additive 확장 | few-shot 주입(Stage 2-B)·multi-hop·retention·사람 리뷰 큐·대시보드 증거 패널 → deferred-work |
| 3-7 defer "S2b mini 요약" 결정 종결 (Task 9) | s3:// presigned URL 변환 (이미지 입력은 http URL/로컬 경로 한정 유지) |

- **신규 Flyway 마이그레이션 없음** — `agent_runs.stage`의 `image|synthesize` 값은 V10에 이미 정의됨. detections 테이블 계약 불변(Epic 4 무영향).
- 일일 cap(`cost_cap.py` $5)·TokenBucket·RetryHandler·TierRouter는 기존 그대로 — 본 스토리는 게시글당 예산만 추가.
- 오케스트레이션은 결정론적 plain Python 유지 — LangChain/LLM 라우팅 금지 [Source: sprint-change-proposal-2026-06-11.md L141-142].

### 완성 후 파이프라인 (변경 제안서 확정 설계)

```
CrawlEvent (posts:queue — 계약 불변)
 ▼ S0 normalizer ($0) → S1 triage (gpt-4o-mini, ~$0.0004)
 ├─ FAST PATH (기타 ∧ conf≥0.80 ∧ 의심 링크 없음) → 트리아지 = verdict
 └─ ESCALATE
     ├─ S2a image_analyst (gpt-4o, 이미지 有 ∧ LLM_SEND_IMAGES) ┐ ThreadPoolExecutor
     ├─ S2b link_tracer (1-hop fetch, $0)                      ┘ (병렬, max_workers=2)
     ▼ [예산 체크: 누적 ≥ AGENT_POST_BUDGET_USD → S3 스킵/mini → degrade]
     ▼ S3 synthesizer (gpt-4o, ~$0.008) → 5필드 verdict (실패 시 트리아지 degrade)
 ▼ tier_router.route(type) → cost_cap.record(스테이지별 기록) → repository.save(+agent_runs 5 stage)
```

비용 모델(3-9 실측 기준선): S2a $0.0058(escalate의 40%) / S3 $0.0080(escalate 전부) — escalation 35%에서 평균 ~$0.0040 ✅ ≤$0.005, p95 ≤$0.02는 예산 가드(0.02)가 상한 강제 [Source: sprint-change-proposal-2026-06-11.md L148-161, prd.md L78].

### 3-7이 남긴 통합 지점 (구현 시작점)

- `orchestrator.py` L112-122: degrade 분기 — "S3 Synthesizer는 Story 3-8" 주석 지점이 본 스토리의 교체 대상. `image_observed=False` 하드코딩(L118)도 S2a contributes로 대체
- `TriageResult.needs_image`(contracts.py L40-57): S1이 이미 산출 — S2a 실행 조건은 `escalate ∧ 이미지 존재 ∧ LLM_SEND_IMAGES`(needs_image는 보조 신호 — 이미지가 실재하면 needs_image=false여도 S2a 실행 권장: 트리아지는 이미지를 보지 못한 채 추정하므로)
- `AgentOrchestrator.run()` 반환 계약 `(LLMResponse, list[AgentRunTrace])` 유지 — pipeline/repository 무수정 통과
- `LLMClient.run_structured`(llm_client.py L280-312): S1이 쓰는 공유 진입점 — Task 2에서 이미지 지원만 추가
- `CLASSIFICATION_SCHEMA`(llm_client.py L84-95): S3 출력 스키마로 그대로 재사용 — 5필드 계약 SSOT
- `_resolve_image_url`(llm_client.py L102-135): 로컬 경로→base64, http(s)/data: 통과, s3:// 경고 skip — S2a가 그대로 위임
- `tier_config`: T1>T2>T3>T4 순서 — S3 프롬프트의 "최상위 Tier type 채택" 규칙에 type→Tier 매핑 명시(9종: 핵_치트·사설서버=T1 등 — tier_config.py 참조)

### 데이터 계약 (불변 — 절대 변경 금지)

- **입력** `CrawlEvent`: image_urls[], s3_image_paths[] 가 S2a 입력 소스 (single 모드 병합 패턴과 동일)
- **출력** `LLMResponse` 5필드 {type, confidence, reason_ko, translated_text_ko, image_observed} + 파생 tier, is_illegal — Epic 4 `DetectionResponse`/프론트 의존. detections 스키마 불변
- type enum 9종 `ALLOWED_DETECTION_TYPES` — S2a/S3 응답 방어 검증 필수
- detections 멱등: `(post_id, model_version)` UNIQUE — model_version은 `agentic:v1:mini+4o:{YYYY-MM}`로 갱신(Task 5)
- agent_runs stage: `normalize|triage|image|link_trace|synthesize` (V10 주석·AGENT_STAGES 기등록)

### 기존 코드 재사용 맵 (바퀴 재발명 금지)

| 재사용 대상 | 위치 | 3-8에서의 사용 |
|---|---|---|
| `LLMClient.run_structured` + `_resolve_image_url` | `pipeline/llm_client.py` | S2a/S3 호출 — 신규 OpenAI wrapper 금지 |
| `CLASSIFICATION_SCHEMA` | `pipeline/llm_client.py` L84-95 | S3 출력 스키마 그대로 |
| `TriageAgent` 구조(주입·검증·trace) | `agents/triage_agent.py` | ImageAnalyst/Synthesizer 클래스 골격 복제 |
| `CostCap.record()` / `estimate_cost_usd` | `rate_limit/cost_cap.py` | S2a/S3 호출마다 record. gpt-4o 단가 기존재 — PRICING 변경 0 |
| `TokenBucket` (`llm:rate_limit:classify`) | `rate_limit/token_bucket.py` | S2a/S3 호출 전 acquire (버킷 공유 — Lua atomic이라 스레드 안전) |
| `RetryHandler` | `retry/retry_handler.py` | S2a/S3 LLM 호출 감싸기(기존 화이트리스트). RateLimitError는 llm_client 자체 1회 재시도 후 raise — 3-3 계약 유지 |
| `AgentRunTrace` → repository batch INSERT | `repository/detection_repository.py` L159-197 | image/synthesize trace 2종 추가 — repository 코드 무수정(stage 문자열만 새 값) |
| `LLMMock` + fixtures | `mocks/llm_mock.py` | 이미지/합성 모드 추가 — 통합 테스트 외부 호출 0 유지 |
| 구조화 로깅 + correlation_id | `shared/structured_logger` | 모든 신규 로그에 correlation_id 필수 |

### ThreadPoolExecutor 병렬 실행 가이드 (AC #2)

- escalate당 1회성 `ThreadPoolExecutor(max_workers=2)` 또는 오케스트레이터 보유 풀 — 게시글 처리량이 낮아(워커 sync 단건 소비) 어느 쪽이든 무방, 1회성이 상태 공유 없어 단순
- 스레드 안전성: openai SDK Client·redis-py ConnectionPool·psycopg pool 모두 thread-safe. TokenBucket은 Redis Lua atomic. **CostCap.record는 Redis INCRBY atomic — 병렬 호출 안전**
- 각 future 예외는 `future.result()`에서 개별 catch — S2a 실패가 S2b 증거를 버리게 하지 말 것(역도 동일). latency_ms는 stage별 자체 측정(병렬이라 합산≠wall clock)
- fakeredis는 thread-safe — 병렬 경로 단위 테스트 가능. 단 테스트에서 결정성 위해 mock agent에 sleep 넣지 말 것

### 예산 가드 설계 (AC #5 — 결정론적)

- 체크 시점: 각 LLM stage **착수 직전**, 기준은 해당 게시글의 **누적 실비용**(`sum(trace.cost_usd for trace in traces)`) — 사전 추정 불요(추정은 비결정적·복잡)
- 기본 0.02에서 정상 경로(S1 0.0004 + S2a 0.0058 + S3 0.008 ≈ 0.014)는 가드에 걸리지 않음 — 가드는 대형 이미지·재시도 등 꼬리 케이스용 (PRD p95 ≤$0.02의 상한 강제 장치)
- degrade 종결이어도 trace에 budget_degraded 사실을 남기고(`output`에 `{"budget_degraded": true, "spent": ...}` 또는 path 로그), **저장은 항상 수행** — 전수 저장 정책(2026-05-27 결정) 위반 금지
- `SYNTH_FALLBACK_MODEL`(선택, 기본 미설정): 설정 시 S3 예산 초과 분기에서 mini로 1회 합성 시도 — "S3-mini" AC 옵션의 opt-in 구현. 미설정이면 트리아지 verdict degrade (단순 우선)

### 이전 스토리 인텔리전스 (3-7 dev/review)

- **LLMClient 재사용 패턴 검증됨**: 3-7이 `_create_with_retry` 추출로 분류/트리아지 단일 진입점 공유 — S2a/S3도 같은 진입점. 신규 wrapper를 만들면 리뷰에서 reject됨
- **실패 격리 원칙**: S2b는 "링크 추적 실패가 게시글 분류를 막으면 안 됨"으로 구현 — S2a/S3에 동일 원칙 적용 (AC #6의 정신)
- **3-7 리뷰 patch 교훈**: 캐시/외부 의존 예외는 전파 금지(warning 후 진행), 상수는 shared로(`REDIS_KEY_LINKTRACE_PREFIX` 사례), env 값은 `.strip()` 처리(model_version 사례 — 신규 `IMAGE_ANALYST_MODEL` 등에도 적용), dead 조건식 금지
- **3-7 리뷰 dismiss 교훈**: Auditor의 "agent_runs NULL 가드" CRITICAL 주장은 오탐이었음 — 리뷰 지적은 코드로 검증 후 수용
- **실사 smoke 관례**: 실 OpenAI 호출 1건 + 비용 출력 + docs 캡처가 dev 완료 조건 (Tracker MVP 본질 = "실사 통합 작동"). 3-7 실측: S1 $0.00052
- **로컬 dev DB drift**: 수동 V5 상태 — agent_runs 포함 PG 통합 테스트는 `requires_pg` skip(11건 기존). V10 적용은 운영자 `!` 실행 (3-7 Task 1 절차 참조). 본 스토리는 마이그레이션 추가 없음 → 절차 변동 없음

### Git 인텔리전스

- 현재 브랜치 `agentic-3-8` — 3-7(89c7d10) + 멀티 프로바이더 PRICING(2981ae6)이 이미 포함된 작업 브랜치. 그대로 사용
- 커밋 2981ae6에서 PRICING이 멀티 프로바이더 확장 + `LLM_PRICING_OVERRIDES_JSON`/`LLM_PRICING_FALLBACK_MODEL` env 지원 — gpt-4o/gpt-4o-mini 단가 기존재, 본 스토리 PRICING 작업 0
- 워킹트리 미추적 파일 `detection/scripts/verify_story_3_3.sh`는 본 스토리와 무관 — PR에 포함하지 말 것
- 커밋 컨벤션: `feat(detection): ...`, 스토리당 PR 1개, flake8 max-line-length=120 CI parity

### 최신 기술 정보 (2026-06 기준)

- gpt-4o vision + structured outputs(json_schema strict:true) 동시 사용 완전 지원 — IMAGE_SCHEMA에 그대로 적용 가능. 이미지 토큰은 usage.prompt_tokens에 합산되어 기존 `estimate_cost_usd` 경로로 정확 집계
- 이미지 detail 파라미터: `"detail": "low"`는 이미지당 고정 ~85 토큰(고해상 타일 분석 생략) — 스크린샷 판독 품질이 필요하므로 기본 `auto` 유지 권장, 비용 초과 시 3-9 튜닝 항목
- openai>=1.50.0 (기존 pin) 충분 — SDK 업그레이드 불요. `concurrent.futures`는 stdlib — 신규 의존성 0

### Project Structure Notes

- 신규 파일은 `detection/src/agents/image_analyst.py`·`synthesizer.py` — architecture.md 확정 트리 그대로(L593, L596). agents/ 패키지 완성으로 트리와 코드 일치
- 네이밍: 에러 UPPER_SNAKE_CASE, 날짜 ISO 8601 UTC, 로그 correlation_id 필수, parse류 함수 None 반환 금지(예외 raise)
- 충돌 메모: 변경 제안서 비용표(L156)는 S2b에 "mini 요약 $0.0006"을 포함하나 3-7은 규칙 기반으로 구현 + 리뷰 defer — Task 9에서 "S3 직접 소비로 종결" 권장안 채택 시 architecture.md L595의 "gpt-4o-mini 요약" 문구는 follow-up 정리 대상(차이 발견 시 변경 제안서 우선 원칙은 3-7과 동일)

### References

- [Source: _bmad-output/planning-artifacts/epics.md L539-556 (Epic 3 재정의 목표·스토리 배분), L751-771 (Story 3.8 원문 AC)]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-06-11.md L107-137 (5단 파이프라인·에이전트 표), L139-161 (설계 결정·비용 모델·3중 가드), L181 (model_version 확정값), L244-247 (성공 기준)]
- [Source: _bmad-output/planning-artifacts/prd.md L78 (평균 ≤$0.005·p95 ≤$0.02), L266 (이미지 PII 법무 미확정), L426-433 (FR12-A / FR16-NEW-1)]
- [Source: _bmad-output/planning-artifacts/architecture.md L577-599 (agents/ 트리 — image_analyst·synthesizer), L806-815 (파이프라인 도식 + AGENT_POST_BUDGET_USD)]
- [Source: _bmad-output/implementation-artifacts/3-7-멀티-에이전트-오케스트레이터-트리아지-linktracer.md (Dev Agent Record·Review Findings — 통합 지점·defer 항목·재사용 맵)]
- [Source: detection/src/agents/orchestrator.py L112-122 (degrade 교체 지점); detection/src/agents/contracts.py L16-18, L40-57 (AGENT_STAGES·TriageResult); detection/src/pipeline/llm_client.py L84-95 (CLASSIFICATION_SCHEMA), L102-135 (_resolve_image_url), L280-312 (run_structured)]

## Dev Agent Record

### Agent Model Used

claude-fable-5 (BMad dev-story workflow)

### Debug Log References

- 기준선: `detection/.venv/bin/python -m pytest tests -q` → 시작 시 130 PASS / 11 skip
- 완료: **167 PASS / 11 skip** (신규 37: image_analyst 7 + synthesizer 11 + orchestrator 12 + llm_client 3 + link_tracer 1 + 통합 3). 회귀 0. <!-- 리뷰 정정: synthesizer/orchestrator 수치 스왑 -->
- lint(CI parity): `flake8 src tests scripts/smoke_agent_pipeline.py --max-line-length=120` → **clean**
- 실사 agentic smoke(실 OpenAI — S1 gpt-4o-mini + S2a/S3 gpt-4o): `docs/integration-smoke-3-8.md` 캡처 — 5 스테이지 trace, type=핵_치트 tier=T1, S2a가 합성 PNG를 contributes=false로 정직 판정(image_observed=False 연동 확인), S2a∥S2b 병렬(1397ms/442ms), S3 합성 verdict에 증거 인용, 총 $0.01143 ≤ p95 목표 $0.02. PG 미가동으로 저장 경로는 trace까지(V10 PG는 운영자 `!` 실행).

### Completion Notes List

- **S2a ImageAnalyst** (gpt-4o): `LLMClient.run_structured(image_blocks=...)` 위임 — 신규 OpenAI wrapper 없음. `build_image_blocks()` 공개 헬퍼를 llm_client에 신설해 `classify()`와 공유(중복 제거). PII 가드 `LLM_SEND_IMAGES`(기본 false)를 S2a에 동일 적용 — false면 `enabled=False` + orchestrator가 `{"skipped": "LLM_SEND_IMAGES=false"}` trace 기록. resolve 가능한 이미지 0이면 LLM 호출 없이 None(`no_resolvable_images` trace). 도메인 가이드 미주입(이미지 판독에 은어 사전 불요 — 해석은 S3 몫).
- **S3 Synthesizer** (gpt-4o): 출력 스키마는 기존 `CLASSIFICATION_SCHEMA` 그대로(5필드 SSOT, 신규 스키마 0). 증거 우선순위·최상위 Tier 채택 규칙은 system prompt에 명시 — Tier 표는 `TYPE_TO_TIER`/`TIER_PRIORITY`에서 동적 렌더(하드코딩 0). `image_observed`는 S2a `contributes`로 결정론적 덮어쓰기(AC #3 — LLM 자가보고 무시). `translated_text_ko`는 S3 null 시 트리아지 값 fallback. `model` 파라미터로 예산 fallback 모델 1회 지정 가능.
- **오케스트레이터 escalate 재구성**: S2a∥S2b `ThreadPoolExecutor(max_workers=2)` 병렬(AC #2) — trace는 image→link_trace 순서로 결정론적 추가, future별 예외 격리(S2a 실패가 S3를 막지 않음). path 4종: `fast_path | escalate_synthesized | escalate_budget_degraded | escalate_s3_failed_degraded` (+synthesizer 미주입 시 3-7 `escalate_degrade` 하위호환). escalate 전부 S3 경유(링크/이미지 없어도 — 비용 모델 적용률 100%).
- **예산 가드(AC #5, 결정론적)**: `AGENT_POST_BUDGET_USD`(기본 0.02, ≤0 비활성) — 각 LLM stage 착수 직전 누적 실비용(`sum(trace.cost_usd)`) 체크. 초과 시 잔여 stage 스킵 → 트리아지 verdict degrade(수집된 S2a contributes는 verdict에 반영). `SYNTH_FALLBACK_MODEL` opt-in 시 S3만 해당 모델로 1회 시도("S3-mini"). degrade 마커를 `stage=synthesize, output={skipped: budget_exceeded, spent_usd, skipped_stages}`로 agent_runs에 기록(3-9 빈도 집계용). 전수 저장 유지 — 모든 경로에서 save 수행.
- **S3 실패 fallback(AC #6)**: Synthesizer 예외(RateLimitError 포함 광역 catch) → 트리아지 verdict degrade + `output={"error": "<클래스: 요약>"}` 실패 trace. 의도된 결정: S3 실패를 RetryHandler로 전파하지 않음 — 재시도 시 트리아지+S2a 비용이 중복 지출되므로 1차 분류 저장이 우선(AC 문구 그대로).
- **verdict 비용/토큰 = 스테이지 합산**: degrade여도 detections.cost_usd가 실지출 반영(3-9 비용 실측 전제). `cost_cap.record`는 pipeline에서 **trace(모델)별** 수행으로 변경 — mini+4o 혼합에서 단일 모델 단가 적용 오류 방지(single 모드는 기존 단일 record 유지).
- **구조화 로그(AC #7)**: 종결 로그에 path/stage_costs/stage_latency_ms/total_cost_usd/escalated/escalation_rate(+budget_degraded·s3_failed 누적) — correlation_id 포함. 표본 ≥10 ∧ escalation율 >50% 시 `FAST_PATH_CONFIDENCE` 하향 검토 warning(임계 하향 조정 신호).
- **model_version**: `agentic:v1:mini+4o:{YYYY-MM}` (변경 제안서 확정 포맷, 50자 가드) — synthesizer 미주입(3-7 구성) 시 기존 포맷 유지로 기존 테스트 회귀 0.
- **LLMMock 확장**: `run_structured`가 `schema_name`으로 에이전트 분기(`tracker_image_analysis`/`tracker_synthesis`) — 신규 fixture 4종(`mock_image_*`/`mock_synth_*`). 예산 degrade 테스트는 고비용 fixture 대신 극소 예산(`AGENT_POST_BUDGET_USD=0.000001`) 주입으로 동일 검증(스토리 Task 7의 의도 충족, fixture 단순화).
- **[Task 9 결정] 3-7 defer "S2b mini 요약 fallback" 종결 — 불요 채택**: S3(gpt-4o)가 `LinkEvidence.excerpt`(신규 additive 필드, html2text 본문 500자 캡, 캐시 왕복 보존)를 직접 소비하므로 S2b 단계의 별도 gpt-4o-mini 요약 호출은 비용·복잡도만 추가. 변경 제안서 비용표의 S2b mini 요약분($0.0006×1.5)은 S3로 흡수 — 실측 $0.01143/escalate로 여전히 p95 목표 내. architecture.md L595 "gpt-4o-mini 요약" 문구는 follow-up 정리 대상(리뷰 시 인지).
- **[명세 해석] Task 3 "TokenBucket acquire — S1과 동일 규율"**: 3-7 구현에서 agentic 경로는 S1도 TokenBucket을 직접 acquire하지 않음(버킷은 single 모드 LLMClassifier 경로 전용, agentic은 llm_client 자체 429 재시도에 위임). S2a/S3도 동일 규율로 구현 — 비용 통제는 cost_cap(일일) + 예산 가드(게시글당)가 담당. agentic 경로 버킷 통합은 필요 시 별도 follow-up.
- **신규 Flyway 마이그레이션 0**: `image`/`synthesize` stage 값은 V10에 기등록. detections 계약 불변 — 출력 계약 불변 회귀 테스트가 S3 경로 포함 통과(Epic 4 무영향).
- 이미지 소스 의미론: `s3_image_paths or image_urls` — single 모드(`_run_single`)와 동일(merge 아님, s3:// presigned 한계 포함). 의도적 일관성 유지.

### File List

신규:
- `detection/src/agents/image_analyst.py`
- `detection/src/agents/synthesizer.py`
- `detection/tests/unit/test_image_analyst.py`
- `detection/tests/unit/test_synthesizer.py`
- `tests/fixtures/llm/mock_image_clean.json`
- `tests/fixtures/llm/mock_image_illegal.json`
- `tests/fixtures/llm/mock_synth_clean.json`
- `tests/fixtures/llm/mock_synth_illegal.json`
- `docs/integration-smoke-3-8.md`

수정:
- `detection/src/agents/contracts.py` (ImageEvidence 신설 + LinkEvidence.excerpt additive)
- `detection/src/agents/link_tracer.py` (excerpt 추출 + 캐시 직렬화 포함)
- `detection/src/agents/orchestrator.py` (S2a∥S2b 병렬 + S3 + 예산 가드 + escalation 로그)
- `detection/src/pipeline/llm_client.py` (build_image_blocks 공개 헬퍼 + run_structured image_blocks)
- `detection/src/pipeline/detection_pipeline.py` (agentic 이미지 전달 + trace별 cost_cap.record)
- `detection/src/main.py` (ImageAnalyst/Synthesizer wiring)
- `detection/src/mocks/llm_mock.py` (schema_name 분기 + image/synth fixture + image_blocks kwarg)
- `detection/scripts/smoke_agent_pipeline.py` (S0~S3 full wiring + SMOKE_IMAGE + 합성 PNG 폴백)
- `detection/.env.example` (IMAGE_ANALYST_MODEL/SYNTHESIZER_MODEL/AGENT_POST_BUDGET_USD/SYNTH_FALLBACK_MODEL)
- `infra/.env.example` (멀티 에이전트 섹션: DETECTION_MODE/AGENT_POST_BUDGET_USD/SYNTH_FALLBACK_MODEL/LINK_TRACE_PROXY)
- `detection/tests/unit/test_orchestrator.py` (3-8 케이스 12건 추가)
- `detection/tests/unit/test_llm_client.py` (build_image_blocks/run_structured 이미지 3건)
- `detection/tests/unit/test_link_tracer.py` (excerpt 캐시 왕복 1건)
- `detection/tests/integration/test_agent_pipeline.py` (full wiring + escalate 합성/예산/S3 실패 E2E)
