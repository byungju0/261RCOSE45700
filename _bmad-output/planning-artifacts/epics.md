---
stepsCompleted: ['step-01-validate-prerequisites', 'step-02-design-epics', 'step-03-create-stories', 'step-04-final-validation']
status: complete
completedAt: '2026-04-25'
inputDocuments:
  - '_bmad-output/planning-artifacts/prd.md'
  - '_bmad-output/planning-artifacts/architecture.md'
---

# Tracker - Epic Breakdown

## Overview

This document provides the complete epic and story breakdown for Tracker, decomposing the requirements from the PRD and Architecture requirements into implementable stories.

## Requirements Inventory

### Functional Requirements

FR1: 시스템은 지정된 커뮤니티 사이트(tailstar.net, PTT, Dcard, tieba.baidu.com, 52pojie.cn, bbs.nga.cn — 최대 6개, 연결 성공 확인 분)를 1시간 주기로 자동 크롤링할 수 있다
FR2: 시스템은 bot 탐지 우회 기술을 사용하여 대상 사이트의 차단 없이 게시글을 수집할 수 있다
FR3: 시스템은 Cloudflare JS 챌린지가 적용된 사이트를 우회하여 수집할 수 있다
FR4: 시스템은 게시글 본문 텍스트와 첨부 이미지를 함께 수집할 수 있다
FR5: 시스템은 수집한 원본 데이터(텍스트+이미지)를 아카이브 스토리지에 보관할 수 있다
FR6: 담당자는 특정 사이트에 대해 즉시 크롤링을 수동으로 실행할 수 있다
FR7: 시스템은 수집된 HTML에서 광고·네비게이션을 제거하고 본문·제목·이미지 URL을 추출할 수 있다
FR8: 시스템은 게시글의 언어(한국어/중국어/번체)를 자동으로 감지할 수 있다
FR9: 시스템은 이미 처리된 게시글을 해시 기반으로 식별하여 중복 처리를 방지할 수 있다
FR10: 시스템은 불법 프로그램 관련 키워드 사전으로 관련 게시글 후보를 1차 선별할 수 있다
FR11: 시스템은 중국어·번체 게시글을 한국어로 자동 번역할 수 있다
FR12: 시스템은 게시글의 불법 여부와 유형(매크로 판매/핵 배포/계정 거래/리세마라/기타)을 자동 분류할 수 있다
FR13: 시스템은 각 탐지 결과에 신뢰도 점수(0~1)를 산출할 수 있다
FR14: 시스템은 탐지 결과와 함께 불법 판단 근거 텍스트를 생성할 수 있다
FR15: 시스템은 탐지 처리 실패 시 자동 재시도하고, 3회 실패 시 격리 큐로 이동시킬 수 있다
FR16: 시스템은 외부 AI API 호출량을 제어하여 할당량 초과를 방지할 수 있다
FR17: 담당자는 탐지된 게시글 목록을 조회할 수 있다
FR18: 담당자는 탐지 목록을 날짜·사이트·탐지 유형·언어로 필터링할 수 있다
FR19: 담당자는 탐지 목록을 신뢰도 기준으로 정렬할 수 있다
FR20: 담당자는 특정 탐지 게시글의 원문·번역문·탐지 유형·신뢰도·판단 근거를 상세 조회할 수 있다
FR21: 담당자는 탐지 상세 화면에서 원본 게시글 URL로 직접 이동할 수 있다
FR22: 시스템은 설정된 신뢰도 임계값 이상의 탐지 결과만 목록에 노출할 수 있다
FR23: 담당자는 오늘의 총 탐지 수와 전일 대비 증감을 조회할 수 있다
FR24: 담당자는 탐지 유형별 분포를 조회할 수 있다
FR25: 담당자는 사이트별 탐지 건수 분포를 조회할 수 있다
FR26: 담당자는 주간·월간 탐지 추이 차트를 조회할 수 있다
FR27: 담당자는 언어별 탐지 분포를 조회할 수 있다
FR28: 시스템은 크롤링 파이프라인을 지정된 시간 간격으로 자동 실행하며, 간격을 재배포 없이 변경할 수 있다
FR29: 시스템은 크롤링 및 탐지 파이프라인의 실행 상태를 모니터링할 수 있다
FR30: 시스템은 처리 실패한 메시지를 격리하고 운영자에게 알람을 발송할 수 있다
FR31: QA 담당자는 수동 라벨링 테스트셋으로 탐지 정확도(Precision/Recall)를 측정할 수 있다
FR32: 시스템은 크롤링 완료 후 5분 이내에 탐지 결과를 대시보드에 반영할 수 있다

### NonFunctional Requirements

NFR1: `GET /detections` API 응답 시간 ≤ 500ms (p95 기준, RDS 인덱스 정상 상태)
NFR2: 대시보드 초기 로드 시간 ≤ 3초 (Chrome 데스크톱, 사내망 기준)
NFR3: 1회 배치(크롤링 → 전처리 → VARCO 탐지 → RDS 저장) 완료 시간 ≤ 30분
NFR4: 크롤링 완료 후 대시보드 탐지 결과 반영 지연 ≤ 5분
NFR5: VARCO API 키·AWS 자격증명은 환경 변수로 관리하며 코드 저장소에 노출 금지
NFR6: AWS 자격증명은 EC2 IAM Role 기반으로 관리하며 Access Key 하드코딩 금지
NFR7: RDS 및 Redis는 VPC 내부망에서만 접근 가능하도록 보안 그룹 구성
NFR8: S3 버킷은 퍼블릭 접근을 차단하고 VPC 내 EC2만 접근 허용
NFR9: 수집된 게시글 데이터는 탐지 목적으로만 사용하며 외부 공개 금지
NFR10: 크롤링 파이프라인은 24시간 무중단 자동 실행을 유지한다 (APScheduler 프로세스 재시작 시 다음 주기에 자동 복구)
NFR11: VARCO API 호출 실패 시 자동으로 최대 3회 재시도하며, 3회 초과 시 DLQ로 격리한다
NFR12: DLQ 메시지 누적 시 Grafana 알람이 발생하여 운영자가 5분 이내에 인지할 수 있다
NFR13: EC2 단일 인스턴스 재시작 후 데이터 유실 없이 파이프라인이 재개된다 (S3 원본 아카이브 + Redis AOF 활용)
NFR14: VARCO API rate limit 초과 시 Redis 토큰 버킷으로 자동 대기하며 수동 개입 없이 처리를 재개한다
NFR15: 프록시 프로바이더(ProxyBroker → NodeMaven) 교체 시 `ProxyProvider` 인터페이스 구현체 변경만으로 완료되며 크롤러 핵심 로직 수정이 불필요하다
NFR16: Redis 큐 연산(`BRPOPLPUSH`)은 원자적으로 실행되어 Worker 크래시 시 메시지 유실이 발생하지 않는다
NFR17: 크롤링 스케줄 간격(`CRAWL_INTERVAL_MINUTES`)은 환경 변수 변경만으로 적용되며 재배포가 불필요하다

### Additional Requirements

- **[ARCH-1] 모노레포 초기화:** 모노레포 디렉토리 구조(crawler/, detection/, api/, dashboard/, shared/, infra/, .github/workflows/) 초기화 및 서브시스템별 스캐폴딩 (Python pip, Spring Boot 3.5.0 Initializr, Vite 8 + React-TS)
- **[ARCH-2] Day 1 공유 모듈 (shared/):** `shared/pyproject.toml`, `shared/correlation_id.py`, `shared/models/crawl_event.py`, `shared/interfaces/varco.py`, `shared/config/redis_config.py`, `shared/structured_logger.py` — 3개 서브시스템 구현 시작 전 반드시 완료
- **[ARCH-3] infra/docker-compose.yml:** Redis DB0~3(`appendonly yes`) + PostgreSQL 로컬 환경, dev/prod 오버라이드 분리
- **[ARCH-4] VARCO Mock 서버:** `detection/src/mocks/varco_mock.py` — rate limit 시뮬레이션, 실패 주입, 재시도 검증 지원. 통합 테스트 선행 조건
- **[ARCH-5] Flyway DB 마이그레이션:** `V1__init_schema.sql`(sources/posts/post_images/detections 4개 테이블), `V2__add_indexes.sql`(복합 인덱스 `idx_detections_filter`), `V3__add_unique_detection.sql`(`(post_id, model_version)` unique constraint)
- **[ARCH-6] 구조화 로깅 표준:** Python/Java 전체 서비스에 `{"timestamp","service","correlation_id","level","message"}` JSON 로그 스키마 적용, `SERVICE_NAME` 환경변수 주입
- **[ARCH-7] GitHub Actions CI/CD:** crawler.yml, detection.yml, api.yml, dashboard.yml 4개 독립 워크플로우 — 코드 푸시 시 자동 빌드·배포
- **[ARCH-8] Prometheus + Grafana 모니터링 스택:** API 응답 시간, 에러율, Redis 큐 깊이, DLQ 적재 알람 대시보드 (`infra/prometheus/prometheus.yml`, `infra/grafana/dashboards/tracker.json`)
- **[ARCH-9] 테스트 픽스처 및 크로스 컴포넌트 테스트 루트:** `tests/fixtures/` (HTML 샘플, VARCO mock 응답 JSON 4종, 수동 라벨셋 CSV 100건), `tests/e2e/`, `tests/performance/k6/`, `tests/chaos/`
- **[ARCH-10] APScheduler 중복 실행 방지:** `max_instances`, `misfire_grace_time` 명시 설정, 크롤링 중복 시작 전 Redis dedup 체크

### UX Design Requirements

UX-DR1: 메인 대시보드 화면 — 오늘 총 탐지 수 + 전일 대비 증감 수치, 탐지 유형별 파이 차트(매크로 판매/핵 배포/계정 거래/리세마라/기타), 사이트별 바 차트 표시 (데스크톱 1280px 이상 우선)
UX-DR2: 탐지 목록 화면 — 날짜·사이트·탐지 유형·언어 필터 컴포넌트 + 신뢰도 정렬 + 페이지네이션(offset 기반, page/size 파라미터), TanStack Query 60초 자동 갱신
UX-DR3: 탐지 상세 화면 — 원문 텍스트, 번역문(중국어·번체 원본인 경우), 탐지 유형, 신뢰도 점수, 판단 근거, 출처 URL 외부 링크 버튼 표시
UX-DR4: 통계 화면 — 주간·월간 탐지 추이 라인 차트, 사이트별·언어별 분포 차트 (Recharts 사용)
UX-DR5: 에러 처리 패턴 — ProblemDetail(RFC 9457) 기반 에러 응답 처리, ErrorBoundary 컴포넌트, LoadingSpinner 컴포넌트 공통화
UX-DR6: 라우팅 구조 — React Router v7 기반 `/` (대시보드), `/detections` (목록), `/detections/:id` (상세), `/stats` (통계) URL 구조, 상세 조치 후 목록 복귀 히스토리 지원
UX-DR7: 모바일 지원 (2026-05-13 추가) — Tailwind `md` (768px) breakpoint 기준으로 < 768px 뷰포트에서도 핵심 기능(탐지 목록·상세·수동 크롤링 트리거)을 사용할 수 있어야 한다. Sidebar는 햄버거 → vaul drawer, DetectionList는 카드 뷰, FilterBar는 bottom Drawer. 외부 운영자의 모바일 긴급 조치 시나리오를 지원한다. PRD L233 "모바일 대응은 Growth 단계" / UX Spec L1503 "모바일 햄버거 X" 결정 폐기.

### FR Coverage Map

FR1: Epic 2 — 1시간 주기 자동 크롤링 (APScheduler)
FR2: Epic 2 — bot 탐지 우회 (Playwright+stealth)
FR3: Epic 2 — Cloudflare JS 챌린지 우회 (스파이크 스토리 포함)
FR4: Epic 2 — 게시글 텍스트 + 이미지 수집
FR5: Epic 2 — S3 원본 아카이브
FR6: Epic 2 — 수동 크롤링 트리거 (Redis pub/sub crawl:trigger)
FR7: Epic 2 — HTML 파싱 (광고·네비게이션 제거, 본문·제목·이미지URL 추출)
FR8: Epic 2 — 언어 감지 (한국어/중국어/번체)
FR9: Epic 2 — 중복 해시 (Redis DB1 dedup)
FR10: Epic 2 — 키워드 1차 필터
FR11: Epic 3 — VARCO Translation (중국어·번체 → 한국어)
FR12: Epic 3 — VARCO LLM 불법 분류 (매크로 판매/핵 배포/계정 거래/리세마라/기타)
FR13: Epic 3 — 신뢰도 점수 (0~1)
FR14: Epic 3 — 판단 근거 텍스트 생성
FR15: Epic 3 — DLQ 재시도 (3회 → posts:dlq 격리)
FR16: Epic 3 — VARCO rate limit 토큰 버킷 (Redis DB2)
FR17: Epic 4 — 탐지 게시글 목록 조회 (GET /detections)
FR18: Epic 4 — 날짜·사이트·유형·언어 필터
FR19: Epic 4 — 신뢰도 정렬
FR20: Epic 4 — 탐지 상세 조회 (GET /detections/{id})
FR21: Epic 4 — 원본 게시글 URL 외부 링크
FR22: Epic 4 — 신뢰도 임계값(0.70) 이상만 노출
FR23: Epic 4 — 오늘 총 탐지 수 + 전일 대비 (GET /stats)
FR24: Epic 4 — 탐지 유형별 분포
FR25: Epic 4 — 사이트별 탐지 분포
FR26: Epic 4 — 주간·월간 추이 차트
FR27: Epic 4 — 언어별 탐지 분포
FR28: Epic 2 — CRAWL_INTERVAL_MINUTES 환경변수 기반 스케줄 제어
FR29: Epic 5 — 파이프라인 실행 상태 모니터링 (Prometheus/Grafana)
FR30: Epic 5 — DLQ 알람 (Grafana Alert, 5분 이내 인지)
FR31: Epic 5 — Precision/Recall 측정 (tests/quality/, 수동 라벨셋 ≥200건)
FR32: Epic 4 — 크롤링 완료 후 5분 이내 대시보드 반영 (E2E 파이프라인 검증)

## Epic List

### Epic 1: 프로젝트 토대 및 인프라 구축

개발팀이 Epic 2~4를 병렬로 착수할 수 있는 계약과 환경을 수립한다. 모노레포 초기화, 공유 인터페이스 계약(crawl_event, varco protocol, redis DB 할당), 로컬 개발 환경, VARCO Mock, Flyway 초기 스키마, 테스트 픽스처, CI 기본 파이프라인(lint + unit test)을 포함한다.

> **Party Mode 반영:** CI/CD를 Epic 5에서 Epic 1으로 이동(Winston, Murat). Spring Boot 버전을 3.4.x로 수정(Amelia). VARCO API 실제 엔드포인트/응답 스키마 사전 확보 필수(Amelia).

**FRs covered:** (직접 FR 없음)
**ARCH covered:** ARCH-1, ARCH-2, ARCH-3, ARCH-4, ARCH-5, ARCH-7(기본 CI), ARCH-9
**NFRs covered:** NFR5, NFR6, NFR7, NFR8

---

### Epic 2: 자동 크롤링 및 전처리 파이프라인

시스템이 지정된 커뮤니티 사이트를 1시간 주기로 자동 크롤링하고, 전처리된 게시글 후보를 AI 탐지 큐에 전달한다. **crawl4ai** 라이브러리 기반으로 봇 탐지 우회 + HTML→Markdown 변환 + 이미지 스코어링을 내장 활용한다.

> **Party Mode 반영:** Cloudflare 바이패스 스파이크 스토리를 Epic 2 첫 번째 스토리로 배치(Winston). 크롤러 에러 처리(사이트 다운, rate limit) 명시(Winston). 크롤러 출력 스키마를 Epic 1 계약과 연동(Amelia).
>
> **[2026-04-28 피벗]** SPIKE 2.1 + Story 2.2(Playwright+stealth 골격) 완료 후 **crawl4ai** 라이브러리 전환 확정. PoC에서 crawl4ai가 봇 우회 + HTML→Markdown + 노이즈 필터링 + 이미지 스코어링을 내장 제공함을 검증. 구 `crawler/` 코드(BaseSite/ProxyProvider/StealthBrowser)는 삭제되고 `crawler2/` 코드베이스가 **메인 `crawler/`** 로 승격됨. BaseSite/ProxyProvider 추상화 대신 **SiteConfig 레지스트리** 패턴 채택. NFR15(ProxyProvider 교체 비용)는 crawl4ai의 `BrowserConfig(proxy=...)` 단일 설정으로 대체. Story 2.3부터 crawl4ai 기반 재작성.
>
> **[2026-05-19 PIVOT]** crawler 전면 재작성. `feat/epic-2-crawler-rewrite` 브랜치에서 `crawler/` 디렉터리를 `crawler_test/`의 신규 구현으로 통째 교체 (deleted 103 / modified 10 / added 8). 외부 contract (Redis `posts:queue` 채널, `shared.models.CrawlEvent` 필드, `crawl:trigger` PubSub, `crawler.src.scheduler.crawl_scheduler.__main__` Dockerfile entry, `infra/compose.prod.yml` crawler 서비스) **모두 호환 검증 완료** — api/, detection/, shared/ 영향 0. 142 PASS / 외부 네트워크 0.
> **신규 능력:** `preprocessor/content_validator.py` (본문 품질 8-kind 가드: real/sticky/auth_wall/captcha/empty/short/error/unknown — 위양성 방지), `preprocessor/url_dedup_checker.py` (Redis ZSET cross-run URL dedup, TTL 7일), `preprocessor/serializer.py` (CrawlEvent 직렬화 전담), Bahamut NC 8게임 사이트 분리 (Lineage/M/W/Classic, Aion/Aion2, BNS, TL), `SiteConfig.title_keywords` 사전 필터 (혼합 보드 절감), inter-site / inter-board delay (±25% jitter).
> **제거:** `html_parser.py` (crawl4ai PruningContentFilter 흡수), `keyword_filter.py` (본문 키워드 매칭은 Epic 3 VARCO LLM 위임, 제목 단계는 `SiteConfig.title_keywords` 필드로 이동).
> **흡수 매핑:** 2-1 stealth/anti-bot → `BrowserConfig` 통합 / 2-2 ProxyProvider → `SiteConfig.proxy` 필드 / 2-3 crawl4ai 전처리 → `crawl4ai_crawler.py` + `preprocessor/` / 2-4 S3 → `s3_uploader.py`+`storage.py` / 2-5 APScheduler → `scheduler/crawl_scheduler.py`+`trigger_listener.py` / 2-6·2-7 → `sites/registry.py` SITES dict.
> **신규 서브트랙:** Stories 2-8~2-12 (검색엔진형 어댑터, board-1-hop → search-SERP-2-hop). 신규 추상화 `SearchEngineConfig` 신설. 대상 8 사이트: github, reddit, bing, duckduckgo_cn, baidu, sogou, bilibili, facebook. Epic 3 완료 후 착수 권장. 자세한 정의는 본 Epic 2 하단 "Epic 2 검색엔진 트랙 (Stories 2.8 ~ 2.12)" 섹션 참조.
> **Known issues:** dcard_online `wait_for=css:article` 타임아웃 (단발 fix), ptt_mobile_game·dcard /f/game 1페이지 NC 0건 (페이지네이션 또는 deprioritize), nga·tieba·52pojie 한국 IP HTTP 403 (중국 residential proxy 인프라 선결 트랙).

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR28
**NFRs covered:** NFR10, NFR13(S3), NFR17
**ARCH covered:** ARCH-10

---

### Epic 3: AI 기반 불법 게시글 탐지 파이프라인 (2026-05-27 PIVOT — 전면 재설계)

시스템이 크롤러 큐에서 게시글을 소비하고 **OpenAI 멀티모달 LLM(GPT-4o/4.1) 단일 호출**로 자동 분류하여, 신뢰도·판단 근거·**Tier(T1/T2/T3/T4)**를 포함한 탐지 결과를 RDS에 저장한다. T1 즉시 알림, Tier별 차등 retry/보존 정책 적용. Epic 3 완료 기준에 Tier별 Precision/Recall + 게시글당 평균 비용 측정 포함.

> **2026-05-27 PIVOT (Correct Course).** VARCO Translation + VARCO LLM 2단 파이프라인을 OpenAI 멀티모달 LLM 단일 호출 + Tier 차등 처리로 교체. 핵·사설서버 등 사업 핵심 카테고리 Recall 집중. Story 3-2(VARCO Translation) 폐기, Story 3-3(VARCO LLM) 재작성, Story 3-4/3-5 AC 확장(Tier 필드 + Tier별 측정), 신규 Story 3-6(Tier 알림+보존) + SPIKE 3.0(1일 PoC). 자세한 결정은 `sprint-change-proposal-2026-05-27.md` 참조.
>
> **Party Mode 반영 (이전):** Precision/Recall 사전 측정을 Epic 3 완료 기준에 추가(Murat). 배치 ≤ 30분 측정 포인트 추가. DLQ idempotency 테스트. LLM API 계약 테스트(스키마 변경 대응) — 2026-05-27 PIVOT 후 OpenAI `response_format=json_schema` 핀닝으로 적용.

**FRs covered:** FR12, FR13, FR14, FR15, FR16, FR16-NEW-1, FR16-NEW-2, FR16-NEW-3 (FR11은 2026-05-27 PIVOT 폐기)
**NFRs covered:** NFR3(배치 측정), NFR11(Tier 차등 retry), NFR13(Redis AOF), NFR14(LLM rate limit + 비용 cap), NFR16

---

### Epic 4: 탐지 결과 조회 및 통계 대시보드

보안 담당자가 탐지된 불법 게시글 목록을 필터·정렬로 탐색하고, 상세 화면에서 원본 URL로 즉시 조치하며, 팀장이 주간·월간 통계로 보고 자료를 준비할 수 있다. API 스켈레톤과 대시보드 스켈레톤은 Epic 2~3과 병렬로 시작 가능하다.

> **Party Mode 반영:** API p95 ≤ 500ms 성능 측정을 Epic 4 완료 기준에 포함(Murat). E2E는 핵심 플로우 2~3개만, Component 테스트 우선(Murat). API skeleton을 Epic 2와 병렬 착수 가능(John, Amelia).
>
> **[2026-05-13 PIVOT] 모바일 지원 MVP 편입.** PRD L233 / UX Spec L1503·L1567의 "모바일 out-of-scope, Growth 단계" 결정 폐기. 외부 운영자가 모바일 환경에서도 긴급 조치(원본 URL 점프 + 수동 크롤링 트리거)를 수행해야 한다는 운영 요구. Tailwind `md` (768px) breakpoint를 모바일 분기로 채택. Story 4.7 신설(`feat/dashboard-mobile-support` 브랜치). Epic 4 done → in-progress 회귀.

**FRs covered:** FR17, FR18, FR19, FR20, FR21, FR22, FR23, FR24, FR25, FR26, FR27, FR32
**UX covered:** UX-DR1, UX-DR2, UX-DR3, UX-DR4, UX-DR5, UX-DR6, UX-DR7(모바일 — 2026-05-13 추가)
**NFRs covered:** NFR1, NFR2, NFR4

---

### Epic 5: 시스템 운영, 모니터링 및 품질 관리

운영자가 파이프라인 실행 상태를 Grafana로 실시간 모니터링하고 DLQ 장애에 5분 내 대응하며, QA 담당자가 최종 Precision/Recall(≥0.85/≥0.65)로 탐지 정확도를 검증하고 부하 테스트로 성능 SLA를 확인한다.

> **Party Mode 반영:** chaos 테스트(tests/chaos/)는 3인 팀 일정 리스크로 scope 축소 또는 optional 처리(Amelia). CI는 Epic 1~4에서 점진적으로 구축하고 Epic 5에서 완전 통합(Murat). 픽스처 라벨셋 ≥300건 권고(Murat — 현재 100건은 부족).

**FRs covered:** FR29, FR30, FR31
**NFRs covered:** NFR9, NFR12
**ARCH covered:** ARCH-7(완전 통합 CI/CD), ARCH-8

---

## Epic 1: 프로젝트 토대 및 인프라 구축

개발팀이 Epic 2~4를 병렬로 착수할 수 있는 계약과 환경을 수립한다. 모노레포 초기화, 공유 인터페이스 계약(crawl_event, varco protocol, redis DB 할당), 로컬 개발 환경, VARCO Mock, Flyway 초기 스키마, 테스트 픽스처, CI 기본 파이프라인(lint + unit test)을 포함한다.

### Story 1.1: 모노레포 구조 초기화 및 서브시스템 스캐폴딩

개발자로서,  
서브시스템별 독립 의존성을 가진 모노레포 구조가 초기화되기를 원한다,  
그래서 팀원이 각자 서브시스템(crawler/detection/api/dashboard)을 독립적으로 개발할 수 있다.

**Acceptance Criteria:**

**Given** 빈 git 저장소가 있을 때  
**When** 모노레포 초기화 스크립트를 실행하면  
**Then** `tracker/crawler/`, `tracker/detection/`, `tracker/api/`, `tracker/dashboard/`, `tracker/shared/`, `tracker/infra/`, `tracker/.github/workflows/` 디렉토리 구조가 생성된다  
**And** `crawler/requirements.txt`에 `playwright==1.58.0`, `APScheduler`, `beautifulsoup4`, `langdetect`, `redis`, `boto3`, `playwright-stealth`가 정의된다  
**And** `detection/requirements.txt`에 `redis`, `boto3`, `httpx`, `python-dotenv`가 정의된다  
**And** `api/`는 Spring Boot 3.5.0 + Java 21 Gradle 프로젝트로 초기화된다 (dependencies: web, data-jpa, postgresql, actuator, lombok, validation) <!-- 2026-05-11 backport: 3.4.x → 3.5.0 (AI-11 결정값) -->  
**And** `dashboard/`는 `npm create vite@latest -- --template react-ts`로 초기화되고 `@tanstack/react-query`, `axios`, `recharts`, `@radix-ui/react-select`, `date-fns`, `react-router-dom`이 설치된다  
**And** `playwright install chromium`이 실행되어 Playwright 브라우저가 설치된다

### Story 1.2: 공유 인터페이스 계약 및 구조화 로깅 수립

개발자로서,  
크롤러·탐지·API 서브시스템이 공유하는 데이터 계약과 로깅 표준이 정의되기를 원한다,  
그래서 팀원이 서로 독립적으로 개발하면서도 통합 시점에 스키마 충돌이 발생하지 않는다.

**Acceptance Criteria:**

**Given** `shared/pyproject.toml`이 `pip install -e shared/`를 지원하도록 설정될 때  
**When** `shared/` 모듈이 완성되면  
**Then** `shared/correlation_id.py`가 UUID를 생성하는 `generate()` 함수를 제공한다  
**And** `shared/models/crawl_event.py`가 Redis MQ 메시지 스키마를 정의한다: `{post_id, source_id, site_name, raw_text, image_urls, language, detected_at, correlation_id}`  
**And** `shared/interfaces/varco.py`가 `Protocol` 클래스로 `translate(text: str) -> str`, `classify(text: str) -> ClassificationResult`를 정의한다  
**And** `shared/config/redis_config.py`가 DB 번호 상수를 정의한다: `REDIS_MQ_DB=0`, `REDIS_DEDUP_DB=1`, `REDIS_RATELIMIT_DB=2`, `REDIS_CACHE_DB=3`  
**And** `shared/structured_logger.py`가 `{"timestamp", "service", "level", "correlation_id", "message"}` JSON 로그를 출력하며 `SERVICE_NAME` 환경변수를 `service` 필드로 사용한다  
**And** `shared/exceptions/base_exception.py`가 공통 예외 기반 클래스를 정의한다

### Story 1.3: 로컬 개발 환경 구성

개발자로서,  
AWS 없이 로컬에서 Redis와 PostgreSQL을 구동할 수 있는 개발 환경이 구성되기를 원한다,  
그래서 외부 인프라 의존 없이 개발과 테스트를 진행할 수 있다.

**Acceptance Criteria:**

**Given** Docker Desktop이 설치된 로컬 머신에서  
**When** `docker compose -f infra/docker-compose.yml up -d`를 실행하면  
**Then** Redis 컨테이너가 포트 6379로 실행되고 `appendonly yes` 설정이 적용된다  
**And** Redis DB0~3 역할(`REDIS_MQ_DB`, `REDIS_DEDUP_DB`, `REDIS_RATELIMIT_DB`, `REDIS_CACHE_DB`)이 `docker-compose.yml` 환경변수로 명시된다  
**And** PostgreSQL 컨테이너가 포트 5432로 실행되고 `tracker` 데이터베이스가 생성된다  
**And** `infra/.env.example`에 모든 필수 환경변수 목록(`VARCO_API_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`, `CRAWL_INTERVAL_MINUTES`, `REDIS_*`, `DB_*`, `SERVICE_NAME`)이 주석과 함께 제공된다  
**And** `.gitignore`에 `.env`, `*.env.local`, `__pycache__/`, `.gradle/`, `node_modules/`, `build/`, `dist/`가 포함된다  
**And** `docker compose up -d` 후 Redis `PING` 응답이 `PONG`이고 PostgreSQL `\l` 명령으로 `tracker` 데이터베이스가 확인된다

### Story 1.4: Flyway DB 초기 스키마 및 VARCO Mock 서버 구축

개발자로서,  
PostgreSQL 스키마와 VARCO API Mock 서버가 준비되기를 원한다,  
그래서 실제 DB와 외부 API 없이도 AI 탐지 파이프라인을 개발하고 테스트할 수 있다.

**Acceptance Criteria:**

**Given** PostgreSQL이 로컬에서 실행 중일 때  
**When** Spring Boot 애플리케이션이 시작되면  
**Then** Flyway가 `V1__init_schema.sql`을 실행하여 `sources`, `posts`, `post_images`, `detections` 4개 테이블을 생성한다  
**And** `V2__add_indexes.sql`이 `CREATE INDEX idx_detections_filter ON detections (detected_at DESC, type, confidence DESC)`를 생성한다  
**And** `V3__add_unique_detection.sql`이 `detections` 테이블에 `(post_id, model_version)` unique constraint를 추가한다  
**And** `detection/src/mocks/varco_mock.py`가 `shared/interfaces/varco.py`의 Protocol을 구현하며 `translate()`, `classify()` 응답을 `tests/fixtures/varco/` JSON 파일에서 로드한다  
**And** `tests/fixtures/varco/`에 `mock_response_illegal.json`, `mock_response_clean.json`, `mock_response_rate_limited.json`, `mock_response_timeout.json` 4개 파일이 제공된다  
**And** `tests/fixtures/html/`에 `sample_illegal_post.html`, `sample_clean_post.html`이 제공된다  
**And** `tests/fixtures/labels/manual_label_set_v1.csv`에 ≥200건의 수동 라벨셋(post_id, text, label, type)이 포함된다 (Murat 권고 기준 적용)

### Story 1.5: GitHub Actions 기본 CI 파이프라인 구성

개발자로서,  
코드 푸시 시 자동으로 lint와 단위 테스트가 실행되기를 원한다,  
그래서 코드 품질이 개발 초기부터 유지된다.

**Acceptance Criteria:**

**Given** 코드가 main 또는 feature 브랜치에 push될 때  
**When** GitHub Actions 워크플로우가 트리거되면  
**Then** `crawler.yml`이 Python flake8 lint + pytest `crawler/tests/unit/`을 실행한다  
**And** `detection.yml`이 Python flake8 lint + pytest `detection/tests/unit/`을 실행한다  
**And** `api.yml`이 `./gradlew test`로 Spring Boot 단위 테스트를 실행한다  
**And** `dashboard.yml`이 ESLint + `npm test`로 React 컴포넌트 테스트를 실행한다  
**And** 각 워크플로우가 실패 시 PR 머지를 블로킹한다  
**And** VARCO API 키 등 시크릿이 GitHub Secrets에서 환경변수로 주입되며 워크플로우 파일에 하드코딩되지 않는다 (NFR5)

---

## Epic 2: 자동 크롤링 및 전처리 파이프라인

시스템이 지정된 커뮤니티 사이트를 1시간 주기로 자동 크롤링하고, 전처리된 게시글 후보를 AI 탐지 큐에 전달한다.

> **[2026-04-28 피벗]** SPIKE 2.1 + Story 2.2(Playwright+stealth 골격) 완료 이후 **crawl4ai** 라이브러리로 전환 확정. PoC에서 crawl4ai가 봇 탐지 우회(`BrowserConfig(enable_stealth=True)`) + HTML→Markdown 변환(`DefaultMarkdownGenerator`) + 노이즈 필터링(`PruningContentFilter`) + 이미지 스코어링을 내장 제공함을 검증. BaseSite/ProxyProvider 추상화 대신 **SiteConfig 레지스트리** 패턴 채택. Story 2.3부터 crawl4ai 기반 재작성. 구 `crawler/` 코드(Story 2.1~2.2 산출물)는 삭제되었으며 `crawler2/` 코드베이스가 `crawler/`로 승격됨.
>
> **`crawler/` — 이미 구현·검증된 항목 (구 crawler2/ PoC):**
> - `Crawl4AICrawler` — `AsyncWebCrawler` + stealth + `PruningContentFilter(threshold=0.5)` + httpx 이미지 다운로드 (`score ≥ 3` 필터) (`crawler/src/crawler.py`)
> - `CrawlResult` — `raw_markdown`, `fit_markdown`, `images`(src/alt/score), `downloaded_images`
> - `SiteConfig` + `SITES` 레지스트리 — `board_urls`, `post_url_pattern`, `image_filter`, `css_selector`, `post_id_extractor` 선언적 설정 (`crawler/src/sites/registry.py`)
> - `PostStorage` — 로컬 디스크 `output/posts/{site_id}/{post_id}/post.json` + 이미지 (`crawler/src/storage.py`)
> - `demo.py` — 게시판 목록 순회 → 게시글 크롤링 → 포스트별 저장 수동 파이프라인
> - 사이트별 이미지 필터: `_inven_image_filter`, `_dcard_image_filter`, `_tieba_image_filter`, `_pojie_image_filter`, `_nga_image_filter`

> **[2026-05-19 PIVOT]** crawler 전면 재작성 — `crawler_test/`의 더 견고한 구현으로 `crawler/` 통째 교체. `feat/epic-2-crawler-rewrite` 브랜치, 142 PASS, 외부 contract 무손실 호환.
>
> **`crawler/` — 신규 구현 추가 항목:**
> - `crawler/src/preprocessor/content_validator.py` — 본문 품질 8-kind 가드 (real/sticky/auth_wall/captcha/empty/short/error/unknown). 사이트별 `validate_*` 함수 + prefix dispatch. 위양성 방지 게이트
> - `crawler/src/preprocessor/url_dedup_checker.py` — Redis ZSET cross-run URL dedup, TTL 7일 (본문 fetch 전 차단 계층)
> - `crawler/src/preprocessor/serializer.py` — `CrawlEvent` 직렬화 전담
> - `crawler/src/scheduler/crawl_scheduler.py` + `scheduler/trigger_listener.py` — APScheduler 분리, inter-site / inter-board delay (±25% jitter)
> - `crawler/src/s3_uploader.py` + `storage.py` — S3 + 로컬 저장 분리
> - `crawler/src/sites/registry.py` — SITES dict (Bahamut NC 8게임 분리: Lineage/M/W/Classic, Aion/Aion2, BNS, TL)
> - `SiteConfig.title_keywords: list[str] | None` 사전 필터 (혼합 보드의 제목 단계 NC 게임 키워드 매칭, 토큰·시간 절감)
> - `crawler/tests/integration/`, `crawler/scripts/smoke_each_site.py`, `crawler/README.md`, `crawler/STATUS.md`
>
> **`crawler/` — 제거 항목:**
> - `html_parser.py` — crawl4ai의 `PruningContentFilter`가 흡수
> - `keyword_filter.py` — 본문 키워드 매칭은 Epic 3 VARCO LLM으로 위임, 제목 단계는 `SiteConfig.title_keywords` 필드로 이동
>
> Stories 2-1~2-7은 신규 코드에 흡수 매핑되었으며 (sprint-status.yaml 메모 참조), 검색엔진형 신규 능력에 대응하는 Stories 2-8~2-12는 아래 "Epic 2 검색엔진 트랙" 섹션 참조.

### SPIKE 2.1: Cloudflare 우회 가능성 검증 (타임박스: 2일)

> ⏱️ **상태: done**  
> 산출물: `docs/cloudflare-spike-result.md` — Playwright+stealth(crawl4ai `enable_stealth=True`) 채택 확정

개발자로서,  
Playwright+stealth로 Cloudflare JS 챌린지 사이트를 우회할 수 있는지 빠르게 검증하기를 원한다,  
그래서 불가능할 경우 FlareSolverr 대안으로 전환하는 시점을 조기에 결정할 수 있다.

**Acceptance Criteria:**

**Given** Playwright+stealth 브라우저가 설정된 환경에서  
**When** tailstar.net 또는 Cloudflare 보호 사이트에 접속 요청을 보내면  
**Then** Cloudflare 챌린지 페이지를 통과하여 실제 게시글 HTML을 응답받거나, 실패 시 FlareSolverr 연동 방안을 기술 결정 문서(`docs/cloudflare-spike-result.md`)에 기록한다  
**And** 스파이크 결과에 따라 stealth 구현체가 결정되며 결정 내용이 문서에 명시된다  
**And** 결정된 구현체에 대한 단위 테스트 1건 이상이 작성된다

### Story 2.2: ProxyProvider 추상화 및 기본 크롤러 구현

> **상태: done** (Playwright+stealth 기반 골격 구현 완료)  
> **[피벗 주석]** Story 2.2의 BaseSite/ProxyProvider 추상화(`crawler/src/proxy/`, `crawler/src/sites/base_site.py`, `crawler/src/sites/tailstar.py`)는 crawl4ai 전환으로 대체되어 삭제됨. 이후 사이트 추가는 SiteConfig 레지스트리(`crawler/src/sites/registry.py`) 방식을 사용. 구 `crawler2/` 코드베이스가 메인 `crawler/`로 승격되었다.

개발자로서,  
ProxyProvider 인터페이스와 첫 번째 사이트 크롤러가 구현되기를 원한다,  
그래서 프록시 교체 없이 크롤러 핵심 로직을 개발하고 테스트할 수 있다.

**Acceptance Criteria:**

**Given** `crawler/src/proxy/proxy_provider.py`에 ProxyProvider Protocol이 정의될 때  
**When** `ProxyBroker` 구현체가 ProxyProvider를 상속하면  
**Then** `ProxyBroker`를 `NodeMaven` 구현체로 교체할 때 크롤러 핵심 로직(`stealth_browser.py`) 코드 수정이 불필요하다  
**And** `crawler/src/sites/base_site.py`가 `parse(html: str) -> ParseResult` 추상 메서드를 정의하며, `None` 반환 대신 `ParseError`를 raise한다  
**And** `crawler/src/sites/tailstar.py`가 `BaseSite`를 상속하여 tailstar.net 게시글 목록과 본문을 파싱한다  
**And** 사이트 다운(5xx), rate limit(429), timeout 시나리오에 대한 예외 처리가 구현되며 각 케이스에 대한 단위 테스트가 존재한다

### Story 2.3: crawl4ai 크롤러 개선 및 전처리 파이프라인 구현

개발자로서,  
`crawler/`의 `Crawl4AICrawler` + `SiteConfig` 레지스트리를 기반으로 crawl4ai가 처리하지 않는 전처리(언어 감지·중복 체크·키워드 필터)가 추가되기를 원한다,  
그래서 AI 탐지 큐에는 정제되고 언어가 식별된 관련 게시글만 전달된다.

**Acceptance Criteria:**

**Given** `crawler/src/crawler.py`의 `Crawl4AICrawler`와 `crawler/src/sites/registry.py`의 SiteConfig 레지스트리가 있을 때  
**When** 크롤러 개선 및 전처리 파이프라인이 추가되면  
**Then** `crawler/src/crawl4ai_crawler.py`가 `Crawl4AICrawler`를 제공하며, `AsyncWebCrawler(BrowserConfig(enable_stealth=True))` + `PruningContentFilter(threshold=0.5)` + httpx 이미지 다운로드가 동작한다 (FR2, FR3)  
**And** `crawler/src/sites/registry.py`가 `SiteConfig` 레지스트리와 `get_enabled_sites()` 함수를 제공한다 (`inven_maple` 기본 활성화 상태) (FR1)  
**And** `crawler/requirements.txt`에 `langdetect`가 추가된다 (`crawl4ai>=0.8.6`, `httpx>=0.27.0`은 이미 존재)  
**And** `language_detector.py`가 `CrawlResult.fit_markdown`을 입력으로 언어를 감지하여 `ko`, `zh-CN`, `zh-TW` 중 하나를 반환한다 (FR8)  
**And** `dedup_checker.py`가 `fit_markdown`의 SHA-256 해시를 Redis DB1(`posts:dedup`)에서 조회하여 이미 처리된 게시글을 건너뛴다 (FR9)  
**And** `keyword_filter.py`가 `fit_markdown`에 불법 프로그램 관련 키워드(매크로, 핵, 外挂, 破解, 텔레그램 등)가 포함된 게시글만 통과시킨다 (FR10)  
**And** 전처리를 통과한 게시글이 `shared/models/crawl_event.py` 스키마로 직렬화된다 (`post_id`, `source_id`, `site_name`, `raw_text`=fit_markdown, `image_urls`, `language`, `detected_at`, `correlation_id`) (FR7)  
**And** `crawler/tests/unit/test_crawl4ai_crawler.py`에서 mock `AsyncWebCrawler`를 사용하여 `Crawl4AICrawler.fetch()` 흐름을 검증한다 (외부 네트워크 호출 0)  
**And** `crawler/tests/unit/test_keyword_filter.py`와 `test_dedup_checker.py`에서 각각 정탐/오탐 케이스를 검증한다

### Story 2.4: S3 원본 아카이브 및 이미지 업로드

개발자로서,  
크롤링된 텍스트(`fit_markdown`)와 이미지 파일이 S3에 보관되기를 원한다,  
그래서 EC2 재시작 후에도 원본 데이터를 복구할 수 있다.

**Acceptance Criteria:**

**Given** 크롤링이 완료된 `CrawlResult`(`fit_markdown`, `downloaded_images`)가 있을 때  
**When** `s3_uploader.py`가 실행되면  
**Then** `fit_markdown` 텍스트가 `s3://{S3_BUCKET_NAME}/raw/{site}/{YYYY-MM-DD}/{post_id}.md` 경로로 업로드된다 (FR5)  
**And** `downloaded_images`의 각 파일이 `s3://{S3_BUCKET_NAME}/images/{site}/{YYYY-MM-DD}/{post_id}/{filename}` 경로로 업로드된다 (FR4)  
**And** S3 업로드는 EC2 IAM Role(boto3)을 사용하며 Access Key가 코드에 하드코딩되지 않는다 (NFR6)  
**And** S3 업로드 실패 시 예외를 raise하고 구조화 로그에 `correlation_id`와 함께 기록된다  
**And** `crawl_event`에 S3 원본 경로(`s3_text_path`, `s3_image_paths`)가 포함된다  
**And** `PostStorage` 로컬 저장(`output/posts/{site_id}/{post_id}/`)과 S3 업로드를 환경변수 `ENABLE_S3_UPLOAD=true/false`로 독립적으로 제어할 수 있다

### Story 2.5: APScheduler 기반 자동 크롤링 및 수동 트리거

개발자로서,  
크롤링이 1시간 주기로 자동 실행되고 Redis pub/sub으로 즉시 트리거할 수 있기를 원한다,  
그래서 긴급 상황에서 담당자가 수동으로 즉시 크롤링을 시작할 수 있다.

**Acceptance Criteria:**

**Given** `CRAWL_INTERVAL_MINUTES` 환경변수가 설정된 환경에서  
**When** `crawl_scheduler.py`가 시작되면  
**Then** APScheduler가 `CRAWL_INTERVAL_MINUTES` 주기로 `Crawl4AICrawler`를 사용해 `get_enabled_sites()`의 모든 사이트를 순회 크롤링한다 (FR1, FR28, NFR17)  
**And** APScheduler Job에 `max_instances=1`, `misfire_grace_time=60`이 설정되어 중복 실행이 방지된다 (ARCH-10)  
**And** `trigger_listener.py`가 Redis `crawl:trigger` 채널을 구독하여 메시지 수신 시 즉시 크롤링을 실행한다 (FR6)  
**And** 크롤링 + 전처리를 통과한 게시글이 Redis DB0 `posts:queue`에 LPUSH된다 (`crawl_event` JSON 직렬화)  
**And** APScheduler 프로세스 재시작 후 다음 주기에 자동으로 크롤링이 재개된다 (NFR10)  
**And** `crawler/tests/integration/test_crawl_pipeline.py`에서 mock `Crawl4AICrawler`를 사용하여 크롤링 → 전처리 → Redis enqueue 흐름을 검증한다  
**And** 통합 테스트 결과로 크롤 성공률 ≥95%, 중복 제거율 ≥90%를 만족해야 Epic 3 착수 조건을 충족한다

### Story 2.6: PTT·Dcard SiteConfig 레지스트리 구성

개발자로서,  
대만 커뮤니티 사이트 PTT와 Dcard가 SiteConfig 레지스트리에 추가되고 `enabled=True`로 활성화되기를 원한다,  
그래서 대만어(번체) 게시글을 자동 수집하여 다국어 탐지 파이프라인을 검증할 수 있다.

**Acceptance Criteria:**

**Given** `crawler/src/sites/registry.py`의 SiteConfig 레지스트리가 구성된 상태에서  
**When** PTT와 Dcard SiteConfig가 `enabled=True`로 설정되면  
**Then** PTT SiteConfig가 `over18` 쿠키를 `CrawlerRunConfig(js_code=...)` 또는 `headers` 주입 방식으로 처리하여 18세 인증 게이트를 통과한다  
**And** `Crawl4AICrawler.fetch()` 호출 시 PTT 게시글 `fit_markdown`과 이미지 URL이 올바르게 추출된다  
**And** Dcard SiteConfig가 React SPA 렌더링에 맞게 `page_timeout`·`wait_for` 튜닝이 적용된다  
**And** `_dcard_image_filter` 콜백이 `images.dcard.tw` / `megapx.dcard.tw` 도메인 이미지만 통과시킨다  
**And** PTT와 Dcard가 `get_enabled_sites()`로 반환되며 `demo.py` 실행 시 게시글을 수집하고 `PostStorage`에 저장된다  
**And** `crawler/tests/unit/test_site_registry.py`에서 `post_url_pattern` 정규식 매칭과 `image_filter` 콜백 동작을 fixture URL/이미지 딕셔너리로 검증한다 (외부 네트워크 호출 0)

### Story 2.7: 중국 사이트 SiteConfig 레지스트리 구성 및 프록시 연동

개발자로서,  
중국 커뮤니티 사이트 tieba, 52pojie, NGA가 SiteConfig 레지스트리에 추가되고 BrowserConfig 프록시와 함께 활성화되기를 원한다,  
그래서 중국어 게시글을 수집하여 VARCO Translation 파이프라인의 다국어 처리를 실제 데이터로 검증할 수 있다.

**Acceptance Criteria:**

**Given** `Crawl4AICrawler`가 `BrowserConfig(proxy=...)` 파라미터를 수신할 수 있도록 확장될 때  
**When** 중국 사이트 SiteConfig가 `enabled=True`로 설정되면  
**Then** `PROXY_URL` 환경변수(NodeMaven 또는 기타 프록시 서비스)가 `BrowserConfig(proxy=PROXY_URL)`로 주입되어 GFW 우회가 적용된다  
**And** tieba의 GB2312/UTF-8 인코딩이 crawl4ai에 의해 자동 처리되어 한자가 올바르게 추출된다  
**And** 52pojie SiteConfig에 Cloudflare 우회를 위한 `enable_stealth=True` + 충분한 `page_timeout`(≥30,000ms)이 설정된다  
**And** `_tieba_image_filter`, `_pojie_image_filter`, `_nga_image_filter` 콜백이 사이트별 CDN 도메인 이미지만 통과시킨다  
**And** 중국 사이트 차단으로 수집 실패 시 경고 로그를 남기고 다음 사이트로 진행하며 파이프라인이 중단되지 않는다  
**And** 각 사이트의 크롤링 성공률이 구조화 로그(`correlation_id` 포함)에 기록되어 NodeMaven 도입 시점 결정에 활용된다  
**And** `crawler/tests/unit/test_site_registry.py`에서 중국 사이트의 `post_url_pattern` 매칭과 `image_filter` 동작을 검증한다 (외부 네트워크 호출 0)

---

### Epic 2 검색엔진 트랙 (Stories 2.8 ~ 2.12) — `SearchEngineConfig` 추상화

> **[2026-05-19 PIVOT 신규 트랙]** 기존 `SiteConfig`는 board → post 1-hop 모델. 검색엔진은 query → SERP → 외부 링크 2-hop 모델로 본질적으로 다름. 신규 `SearchEngineConfig` 추상화를 신설하여 분리. 출력은 `CrawlEvent` 동일, 다운스트림 (Epic 3 탐지 파이프라인) 무영향.
>
> **착수 조건:** Epic 3 (탐지 파이프라인) 안정화 후. Story 2-8(github)은 추상화 검증용 첫 도전이며, 검증 결과에 따라 2-9 이후 분해를 재조정할 수 있다.
>
> **`SearchEngineConfig` 예상 필드:** `search_url_template`, `result_link_selector`, `query_keywords`, `result_filter`, `proxy` (지역별 필수 여부).

#### Story 2.8: `SearchEngineConfig` 추상화 신설 + GitHub 어댑터

개발자로서,  
`SearchEngineConfig` 추상화 (query → SERP → 외부 링크 2-hop) 와 GitHub 어댑터가 구현되기를 원한다,  
그래서 추상화 모델의 타당성을 검증하고 이후 어댑터 추가의 패턴을 확립할 수 있다.

**Acceptance Criteria:**

**Given** `crawler/src/search/search_engine_config.py`에 `SearchEngineConfig` dataclass가 정의될 때  
**When** GitHub 검색 어댑터가 `search_url_template`, `result_link_selector`, `query_keywords` 설정만으로 구현되면  
**Then** GitHub 검색 결과 페이지에서 결과 링크를 수집하고 각 링크의 콘텐츠를 `CrawlEvent`로 직렬화한다  
**And** 2-hop 흐름 (query → SERP → 외부 링크) 이 단위 테스트로 검증된다 (mock fixture, 외부 네트워크 호출 0)  
**And** `SearchEngineConfig`와 기존 `SiteConfig`의 차이점이 `crawler/README.md`에 문서화된다  
**And** 한국 IP에서 GitHub 검색이 정상 동작함이 smoke 테스트로 확인된다

#### Story 2.9: Reddit 어댑터

개발자로서,  
글로벌 NC 관련 정보가 유통되는 Reddit를 검색엔진 어댑터로 통합하기를 원한다,  
그래서 글로벌 채널의 불법 게시글 유포 양상을 추가로 모니터링할 수 있다.

**Acceptance Criteria:**

**Given** `SearchEngineConfig` 추상화 (Story 2.8 완료) 가 안정화된 상태에서  
**When** Reddit 어댑터가 `SearchEngineConfig` 설정만으로 추가되면  
**Then** Reddit 검색 결과의 외부 링크가 수집된다  
**And** 한국 IP에서 Reddit 검색 접근이 정상 동작한다  
**And** Story 2.8과 동일한 단위 테스트 패턴 (mock fixture, 외부 네트워크 0) 이 적용된다

#### Story 2.10: Bing + DuckDuckGo (CN) 어댑터

개발자로서,  
중국 콘텐츠의 글로벌 유통 경로인 Bing과 추적 회피 검색엔진 DuckDuckGo를 어댑터로 추가하기를 원한다,  
그래서 한국 IP에서 접근 가능한 검색 채널로 중국발 불법 게시글의 우회 유통을 탐지할 수 있다.

**Acceptance Criteria:**

**Given** `SearchEngineConfig` 추상화가 안정화된 상태에서  
**When** Bing 및 DuckDuckGo(CN 쿼리) 어댑터가 추가되면  
**Then** 두 검색엔진 모두 한국 IP에서 정상 동작하며 외부 링크가 수집된다  
**And** Bing은 우회 유통 링크, DuckDuckGo는 추적 회피 검색 쿼리에 특화 설정된다  
**And** 각 어댑터의 단위 테스트 (mock fixture, 외부 네트워크 0) 가 존재한다

#### Story 2.11: Facebook (Bing 우회) 어댑터

개발자로서,  
Facebook 자체 검색 API 제약 때문에 Bing 사이트 검색 (`site:facebook.com`) 으로 우회 수집하기를 원한다,  
그래서 가장 어려운 케이스인 Facebook 콘텐츠를 간접 경로로 탐지할 수 있다.

**Acceptance Criteria:**

**Given** Bing 어댑터 (Story 2.10) 가 동작하는 상태에서  
**When** Facebook 우회 어댑터가 Bing의 `site:facebook.com` 쿼리 패턴으로 구현되면  
**Then** Facebook 관련 검색 결과 링크가 수집된다  
**And** Bing 차단 / rate limit 대응이 구현된다  
**And** 단위 테스트가 mock fixture로 외부 네트워크 호출 없이 수행된다

#### Story 2.12: 중국 검색엔진 (Baidu / Sogou / Bilibili) 어댑터

> **전제 조건:** 중국 residential proxy 인프라 트랙 완료 후 착수. nga·tieba·52pojie와 동일한 차단 패턴 (한국 IP HTTP 403) 이 검색엔진에도 적용될 가능성이 높다.

개발자로서,  
중국 1위 검색엔진 Baidu, 보조 Sogou, 영상 플랫폼 Bilibili를 검색엔진 어댑터로 통합하기를 원한다,  
그래서 중국 내부에서 유통되는 불법 게시글의 검색 채널 양상을 탐지할 수 있다.

**Acceptance Criteria:**

**Given** 중국 residential proxy 인프라가 준비되고 `SearchEngineConfig`가 `proxy` 필드를 지원하는 상태에서  
**When** Baidu / Sogou / Bilibili 어댑터가 각각 추가되면  
**Then** 중국 residential proxy 경유로 각 검색엔진의 결과가 수집된다  
**And** Bilibili는 영상 메타데이터 + 설명 기반 텍스트가 `CrawlEvent.raw_text`에 직렬화된다  
**And** 중국 사이트 차단으로 수집 실패 시 경고 로그를 남기고 다음 어댑터로 진행하며 파이프라인이 중단되지 않는다 (Story 2.7과 동일 패턴)

---

## Epic 3: AI 기반 불법 게시글 탐지 파이프라인

시스템이 크롤러 큐에서 게시글을 소비하고 **비용 차등 멀티 에이전트**(저비용 트리아지 → 조건부 이미지/링크 심층 분석 → 증거 통합)로 자동 분류하여, 신뢰도·판단 근거·**Tier(T1/T2/T3/T4)**를 포함한 탐지 결과를 RDS에 저장한다. 탐지는 사이트에 비종속적(게임 맥락 자가 추론)이며, 위험 링크는 1-hop 추적으로 증거를 수집한다. T1 즉시 알림 적용. Epic 3 완료 기준에 신·구 아키텍처 A/B 정확도 비교 + 게시글당 평균 비용 측정 포함.

> **2026-06-11 재정의 (Correct Course)** — OpenAI 멀티모달 LLM **단일 호출**을 **비용 차등 멀티 에이전트**로 확장. detection 사이트 종속(게임별 프롬프트 오버레이) 제거. 자세한 결정은 `sprint-change-proposal-2026-06-11.md` 참조.
>
> **2026-06-11 스토리 변경 요약:**
> - **Story 3.1** (유지): Redis 큐 소비자 + Watchdog — 오케스트레이션 무관
> - **Story 3.3** (트리아지로 흡수): 단일 호출 코드(llm_client/structured output/이미지)를 S1 TriageAgent + S3 Synthesizer의 모태로 재활용. `DETECTION_MODE=single` 폴백 보존
> - **Story 3.4** (유지): detections 테이블 계약 불변. agent_runs는 V10 additive 확장
> - **Story 3.5** (유지): 수집된 라벨 코퍼스를 신규 3-9 A/B 비교의 ground truth로 활용
> - **Story 3.6** (폐기): 알림 시스템이 이미 완성돼 있음(백엔드 notification_* + 룰 엔진 minTier + 프론트 UI). T1 알림은 신규 구현 불필요 → Story 3-9에 E2E 검증만 흡수. T2 다이제스트/T3 주간/90일 retention/사람 리뷰 큐는 deferred-work 이월
> - **Story 3.7** (신규): LinkTracer 1-hop + SSRF 가드 + agent_runs(V10)
> - **Story 3.8** (신규): ImageAnalyst + Synthesizer + 게시글당 예산 가드
> - **Story 3.9** (신규): 신·구 아키텍처 A/B 정확도 비교 + 비용 실측 + 데모 리허설 + T1 알림 E2E 검증(기존 시스템)
> - ~~**Story 3.10**~~ (폐기): 기존 알림 시스템 중복 — 3-9에 검증 흡수
>
> **2026-05-27 PIVOT (Correct Course)** — VARCO Translation+LLM 2단 → OpenAI 멀티모달 LLM 단일 호출 + Tier 차등 처리. (이력 — 위 재정의의 직전 단계)
>
> **스토리 변경 요약 (2026-05-27, 이력):**
> - **SPIKE 3.0** (신규, 1일 타임박스): OpenAI 멀티모달 PoC — 동작 검증 우선
> - **Story 3.1** (유지): Redis 큐 소비자 + Watchdog — LLM backend 무관, 변경 없음
> - **Story 3.2** (폐기): VARCO Translation 연동 — review 코드 폐기 (RetryHandler/TokenBucket/correlation_id 부품은 신규 3-3에서 재사용)
> - **Story 3.3** (전면 재작성): OpenAI 멀티모달 LLM 분류 + Tier 라우팅 + 텍스트/이미지 분리 호출 가능 인터페이스
> - **Story 3.4** (AC 확장): RDS 저장 — `detections.tier` 필드 + `model_version` 백엔드 식별자(`openai:gpt-4o-2024-XX-XX`)
> - **Story 3.5** (AC 확장): 정확도 사전 측정 — Tier별 confusion matrix + 라벨셋 ≥300건(Tier별 ≥75건) + 게시글당 평균 비용 측정
> - **Story 3.6** (신규): Tier 기반 알림(T1 즉시 / T2 다이제스트 / T3 주간 / T4 통계만) + Tier 보존 정책(T1 영구 / T2·T3 90일 / T4 즉시 폐기)

### SPIKE 3.0: OpenAI 멀티모달 PoC — 1일 타임박스

> ⏱️ **상태: 신규 (2026-05-27 PIVOT) — Sprint Change Proposal 승인 직후 즉시 착수**
> 산출물: `docs/llm-spike-2026-05-27.md` — 동작 검증 + 단가 측정 + Tier 라우팅 프로토타입

AI 담당자로서,
OpenAI 멀티모달 LLM(GPT-4o)이 게임 도메인 라벨셋(소규모 ≥30건)에서 동작함을 1일 안에 검증하기를 원한다,
그래서 Story 3-3 본 구현 착수 전에 프롬프트·response_format·Tier 매핑·이미지 토큰 단가에 대한 사실 기반 정보를 확보할 수 있다.

**Acceptance Criteria:**

**Given** `tests/fixtures/labels/manual_label_set_spike.csv` ≥ 30건 (Tier별 ≥ 7건, 이미지 첨부 ≥ 10건)이 준비된 상태에서
**When** SPIKE 스크립트(`detection/scripts/spike_llm.py`)를 실행하면
**Then** OpenAI Chat Completions API에 텍스트+이미지 통합 멀티모달 호출이 성공한다
**And** `response_format=json_schema` 또는 동등한 구조화 출력으로 `{type, tier, confidence, reason_ko}` 필드가 반환된다
**And** 30건 전체에 대한 정탐/오탐 카운트, Tier별 분포, 게시글당 평균 비용(USD), 평균 latency가 `docs/llm-spike-2026-05-27.md`에 기록된다
**And** 본 구현(Story 3-3)에 사용할 권장 모델·프롬프트·response schema·일일 비용 cap 초기값이 결정된다
**And** 이미지 PII OpenAI 전송 컴플라이언스 1차 검토 결과가 기록된다 (법무 미확정 시 텍스트-only fallback 옵션 명시)

### Story 3.1: Redis 큐 소비자 및 Watchdog 구현

개발자로서,  
Redis 큐에서 게시글을 원자적으로 소비하고 처리 중 Worker 크래시 시 메시지가 유실되지 않기를 원한다,  
그래서 파이프라인이 장애 상황에서도 데이터 정합성을 보장한다.

**Acceptance Criteria:**

**Given** Redis DB0 `posts:queue`에 게시글이 적재된 상태에서  
**When** `queue_consumer.py`가 실행되면  
**Then** `BRPOPLPUSH posts:queue posts:processing`으로 메시지를 원자적으로 소비한다 (NFR16)  
**And** 처리 완료 후 `LREM posts:processing 1 {message}`로 메시지를 제거한다  
**And** `watchdog.py`가 `posts:processing`에 일정 시간 이상 잔류하는 메시지를 감지하여 `posts:queue`로 재투입한다  
**And** Worker 프로세스 재시작 후 Redis AOF에 의해 `posts:processing`의 미완료 메시지가 보존된다 (NFR13)  
**And** `detection/tests/unit/test_consumer_idempotency.py`에서 동일 메시지 중복 처리 시 `detections` 테이블에 중복 삽입이 발생하지 않음을 검증한다  
**And** 동일 메시지가 3회 이상 재전달되는 retry storm 시나리오에서 DLQ로 격리되며 무한 재처리 루프가 발생하지 않는다

### Story 3.2: ~~VARCO Translation 연동 및 rate limit 제어~~ — **폐기 (2026-05-27 PIVOT)**

> **2026-05-27 PIVOT.** FR11(VARCO Translation) 폐기. OpenAI 멀티모달 LLM이 KR/CN(간체·번체) native 처리하므로 별도 Translation 단계 불필요.
>
> **현재 상태(2026-05-27 시점):** review 상태. PR 머지하지 않고 폐기. **재사용 부품 추출:**
> - `detection/src/rate_limit/token_bucket.py` — 신규 Story 3-3의 LLM rate limit에 재활용
> - `detection/src/retry/retry_handler.py` (Story 3-3에서 구현됨) — Tier별 차등 retry로 확장 재활용
> - `correlation_id` 전파 패턴 — 그대로 유지
> - **폐기:** `translate.py`, `pipeline/translate_*` 테스트, `VarcoHttpClient.translate`
>
> **처리 가이드:** `feat/epic3-detection` 브랜치에서 `translate.py` 등 폐기 파일 삭제. 재사용 부품은 신규 3-3 PR에 포함. 옛 코드는 git history(브랜치 머지 전 마지막 review commit)로 보존.

### Story 3.3: OpenAI 멀티모달 LLM 분류 + Tier 라우팅 — **전면 재작성 (2026-05-27 PIVOT)**

> **2026-06-11 재정의.** 본 스토리의 단일 호출 분류기는 멀티 에이전트의 **S1 TriageAgent + S3 Synthesizer의 모태**로 흡수된다. `llm_client.py`(structured output, 멀티모달, 이미지 처리)는 모든 에이전트가 공유하며, 본 단일 호출 경로는 `DETECTION_MODE=single` **폴백**으로 보존된다(데모 당일 A/B 회귀용). 아래 AC는 single 모드 기준으로 유효하며, agentic 모드는 Story 3-7/3-8에서 구현.
>
> **2026-05-27 PIVOT.** 기존 VARCO LLM 분류 → OpenAI 멀티모달 단일 호출 + Tier 차등으로 전면 재작성. 기존 review 코드의 `RetryHandler`, `TokenBucket`, `correlation_id` 전파, `DetectionPipeline` 스켈레톤은 재활용. `LLMClassifier`, `VarcoHttpClient`는 신규 `LLMClient`(OpenAI HTTP) + `tier_router.py`로 대체.

개발자로서,
게시글의 본문 텍스트와 첨부 이미지가 OpenAI 멀티모달 LLM 단일 호출로 분류되어 Tier(T1/T2/T3/T4)와 함께 결과가 산출되기를 원한다,
그래서 별도 번역·Vision 단계 없이 단일 호출로 다국어·이미지·불법 분류·Tier 라우팅이 통합 처리된다.

**Acceptance Criteria:**

**Given** Redis `posts:processing`에서 소비된 `CrawlEvent`(텍스트 + 이미지 URL/S3 경로)가 있을 때
**When** `detection/src/pipeline/llm_classifier.py`가 실행되면
**Then** `LLMClient`(`detection/src/pipeline/llm_client.py`)가 OpenAI Chat Completions API에 텍스트+이미지 멀티모달 단일 호출을 보낸다 (FR12, FR16-NEW-1)
**And** 응답이 `response_format=json_schema` 또는 동등한 구조화 출력으로 `{type, confidence, reason_ko, image_observed: bool, translated_text_ko: str | null}` 형식을 강제한다 — SPIKE 3.0 결과 schema 핀닝
**And** `translated_text_ko` 필드는 **한국어 외 게시글(zh-CN / zh-TW / en 등)의 본문 + 이미지 속 외국어 텍스트를 한국어로 번역한 결과**를 담는다 (FR11). 한국어 원문은 `null`. 프롬프트에서 "for non-Korean source, also include Korean translation in translated_text_ko" 명시 — 분류·reason·번역을 단일 호출로 동시 산출
**And** `type` enum: `핵_치트` / `사설서버` / `불법프로그램_배포` / `계정_거래` / `매크로_판매` / `리세마라` / `현금화` / `광고_도배` / `기타`
**And** `tier_router.py`가 `type` → `Tier(T1/T2/T3/T4)` 매핑을 적용하고 **다중 라벨 시 최상위 Tier**를 선택한다 (FR12)
**And** Tier별 차등 threshold 적용: T1=0.65, T2=0.75, T3=0.85, T4=0.90 (`tier_config.py`) — **threshold는 대시보드 디스플레이 필터로만 작동**. 모든 분류 결과(`is_illegal=false` 포함, 임계값 미만 포함, T4 포함)는 RDS에 저장된다 (FR13, FR22 — 2026-05-27 PIVOT post-approval: 크롤 볼륨 낮음, 전수 저장으로 디버깅·라벨셋 확장·오탐 분석)
**And** `posts` 테이블에는 크롤링된 모든 게시글이 저장되며, `detections` 테이블에는 모든 LLM 분류 결과가 1:1로 저장된다 (사전 필터 — `content_validator` 8-kind 가드 + URL/content 중복 제거 — 만 통과한 게시글에 한정)
**And** `reason_ko`가 항상 한국어로 생성됨을 프롬프트에서 강제 (시스템 프롬프트에 `respond in Korean for reason_ko field` 명시)
**And** `LLMClient`가 **텍스트 호출과 이미지 호출을 분리 가능한 인터페이스**로 구현되어 향후 비용·정확도 측정에 따라 라우팅 분리 가능 (현재 기본 동작은 단일 호출, 분리는 환경변수 `LLM_SPLIT_TEXT_IMAGE=true` 토글)
**And** `RetryHandler`(Story 3-2/3-3 코드 부품 재사용)가 **Tier별 차등 재시도** 적용: T1=3회 / T2=2회 / T3=1회 / T4=0회. 모두 실패 시 `posts:dlq`로 이동 (FR15, NFR11)
**And** `TokenBucket`이 Redis DB2 `llm:rate_limit` 키로 OpenAI rate limit 토큰 소비를 제어한다 (FR16, NFR14) — `varco:rate_limit` prefix는 폐기
**And** `cost_cap.py`가 누적 일일 비용(USD)을 추적하여 `LLM_DAILY_COST_CAP_USD` 환경변수 도달 시 Hold(큐 대기). T4 inactive 처리로 호출량 1차 감축
**And** `detection/tests/unit/test_tier_router.py`에서 다중 라벨 최상위 Tier 선택 + threshold 적용을 검증
**And** `detection/tests/integration/test_llm_pipeline.py`에서 분류 → Tier 라우팅 → 저장 전체 흐름을 `llm_mock.py`로 검증 (외부 네트워크 0)
**And** `detection/tests/unit/test_cost_cap.py`에서 cap 도달 시 Hold 동작을 검증
**And** 모든 API 호출 로그에 `correlation_id` + Tier + token usage + 비용(USD) 포함

### Story 3.4: 탐지 결과 RDS 저장 및 스키마 계약 검증 (2026-05-27 PIVOT — Tier 필드 + OpenAI 스키마 핀닝)

개발자로서,
탐지 결과가 RDS `detections` 테이블에 **Tier 정보와 함께** 저장되고 중복 삽입이 방지되기를 원한다,
그래서 동일 게시글이 재처리되어도 탐지 결과가 하나만 존재하며 Tier별 필터·통계·보존 정책이 적용 가능하다.

**Acceptance Criteria:**

**Given** OpenAI 멀티모달 LLM 분류 결과가 있을 때
**When** `detection_repository.py`가 RDS에 저장을 시도하면
**Then** `detections` 테이블에 `post_id`, `model_version`, `is_illegal`, `type`, **`tier`** (T1/T2/T3/T4), `confidence`, `reason_ko`, **`translated_text_ko`** (한국어 외 원문의 번역, 한국어 원문이면 NULL — FR11), **`image_observed`** (bool), **`token_usage_json`** (input/output/image tokens), **`cost_usd`**, `detected_at`, `correlation_id`가 저장된다
**And** `tier` 필드 + `translated_text_ko` 컬럼 추가를 위한 Flyway 마이그레이션 `V5__add_tier_columns.sql` 생성 (`tier VARCHAR(2) NOT NULL DEFAULT 'T4'`, `translated_text_ko TEXT`, `image_observed BOOLEAN`, `token_usage_json JSONB`, `cost_usd NUMERIC(8,5)`)
**And** Spring API `DetectionResponse.translatedText` 필드가 `translated_text_ko` 컬럼을 직접 반영 (Story 4.2 AC의 `translatedText` 계약과 정합)
**And** `idx_detections_filter` 인덱스를 `(detected_at DESC, tier, type, confidence DESC)`로 확장 (Tier 필터 우선)
**And** `model_version` 포맷이 **`openai:{model_name}:{date}`**(예: `openai:gpt-4o:2024-08-06`)로 변경됨 — 단일 vendor지만 모델 식별 명시
**And** 동일 `(post_id, model_version)` 조합으로 중복 삽입 시 `UniqueConstraintError`가 발생하고 로그에 기록된다 (V3 unique constraint 유지)
**And** `detection_repository.py`의 public 메서드가 write 전용(`save`, `batch_save`)만 노출되며, read 쿼리는 포함하지 않는다 (구현 규칙: read는 Spring API 레이어 전담)
**And** `detection/tests/integration/test_llm_response_schema.py`에서 OpenAI 응답 스키마가 `shared/interfaces/llm.py`의 Protocol(2026-05-27 PIVOT 신설, 이전 `varco.py` 대체)과 일치함을 검증
**And** OpenAI 응답 스키마 변경 시 이 테스트가 CI에서 즉시 실패하도록 JSON Schema 핀닝이 적용된다
**And** API 레이어(`api/`) 변경: `DetectionResponse`에 `tier` 필드 추가 + 목록 API 필터에 `tier` 파라미터 추가 (Epic 4 follow-up 노트)

### Story 3.5: Few-shot 학습용 라벨 데이터 수집 기반 및 경량 정확도 스냅샷 (2026-06-02 재정의 — few-shot 데이터 수집)

> **[2026-06-02 재정의]** 원안("Tier별 배치 처리 시간 + Tier별 정확도 + 비용 사전 측정" — ≥300 라벨셋 / Tier별 confusion matrix / 게시글당 비용·p95 정식 측정)을 그대로 구현하는 대신, **"데이터를 모아서 나중에 few-shot learning을 구현할 방향"**으로 재정의(운영자 create-story 결정). 프롬프트 진화(단일 → 게임별/유형별 → **few-shot**)의 **데이터 수집 단계**. 라벨은 **RDS 컬럼**(backend-connected — Spring API/대시보드가 읽기 가능), 측정은 **경량 스냅샷만**. 원안의 ≥300 게이트·Tier confusion matrix·비용/p95 정식 측정은 **deferred-work로 이월**(미래 측정 스토리).

QA/운영 담당자로서,
전수 저장된 탐지 결과에 사람이 검증한 정답 라벨을 부여하고 게임·유형별로 누적·열람·export할 수 있기를 원한다,
그래서 향후 few-shot 예시 코퍼스를 구축해 분류 정확도를 점진적으로 개선할 수 있다.

**Acceptance Criteria:**

**Given** Flyway V1~V8이 적용된 RDS PostgreSQL이 있을 때
**When** `V9__add_human_label.sql`이 적용되면
**Then** `detections`에 `human_label`(9-type enum 또는 `unknown`, NULL=미라벨) / `human_verified_at` / `label_source` 컬럼이 additive로 추가되고, 미라벨 partial 인덱스가 생성된다 (기존 컬럼·제약 무변경)
**And** `DetectionRepository.set_human_label(post_id, model_version, label, source)`가 parameterized UPDATE로 라벨을 기록한다 (멱등 / enum 외 값 ValueError / 기존 `save()` 무변경)
**And** `detection/scripts/label_detections.py` CLI가 미라벨 detections를 `--game`/`--tier`/`--limit` 필터로 조회하고 **LLM 예측(type/tier/reason_ko)을 기본값으로 제시**, dev가 Enter(동의)/정정/`u`(unknown)/`s`(skip)로 확정 → RDS 기록 (game 필터는 `registry.SOURCE_ID_TO_GAME` 재사용)
**And** human_label이 RDS 컬럼이므로 Spring API가 별도 마이그레이션 없이 읽기 가능 — `DetectionResponse.humanLabel` 노출 + 목록 필터 + 대시보드 라벨링 UI는 **Epic 4 follow-up**(본 스토리 스코프 외)
**And** `detection/scripts/build_fewshot_corpus.py`가 `human_label IS NOT NULL` 행을 **game_key × type별 그룹화**하여 그룹당 최대 N건(기본 3)을 `detection/src/prompts/examples/{game_key}.jsonl`로 export한다 (레코드: text 발췌/label/reason_ko/tier, 라벨 0건이면 동작 중립 fallback)
**And** `detection/src/prompts/examples/README.md`에 JSONL 포맷 계약 + 소비 지점(`build_system_prompt()` Stage 2-B 빈 슬롯)을 문서화하되, **실제 프롬프트 주입·정확도 효과 측정은 별도 미래 스토리**임을 명시 (본 스토리는 코퍼스 생성까지)
**And** `detection/scripts/labelset_snapshot.py`가 **경량 스냅샷**(overall agreement `human_label==type` + game별/type별 커버리지 카운트)을 `docs/labelset-snapshot.md`에 기록한다 — **≥300 게이트·Tier confusion matrix·비용/p95 측정은 미포함**(deferred-work 이월)
**And** 신규 테스트 ≥6건(`set_human_label` update/멱등/invalid + corpus 그룹화/빈 코퍼스 noop + snapshot 집계)이 PASS하여 누적 ≥60 PASS / 외부 호출 0 / 회귀 0 (crawler·api 코드 무변경, V9는 additive)

### Story 3.6: Tier 기반 알림 및 보존 정책 (2026-05-27 PIVOT — 신규) — **2026-06-11 폐기 (기존 알림 시스템으로 충족)**

> **2026-06-11 재정의.** 조사 결과 알림 시스템은 **이미 완성**되어 있다 — 백엔드 `notification_events`/`notification_channels`/`notification_rules`/`notification_deliveries` 4테이블(`V7__notification_outbox.sql`) + `NotificationEventProcessor`(5초 폴링·발송·재시도) + 채널 6종(Discord/Slack/Teams/Google Chat/Webhook) + 룰 엔진(`NotificationRuleEvaluator`의 `minTier` 필터) + 프론트 3탭 UI + detection의 `notification_events` 적재(`detection_repository.py`). 따라서 `t1_notifier.py` 신규 구현은 **중복이라 폐기**. T1 알림은 대시보드에서 `minTier=T1` 룰 설정만으로 동작하며, agentic 파이프라인과의 E2E 검증은 **Story 3.9에 흡수**. **미구현 항목(deferred-work 이월):** 사람 리뷰 큐(human-in-the-loop — 현재 즉시 발송 설계와 충돌), T2 일일 다이제스트, T3 주간 리포트, 90일 retention job. 아래 AC는 이력 보존용.

운영자로서,
T1 Critical 탐지가 발생하면 즉시 알림을 받고 Tier별로 데이터가 차등 보존·폐기되기를 원한다,
그래서 핵·사설서버 등 사업 핵심 카테고리에 빠르게 대응하면서 저장 비용·PII 노출을 통제할 수 있다.

**Acceptance Criteria (이력 — 2026-05-27):**

**[알림 — FR16-NEW-2]**

**Given** `detections` 테이블에 신규 행이 insert될 때
**When** `tier`가 `T1`이면
**Then** `notification/t1_notifier.py`가 외부 알림 채널(채널 구체값은 운영팀 협의 후 환경변수 `T1_NOTIFICATION_CHANNEL`로 주입)로 즉시 알림을 발송한다
**And** T1 알림은 운영 단계에서 **사람 리뷰 큐**를 경유한다 — `t1_review_queue` Redis list로 PUSH, 운영자 승인 후에만 외부 발송 (PRD § 탐지 오류 관리 반영)
**And** `tier`가 `T2`이면 `notification/digest_scheduler.py`가 일 1회 누적 다이제스트를 발송한다 (APScheduler cron 09:00 KST)
**And** `tier`가 `T3`이면 `notification/weekly_report.py`가 주 1회 리포트를 발송한다 (월요일 09:00 KST)
**And** `tier`가 `T4`이면 알림 없이 통계만 누적된다 (저장은 수행, 대시보드 기본 목록에는 미노출 — QA 리뷰 모드로만 조회)
**And** 알림 발송 실패 시 구조화 로그(`correlation_id` 포함)에 기록되고 다음 사이클에서 재시도된다

**[보존 — FR16-NEW-3]**

**Given** `retention/tier_retention_job.py`가 일 1회 실행될 때
**When** 보존 기간 정책이 적용되면
**Then** T1 Critical 행과 연결된 S3 객체(원본 텍스트 + 이미지)는 영구 보존된다
**And** T2 / T3 / **T4** 행 중 `detected_at < now() - 90 days` 조건을 만족하는 행은 S3 원본을 archive 스토리지로 이동하고 `detections.archived_at` 컬럼을 갱신한다 (Flyway `V6__add_retention_columns.sql`) — **2026-05-27 PIVOT post-approval**: T4도 90일 보존 (이전 "즉시 폐기" 폐기, 크롤 볼륨 낮음 + 라벨셋 확장 가치)
**And** `is_illegal=false` 분류 결과(모든 Tier)도 같은 보존 기간 동안 RDS에 유지된다 — 오탐 분석 + Recall 측정 분모로 활용
**And** `detection/tests/unit/test_tier_retention_job.py`에서 Tier별 보존 분기·archive 이동·purge 동작을 검증한다

**[이미지 PII 컴플라이언스 — 미해결 항목]**

**Given** SPIKE 3.0 결과로 이미지 PII OpenAI 전송 정책이 결정될 때
**Then** Story 3-3의 호출 경로에 마스킹 또는 텍스트-only fallback이 적용된다 (법무 결정 결과에 따름)
**And** 결정이 미정인 동안에는 환경변수 `LLM_SEND_IMAGES=true|false` 토글로 즉시 차단 가능

### Story 3.7: 멀티 에이전트 오케스트레이터 + 트리아지 + LinkTracer (2026-06-11 재정의 — 신규)

> **2026-06-11 재정의 (Correct Course).** 멀티 에이전트 골격의 1차 증분. 본 스토리 완료 시 `DETECTION_MODE=agentic`로 E2E 데모가 성립한다(escalate 경로는 트리아지 verdict로 degrade). LinkTracer는 운영자의 "유통 경로 추적 에이전트" 요청을 1-hop으로 구현한다.

개발자로서,
큐에서 소비한 게시글이 결정론적 오케스트레이터를 거쳐 정규화 → 트리아지 분류되고, 위험 링크가 1-hop으로 추적되어 증거가 남기를 원한다,
그래서 사이트별 설정 없이 게시글 맥락을 자가 추론하면서 외부 유통 경로까지 증거 기반으로 탐지한다.

**Acceptance Criteria:**

**Given** `DETECTION_MODE=agentic` 환경에서 `CrawlEvent`가 소비될 때
**When** `detection/src/agents/orchestrator.py`가 실행되면
**Then** **S0 `normalizer.py`**(순수 Python, LLM 없음)가 NFKC 정규화·zero-width 제거·변형문자 매핑(ㅎr킹→하킹 등 정적 테이블)·반복문자 축약을 수행하고 markdown에서 `links[]`를 추출한다 (운영자 "텍스트 클린 에이전트" 요청)
**And** **S1 `triage_agent.py`**(gpt-4o-mini)가 정규화 텍스트로 `{type, confidence, game_context, reason_ko, translated_text_ko, needs_image, needs_link_trace}`를 산출한다 — `game_context`는 게시글 자체에서 **자가 추론**한다 (FR12-C 라우팅 제거)
**And** **사이트→게임 라우팅 제거**: `prompts/registry.py`의 `SOURCE_ID_TO_GAME` 매핑과 `prompts/games/*.md` 게임별 오버레이를 분류 경로에서 제거한다 (라벨 CLI용 매핑은 `scripts/label_detections.py`로 이동, Story 3-5 무영향)
**And** **공용 도메인 가이드 유지**: 사이트 비종속 큐레이션 지식(게임 은어 사전 — 外掛/私服/代儲/蝦皮 등 + 오탐 방지 규칙 — 메이플=NEXON 비교군·52pojie=게임 무관 크랙 포럼 등)을 **단일 공용 가이드**(`prompts/domain_guide.md` 또는 동등)로 통합하여 트리아지 프롬프트에 항상 주입한다 — 게임별 파일 분기 없이 모든 게시글에 동일 제공 (FR12-C 도메인 지식 보존). 기존 `games/*.md` 7종의 은어·오탐 규칙을 게임 라벨 없이 병합
**And** **FAST PATH**: `type=기타 ∧ confidence≥0.80 ∧ 의심 링크 없음`이면 트리아지 결과를 그대로 최종 verdict로 변환한다 (`image_observed=False`)
**And** **S2b `link_tracer.py`**가 escalate ∧ 링크 존재 시 게시글당 최대 3개 링크를 1-hop fetch(httpx + html2text)하여 `LinkEvidence{url, kind, fetch_status, page_title, is_distribution_site, indicators[]}`를 산출한다 (FR12-B)
**And** `link_fetch_guard.py`가 (a) http/https + 80/443만 (b) DNS 해석 후 사설/loopback/link-local/메타데이터(169.254.169.254) IP 차단 (c) redirect 매 hop 재검증(최대 3) (d) 응답 512KB 캡 (e) `application/*` content-type 즉시 abort(바이트 폐기, "배포 파일 직링크" 증거만 기록)를 강제한다 — 단위 테스트 ≥8건
**And** discord.gg / t.me / open.kakao.com / line.me / qq.com 초대링크는 fetch 없이 `kind=messenger`로 분류한다
**And** 동일 URL은 Redis `linktrace:{sha256(url)}` 캐시(TTL 7일)로 재fetch를 방지한다 — 캐시 hit 테스트 포함
**And** `LINK_TRACE_PROXY` 환경변수가 설정되면 모든 fetch가 egress 프록시를 경유한다
**And** **agent_runs 테이블**(Flyway `V10__agent_runs.sql`, additive)이 추가되고 `detection_repository.py`가 detections + agent_runs를 **동일 트랜잭션**으로 저장한다 (detections 멱등 conflict 시 agent_runs도 skip). detections 테이블 계약은 불변
**And** `DETECTION_MODE=single` 폴백이 그대로 동작하여 기존 테스트 회귀 0 + 외부 호출 0 (mock 에이전트로 검증)
**And** **출력 계약 불변 회귀 테스트**: agentic 모드가 저장하는 `detections` 행이 single 모드와 동일한 필드 집합(`type, confidence, reason_ko, translated_text_ko, image_observed` + 파생 `tier, is_illegal`)을 채움을 검증하는 테스트가 추가되어, 스키마/DTO(`DetectionResponse`)/프론트(`Detection` 타입) 계약이 깨지면 CI에서 즉시 실패한다 — 백엔드→프론트 무변경 보장 (agent_runs는 별도 테이블, 본 계약에 미포함)
**And** 로컬 dev DB drift(수동 V5 상태) 대응: V10 적용 전 flyway baseline/repair 절차를 task 노트에 명시 (Claude 직접 적용 차단 → 운영자 `!` 실행)

### Story 3.8: ImageAnalyst + Synthesizer + 게시글당 예산 가드 (2026-06-11 재정의 — 신규)

> **2026-06-11 재정의 (Correct Course).** escalate 심층 경로를 완성한다. 이미지 분석과 증거 통합 verdict가 5필드 스키마를 충족하고, 게시글당 비용이 강제된다.

개발자로서,
의심 게시글의 이미지가 분석되고 모든 증거(본문·트리아지·이미지·링크)가 통합되어 최종 판정이 내려지되 게시글당 비용이 통제되기를 원한다,
그래서 정확도를 높이면서도 escalate 게시글의 비용 폭증을 막는다.

**Acceptance Criteria:**

**Given** Story 3-7의 escalate 경로가 동작하는 상태에서
**When** 게시글이 escalate되면
**Then** **S2a `image_analyst.py`**(gpt-4o)가 이미지 존재 시 핵 UI/사설서버 배너/워터마크/연락처를 판독하여 `ImageEvidence{illegal_indicators[], extracted_text, summary_ko, contributes}`를 산출한다 (FR16-NEW-1)
**And** S2a와 S2b(LinkTracer)는 `ThreadPoolExecutor`로 **병렬 실행**된다 (기존 sync 워커 구조 유지, 침습 최소)
**And** **S3 `synthesizer.py`**(gpt-4o)가 본문 + 트리아지 + 이미지/링크 증거를 통합하여 기존 `{type, confidence, reason_ko, translated_text_ko, image_observed}` 5필드 스키마를 산출한다 — `image_observed`는 S2a `contributes` 값, `reason_ko`에 채택한 증거를 1문장 포함
**And** 증거 충돌 시 더 구체적 증거(다운로드 페이지 확인·핵 UI 스크린샷) 우선 + 다중 type 신호 시 최상위 Tier type 채택을 S3 프롬프트에 명시
**And** **게시글당 예산 가드**: `AGENT_POST_BUDGET_USD`(기본 0.02) 초과 시 잔여 stage를 스킵하고 현재까지의 증거로 degrade 종결(S3-mini 또는 트리아지 verdict) — 전수 저장 정책 유지
**And** S3 호출 실패 시 트리아지 결과로 degrade 저장(verdict 없는 것보다 1차 분류라도 저장)하고 `agent_runs`에 실패 trace를 기록한다
**And** escalation율·스테이지별 비용·latency가 구조화 로그(`correlation_id` 포함)로 남는다 — 50% 초과 지속 시 fast-path 임계 하향 조정 신호
**And** 신규 단위/통합 테스트가 mock 에이전트로 escalate 전 경로 + 예산 degrade + S3 실패 fallback을 검증 (외부 호출 0)

### Story 3.9: 신·구 아키텍처 A/B 정확도 비교 + 비용 실측 + 데모 리허설 (2026-06-11 재정의 — 신규)

> **2026-06-11 재정의 (Correct Course).** Story 3-5에서 수집한 human_label 코퍼스를 ground truth로 single vs agentic 모드를 비교하고, 데모 시나리오를 확정한다.

QA/AI 담당으로서,
신·구 아키텍처를 동일 라벨셋으로 비교하고 게시글당 비용을 실측하여 데모 모드를 결정하기를 원한다,
그래서 "명확 불법 10건 실시간 탐지" 데모를 신뢰도 높게 성공시킨다.

**Acceptance Criteria:**

**Given** Story 3-5의 `human_label IS NOT NULL` detections와 양 모드(`single` / `agentic`)가 준비된 상태에서
**When** A/B 비교 스크립트를 실행하면
**Then** 동일 게시글을 양 모드로 재분류하여 `model_version` 분리(`openai:...` vs `agentic:v1:...`)로 DB에 공존시키고, agreement + Tier별 Recall + Precision 비교표를 `docs/`에 기록한다
**And** agentic 모드의 게시글당 **평균 비용 ≤ $0.005, p95 ≤ $0.02**를 실측 확인하고, escalation율을 보고한다
**And** fast-path 임계(0.80)를 실측 결과로 튜닝한다
**And** `llm_mock.py`에 에이전트 모드를 추가하여 오프라인 데모 리허설이 가능하다
**And** "명확 불법(가격·텔레그램·매크로 명시) 10건 실시간 탐지" 데모 리허설 스크립트가 작성되고, single 모드 즉시 회귀 절차가 문서화된다

**[T1 알림 E2E 검증 — 2026-06-11 흡수, 구 Story 3.10]**

> **2026-06-11 재정의.** 알림 시스템은 이미 완성돼 있음(백엔드 `notification_*` 4테이블 + `NotificationEventProcessor` 5초 폴링 + 채널 6종 + 룰 엔진 `minTier` 필터 + 프론트 3탭 UI + detection의 `notification_events` 적재). 따라서 구 Story 3-10의 `t1_notifier.py` 신규 구현은 **중복이라 폐기**하고, "기존 시스템이 agentic 파이프라인과 함께 동작하는지" 검증만 본 스토리에 흡수. **사람 리뷰 큐(human-in-the-loop)**는 현재 백엔드 즉시 발송 설계와 충돌하여 deferred-work 이월.

**Given** agentic 모드로 `tier=T1` 탐지가 저장될 때
**When** detection이 `notification_events`(PENDING)를 적재하고 백엔드 `NotificationEventProcessor`가 폴링하면
**Then** 대시보드에서 생성한 `minTier=T1` 룰에 매칭되어 설정된 채널(Discord/Slack 등)로 발송되고 `notification_deliveries`에 이력이 남음을 **E2E로 확인**한다 (신규 코드 없이 기존 시스템 검증)
**And** `minTier=T1` 룰 설정 방법 + 필요한 배포 환경변수(`NOTIFICATION_ENCRYPTION_KEY`, `tracker.notifications.scheduler.enabled`)가 문서화된다
**And** 사람 리뷰 큐 + T2 다이제스트/T3 주간 리포트는 본 스토리 범위 외 (deferred-work 참조)

---

## Epic 4: 탐지 결과 조회 및 통계 대시보드

보안 담당자가 탐지된 불법 게시글 목록을 필터·정렬로 탐색하고, 상세 화면에서 원본 URL로 즉시 조치하며, 팀장이 주간·월간 통계로 보고 자료를 준비할 수 있다.

### Story 4.1: Spring REST API 기반 구조 및 탐지 목록 엔드포인트

백엔드 개발자로서,  
Spring Boot REST API의 기본 레이어 구조와 `GET /detections` 엔드포인트가 구현되기를 원한다,  
그래서 프론트엔드 개발자가 실제 API를 연동하여 탐지 목록을 표시할 수 있다.

**Acceptance Criteria:**

**Given** RDS `detections` 테이블에 탐지 결과가 저장된 상태에서  
**When** `GET /detections?date=2026-04-24&site=tailstar.net&type=매크로_판매&lang=ko&page=0&size=20`을 요청하면  
**Then** 신뢰도 임계값 0.70 이상인 결과만 반환된다 (FR22)  
**And** 응답 JSON 필드는 camelCase(`isIllegal`, `detectedAt`, `confidence`)를 사용한다  
**And** `detectedAt`은 ISO 8601 UTC 문자열(`2026-04-24T14:30:00Z`)로 반환된다  
**And** 응답 p95 ≤ 500ms를 `idx_detections_filter` 복합 인덱스로 달성한다 (NFR1)  
**And** API 에러 응답은 ProblemDetail(RFC 9457) 형식(`status`, `title`, `detail`, `errorCode`)으로 반환된다  
**And** Swagger UI(`/swagger-ui.html`)에서 엔드포인트가 자동 문서화된다  
**And** `GlobalExceptionHandler`(`@ControllerAdvice`)가 모든 예외를 ProblemDetail 형식으로 처리하며 스택 트레이스를 응답에 노출하지 않는다

### Story 4.2: 탐지 상세 조회 및 수동 크롤링 트리거 엔드포인트

백엔드 개발자로서,  
탐지 상세 조회와 수동 크롤링 트리거 API가 구현되기를 원한다,  
그래서 담당자가 특정 게시글 상세 정보를 확인하고 긴급 시 즉시 크롤링을 실행할 수 있다.

**Acceptance Criteria:**

**Given** 유효한 `detection_id`가 있을 때  
**When** `GET /detections/{id}`를 요청하면  
**Then** 원문(`rawText`), 번역문(`translatedText`, 원본이 중국어인 경우), 탐지 유형(`type`), 신뢰도(`confidence`), 판단 근거(`reason`), 출처 URL(`postUrl`)이 반환된다 (FR20, FR21)  
**And** 존재하지 않는 `id`에 대해 ProblemDetail `404 DETECTION_NOT_FOUND`를 반환한다  
**When** `POST /crawl/trigger`를 요청하면  
**Then** Redis `crawl:trigger` 채널에 메시지를 PUBLISH하고 `202 Accepted`와 함께 `{"status": "triggered", "estimatedMinutes": 3}`을 반환한다 (FR6)  
**And** 응답 헤더에 `X-Correlation-ID`가 포함된다  
**And** `api/src/test/java/.../controller/DetectionControllerTest.java`에서 목록 조회·상세 조회·존재하지 않는 ID·크롤 트리거 케이스를 검증한다

### Story 4.3: 통계 엔드포인트 구현

백엔드 개발자로서,  
오늘 탐지 수·유형별·사이트별·언어별 분포와 주간·월간 추이를 반환하는 `GET /stats` API가 구현되기를 원한다,  
그래서 팀장이 보고 자료용 통계 데이터를 즉시 조회할 수 있다.

**Acceptance Criteria:**

**Given** RDS `detections`에 복수의 탐지 결과가 있을 때  
**When** `GET /stats`를 요청하면  
**Then** 오늘 총 탐지 수와 전일 대비 증감(`todayCount`, `deltaFromYesterday`)이 반환된다 (FR23)  
**And** 탐지 유형별 분포(`typeDistribution: [{type, count}]`)가 반환된다 (FR24)  
**And** 사이트별 분포(`siteDistribution: [{site, count}]`)가 반환된다 (FR25)  
**And** 언어별 분포(`langDistribution: [{lang, count}]`)가 반환된다 (FR27)  
**And** `?period=weekly` 또는 `?period=monthly` 파라미터로 추이 데이터(`trend: [{date, count}]`)가 반환된다 (FR26)  
**And** Redis DB3(`cache:detections`)에 통계 결과가 캐싱되어 반복 요청 시 RDS 쿼리 없이 응답한다

### Story 4.4: React 대시보드 메인 화면 및 라우팅 구조

프론트엔드 개발자로서,  
React Router v7 기반 라우팅 구조와 메인 대시보드 화면이 구현되기를 원한다,  
그래서 담당자가 오늘 탐지 현황을 한눈에 파악하고 각 화면으로 이동할 수 있다.

**Acceptance Criteria:**

**Given** 브라우저에서 대시보드 URL에 접속할 때  
**When** 메인 대시보드(`/`)가 로드되면  
**Then** 오늘 총 탐지 수와 전일 대비 증감이 표시된다 (FR23, UX-DR1)  
**And** 탐지 유형별 파이 차트(Recharts `PieChart`)가 표시된다 (FR24, UX-DR1)  
**And** 사이트별 바 차트(Recharts `BarChart`)가 표시된다 (FR25, UX-DR1)  
**And** 오늘 탐지 0건일 때 "오늘 탐지된 게시글이 없습니다" Empty State 메시지가 표시된다  
**And** 마지막 업데이트 시각("N분 전 업데이트")이 대시보드 우측 상단에 표시된다  
**And** React Router v7로 `/`, `/detections`, `/detections/:id`, `/stats` 라우팅이 동작한다 (UX-DR6)  
**And** TanStack Query `useQuery({ refetchInterval: 60_000 })`로 60초마다 통계가 자동 갱신되며, 갱신 중에는 전체 스피너 대신 상단 진행 인디케이터만 표시된다  
**And** `ErrorBoundary`와 `LoadingSpinner` 공통 컴포넌트가 모든 페이지에 적용된다 (UX-DR5)  
**And** 대시보드 초기 로드 시간이 Chrome 데스크톱(1280px 이상)에서 ≤ 3초이다 (NFR2)

### Story 4.5: 탐지 목록·상세 화면 및 파이프라인 반영 검증

프론트엔드 개발자로서,  
탐지 목록과 상세 화면이 구현되고 크롤링 완료 후 5분 이내 대시보드 반영이 검증되기를 원한다,  
그래서 담당자가 최신 탐지 게시글을 신뢰하고 즉시 조치할 수 있다.

**Acceptance Criteria:**

**Given** `/detections`에 접속할 때  
**When** 날짜·사이트·탐지 유형·언어 필터를 적용하면  
**Then** 필터 조건에 맞는 탐지 목록이 신뢰도 내림차순으로 표시된다 (FR17, FR18, FR19, UX-DR2)  
**And** 신뢰도 구간별 색상 배지가 표시된다: 🔴 High(≥0.8), 🟡 Medium(0.5~0.8), ⚫ Low(<0.5)  
**And** 신뢰도 0.70 미만 게시글은 목록에 노출되지 않는다 (FR22)  
**And** 필터 조건에 맞는 결과가 없을 때 "해당 조건에 맞는 탐지 결과가 없습니다" Empty State와 필터 초기화 버튼이 표시된다  
**And** offset 기반 페이지네이션(`page/size`)이 동작한다  
**And** 필터 변경 시 전체 페이지 스피너 대신 목록 영역만 로딩 상태로 전환된다  
**When** 목록에서 게시글을 클릭하면  
**Then** `/detections/:id` 상세 화면에서 원문·번역문·유형·신뢰도·판단 근거·출처 URL이 표시된다 (FR20, UX-DR3)  
**And** 출처 URL 클릭 시 새 탭(`target="_blank"`)으로 원본 게시글 사이트로 이동한다 (FR21)  
**And** 출처 URL 옆에 링크 복사 버튼이 제공된다  
**And** 수동 크롤링 트리거 버튼 클릭 시 버튼이 "실행 중..." 상태로 비활성화되고 스피너가 표시되며, 완료 시 토스트 알림이 표시된다  
**And** 크롤링 완료 후 5분 이내 신규 탐지 게시글이 대시보드 목록에 반영됨을 성능 전용 테스트(`tests/performance/test_pipeline_latency.py`)에서 검증한다 (FR32, NFR4) — 이 테스트는 CI 주 파이프라인에서 분리된 별도 스테이지에서 실행된다

### Story 4.6: 통계 화면 구현

프론트엔드 개발자로서,  
주간·월간 탐지 추이와 사이트별·언어별 분포를 차트로 볼 수 있는 통계 화면이 구현되기를 원한다,  
그래서 팀장이 별도 집계 요청 없이 5분 내에 주간 보고 자료를 준비할 수 있다.

**Acceptance Criteria:**

**Given** `/stats`에 접속할 때  
**When** 통계 화면이 로드되면  
**Then** 주간 탐지 추이 라인 차트(Recharts `LineChart`, `?period=weekly`)가 표시된다 (FR26, UX-DR4)  
**And** 월간 탐지 추이 차트(`?period=monthly`)로 전환할 수 있다  
**And** 사이트별 탐지 분포 바 차트가 표시된다 (FR25, UX-DR4)  
**And** 언어별 탐지 분포 파이 차트가 표시된다 (FR27, UX-DR4)  
**And** 선택한 기간에 데이터가 없을 때 "해당 기간에 탐지 데이터가 없습니다" Empty State가 표시된다  
**And** TanStack Query 60초 폴링으로 통계가 자동 갱신된다  
**And** CSV 내보내기 기능은 이 스토리 범위 밖(Out of Scope)이며, Growth 단계 백로그에 기록된다  
**And** API 오류 시 `ErrorBoundary`가 사용자에게 에러 메시지를 표시하고 앱이 크래시되지 않는다 (UX-DR5)

### Story 4.7: 대시보드 모바일 지원 (Tailwind md 768px breakpoint)

> **2026-05-13 신설.** PRD L233 / UX Spec L1503·L1567 "모바일 out-of-scope, Growth 단계" 폐기 PIVOT. 외부 운영자가 모바일에서도 긴급 조치(원본 URL 점프 + 수동 크롤링 트리거)를 수행해야 하는 운영 요구.

프론트엔드 개발자로서,  
Tracker 대시보드를 모바일 (< 768px) 환경에서도 사용할 수 있기를 원한다,  
그래서 외부에 있는 운영자가 알림을 받았을 때 노트북 없이도 모바일로 탐지 상세를 확인하고 원본 URL로 점프해 조치할 수 있다.

**Acceptance Criteria:**

**Given** Tailwind `md` (768px) breakpoint를 모바일 분기로 채택할 때  
**When** 사용자가 < 768px 뷰포트로 접속하면  
**Then** `useIsMobile()` 훅(`window.matchMedia('(max-width: 767px)')` 기반)이 모바일 상태를 반환한다 (UX-DR7)  
**And** Sidebar는 `< lg` 뷰포트에서 햄버거 버튼(`aria-label="메뉴 열기"`) → vaul drawer 슬라이드로 전환된다  
**And** 라우트 전환 시 drawer가 자동으로 닫힌다 (translate-x-full로 viewport 밖 이동)  
**And** DetectionList는 `< md`에서 `<table>` 숨김, `DetectionCard` 그리드로 교체된다 — 행 클릭 = 상세 진입  
**And** 모바일에서 가로 스크롤(horizontal table overflow) 0  
**And** FilterBar는 `< md`에서 "필터" 버튼 → bottom Drawer(vaul)로 전체 필터 패널(날짜·사이트·유형·언어)을 표시한다  
**And** Dashboard / Detection Detail / Stats 페이지는 < 768px 에서 카드·차트가 단일 컬럼으로 stack되며 가로 스크롤 없이 표시된다  
**And** 키보드 단축키(j/k/enter/o/c/esc/g+t/g+d/g+l/g+s)는 데스크톱 전용으로 유지하며, 모바일에서는 비활성화된다 (혹은 무해)  
**And** Playwright e2e `e2e/mobile.mobile.spec.ts`에 Pixel 7 viewport 시나리오 3건이 포함된다 (햄버거 drawer / DetectionList 카드 / FilterBar bottom Drawer)  
**And** 다크 테마는 `next-themes` + `data-theme` 토글로 활성화되며, FOUC 가드를 위한 동기 스크립트가 `index.html`에 포함된다  
**And** ~~vite-plugin-pwa 가 도입되어 manifest + workbox 정적 자산 캐시(이미지/폰트만)를 제공한다 — API 응답은 캐시 제외~~ (**2026-05-14 폐기** — commit `2526ac4`, frontend-only 데모 경로 도입으로 SW 캐싱 정책 충돌. 학생 프로젝트 운영 범위에서 설치성 가치가 비용을 정당화 못함)  
**And** Story 4.5의 키보드 네비게이션·데스크톱 레이아웃 회귀가 발생하지 않는다 (기존 e2e PASS 유지)

---

## Epic 5: 시스템 운영, 모니터링 및 품질 관리

운영자가 파이프라인 실행 상태를 Grafana로 실시간 모니터링하고 DLQ 장애에 5분 내 대응하며, QA 담당자가 최종 Precision/Recall로 탐지 정확도를 검증한다.

### SPIKE 5.0: 배포 토폴로지 및 운영 인프라 상세 설계 (타임박스: 1일)

> ⏱️ **스파이크 타임박스: 1일 (Epic 5 착수 직전)**
> 산출물: 기술 결정 문서 (`docs/infrastructure-design.md`)
> 결과가 Story 5.1 / 5.2 / 5.3의 입력으로 사용됨. 본 SPIKE 미수행 시 Story 5.3 dev에서 토폴로지·호스팅·DR 결정을 임의로 내려 추후 갈아엎는 비용 발생.

인프라 담당자로서,
AWS 프로덕션 인프라 프로비저닝(Story 5.3)에 들어가기 전에 VPC 토폴로지·dashboard 호스팅·모니터링·로그·DR·비용 등 architecture.md에서 결정되지 않은 deep-dive 항목을 묶어 결정하기를 원한다,
그래서 Story 5.1/5.2/5.3 진행 시 dev가 임의 결정을 내리지 않고 일관된 사양에 따라 Terraform 모듈을 작성할 수 있다.

**Acceptance Criteria:**

**Given** Story 5.0 SPIKE 작업이 시작될 때
**When** `docs/infrastructure-design.md`가 작성되면
**Then** 다음 10개 항목에 대한 결정과 근거가 모두 기록된다:
1. **VPC 토폴로지** — AZ 개수(1개 vs 2개+), 퍼블릭/프라이빗 서브넷 분리 여부, NAT Gateway 사용 여부 (비용 vs 보안 trade-off)
2. **dashboard 호스팅** — S3 + CloudFront / Vercel / Cloudflare Pages / 별도 EC2 중 선택 + 근거
3. **Region · DNS · TLS** — AWS region **`us-east-1` 확정 (2026-05-06 학생 계정 <student-iam-user> 제약 — 다른 region에서 자원 생성 거부, 이전 ap-northeast-2 가정은 잘못된 가정)**, 도메인 사용 여부, ACM 인증서 발급 전략
4. **Load Balancer** — API EC2 단일 인스턴스 vs ALB 도입 (HTTPS 종단 / 헬스체크 / 향후 스케일 대비)
5. **모니터링 인프라 위치** — Prometheus/Grafana 호스팅 위치 (별도 EC2 / API EC2 공존 / Managed Grafana / docker-compose)
6. **로그 수집 전략** — CloudWatch Logs 통합 / 자체 stack(Loki) / structured_logger의 stdout을 어떻게 수집할지
7. **CI → AWS 배포 파이프라인** — `terraform apply` 호출 시점, EC2 코드 배포 방식(Docker pull / SCP / CodeDeploy / SSM) — Story 5.2의 입력
8. **Backup / DR 정책** — RDS automated snapshot 보관 기간, S3 versioning, 재해 복구 RPO/RTO 목표
9. **Bootstrap 절차** — Terraform state 백엔드(S3 + native locking, Terraform 1.10+ `use_lockfile = true`) 자체를 어떻게 만들지 — `infra/terraform/bootstrap/` 구체 절차
10. **비용 예측** — **월 인프라 예산 30만원(~$215, 환율 1400원/USD 기준)** 상한 내 추정. architecture.md "EC2 사이징" 결정값(Crawler r6g.large + Detection t4g.medium + API t4g.large + RDS db.t4g.micro Single-AZ) 기반으로 합계 ~$208/월(~29만원). 임계값 초과 시 알림(AWS Budgets) 옵션. BERT 도입 시 예산 재산정.
11. **NAT 운영 방식** — NAT Gateway(~$37/월, 자동 HA) / NAT Instance(t4g.nano $3/월 + 직접 운영, SPOF) / public subnet only(NAT 자체 제거, NFR7 정합 검토 필요) 중 택. 결정에 따라 Terraform networking 모듈 구조와 비용이 달라짐 — Story 5.3 AC에 반영.
12. **EC2 접근/관리 방식** — SSM Session Manager 단독(SSH 키 미사용) vs EC2 Instance Connect(임시 SSH 키) vs SSH Bastion. architecture.md 결정값은 SSM Session Manager 단독 — 구현 상 한계(Linux 외 OS, 특수 도구) 발견 시 본 SPIKE에서 백업 방식 지정.

**And** 각 항목에 대해 "선택 / 근거 / 대안 / 다음 스토리(5.1·5.2·5.3) 영향" 4개 항목이 표 또는 섹션 형식으로 기록된다
**And** 결정 결과가 `architecture.md`의 Infrastructure & Deployment 섹션에 짧은 요약 행으로 backport된다 (단일 진실의 원천 유지)
**And** Story 5.1/5.2/5.3의 AC가 본 SPIKE 결정과 충돌할 경우 SPIKE 결과를 따르도록 epics.md에 표시된다 (필요 시 AC 수정)
**And** SPIKE 결과가 비용·구현 복잡도 측면에서 Epic 5의 일정·범위를 변경해야 하면 `bmad-correct-course`를 통해 sprint plan을 조정한다



운영자로서,  
API 응답 시간·에러율·Redis 큐 깊이가 Grafana에서 실시간으로 모니터링되기를 원한다,  
그래서 파이프라인 이상 징후를 즉시 파악할 수 있다.

**Acceptance Criteria:**

**Given** Spring Boot Actuator와 Prometheus가 구성된 환경에서  
**When** `infra/prometheus/prometheus.yml`에 API EC2가 scrape 대상으로 등록되면  
**Then** `GET /actuator/prometheus`가 API 응답 시간(`http_server_requests_seconds`), 에러율, JVM 메트릭을 노출한다 (FR29)  
**And** `infra/grafana/dashboards/tracker.json`에 API p95 응답 시간, Redis `posts:queue` 깊이, `posts:dlq` 적재 건수 패널이 포함된다  
**And** `posts:dlq`에 메시지가 누적될 때 Grafana Alert이 발생하여 운영자가 5분 이내에 인지할 수 있다 (FR30, NFR12)  
**And** DLQ 임계값(≥1건) 초과 시 Grafana 알림이 실제로 발송됨을 테스트 환경에서 확인한다  
**And** `docker compose up -d`로 로컬에서 Grafana(`localhost:3000`)와 Prometheus(`localhost:9090`)가 실행된다

### Story 5.2: GitHub Actions 완전 통합 CI/CD 파이프라인

> **2026-05-06 PIVOT — OIDC + IAM Role 자동 배포 봉인, SSH `.pem` GH Secret으로 전환.** 학생 IAM 사용자 `<student-iam-user>`에서 (1) IAM Role 신규 생성 차단 (2) IAMFullAccess 등 권한 정책 attach 화이트리스트 외 차단 (`AmazonAPIGatewayPushToCloudWatchLogs` / `AWSCloud9SSMInstanceProfile` / `AWSLambdaBasicExecutionRole` 3개만 허용 — 모두 service role용) (3) AWS Access Key 발급 차단 — GHA→AWS 자동 배포 통로(OIDC / Access Key / CodeDeploy) 모두 봉인 확인. EC2 접근 통로도 SSM Session Manager / EC2 Instance Connect 모두 권한 차단되어 **SSH `.pem` 키만 가능** 확인. 외부 SaaS(Cloudflare Tunnel / Tailscale) 가입 회피 결정으로 22번 인바운드는 `0.0.0.0/0` + defense-in-depth 6 layer로 안전화.
>
> **신 사양**: GHA → Docker 이미지 빌드 → GHCR push (`GITHUB_TOKEN` + `permissions: packages: write`) → main 머지 시 `appleboy/ssh-action`으로 EC2에 SSH(`.pem` GH Secret 등록) 직결 → `docker pull` + healthcheck + 자동 롤백. **단일 EC2 docker compose** 운영 (Story 5.3 PIVOT으로 EC2 1대로 통합). 자동 배포 안전장치: `concurrency: deploy-prod / cancel-in-progress: false`, branch protection (PR + 1 리뷰, direct push 금지, auto-merge OFF), GitHub Environment "production" Secret 격리, host fingerprint verification, BuildKit registry cache `mode=max`, dependabot.yml 제거. 12 AC (이전 권장 14 AC에서 GHA 전용 deploy 키 분리 + deploy 전용 SSH 사용자 제거 — 사용자 결정으로 단일 `.pem` 사용).
>
> **신 사양 source of truth**: 5-2 스토리 파일 (`_bmad-output/implementation-artifacts/5-2-*.md`, 작성 예정).
>
> **아래 AC는 historical record** — OIDC + 4개 서브시스템 분산 배포 + JAR/Nginx 분리 가정은 모두 stale.

개발자로서,  
4개 서브시스템의 CI 파이프라인이 통합 테스트·빌드·AWS 배포까지 자동화되기를 원한다,  
그래서 코드 푸시만으로 각 EC2에 최신 버전이 배포된다.

**Acceptance Criteria:** _(2026-05-06 PIVOT 후 historical — 위 PIVOT 박스 참조)_

**Given** main 브랜치에 코드가 push될 때  
**When** GitHub Actions 워크플로우가 실행되면  
**Then** Epic 1에서 구성한 lint·unit test에 더해 통합 테스트(`crawler/tests/integration/`, `detection/tests/integration/`)가 CI에 포함된다  
**And** `api.yml`이 `./gradlew bootJar`로 JAR를 빌드하고 Crawler EC2에 SSH 배포한다  
**And** `dashboard.yml`이 `npm run build`로 정적 파일을 빌드하고 API EC2의 Nginx에 배포한다  
**And** 모든 워크플로우에서 AWS 자격증명이 GitHub OIDC + IAM Role로 처리되며 Access Key가 사용되지 않는다 (NFR6)

### Story 5.3: AWS 프로덕션 인프라 프로비저닝

> ⚠️ **OBSOLETE — 본 스토리 AC 전체가 historical record입니다.** 2026-05-06 Terraform IaC 폐기 + 2026-05-09 인프라 사양 3차/4차 PIVOT 누적으로 아래 AC는 **참고용**이며 실 인프라와 다름.
>
> **실제 채택 사양 (2026-05-11 기준)**:
> - **인프라 운영**: ClickOps (학생 IAM 자격증명 통로 0개로 Terraform apply 불가). Terraform 코드는 git history(`b7e24d3`, `bd172d9`)에 historical record로 보존
> - **EC2**: 단일 t3.xlarge x86_64 16GB (3차 PIVOT — cross-SG ingress 차단으로 2 EC2 분리 폐기, RAM 가장 큰 단일 EC2로 회귀). production 사양 r6g.large / t4g.medium / t4g.large는 git history 보존
> - **RDS**: PostgreSQL **18.3** / db.t3.micro Single-AZ (4차 PIVOT — 학생 SCP가 16/17 노출 안 해 18.3-R1만 가용)
> - **EC2 접근**: SSH `.pem` only (SSM/Instance Connect/OIDC 모두 봉인). 22번 인바운드 `0.0.0.0/0` + ed25519 + fail2ban
> - **인프라 사양 표 backport 완료**: `architecture.md` Infrastructure & Deployment 섹션, `tracker_기획서.md` 2.1.1.a 표 → 모두 단일 t3.xlarge + PG 18.3 반영 (2026-05-11)
>
> **2026-05-06 PIVOT — Terraform IaC 폐기, ClickOps로 전환.** 학생 IAM 사용자(`<student-iam-user>`)에서 자격증명 통로 0개(IAM Access Key 차단 + CloudShell `cloudshell:CreateEnvironment` deny + IAM Role 생성 deny)로 Terraform apply 자체 불가능 — 코드/CI/lint 자산 일괄 제거(commit `13d96a9`). 데모는 ClickOps + 스크린샷, 코드는 git history(`b7e24d3`, `bd172d9`) 보존. 아래 AC는 **IaC 시도 시점의 historical record**이며, ClickOps 환경에서는 **인프라 사양(EC2/RDS/SG/IAM 권한 패턴)만 동일하게 적용**하고 Terraform/CI 자동화 관련 AC(#1, #2, #14, #16, #17, #20)는 적용 불가. 상세는 Story 5.3 결과 문서 + sprint-status.yaml 참조.
>
> **전제 조건:** SPIKE 5.0(배포 토폴로지 및 운영 인프라 상세 설계)이 완료된 상태에서 시작. SPIKE 결과(`docs/infrastructure-design.md`)가 본 스토리 Terraform 모듈 작성의 입력.

인프라 담당자로서,  
AWS EC2·RDS·S3·보안 그룹이 Terraform 코드로 프로덕션 환경에 맞게 구성되기를 원한다,  
그래서 시스템이 안전하게 운영 가능한 상태로 배포되며 인프라 변경이 PR 리뷰를 거친다.

**Acceptance Criteria:** _(⚠️ 2026-05-06 PIVOT 후 historical — 실 사양은 위 OBSOLETE 박스 참조. 아래 AC는 IaC 시도 시점의 기록일 뿐 실 구현과 다름)_

**Given** AWS 계정과 IAM 권한이 준비된 상태에서  
**When** 인프라 프로비저닝이 완료되면  
**Then** 모든 AWS 리소스가 `infra/terraform/` 코드로 정의되며 Console 수동 생성(ClickOps)이 금지된다 (architecture.md "IaC 도구: Terraform" 결정 준수)  
**And** Terraform `>= 1.14` + AWS provider `~> 6.0`이 명시적으로 핀되며, `terraform-aws-modules/vpc/aws ~> 6.6` · `rds/aws ~> 7.2` · `ec2-instance/aws ~> 6.4` · `security-group/aws ~> 5.3` 공식 모듈 버전이 모두 핀된다  
**And** Crawler EC2(**r6g.large**, 2vCPU/16GB, arm64), Detection EC2(**t4g.medium**, 2vCPU/4GB, arm64), API EC2(**t4g.large**, 2vCPU/8GB, arm64) 3개 Graviton 인스턴스가 각각 분리된 보안 그룹으로 구성되며, AMI는 ARM64 명시 선택된다 (architecture.md "EC2 사이징" 결정 준수)  
**And** RDS PostgreSQL **16.13** 보안 그룹이 Detection EC2와 API EC2에서만 접근을 허용하고 퍼블릭 접근을 차단하며, **db.t4g.micro Single-AZ + automated backup 7일** 설정으로 프로비저닝된다 (NFR7)  
**And** Redis(docker-compose on API EC2) 포트가 외부 접근을 차단하고 API EC2 내부에서만 접근된다  
**And** S3 버킷 정책이 퍼블릭 접근을 차단하고 Crawler EC2 IAM Role에만 쓰기 권한을 부여하며, **VPC Gateway Endpoint(S3)**가 라우트 테이블에 추가되어 EC2→S3 트래픽이 NAT을 통과하지 않는다 (NFR8 + 비용 절감)  
**And** 각 EC2에 IAM Instance Role이 부여되어 AWS SDK가 환경변수 Access Key 없이 동작한다 (NFR6)  
**And** **EC2 접근은 SSM Session Manager**를 통해 이루어지며, 외부 22번 포트는 보안 그룹에서 완전 차단된다(SSH 키 미사용). 각 EC2 IAM Role에 `AmazonSSMManagedInstanceCore` 정책이 부여된다 (NFR6 + NFR7)  
**And** **EBS encryption by default**가 region 단위로 활성화되어 모든 EBS 볼륨이 KMS로 자동 암호화된다 (Checkov `CKV_AWS_3` 통과)  
**And** **VPC Flow Logs**가 CloudWatch Logs(14일 보관)로 적재되어 네트워크 트래픽이 감사 가능하다 (NFR9)  
**And** S3 버킷 및 RDS에 AWS CloudTrail(KMS 암호화, 모든 region) 또는 S3 Access Logging이 활성화되어 데이터 접근 이력이 기록된다 (NFR9, Checkov `CKV_AWS_35` 통과)  
**And** `infra/terraform/bootstrap/`을 1회 apply하여 state 백엔드(S3 버킷 + native locking `use_lockfile = true`, 별도 DynamoDB 테이블 불필요)가 생성되며, `infra/terraform/environments/{dev,prod}/`가 해당 백엔드를 사용한다  
**And** `infra/terraform/environments/dev/`와 `environments/prod/`가 동일 모듈을 다른 변수로 호출하며, 환경별 state는 분리된다  
**And** EC2·RDS·VPC·Security Group은 `terraform-aws-modules/{vpc,ec2-instance,rds,security-group}/aws` 공식 검증 모듈을 우선 사용하며, 자체 리소스 직접 정의는 모듈로 표현 불가능한 경우로 한정한다  
**And** 시크릿(VARCO_API_KEY 등)은 AWS Secrets Manager 또는 SSM Parameter Store에 저장되며 `tfvars`/`tfstate`에 평문으로 포함되지 않는다 (NFR5)  
**And** pre-commit hook은 `antonbabenko/pre-commit-terraform` 표준 저장소의 hook(`terraform_fmt`, `terraform_validate`, `terraform_tflint`, `terraform_checkov`, `terraform_docs`)을 사용하며, 모듈별 README.md의 Inputs/Outputs 표가 `terraform-docs`에 의해 자동 생성·갱신된다  
**And** PR에서 `terraform fmt`·`terraform validate`·TFLint·Checkov가 GitHub Actions로 자동 실행되며, 1건 이상 실패 시 머지가 차단된다  
**And** 인프라 월 비용이 **30만원(~$215) 예산 상한** 내로 운영되며, AWS Budgets 알림이 80%·100% 임계값에 설정된다 (BERT 도입 등 예산 영향 변경은 별도 협의)  
**And** PR에서 `terraform plan` 결과가 자동으로 PR 코멘트에 게시되며, dev 환경 `apply`는 main 머지 시 자동, prod 환경 `apply`는 GitHub Environments 보호 규칙으로 수동 승인을 요구한다  
**And** `infra/DATA_POLICY.md`에 수집 데이터의 탐지 목적 전용 사용 방침과 외부 공개 금지 정책이 문서화된다 (NFR9)  
**And** Terraform 모듈·환경 사용법, bootstrap 절차, drift 점검 가이드가 `infra/terraform/README.md`에 문서화된다

### Story 5.4: 최종 탐지 정확도 검증 및 E2E 데모 테스트

> **전제 조건:** Story 5.3(AWS 프로덕션 인프라)이 완료된 상태에서 실행

QA 담당자로서,  
최종 수동 라벨셋으로 Precision/Recall을 측정하고 발표 시연용 E2E 탐지 데모를 자동화하기를 원한다,  
그래서 NC AI 발표에서 명확한 불법 게시글 ≥10건의 실시간 탐지를 안정적으로 시연할 수 있다.

**Acceptance Criteria:**

**[오프라인 정확도 검증 — mock 기반, CI 실행 가능]**

**Given** `tests/fixtures/labels/manual_label_set_v1.csv`의 ≥200건 라벨셋이 준비된 상태에서  
**When** `detection/tests/quality/test_varco_precision_recall.py`를 오프라인 모드(mock 기반)로 실행하면  
**Then** Precision ≥ 0.85, Recall ≥ 0.65를 만족한다 (FR31)  
**And** 명확 케이스(가격·텔레그램·매크로 명시 게시글)의 정탐율이 ≥ 90%이다  
**And** 유형별(`매크로_판매|핵_배포|계정_거래|리세마라|기타`) 분류 결과가 출력된다  

**[라이브 검증 — 실제 VARCO API, 수동 실행]**

**Given** AWS 프로덕션 인프라(Story 5.3)와 실제 VARCO API 접근이 준비된 상태에서  
**When** `tests/quality/test_varco_live.py`를 수동으로 실행하면  
**Then** 라이브 Precision/Recall 결과가 `docs/quality-gate-final.md`에 기록된다  
**And** 라이브 검증 불가 시 오프라인 결과로 대체하되, `docs/quality-gate-final.md`에 "오프라인 검증(mock 기반)" 명시 고지가 포함된다  

**[E2E 파이프라인 데모 — 프로덕션 인프라 필요]**

**Given** Story 5.3의 AWS 프로덕션 인프라가 완료된 상태에서  
**When** `tests/e2e/test_detection_10_posts.py`를 실행하면  
**Then** 실제 파이프라인을 통해 불법 게시글 ≥10건이 탐지되고 대시보드에 표시되며, false positive 0건임을 확인한다  
**And** `tests/e2e/test_full_pipeline_smoke.py`에서 크롤링 → 전처리 → VARCO 탐지 → RDS 저장 → 대시보드 반영 전체 E2E 흐름이 오류 없이 완료된다  
**And** 모든 측정 결과가 `docs/quality-gate-final.md`에 기록된다
