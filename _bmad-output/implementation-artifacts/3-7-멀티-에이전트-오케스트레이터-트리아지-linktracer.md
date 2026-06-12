# Story 3.7: 멀티 에이전트 오케스트레이터 + 트리아지 + LinkTracer

Status: done

<!-- 2026-06-11 Epic 3 재정의(Correct Course) 1차 구현 증분. sprint-change-proposal-2026-06-11.md 승인분. -->

## Story

개발자로서,
큐에서 소비한 게시글이 결정론적 오케스트레이터를 거쳐 정규화 → 트리아지 분류되고, 위험 링크가 1-hop으로 추적되어 증거가 남기를 원한다,
그래서 사이트별 설정 없이 게시글 맥락을 자가 추론하면서 외부 유통 경로까지 증거 기반으로 탐지한다.

> 본 스토리 완료 시 `DETECTION_MODE=agentic`으로 E2E 데모가 성립한다(escalate 경로는 S3 Synthesizer가 없으므로 **트리아지 verdict로 degrade**). LinkTracer는 운영자의 "유통 경로 추적 에이전트" 요청을 1-hop으로 구현한다.

## Acceptance Criteria

**Given** `DETECTION_MODE=agentic` 환경에서 `CrawlEvent`가 소비될 때
**When** `detection/src/agents/orchestrator.py`가 실행되면

1. **S0 `normalizer.py`** (순수 Python, LLM 없음)가 NFKC 정규화·zero-width 제거·변형문자 매핑(ㅎr킹→하킹 등 정적 테이블)·반복문자 축약을 수행하고 markdown에서 `links[]`를 추출한다 (운영자 "텍스트 클린 에이전트" 요청)
2. **S1 `triage_agent.py`** (gpt-4o-mini)가 정규화 텍스트로 `{type, confidence, game_context, reason_ko, translated_text_ko, needs_image, needs_link_trace}`를 산출한다 — `game_context`는 게시글 자체에서 **자가 추론**한다 (FR12-C 라우팅 제거)
3. **사이트→게임 라우팅 제거**: `prompts/registry.py`의 `SOURCE_ID_TO_GAME` 매핑과 `prompts/games/*.md` 게임별 오버레이를 분류 경로에서 제거한다 (라벨 CLI용 매핑은 `scripts/label_detections.py`로 이동, Story 3-5 무영향)
4. **공용 도메인 가이드 유지**: 사이트 비종속 큐레이션 지식(게임 은어 사전 — 外掛/私服/代儲/蝦皮 등 + 오탐 방지 규칙 — 메이플=NEXON 비교군·52pojie=게임 무관 크랙 포럼 등)을 **단일 공용 가이드**(`prompts/domain_guide.md` 또는 동등)로 통합하여 트리아지 프롬프트에 항상 주입한다 — 게임별 파일 분기 없이 모든 게시글에 동일 제공 (FR12-C 도메인 지식 보존). 기존 `games/*.md`의 은어·오탐 규칙을 게임 라벨 없이 병합
5. **FAST PATH**: `type=기타 ∧ confidence≥0.80 ∧ 의심 링크 없음`이면 트리아지 결과를 그대로 최종 verdict로 변환한다 (`image_observed=False`)
6. **S2b `link_tracer.py`**가 escalate ∧ 링크 존재 시 게시글당 최대 3개 링크를 1-hop fetch(httpx + html2text)하여 `LinkEvidence{url, kind, fetch_status, page_title, is_distribution_site, indicators[]}`를 산출한다 (FR12-B)
7. `link_fetch_guard.py`가 (a) http/https + 80/443만 (b) DNS 해석 후 사설/loopback/link-local/메타데이터(169.254.169.254) IP 차단 (c) redirect 매 hop 재검증(최대 3) (d) 응답 512KB 캡 (e) `application/*` content-type 즉시 abort(바이트 폐기, "배포 파일 직링크" 증거만 기록)를 강제한다 — 단위 테스트 ≥8건
8. discord.gg / t.me / open.kakao.com / line.me / qq.com 초대링크는 fetch 없이 `kind=messenger`로 분류한다
9. 동일 URL은 Redis `linktrace:{sha256(url)}` 캐시(TTL 7일)로 재fetch를 방지한다 — 캐시 hit 테스트 포함
10. `LINK_TRACE_PROXY` 환경변수가 설정되면 모든 fetch가 egress 프록시를 경유한다
11. **agent_runs 테이블**(Flyway `V10__agent_runs.sql`, additive)이 추가되고 `detection_repository.py`가 detections + agent_runs를 **동일 트랜잭션**으로 저장한다 (detections 멱등 conflict 시 agent_runs도 skip). detections 테이블 계약은 불변
12. `DETECTION_MODE=single` 폴백이 그대로 동작하여 기존 테스트 회귀 0 + 외부 호출 0 (mock 에이전트로 검증)
13. **출력 계약 불변 회귀 테스트**: agentic 모드가 저장하는 `detections` 행이 single 모드와 동일한 필드 집합(`type, confidence, reason_ko, translated_text_ko, image_observed` + 파생 `tier, is_illegal`)을 채움을 검증하는 테스트가 추가되어, 스키마/DTO(`DetectionResponse`)/프론트(`Detection` 타입) 계약이 깨지면 CI에서 즉시 실패한다 — 백엔드→프론트 무변경 보장 (agent_runs는 별도 테이블, 본 계약에 미포함)
14. 로컬 dev DB drift(수동 V5 상태) 대응: V10 적용 전 flyway baseline/repair 절차를 task 노트에 명시 (Claude 직접 적용 차단 → 운영자 `!` 실행)

[Source: _bmad-output/planning-artifacts/epics.md L723-748 — AC 원문 그대로]

## Tasks / Subtasks

- [x] Task 1: Flyway `V10__agent_runs.sql` 작성 (AC: #11, #14)
  - [x] `api/src/main/resources/db/migration/V10__agent_runs.sql` — 변경 제안서의 DDL 그대로 (아래 Dev Notes "agent_runs V10 DDL" 참조). additive only, detections/posts 기존 테이블 무변경
  - [x] 인덱스: `idx_agent_runs_post_id` (post_id), 필요 시 `idx_agent_runs_correlation` — 조회 패턴은 디버깅/비용 집계용
  - [x] **운영자 실행 절차 노트**: 로컬 dev DB는 수동 V5 상태(flyway 이력 없음, V6~V9 미적용). V10 적용 전 운영자가 `!`로 직접 실행해야 함:
    1. `cd api && ./gradlew flywayInfo` 로 현재 상태 확인
    2. flyway 이력이 없으므로 `flywayBaseline` (baselineVersion=5) 후 `flywayMigrate` 로 V6→V10 순차 적용, 또는 dev DB 재생성 후 V1부터 전체 마이그레이션 (권장)
    3. 적용 후 `\d agent_runs` 로 테이블 확인
  - [x] V10 적용 전까지 agent_runs 저장 경로는 통합 테스트에서 PG-free(mock cursor) 또는 `requires_pg` skip 마커로 격리 (3-5의 conftest 패턴 재사용)
- [x] Task 2: Stage 간 계약 dataclass — `detection/src/agents/contracts.py` (AC: #1, #2, #6)
  - [x] `NormalizedPost{text, links[], removed_chars_count, ...}` (S0 출력)
  - [x] `TriageResult{type, confidence, game_context, reason_ko, translated_text_ko, needs_image, needs_link_trace, input_tokens, output_tokens, cost_usd}` (S1 출력)
  - [x] `LinkEvidence{url, kind, fetch_status, page_title, is_distribution_site, indicators[]}` (S2b 출력) — `kind ∈ {web, messenger, file_direct_link, blocked, error}` 수준의 enum 정의
  - [x] `AgentRunTrace{stage, model, input_tokens, output_tokens, cost_usd, latency_ms, output(dict)}` — agent_runs 1행에 대응. stage 값은 V10 주석과 일치: `normalize|triage|image|link_trace|synthesize`
- [x] Task 3: S0 `detection/src/agents/normalizer.py` (AC: #1)
  - [x] NFKC 정규화(`unicodedata.normalize("NFKC", ...)`) + zero-width(U+200B/200C/200D/FEFF 등) 제거
  - [x] 변형문자 정적 매핑 테이블(ㅎr킹→하킹, 현금화 변형 등 — games/*.md 병합 과정에서 발견되는 변형 패턴을 시드로) + 반복문자 축약(ㅋㅋㅋㅋ→ㅋㅋ 등)
  - [x] markdown 링크 추출: `[text](url)` + bare URL 정규식 → `links[]` (중복 제거, 순서 보존)
  - [x] 단위 테스트: 변형문자/zero-width/링크 추출/빈 텍스트/한·중·영 혼합 케이스
- [x] Task 4: 프롬프트 개편 — 라우팅 제거 + 공용 도메인 가이드 (AC: #3, #4)
  - [x] `prompts/games/*.md` 전부의 은어 사전·오탐 방지 규칙을 게임 라벨 없는 단일 `prompts/domain_guide.md`로 병합 (게임별 헤더 대신 주제별 — 은어 사전 / 오탐 방지 / 거래 패턴)
  - [x] `registry.py`에서 `SOURCE_ID_TO_GAME` + `get_game_overlay()` 분류 경로 제거, `get_domain_guide()` 신설. `SOURCE_ID_TO_GAME` dict 자체는 `scripts/label_detections.py`로 이동 (Story 3-5 라벨 CLI 무영향 확인)
  - [x] `llm_client.py::build_system_prompt()` 시그니처에서 source_id 의존 제거 → `base + type_guidance + domain_guide` 고정 조립 (OpenAI prompt caching을 위해 prefix 안정성 유지 — "\n\n" join 패턴 보존)
  - [x] `games/*.md` 파일 삭제, 기존 `test_prompt_registry.py`의 오버레이 라우팅 테스트를 domain_guide 주입 테스트로 대체 (회귀 0의 의미: 파이프라인 동작 테스트는 무수정 통과, 제거된 기능 전용 테스트만 대체)
- [x] Task 5: S1 `detection/src/agents/triage_agent.py` (AC: #2)
  - [x] 기존 `LLMClient` 재사용 (신규 OpenAI wrapper 작성 금지) — gpt-4o-mini + structured output(json_schema strict) 으로 7필드 트리아지 스키마 호출. 모델명은 `TRIAGE_MODEL` env (기본 `gpt-4o-mini`)
  - [x] 트리아지 응답 검증: type ∈ ALLOWED_DETECTION_TYPES(9종), confidence ∈ [0,1] — `llm_classifier.py`의 가드 패턴 재사용
  - [x] `llm_client.py::PRICING`에 gpt-4o-mini 단가 추가 ($0.15/$0.60 per 1M) — cost_cap.record가 정확한 비용 집계
  - [x] `mocks/llm_mock.py` 확장: 트리아지 모드 응답(7필드) 추가 — `tests/fixtures/llm/mock_triage_*.json` fixture
  - [x] 토큰 버킷: 기존 `llm:rate_limit:classify` 버킷 공유 (호출량 통합 제한)
- [x] Task 6: `detection/src/agents/link_fetch_guard.py` — SSRF 가드 (AC: #7)
  - [x] `validate_url(url) -> GuardDecision`: 스킴 http/https만, 포트 80/443만(명시 포트 포함 검증), hostname → `socket.getaddrinfo` 해석 후 **모든** 해석 IP에 대해 차단 판정
  - [x] IP 차단 로직: `ipaddress` 모듈 — `is_private | is_loopback | is_link_local` + **명시 추가 차단**: 100.64.0.0/10(CGNAT — is_private=False 함정), IPv6 `::ffff:` mapped 주소는 `ipv4_mapped`로 언랩 후 재검사, fc00::/7
  - [x] DNS rebinding 완화: 해석된 IP로 직접 접속하도록 검증 시점 IP를 고정(pinned IP + Host 헤더/SNI 유지) — 불가 시 차선책으로 fetch 직전 재해석·재검증하고 한계를 docstring에 명시
  - [x] redirect: `follow_redirects=False` + 수동 루프 최대 3 hop, **매 hop Location을 validate_url로 재검증**
  - [x] 응답: streaming(`client.stream` + `iter_bytes`)으로 512KB 캡 (초과 시 절단·기록), `Content-Type: application/*` 즉시 abort + `kind=file_direct_link` 증거화
  - [x] 단위 테스트 ≥8건: ① 사설 IP(10.x/192.168.x) ② loopback(127.0.0.1, ::1) ③ 메타데이터(169.254.169.254) ④ CGNAT(100.64.x) ⑤ IPv6 mapped(::ffff:127.0.0.1) ⑥ 비허용 포트(:8080)/스킴(ftp) ⑦ redirect로 사설 IP 진입 시도 차단 ⑧ 512KB 초과 절단 ⑨ application/octet-stream abort — 네트워크 mock(httpx MockTransport 또는 monkeypatch)으로 외부 호출 0
- [x] Task 7: S2b `detection/src/agents/link_tracer.py` (AC: #6, #8, #9, #10)
  - [x] 게시글당 최대 3개 링크 (S0 추출 순서 우선), 각각: messenger 도메인 판정 → 캐시 조회 → guard 검증 → httpx 1-hop fetch → html2text 본문 추출 → `LinkEvidence` 구성
  - [x] messenger 도메인(discord.gg / t.me / open.kakao.com / line.me / qq.com — 서브도메인 포함 suffix 매칭)은 fetch 없이 `kind=messenger` + indicators=["비공개 채널 유도"]
  - [x] `is_distribution_site`/`indicators[]` 판정: 1차는 규칙 기반(다운로드 버튼/판매 가격/연락처 패턴 키워드) — gpt-4o-mini 요약 호출은 page_title+발췌 텍스트가 규칙으로 판정 불가할 때만 (비용 절감; 호출 시 cost_cap.record + AgentRunTrace에 비용 기록)
  - [x] Redis 캐시: key `linktrace:{sha256(url)}`, value=LinkEvidence JSON, TTL 7일(604800s). **DB1(dedup) 사용**, 키 상수는 `shared/config/redis_config.py`에 `REDIS_KEY_LINKTRACE_PREFIX` 추가 (`{도메인}:{역할}` 컨벤션). 캐시 hit 시 fetch 0회 검증 테스트
  - [x] `LINK_TRACE_PROXY` 설정 시 `httpx.Client(proxy=...)` 경유. `LINK_TRACE_TIMEOUT_SEC`(기본 5) 적용
  - [x] fetch 실패(타임아웃/4xx/5xx/guard 차단)는 예외 전파 금지 — `fetch_status`에 기록하고 다음 링크 진행 (링크 추적 실패가 게시글 분류를 막으면 안 됨)
  - [x] `requirements.txt`에 `html2text` 추가 (httpx는 기존 의존성)
- [x] Task 8: `detection/src/agents/orchestrator.py` + DETECTION_MODE 분기 (AC: #5, #12)
  - [x] 결정론적 순수 Python (LangChain/LLM 라우팅 금지): S0 → S1 → [FAST PATH 판정] → (escalate 시) S2b → **degrade 종결**(S3 부재 — 트리아지 결과를 최종 verdict로, S2b 증거는 agent_runs에만 기록). `needs_image=True` 신호는 trace에 기록만 (S2a는 Story 3-8)
  - [x] FAST PATH 조건: `type=기타 ∧ confidence≥0.80 ∧ S0 links[] 중 의심 링크 없음` → 트리아지 결과 그대로 verdict (`image_observed=False`). 임계값 0.80은 `FAST_PATH_CONFIDENCE` env로 추출 (Story 3-9 튜닝 대비)
  - [x] 반환: `(LLMResponse 호환 verdict, list[AgentRunTrace])` — verdict는 기존 5필드 스키마로 변환해 tier_router/repository 기존 경로에 그대로 투입
  - [x] `detection_pipeline.py`에 `DETECTION_MODE=single|agentic` 분기 (기본 `single`): single이면 기존 `llm_classifier.classify` 경로 무수정, agentic이면 orchestrator 호출. retry_handler/cost_cap/tier_router/correlation_id 전파는 두 모드 공통
  - [x] `model_version` 포맷: agentic 모드는 `agentic:v1:mini+4o:2026-06` 형식 (VARCHAR(50) 이내) — single 모드와 (post_id, model_version) 유니크가 분리되어 Story 3-9 A/B 공존 가능
  - [x] `main.py` wiring + `.env.example`에 신규 env 5종 추가 (DETECTION_MODE / TRIAGE_MODEL / FAST_PATH_CONFIDENCE / LINK_TRACE_PROXY / LINK_TRACE_TIMEOUT_SEC)
- [x] Task 9: `detection_repository.py` agent_runs 동일 트랜잭션 확장 (AC: #11)
  - [x] `save(event, response, tier, model_version, agent_runs: list[AgentRunTrace] | None = None)` — 기존 시그니처 하위호환 (single 모드 무수정 동작)
  - [x] 동일 connection/transaction에서: sources UPSERT → posts UPSERT → detections INSERT(ON CONFLICT DO NOTHING) → **detections RETURNING id가 있을 때만** agent_runs batch INSERT(detection_id, post_id FK) — conflict(중복 재처리) 시 agent_runs도 skip
  - [x] agent_runs.output JSONB에 스테이지 출력 전문(LinkEvidence 포함), correlation_id 컬럼 채움. 파라미터화 SQL 필수
- [x] Task 10: 테스트 — 출력 계약 불변 + 통합 (AC: #12, #13)
  - [x] `tests/unit/`: test_normalizer / test_triage_agent(mock) / test_link_fetch_guard(≥8) / test_link_tracer(캐시 hit·messenger·실패 격리)
  - [x] `tests/integration/test_agent_pipeline.py`: fakeredis + llm_mock으로 agentic E2E — fast path 케이스 / escalate+링크 케이스 / degrade 종결 케이스. 외부 네트워크·실제 Redis·실제 OpenAI 0
  - [x] **출력 계약 불변 회귀 테스트**: 동일 입력에 대해 single·agentic 두 모드가 저장하는 detections 행의 필드 집합(type, confidence, reason_ko, translated_text_ko, image_observed + tier, is_illegal)이 동일함을 assert — repository.save 호출 캡처 비교 방식 (PG 불요)
  - [x] 기존 테스트 전체 회귀 0 확인 (3-5 시점 PG-free 63 PASS 기준선 + 본 스토리 신규)
- [x] Task 11: 실사 smoke + 문서 (AC: #12 데모 성립 확인)
  - [x] `scripts/smoke_agent_pipeline.py`: 실 OpenAI gpt-4o-mini 1건 — seed_one_post 패턴 재사용, agentic 모드로 S0→S1→(escalate 시 S2b)→저장까지, 비용·스테이지 trace 출력 (V10 적용된 DB 필요 — 운영자 `!` 실행)
  - [x] `docs/integration-smoke-3-7.md`에 캡처 (3-3/3-4 관례)

### Review Findings

<!-- 2026-06-11 적대적 코드 리뷰 (Blind Hunter / Edge Case Hunter / Acceptance Auditor 3-layer). dismiss 8건 제외. patch 9건 전부 적용 완료 — 118 PASS/11 skip + flake8 clean 재검증. -->

- [x] [Review][Patch] `_messenger_kind` 중복 조건 제거 — `host == s`가 boolean 식에 두 번 등장 (dead code) [detection/src/agents/link_tracer.py:65]
- [x] [Review][Patch] `_cache_get` 손상 캐시 방어 — `json.loads`/`LinkEvidence(**data)` 실패 시 예외 대신 캐시 miss(None) 처리. 현재는 손상 엔트리가 TTL 7일 동안 해당 URL을 `kind=error`로 고착시킴 [detection/src/agents/link_tracer.py:188-196]
- [x] [Review][Patch] 캐시 연산 Redis 장애 격리 — `_cache_put`(및 `_cache_get`의 redis.get) 예외가 전파되면 이미 수집한 fetch evidence가 `trace()` catch에서 `kind=error`로 대체됨. 캐시 실패는 warning 로그 후 evidence 그대로 반환 [detection/src/agents/link_tracer.py:188-204]
- [x] [Review][Patch] 4xx/5xx 상태 코드를 본문 streaming **전에** 검사 — 현재 에러 응답도 512KB까지 소비 후 폐기 [detection/src/agents/link_tracer.py:160-170]
- [x] [Review][Patch] `_resolve_all_ips`의 `except socket.gaierror` → `except OSError`로 확대 — getaddrinfo는 gaierror 외 OSError 계열도 발생 가능, 미포착 시 가드가 error 경로로 빠짐 [detection/src/agents/link_fetch_guard.py:68-71]
- [x] [Review][Patch] `REDIS_KEY_LINKTRACE_PREFIX` 상수를 `shared/config/redis_config.py`에 추가하고 link_tracer가 import — Task 7 명세 항목인데 `_CACHE_PREFIX = "linktrace:"` 하드코딩으로 구현됨 [detection/src/agents/link_tracer.py:33]
- [x] [Review][Patch] `model_version`의 `LLM_MODEL_RELEASE_DATE` `.strip()` 처리 — 공백 포함 시 (post_id, model_version) 유니크 키와 3-9 A/B 비교가 보이지 않게 깨짐 [detection/src/agents/orchestrator.py:54-57]
- [x] [Review][Patch] `_extract_title` 함수 내부 `import re` → 모듈 상단 이동 [detection/src/agents/link_tracer.py:208]
- [x] [Review][Patch] `removed_char_count` 주석 정정 — 실제로는 길이 감소량 근사(1:1 변형문자 치환은 미집계). "변경된 문자 수" 표현이 과대 기술 [detection/src/agents/contracts.py:36]
- [x] [Review][Defer] Task 7 "규칙 판정 불가 시 gpt-4o-mini 요약 fallback" 미구현 [detection/src/agents/link_tracer.py:68-78] — deferred, 현 규칙 엔진은 항상 boolean 판정을 산출해 "판정 불가" 트리거가 정의되지 않음. 3-8 Synthesizer의 증거 소비 설계와 함께 결정
- [x] [Review][Defer] DNS rebinding TOCTOU 잔여 리스크 — `validate_url` 해석 IP와 httpx 실제 접속 IP 간 핀 미적용(코드에 2차 방어로 문서화됨). IP-핀 transport 또는 운영 `LINK_TRACE_PROXY` egress 정책으로 보완 [detection/src/agents/link_fetch_guard.py:84-90] — deferred, 문서화된 설계 결정

## Dev Notes

### 스코프 경계 — 반드시 지킬 것

| 포함 (3-7) | 제외 (이월처) |
|---|---|
| 오케스트레이터 + S0 + S1 + fast path | S2a ImageAnalyst, S3 Synthesizer → **3-8** |
| S2b LinkTracer + link_fetch_guard + 캐시 | `AGENT_POST_BUDGET_USD` 게시글당 예산 가드 → **3-8** |
| agent_runs V10 + repository 트랜잭션 확장 | A/B 정확도 비교·비용 실측·임계 튜닝 → **3-9** |
| DETECTION_MODE=single\|agentic 토글 | T1 알림 → **3-10** |
| SOURCE_ID_TO_GAME 라우팅 제거 + domain_guide 통합 | few-shot 주입(Stage 2-B)·multi-hop·retention job → deferred-work |

- escalate 경로의 최종 verdict는 **트리아지 결과로 degrade** (S3 부재). S2b 증거는 agent_runs.output에만 남는다 — 3-8에서 S3가 이 증거를 소비.
- 일일 비용 cap(기존 `cost_cap.py` $5)은 그대로 동작시키되, 게시글당 예산 가드는 구현하지 말 것 (3-8 범위).
- multi-hop fetch 금지 — 1-hop만 (FR12-B). 파일 다운로드 금지.

### 파이프라인 구조 (변경 제안서 확정 설계)

```
CrawlEvent (posts:queue — 계약 불변)
 ▼ S0 normalizer (순수 Python, $0): NFKC·변형문자·zero-width + links[] 추출
 ▼ S1 triage_agent (gpt-4o-mini, 전 게시글, ~$0.0004): 7필드 + 게임 자가 추론
 ├─ FAST PATH (기타 ∧ conf≥0.80 ∧ 의심 링크 없음) → 트리아지 = 최종 verdict
 └─ ESCALATE → S2b link_tracer (1-hop, 최대 3링크) → [3-7에선 degrade: 트리아지 verdict 채택]
 ▼ tier_router.route(type) → cost_cap.record(스테이지 합산) → repository.save(+agent_runs)
```

오케스트레이션은 결정론적 plain Python — LangChain 등 도입 금지 (2.5주 타임라인 + 데모 신뢰성 + 기존 RetryHandler/TokenBucket/CostCap 부품 재사용 결정) [Source: sprint-change-proposal-2026-06-11.md L140-145].

### agent_runs V10 DDL (변경 제안서 확정안 — 그대로 사용)

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
```

링크 fetch 결과는 별도 테이블 없이 `agent_runs.output` JSONB에 내장 [Source: sprint-change-proposal-2026-06-11.md L163-180]. Flyway 파일명 컨벤션 `V{순번}__{설명}.sql` (언더스코어 2개), 위치 `api/src/main/resources/db/migration/` (현재 최신 V9) [Source: architecture.md L227, L486].

### 데이터 계약 (불변 — 절대 변경 금지)

- **입력** `shared/models/crawl_event.py::CrawlEvent`: post_id, source_id, site_name, raw_text, language, detected_at(ISO 8601), correlation_id, image_urls[], s3_text_path, s3_image_paths[], post_url — Epic 2 crawler 계약, 무변경
- **출력** `shared/interfaces/llm.py::LLMResponse` 5필드 {type, confidence, reason_ko, translated_text_ko, image_observed} + 파생 tier, is_illegal — Epic 4 API `DetectionResponse`/프론트 `Detection` 타입이 의존. detections 테이블 스키마 V5 그대로 (V10은 agent_runs 신규 테이블만)
- type enum 9종: 핵_치트/사설서버/불법프로그램_배포/계정_거래/매크로_판매/리세마라/현금화/광고_도배/기타 (`ALLOWED_DETECTION_TYPES`)
- detections 멱등성: `(post_id, model_version)` UNIQUE (V3) — agentic은 별도 model_version으로 single과 공존 (3-9 A/B 전제)
- is_illegal 파생 규칙은 현 repository 로직 유지 (`tier != "T4"`)

### 기존 코드 재사용 맵 (바퀴 재발명 금지)

| 재사용 대상 | 위치 | 3-7에서의 사용 |
|---|---|---|
| `LLMClient` (structured output, 이미지, 비용 계산) | `pipeline/llm_client.py` | S1이 위임 호출 — 신규 OpenAI wrapper 금지. PRICING에 gpt-4o-mini만 추가 |
| `TokenBucket` (Lua atomic) | `rate_limit/token_bucket.py` | S1 호출 전 acquire — 기존 `llm:rate_limit:classify` 키 공유 |
| `CostCap.record()` | `rate_limit/cost_cap.py` | 스테이지별 LLM 호출마다 record (S1 + S2b 요약 호출 시) |
| `RetryHandler` | `retry/retry_handler.py` | S1 LLM 호출 감싸기 (기존 화이트리스트). LinkTracer fetch는 재시도 대상 아님 — 실패는 fetch_status 기록 후 진행 |
| `TierRouter` | `pipeline/tier_router.py` | 최종 verdict type → Tier, 무수정 |
| `DetectionRepository.save()` 트랜잭션 패턴 | `repository/detection_repository.py` | agent_runs batch INSERT를 같은 트랜잭션에 추가 (시그니처 하위호환) |
| `LLMMock` + fixtures | `mocks/llm_mock.py`, `tests/fixtures/llm/` | 트리아지 모드 추가 — 통합 테스트 외부 호출 0 유지 |
| conftest `db_pool`/`clean_db`/PG-free skip | `tests/conftest.py` | V10 미적용 로컬 DB 대응 (3-5에서 검증된 패턴) |
| 구조화 로깅 + correlation_id | `shared/` | 모든 스테이지 로그에 correlation_id 필수 (안티패턴: correlation_id 없는 로그) |

### 프롬프트 개편 상세 (FR12-C)

현재: `build_system_prompt(source_id)` = base + `type_guidance.md`(Stage 2-A) + `games/{SOURCE_ID_TO_GAME[source_id]}.md`(Stage 1 오버레이) [Source: llm_client.py L60, registry.py L20/L75].

변경: **(1) 라우팅 제거** — SOURCE_ID_TO_GAME 분기 삭제, 새 사이트 추가 시 detection 설정 변경 0. **(2) 지식 보존** — games/*.md의 은어(外掛=핵/외부프로그램, 私服=사설서버, 代儲=대리충전, 蝦皮=쇼피 거래 등)·오탐 규칙(메이플=NEXON 게임 비교군일 뿐, 52pojie=게임 무관 크랙 포럼 등)을 게임 라벨 없는 단일 `domain_guide.md`로 병합해 **모든** 게시글에 항상 주입. "어느 게임인가"는 S1이 추론하되 "그 생태계 지식"은 잃지 않는다 [Source: prd.md FR12-C L428-429].

- single 모드 폴백도 같은 조립(base+type_guidance+domain_guide)을 사용 — 분류 경로 전체에서 사이트 종속 제거. 기존 오버레이 라우팅 전용 테스트는 대체하고, 파이프라인 동작 테스트는 무수정 통과해야 함
- few-shot(`prompts/examples/*.jsonl`)은 주입하지 않음 — Stage 2-B는 deferred (Story 3-5가 수집만, 주입은 이월)
- `scripts/label_detections.py`는 SOURCE_ID_TO_GAME을 자체 보유하게 이동 — Story 3-5 라벨 CLI 동작 무영향 확인 필수

### SSRF 가드 구현 가이드 (보안 critical — 웹 리서치 반영)

- httpx는 기본적으로 redirect를 따르지 않음 — 그 기본값을 유지하고 수동 루프에서 매 hop `validate_url` 재검증 (자동 follow_redirects=True 절대 금지: redirect 기반 SSRF 우회의 주 벡터)
- `ipaddress.is_private` 함정 2가지를 명시적으로 보완: ① 100.64.0.0/10(CGNAT)은 is_private=False — 수동 차단 ② IPv6 `::ffff:127.0.0.1` 같은 IPv4-mapped는 `addr.ipv4_mapped`로 언랩 후 재검사 (is_loopback이 mapped 주소에서 False 반환하는 stdlib 동작 확인됨)
- DNS rebinding(검증→접속 사이 재바인딩): httpx에 IP 핀 내장 기능 없음 — `getaddrinfo` 해석 IP로 직접 접속(URL host를 IP로 교체 + `Host` 헤더/SNI에 원 hostname 유지)이 정공법. 구현 복잡도가 과하면 fetch 직전 재해석·재검증으로 완화하고 한계를 docstring에 기록 (1-hop·512KB·텍스트만이라 위험 표면이 작음)
- 바이트 캡: `client.stream(...)` + `iter_bytes()` 누적 카운터로 512KB 절단 — httpx에 내장 응답 크기 제한 없음. `Content-Length` 헤더만 믿지 말 것
- 대학/가정 IP에서 불법 배포 사이트 방문 리스크 → `LINK_TRACE_PROXY`(NodeMaven egress 재사용) 경유. 바이너리 비다운로드 + 텍스트 발췌·해시만 저장. `infra/DATA_POLICY.md` 문서화는 PM 병행 트랙 [Source: sprint-change-proposal-2026-06-11.md L238]

### 비용 모델 (Story 3-9 실측의 기준선)

| 스테이지 | 모델 | 호출당 비용 | 적용률 |
|---|---|---|---|
| S0 | — | $0 | 100% |
| S1 triage | gpt-4o-mini | ~$0.00042 | 100% |
| S2b link | fetch $0 (+mini 요약 ~$0.0006×1.5) | escalate의 ~50% |

gpt-4o-mini 단가 $0.15/$0.60 per 1M (PRICING 추가값). PRD 목표: 평균 ≤$0.005, p95 ≤$0.02 — 측정은 3-9, 본 스토리는 agent_runs.cost_usd로 측정 가능한 데이터를 남기는 것까지 [Source: sprint-change-proposal-2026-06-11.md L148-160, prd.md L70-83].

### 신규 환경변수 (.env.example 반영)

| 변수 | 기본값 | 용도 |
|---|---|---|
| `DETECTION_MODE` | `single` | single\|agentic 분기 (데모 당일 아침 A/B 결과로 선택 — 기본은 안전한 single) |
| `TRIAGE_MODEL` | `gpt-4o-mini` | S1 모델 |
| `FAST_PATH_CONFIDENCE` | `0.80` | fast path 임계 (3-9 튜닝 대비 env 추출) |
| `LINK_TRACE_PROXY` | (없음) | 설정 시 모든 fetch가 egress 프록시 경유 |
| `LINK_TRACE_TIMEOUT_SEC` | `5` | httpx 타임아웃 |

`AGENT_POST_BUDGET_USD`는 3-8 범위 — 본 스토리에서 읽지 말 것.

### 테스트 표준

- unit/integration 분리, 외부 네트워크·실제 Redis·실제 OpenAI 0 (fakeredis + LLMMock + httpx MockTransport)
- 기준선: 3-5 시점 PG-free 63 PASS — 회귀 0 필수. crawler/api 코드 무변경 (V10 SQL 파일 추가만)
- PG 필요한 repository 테스트는 conftest `requires_pg` 패턴으로 skip 가능하게 — 로컬 dev DB drift 때문에 V10 적용 전에도 나머지 테스트가 전부 돌아야 함
- 실사 smoke는 별도 스크립트(테스트 아님) + docs 캡처 — 3-3(`docs/integration-smoke-3-3.md`)/3-4 관례

### 이전 스토리 인텔리전스 (3-3/3-4/3-5)

- **3-3**: llm_client의 RateLimitError는 RetryHandler가 catch하지 않음(호출자 책임) — S1에서도 동일 계약 유지. 429 1회 자체 재시도 후 2회째 raise 패턴이 llm_client에 이미 있음
- **3-4**: repository는 B안(detection이 posts UPSERT + detections INSERT 한 트랜잭션) — agent_runs는 이 트랜잭션 뒤에 자연 확장. psycopg3 `make_conninfo` password escape 이슈 기해결. ON CONFLICT DO NOTHING + RETURNING id로 conflict 판정 (id 없으면 skip)
- **3-5**: 로컬 dev DB 수동 V5 드리프트 — save() 기반 통합 테스트는 마이그레이션 적용 후에만 정식 통과. PG-free 테스트 설계를 우선하는 패턴이 검증됨. 운영자 `!` 실행 절차를 스토리에 명시하는 관례 확립
- 실사 smoke(실 OpenAI 1건 + 비용 출력)를 dev 완료 조건에 포함하는 관례 — 3-7도 동일 (Tracker MVP의 본질은 "실사 통합 작동")

### Git 인텔리전스

- 현재 브랜치 `feat/detection-per-game-prompts` — Stage 0~2 조립식 프롬프트 인프라(registry.py, games/*.md, type_guidance.md)가 이 브랜치에서 구현됨. **본 스토리가 그중 게임별 라우팅을 제거**하므로, 같은 브랜치에서 이어가기보다 develop 기준 신규 브랜치(`feat/story-3-7-agentic-orchestrator` 등) 분기 검토 — 단 per-game prompts 작업이 미머지 상태면 운영자와 머지/리베이스 순서 합의 필요
- 워킹트리의 `llm_classifier.py` 수정(L65-69 메모 제거 + import 복구)은 Correct Course 부수 결정 — 본 스토리 PR에 포함
- 최근 패턴: 스토리당 PR 1개, 리뷰 3-layer(Blind/Edge/Auditor), 커밋 메시지 `feat(detection): ...`

### 최신 기술 정보 (2026-06 기준)

- httpx 0.28.x (이미 의존성), html2text 2025.4.15 활성 유지보수 중 — **requirements.txt에 html2text 추가 필요**
- gpt-4o-mini는 structured outputs(json_schema strict:true) 완전 지원 — 기존 CLASSIFICATION_SCHEMA 방식 그대로 트리아지 스키마에 적용 가능
- openai>=1.50.0 (기존 pin) 으로 충분 — SDK 업그레이드 불요

### Project Structure Notes

- 신규 디렉터리 `detection/src/agents/` — architecture.md 확정 트리: orchestrator.py / normalizer.py / triage_agent.py / link_tracer.py / link_fetch_guard.py / contracts.py (+ image_analyst.py·synthesizer.py는 3-8) [Source: architecture.md L577-631]
- link_fetch_guard.py는 `agents/` 안 (scripts/ 아님 — 단위 테스트 격리 대상 소스 모듈)
- Redis 키 컨벤션 `{도메인}:{역할}`: `linktrace:` prefix, 상수는 shared/config/redis_config.py에 등록
- 네이밍: DB snake_case 복수형(agent_runs), 에러 UPPER_SNAKE_CASE, 날짜 ISO 8601 UTC, 로그 correlation_id 필수, parse류 함수 None 반환 금지(예외 raise)
- 충돌 메모: architecture.md L595는 link_tracer에 "gpt-4o-mini 요약"을 언급, 변경 제안서 L143은 "fetch (no LLM) + 요약" — 본 스토리는 규칙 기반 우선 + 필요 시 mini 요약(Task 7)으로 절충. 차이 발견 시 변경 제안서가 우선

### References

- [Source: _bmad-output/planning-artifacts/epics.md L539-541 (Epic 3 목표), L723-748 (Story 3.7 원문 AC)]
- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-06-11.md L55-66 (스토리 배분), L108-145 (파이프라인·오케스트레이션 설계), L148-160 (비용 모델·3중 가드), L163-180 (agent_runs DDL·model_version), L237-243 (리스크·성공 기준)]
- [Source: _bmad-output/planning-artifacts/prd.md L425-435 (FR12/FR12-A/B/C), L70-83 (비용·Recall 목표), L479-492 (NFR11/NFR14)]
- [Source: _bmad-output/planning-artifacts/architecture.md L577-631 (detection 트리), L806-823 (파이프라인 도식), L330-497 (네이밍·안티패턴), L404-414 (구조화 로그)]
- [Source: detection/src/pipeline/llm_client.py L60 (build_system_prompt), L81 (CLASSIFICATION_SCHEMA); detection/src/prompts/registry.py L20 (SOURCE_ID_TO_GAME); detection/src/repository/detection_repository.py L47 (save 트랜잭션); shared/interfaces/llm.py (LLMResponse·9종 enum)]
- [Source: _bmad-output/implementation-artifacts/deferred-work.md (multi-hop·few-shot 주입·T2/T3 알림·retention 이월 항목)]

## Dev Agent Record

### Agent Model Used

claude-fable-5 (BMad dev-story workflow)

### Debug Log References

- 기준선: `detection/.venv/bin/python -m pytest detection/tests -q` → 시작 시 72 PASS / 8 skip
- 완료: **118 PASS / 11 skip** (신규 11 skip은 V10·agent_runs 포함 PG-required 통합 테스트 — 로컬 PG 미가동으로 skip). 회귀 0.
- lint(CI parity): `flake8 src tests --max-line-length=120` → **clean**. 부수로 워킹트리의 `llm_classifier.py` 끝 개행 누락(W292) 복구.
- 실사 agentic smoke(실 gpt-4o-mini): `docs/integration-smoke-3-7.md` 캡처 — type=핵_치트 tier=T1, escalate→degrade, link_trace 2건(404 격리/messenger skip), 비용 $0.00052(목표 ≤$0.005 충족), 3 스테이지 trace.

### Completion Notes List

- **S0 normalizer** (순수 Python, $0): NFKC + zero-width 제거 + 키릴 동형 글리프 매핑 + 반복문자 축약 + markdown/bare 링크 추출. NFKC가 호환 자모(ㅋ→ᄏ)를 결합 자모로 바꾸는 표준 동작을 테스트가 반영.
- **S1 triage_agent** (gpt-4o-mini): `LLMClient.run_structured` 재사용(신규 OpenAI wrapper 없음 — `_create_with_retry` 추출로 분류/트리아지 단일 진입점 공유). 7필드 스키마 + type/confidence 방어 검증. gpt-4o-mini 단가는 기존 PRICING에 존재.
- **프롬프트 라우팅 제거(FR12-C)**: `SOURCE_ID_TO_GAME`+`games/*.md` 분류 경로 제거 → 단일 공용 `domain_guide.md`로 은어·오탐 지식 병합(7개 게임 파일에서 통합). 매핑은 `scripts/label_detections.py`로 SSOT 이동(labelset_snapshot/build_fewshot_corpus가 거기서 import — Story 3-5 무영향). `build_system_prompt`는 source_id 비의존.
- **SSRF 가드(보안 critical)**: `ipaddress.is_private` 함정 2종 명시 보완(CGNAT 100.64/10, IPv4-mapped `::ffff:` 언랩). 스킴/포트 화이트리스트 + DNS 전체 IP 검사 + redirect 매 hop 재검증 + 512KB 캡 + application/* abort. 단위 14건(요구 ≥8).
- **S2b LinkTracer**: httpx 수동 redirect 루프(follow_redirects=False) + html2text + 규칙 기반 지표 + Redis `linktrace:{sha256}` 캐시(TTL 7일, DB1) + messenger fetch-free + `LINK_TRACE_PROXY`. fetch 실패 격리(예외 전파 금지). transport 주입으로 MockTransport 테스트(네트워크 0).
- **오케스트레이터**: 결정론적 FSM(LangChain 없음) S0→S1→(fast path | escalate→degrade). S2a/S3/예산 가드는 Story 3-8 범위로 제외 — escalate는 트리아지 verdict로 degrade, S2b 증거는 agent_runs에만. `model_version=agentic:v1:{model}:{YYYY-MM}`로 single과 분리(3-9 A/B 공존).
- **DETECTION_MODE 분기**: `detection_pipeline.py` single|agentic, 기본 single. retry/cost_cap/tier_router/correlation_id 두 모드 공통. single 경로·기존 테스트 회귀 0.
- **repository agent_runs**: `save(..., agent_runs=None)` 하위호환. detections 신규 행일 때만 동일 트랜잭션 `executemany` INSERT(멱등 conflict 시 trace도 skip). detections 스키마/계약 불변.
- **출력 계약 불변 회귀 테스트**: single vs agentic이 동일 LLMResponse 5필드 + 동일 save 키 + 동일 tier 파생을 채움을 assert — DTO/프론트 계약 깨지면 CI 즉시 실패.
- **V10**: `api/.../V10__agent_runs.sql` additive(CREATE TABLE/INDEX IF NOT EXISTS). 로컬 dev DB drift 대응 운영자 절차는 Task 1 노트 + smoke 문서에 명시(Claude 직접 적용 차단).
- 의존성: `html2text>=2024.2.26` 추가(requirements.txt). httpx/openai 기존 pin 충분.

### File List

신규:
- `detection/src/agents/__init__.py`
- `detection/src/agents/contracts.py`
- `detection/src/agents/normalizer.py`
- `detection/src/agents/triage_agent.py`
- `detection/src/agents/link_fetch_guard.py`
- `detection/src/agents/link_tracer.py`
- `detection/src/agents/orchestrator.py`
- `detection/src/prompts/domain_guide.md`
- `detection/scripts/smoke_agent_pipeline.py`
- `api/src/main/resources/db/migration/V10__agent_runs.sql`
- `docs/integration-smoke-3-7.md`
- `detection/tests/unit/test_normalizer.py`
- `detection/tests/unit/test_triage_agent.py`
- `detection/tests/unit/test_link_fetch_guard.py`
- `detection/tests/unit/test_link_tracer.py`
- `detection/tests/unit/test_orchestrator.py`
- `detection/tests/integration/test_agent_pipeline.py`

수정:
- `detection/src/pipeline/llm_client.py` (`_create_with_retry`/`run_structured` 추출, build_system_prompt → domain_guide)
- `detection/src/pipeline/llm_classifier.py` (끝 개행 복구 — 워킹트리 부수)
- `detection/src/pipeline/detection_pipeline.py` (DETECTION_MODE 분기 + agent_runs 전달)
- `detection/src/repository/detection_repository.py` (save agent_runs 트랜잭션 확장)
- `detection/src/prompts/registry.py` (라우팅 제거 → get_domain_guide)
- `detection/src/mocks/llm_mock.py` (run_structured 추가)
- `detection/src/main.py` (agentic orchestrator wiring)
- `detection/src/config/redis_config.py` (get_dedup_client)
- `detection/scripts/label_detections.py` (SOURCE_ID_TO_GAME SSOT 이동)
- `detection/scripts/labelset_snapshot.py` (import 경로)
- `detection/scripts/build_fewshot_corpus.py` (import 경로 + 주석)
- `detection/requirements.txt` (html2text)
- `detection/.env.example` (DETECTION_MODE/TRIAGE_MODEL/FAST_PATH_CONFIDENCE/LINK_TRACE_* 추가)
- `detection/tests/unit/test_prompt_registry.py` (domain_guide 검증으로 대체)
- `detection/tests/unit/test_llm_client.py` (오버레이 테스트 → domain_guide 테스트 대체)
- `detection/tests/integration/test_detection_repository.py` (agent_runs PG 테스트 추가)
- `tests/fixtures/llm/mock_response_clean.json`, `mock_response_illegal.json` (트리아지 7필드 추가)

삭제:
- `detection/src/prompts/games/{aion,bns,cracking_forum,lineage,lineage_mobile,mixed_mobile,tl}.md` (domain_guide.md로 병합)
