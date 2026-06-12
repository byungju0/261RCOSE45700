---
title: Sprint Change Proposal — Epic 3 재정의: 멀티 에이전트 탐지 아키텍처
date: 2026-06-11
author: Tracker (with BMad Correct Course workflow)
status: approved
workflow: bmad-correct-course
mode: Batch
related_pivots:
  - 2026-05-27 Epic 3 LLM 아키텍처 전면 재설계 (VARCO 3단 → OpenAI 멀티모달 단일 호출 + Tier)
  - 2026-05-19 Epic 2 crawler 전면 재작성
scope_classification: Major (PM/Architect — 본 문서 Section 5 참조)
---

# Sprint Change Proposal — Epic 3 재정의: 멀티 에이전트 탐지 아키텍처 (2026-06-11)

## Section 1. Issue Summary

### 트리거
2026-06-11, Epic 3 진행 중(Story 3-3/3-5 review, 3-6 backlog) 운영자가 다음 방향 전환을 요청:

> "현재 AI로 detection하는 구조를, 크롤러가 수집해온 데이터에 따라 여러 agent로 나누고 싶다. 게시물에 위험한 이미지·텍스트 링크가 있으면 그걸 따라 추적하는 agent, 게시물 텍스트를 클린하는 agent 등 **불법 프로그램의 구조에 맞게** agent를 나눠서, **최대한 사이트에 구애받지 않고 새 사이트를 넣어도 적응**할 수 있도록, **키워드 기반을 최대한 제거**해서 구상해달라."

### 핵심 문제 정의 (유형: 전략적 pivot — 실패한 접근이 아닌 능력 확장)
현 단일 OpenAI 멀티모달 호출 구조(2026-05-27 PIVOT 산물)는 동작하나 세 가지 한계가 있다:

1. **단일 호출의 표현력 한계** — 게시글 본문·이미지·링크를 한 번의 호출로 동시 판단하므로, "이 링크가 실제로 배포 페이지인가"처럼 **추가 증거 수집이 필요한 케이스**를 처리하지 못한다. 불법 프로그램 게시글은 본문에 미끼만 두고 디스코드·텔레그램·외부 다운로드 링크로 유도하는 구조가 흔하다.
2. **사이트 종속성이 detection에 잔존** — `SOURCE_ID_TO_GAME` 매핑 + `prompts/games/*.md` 7개 오버레이는 크롤러 site_id에 의존한다. 새 사이트를 추가하면 detection 측에 매핑·오버레이를 손으로 추가해야 적응한다.
3. **비용·정확도 trade-off가 단일 노브** — 모든 게시글에 동일 gpt-4o 호출. 명백한 무관 게시글(대다수)과 의심 게시글을 같은 비용으로 처리한다.

### 발견 경위 / 부가 사실
- `detection/src/pipeline/llm_classifier.py` 65-69행에 운영자의 구상 메모(평문 한국어: "어떤 프로그램 / 핵이 유통되는 경로 / 불법 프로그램 구매 경로 / 크롤러 양을 최대한 늘려라 / 코드를 짜는 게 아니라 결과로 스크립트 자동화 중심")가 코드 뒤에 삽입되어 **모듈이 SyntaxError로 import 불가** 상태였다. 이 메모의 의도(유통·구매 경로 추적, 스크립트 자동화 중심)는 본 제안의 **링크 추적 에이전트 + 결정론적 오케스트레이터** 설계에 반영되었으며, 코드 파일은 import 가능 상태로 복구한다.

### 운영자 확정 결정 (Correct Course 인터뷰)
1. **Epic 3 전면 재정의** — 신규 Epic 분리가 아니라 Epic 3 잔여 스토리를 멀티 에이전트 기준으로 재편. 기존 단일 호출 분류기는 새 구조의 **1차 트리아지 에이전트**로 강등. 데모는 새 아키텍처로 수행.
2. **링크 추적 = 1-hop fetch만** — 게시글 내 링크의 HTML/텍스트를 1단계만 fetch해 분석. 파일 다운로드 금지. 디스코드·텔레그램 초대링크는 메타데이터만.
3. **사이트 비종속화는 detection 한정** — **(라우팅 제거)** `SOURCE_ID_TO_GAME`/게임 오버레이 파일 선택을 분류 경로에서 제거하고 에이전트가 게시글 자체에서 게임·맥락을 추론. **(도메인 지식 보존)** 단, 사이트에 종속되지 않는 큐레이션 지식(게임 은어 사전·오탐 방지 규칙)은 **단일 공용 도메인 가이드**로 모든 게시글에 항상 제공 — "어느 게임인가"는 추론하되 "그 생태계 지식"은 잃지 않는다(순수 추정 시 틈새 중문 거래 용어 누락·메이플 오탐 risk 회피). 크롤러의 `title_keywords`·per-site validator는 비용 절감 프리필터로 **유지**.
4. **Batch 모드** — 전체 변경안을 본 제안으로 일괄 제시.

---

## Section 2. Impact Analysis

### Epic 영향

| Epic | 상태 | 영향 |
|------|------|------|
| Epic 1 | done | 영향 없음 |
| Epic 2 | in-progress | **영향 없음** — CrawlEvent 계약 불변, 크롤러 무수정 (사이트 비종속화는 detection 한정) |
| **Epic 3** | **in-progress (재정의 대상)** | **잔여 스토리 전면 재편 — 본 제안의 주 범위** |
| Epic 4 | done | **영향 없음** — `detections` 테이블 계약 불변. `model_version`은 단순 문자열 컬럼이라 신규 값(`agentic:...`)이 대시보드/API에 무영향. agent_runs는 별도 테이블 (대시보드 미참조) |
| Epic 5 | in-progress | 경미 — escalation율·스테이지 비용 메트릭이 Story 5-1 Prometheus에 추가 가능 (backlog, 본 제안 강제 아님) |

### Epic 3 스토리별 변경

| Story | 변경 전 | 변경 후 |
|-------|---------|---------|
| **3.1** | done (Redis 큐 소비자 + Watchdog) | **변경 없음** — 오케스트레이션 무관, 큐/DLQ/watchdog 그대로 |
| **3.2** | deprecated (VARCO Translation) | 변경 없음 (이미 폐기) |
| **3.3** | review (OpenAI 멀티모달 단일 호출 + Tier) | **트리아지 에이전트로 흡수.** 단일 호출 코드(`llm_client.py`, structured output, 이미지 처리)는 S1 TriageAgent + S3 Synthesizer의 모태로 재활용. `DETECTION_MODE=single` 폴백으로 보존 |
| **3.4** | done (RDS 저장 + 스키마) | **변경 없음** — detections 테이블 계약 불변. agent_runs는 신규 V10으로 additive 확장 |
| **3.5** | review (few-shot 라벨 수집) | **변경 없음** — 수집된 라벨 코퍼스를 신규 3-9 A/B 정확도 비교의 ground truth로 활용 |
| **3.6** | backlog (Tier 알림 + 보존) | **폐기.** 알림 시스템이 이미 완성돼 있음(백엔드 `notification_*` 4테이블 + `NotificationEventProcessor` 5초 폴링 + 채널 6종 + 룰 엔진 `minTier` 필터 + 프론트 3탭 UI + detection의 `notification_events` 적재). T1 알림은 `minTier=T1` 룰 설정만으로 동작 → 신규 구현 불필요. E2E 검증은 3-9에 흡수 |
| **3.7 (신규)** | — | LinkTracer 1-hop + SSRF 가드 + agent_runs(V10) |
| **3.8 (신규)** | — | ImageAnalyst + Synthesizer + 게시글당 예산 가드 |
| **3.9 (신규)** | — | 신·구 아키텍처 A/B 정확도 비교(3-5 라벨 코퍼스) + 비용 실측 + 데모 리허설 + T1 알림 E2E 검증(기존 시스템) |
| ~~**3.10**~~ | — | **폐기 (2차).** 기존 알림 시스템 중복 — `t1_notifier.py` 신규 구현 불필요. 검증만 3-9에 흡수. 사람 리뷰 큐는 deferred |

> **참고 (2026-06-11 2차 갱신):** 초안에서 구 3.6을 "T1 알림(축소) → 3-10"으로 잡았으나, 조사 결과 알림 시스템이 이미 end-to-end로 완성돼 있어 **3-10을 폐기**하고 T1 알림 E2E 검증만 3-9에 흡수한다. 에이전트 골격은 신규 **3.7~3.9** 3개로 확정. (Section 4 / sprint-status 참조)

### 산출물 충돌 및 갱신

#### PRD (`prd.md`)
- **AI 탐지 FR (L418-430)**: FR12 유지(분류 의미 동일) + **FR12-A 신규**(다단계 에이전트 차등 분석) + **FR12-B 신규**(1-hop 링크 증거 추적 + 안전 가드) + **FR12-C 신규**(탐지 사이트 무관성). FR16-NEW-2는 T1 즉시 알림만 본 기수 범위 명시, FR16-NEW-3 retention defer 명시.
- **Success Criteria (L78)**: 게시글당 비용에 "평균 ≤ $0.005, **p95 ≤ $0.02**" 추가.
- **What Makes Special / Innovation / MVP (L31, L132, L234, L422)**: "단일 호출" 표현을 "다단계 에이전트(트리아지 → 조건부 심층 분석 → 증거 통합)"로 갱신. 단, 멀티모달 분석 능력 자체는 유지.

#### Architecture (`architecture.md`)
- **L577-608 detection/ 디렉터리 트리**: `agents/` 서브패키지 신설(orchestrator/normalizer/triage_agent/image_analyst/link_tracer/link_fetch_guard/synthesizer/contracts), `pipeline/`은 모드 분기 진입점으로 유지.
- **L782-796 데이터 흐름 도식**: 단일 호출 단계를 에이전트 파이프라인 5단으로 교체.
- detections 테이블/Redis 키 계약 불변 명시 + agent_runs(V10) 추가.

#### Epics (`epics.md`)
- **L539-705 Epic 3 detail**: 재정의 PIVOT 헤더 + Story 3-3 트리아지 흡수 노트 + Story 3-6 폐기(알림 시스템 기완성) + Story 3-7/3-8/3-9 신규 AC(3-9에 T1 알림 E2E 검증 흡수).

#### Sprint Status / Deferred Work
- `sprint-status.yaml`: 변경 로그 코멘트 + 3-7/3-8/3-9 backlog 등록 + 3-6 범위 축소.
- `deferred-work.md`: multi-hop / few-shot 주입 / T2·T3 알림 / 90일 retention / 대시보드 증거 패널 이월.

#### 코드베이스 영향 (참고 — 실 구현은 승인 후 별도 스토리 사이클)
- `detection/src/agents/` — 신규 패키지 (8개 모듈)
- `detection/src/pipeline/detection_pipeline.py` — `DETECTION_MODE` 분기 진입점으로 수정
- `detection/src/pipeline/llm_classifier.py` — 메모 제거 복구 + 트리아지 에이전트로 흡수
- `detection/src/prompts/registry.py` — `SOURCE_ID_TO_GAME` 분류 경로 제거 (라벨 CLI용 매핑은 `scripts/label_detections.py`로 이동), `prompts/games/*.md` 제거
- `detection/src/repository/detection_repository.py` — agent_runs 트랜잭션 확장
- `api/.../db/migration/V10__agent_runs.sql` — 신규
- `infra/.env.example` — `DETECTION_MODE`, `AGENT_POST_BUDGET_USD`, `LINK_TRACE_PROXY` 추가
- `infra/DATA_POLICY.md` — 1-hop fetch 정책 추가

---

## Section 3. Recommended Approach

### 선택된 path: **Direct Adjustment (Epic 3 내 스토리 재편)**

기존 Epic 구조를 유지한 채 잔여 스토리를 재편하고 신규 스토리를 추가한다. 완료된 인프라(큐/DLQ/watchdog/RetryHandler/TokenBucket/CostCap/repository)와 단일 호출 코드를 **재활용**하므로 rollback 불필요.

### 설계 핵심 — 비용 차등 5단 에이전트 파이프라인

```
CrawlEvent (Redis posts:queue — 계약 불변)
   │
   ▼ S0 Normalizer (순수 Python, $0)
   │    NFKC·zero-width 제거·변형문자 매핑(ㅎr킹→하킹)·markdown에서 links[] 추출
   ▼ S1 TriageAgent (gpt-4o-mini, 전 게시글, ~$0.0004)
   │    게임/도메인 자가 추론(per-game 오버레이 대체) + 9-type 1차 분류
   │    + 번역(translated_text_ko) + escalation 신호(needs_image / needs_link_trace)
   │
   ├── FAST PATH: type=기타 ∧ conf≥0.80 ∧ 의심 링크 없음 ──┐
   │   (트리아지 결과를 그대로 최종 verdict로 채택)         │
   ▼ ESCALATE                                            │
   ├─ S2a ImageAnalyst (gpt-4o, 이미지 有시) ─┐           │
   ├─ S2b LinkTracer (1-hop, httpx, $0 fetch) ┤ (병렬)     │
   ▼ S3 Synthesizer (gpt-4o, 증거 통합 최종 판정) ◄───────┘
   │    출력: 기존 5필드 스키마 {type, confidence, reason_ko,
   │           translated_text_ko, image_observed} 그대로
   ▼
TierRouter → CostCap.record(스테이지 합산) → DetectionRepository.save
                                          └→ agent_runs (V10, 신규 테이블)
```

| # | 에이전트 | 모델 | 호출 조건 | 단일 책임 |
|---|---------|------|----------|----------|
| S0 | Normalizer | 없음 (Python) | 전 게시글 | 변형문자 정규화 + 링크 추출 (텍스트 클린 에이전트 = 운영자 요청) |
| S1 | TriageAgent | gpt-4o-mini | 전 게시글 | 게임 맥락 자가 추론 + 1차 9-type 분류 + 번역 + escalation 판단 |
| S2a | ImageAnalyst | gpt-4o | escalate ∧ 이미지 존재 | 핵 UI/배너/워터마크/연락처 판독 |
| S2b | LinkTracer | fetch 없음 + gpt-4o-mini 요약 | escalate ∧ 링크 존재 | 1-hop 링크 추적 → 배포 사이트 판정 (유통 경로 추적 에이전트 = 운영자 요청) |
| S3 | Synthesizer | gpt-4o | escalate 전 경로 | 본문 + 트리아지 + 이미지/링크 증거 통합 → 최종 verdict |

### 핵심 설계 결정 및 정당화

1. **오케스트레이션 = 결정론적 plain Python** (LangChain·LLM 라우팅 기각)
   - 2.5주 타임라인 / 데모 신뢰성("10건 실시간 탐지"에서 라우팅이 실패 모드가 되면 안 됨) / 비용 통제(escalation 규칙이 코드에 있어야 예산 강제 가능) / 기존 RetryHandler·TokenBucket·CostCap이 이미 프레임워크 역할 수행.
2. **사이트 비종속화** = `SOURCE_ID_TO_GAME` 라우팅을 S1의 `game_context` 자가 추론으로 대체(라우팅 제거). 게임별 오버레이의 은어·오탐 규칙은 게임 라벨 없는 **단일 공용 도메인 가이드**로 병합해 트리아지에 항상 주입(지식 보존). 새 사이트는 detection 설정 변경 0으로 동작.
3. **LinkTracer** = httpx + html2text (crawl4ai/Chromium 기각 — detection 컨테이너에 Playwright 의존 추가 과대 + JS 실행 안전 리스크). SSRF 가드(사설 IP/redirect 재검증/512KB 캡/Content-Type 가드), `application/*` 응답은 즉시 abort하되 "배포 파일 직링크 존재"를 증거로 기록, 메신저 링크는 fetch 없이 메타데이터화, Redis 7일 캐시, `LINK_TRACE_PROXY` egress 프록시(대학/가정 IP로 불법 사이트 방문 회피).
4. **detections 테이블 불변** — Epic 4 대시보드 호환의 핵심. agent traces는 신규 `agent_runs`(V10)에 격리. `model_version=agentic:v1:...`로 구·신 결과가 DB에서 공존 → A/B 비교 무료.
5. **`DETECTION_MODE=single|agentic` 폴백 유지** — 데모 당일 아침까지 A/B 결과로 모드 선택 가능. 정확도 회귀 시 즉시 회귀.

### 비용 모델
SPIKE 3.0 베이스라인 단일 gpt-4o = $0.0019/건.

| 스테이지 | 모델 | 호출당 | 적용률 |
|---|---|---|---|
| S0 | — | $0 | 100% |
| S1 Triage | 4o-mini | $0.00042 | 100% |
| S2a Image | gpt-4o | $0.0058 | escalate의 40% |
| S2b Link | 4o-mini | $0.0006×1.5링크 | escalate의 50% |
| S3 Synth | gpt-4o | $0.0080 | escalate 전부 |

- escalation 25% → 평균 ~$0.0030 / 35%(기준) → ~$0.0040 ✅ ≤$0.005 / 50%(악화) → ~$0.0056 ⚠️
- **3중 가드레일**: (a) 기존 일일 cap $5, (b) 게시글당 `AGENT_POST_BUDGET_USD=0.02`(초과 시 잔여 stage 스킵 → degrade 종결), (c) escalation율 모니터(50% 초과 지속 시 fast-path 임계 하향).
- **PRD 목표**: 평균 ≤$0.005 유지 + "p95 ≤$0.02" 추가(escalate 게시글 꼬리 비용 명시).

### 데이터 모델 변경 — V10 (additive only)
```sql
CREATE TABLE agent_runs (
    id            BIGSERIAL PRIMARY KEY,
    detection_id  BIGINT REFERENCES detections(id) ON DELETE CASCADE,
    post_id       BIGINT NOT NULL REFERENCES posts(id),
    stage         VARCHAR(20) NOT NULL,   -- normalize|triage|image|link_trace|synthesize
    model         VARCHAR(50),            -- NULL = LLM 미사용 스테이지
    input_tokens  INT NOT NULL DEFAULT 0,
    output_tokens INT NOT NULL DEFAULT 0,
    cost_usd      NUMERIC(10,6) NOT NULL DEFAULT 0,
    latency_ms    INT,
    output        JSONB,                  -- 스테이지 출력 전문 (링크 fetch 결과 내장)
    correlation_id VARCHAR(100),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_agent_runs_detection ON agent_runs(detection_id);
```
링크 fetch 결과는 별도 테이블 없이 `agent_runs.output` jsonb에 내장. `model_version`은 `agentic:v1:mini+4o:2026-06`(33자, VARCHAR(50) 적합). 로컬 dev DB가 수동 V5 drift 상태이므로 V10 적용 전 flyway baseline 정리를 Story 3-7 task로 명시.

### 대안 검토 (기각)
- **신규 Epic 6 분리**: 운영자가 "Epic 3 재정의" 명시. 기각.
- **multi-hop 추적**: 안전·anti-bot 리스크 + 타임라인. 1-hop으로 한정, multi-hop은 defer.
- **LangChain/LLM 라우팅 오케스트레이터**: 위 정당화 1번. 기각.
- **crawler까지 사이트 비종속화**: LLM 전수 호출로 비용 급증 + Epic 2 재작업. 운영자가 "detection만" 명시. 기각.

### 추정 노력 / 리스크 / 일정
- 3-7(LinkTracer+V10) 3-4d / 3-8(Image+Synth+예산) 3-4d / 3-9(A/B+리허설+T1 알림 E2E 검증) 2-3d. 구 3-6/3-10(T1 알림)은 기존 시스템으로 충족되어 신규 구현 0d
- 총 ~2.5주 (3인 병행). **3-7만으로 agentic E2E 데모 성립** (escalate는 트리아지 verdict로 degrade).
- Risk: Medium — 타임라인 압축이 주 리스크. `DETECTION_MODE=single` 폴백으로 데모 실패 모드 차단.

---

## Section 4. Detailed Change Proposals

본 섹션의 PRD/architecture/epics/sprint-status/deferred-work 편집은 **본 제안과 동시에 파일에 반영 완료**되었다. 아래는 추적용 요약.

### 4.1 PRD (반영 완료)
- FR12-A/B/C 신규 (다단계 에이전트 / 1-hop 링크 추적 / 사이트 무관성)
- FR16-NEW-2 본 기수 범위를 T1 즉시 알림으로 한정, T2/T3 defer 명시
- Success Criteria 게시글당 비용에 p95 ≤$0.02 추가
- What Makes Special / Innovation / MVP "단일 호출" → "다단계 에이전트" 갱신 (멀티모달 능력은 유지)

### 4.2 Architecture (반영 완료)
- detection/ 디렉터리 트리에 `agents/` 패키지 + agent_runs(V10)
- 데이터 흐름 도식 5단 에이전트 파이프라인으로 교체
- detections 테이블/Redis 키 계약 불변 + Epic 4 호환 명시

### 4.3 Epics (반영 완료)
- Epic 3 재정의 PIVOT 헤더
- Story 3-3 트리아지 흡수 노트, Story 3-6 폐기(알림 시스템 기완성), Story 3-10 폐기
- Story 3-7(LinkTracer+V10) / 3-8(Image+Synth+예산) / 3-9(A/B+리허설) 신규 AC

### 4.4 Sprint Status / Deferred Work (반영 완료)
- 변경 로그 코멘트 + 3-7/3-8/3-9 backlog 등록 + 3-6 범위 축소
- defer 항목 이월

### 4.5 코드 (선행 복구만 — 나머지는 스토리 사이클)
- `llm_classifier.py` 65-69행 메모 제거 → import 가능 상태 복구 (메모 의도는 본 제안에 보존)

---

## Section 5. Implementation Handoff

### Scope Classification: **Major**
근거: detection 아키텍처 패러다임 전환(단일 호출 → 멀티 에이전트) + 사이트 비종속화 + 신규 외부 행위(링크 fetch) + PRD FR 신설.

### 라우팅
- **Primary owner**: PM / Solution Architect (본 제안 승인 + 링크 fetch 안전·법무 검토)
- **Implementation owners**:
  - **AI 담당(일드매)**: 3-7 오케스트레이터+트리아지 골격, 3-8 ImageAnalyst+Synthesizer, 3-9 A/B 측정
  - **백엔드(최병주)**: V10 마이그레이션 + detection_repository agent_runs 트랜잭션 확장 + (선택) 대시보드 증거 패널 follow-up
  - **인프라/운영(박재성)**: LinkTracer SSRF 가드 + `LINK_TRACE_PROXY` 셋업 + escalation율/비용 메트릭 + 기존 알림 시스템 `minTier=T1` 룰 설정·배포 env(`NOTIFICATION_ENCRYPTION_KEY`) 확인(신규 구현 아님)
- **QA**: Story 3-5 라벨 코퍼스로 3-9 A/B ground truth 제공

### 외부 의존 / 미해결
1. **링크 fetch 안전·법무** — 불법 배포 사이트를 대학/가정 IP로 방문하는 리스크. `LINK_TRACE_PROXY` egress 프록시(크롤러 NodeMaven 재사용 권고) + 바이너리 무다운로드 + 텍스트 발췌+해시만 저장 + `infra/DATA_POLICY.md` 문서화.
2. **로컬 dev DB drift** — 수동 V5 상태. V10 전 flyway baseline 정리 필요 (Claude 직접 적용 차단 → 운영자 `!` 실행).
3. **escalation 임계 초기값** — 3-9 실측으로 fast-path 임계(0.80) 튜닝.

### 성공 기준
- 3-7: 1-hop 링크 증거가 SSRF 가드·캐시와 함께 동작, trace가 RDS에 기록, agentic E2E 데모 성립. **출력 계약 불변 회귀 테스트 통과**(detections 5필드 = single 모드 동일, DTO/프론트 무변경 CI 가드).
- 3-8: escalate 전 경로 완성, 게시글당 예산 강제, S3 실패 시 트리아지 fallback 저장.
- 3-9: 신·구 A/B agreement/Tier별 Recall 비교표 + 평균 비용 ≤$0.005 실측 + "10건 실시간" 리허설 통과.
- T1 알림: 기존 백엔드 알림 시스템 + `minTier=T1` 룰로 agentic 탐지가 채널에 발송됨을 3-9에서 E2E 검증(신규 구현 없음). 사람 리뷰 큐는 deferred.

### 다음 단계
1. 본 제안 승인 → sprint-status.yaml의 3-7을 `ready-for-dev`로 이동.
2. create-story → dev-story 사이클로 3-7부터 착수 (별도 컨텍스트 권장).
3. 링크 fetch 안전·법무 검토는 PM 책임으로 병행.

---

## 부록 A. Checklist (BMad Correct Course)

| Section | Status | Notes |
|---------|--------|-------|
| §1 Trigger context | [x] Done | 트리거 + 운영자 비전 + llm_classifier 메모 반영 + 4개 확정 결정 |
| §2 Epic impact | [x] Done | Epic 1-5 영향 표 + Story별 변경 (Epic 2/4 무영향 검증) |
| §3 Artifact conflicts | [x] Done | PRD / Architecture / Epics / Sprint Status / 코드베이스 |
| §4 Path forward | [x] Done | Direct Adjustment — 정당화 + 비용 모델 + 데이터 모델 + 대안 기각 |
| §5 Proposal components | [x] Done | Issue / Impact / Approach / Detailed Changes / Handoff |
| §6 Final review | [x] Done | 운영자 승인 (plan mode 승인) — 산출물 편집 동시 적용 |

## 부록 B. 관련 PIVOT 메모 체인

| 날짜 | PIVOT | 본 재정의와의 관계 |
|------|-------|-----------------|
| 2026-05-19 | Epic 2 crawler 전면 재작성 | CrawlEvent 계약 안정 — 본 재정의가 의존하는 입력 계약 |
| 2026-05-27 | Epic 3 VARCO → OpenAI 멀티모달 단일 호출 | 본 재정의의 직전 단계 — 단일 호출이 트리아지로 강등 |
| **2026-06-11** | **Epic 3 멀티 에이전트 재정의 (본 제안)** | **현재** |
