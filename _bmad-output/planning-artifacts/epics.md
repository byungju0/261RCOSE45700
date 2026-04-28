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

- **[ARCH-1] 모노레포 초기화:** 모노레포 디렉토리 구조(crawler/, detection/, api/, dashboard/, shared/, infra/, .github/workflows/) 초기화 및 서브시스템별 스캐폴딩 (Python pip, Spring Boot 4.0.5 Initializr, Vite 8 + React-TS)
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

시스템이 지정된 커뮤니티 사이트를 1시간 주기로 자동 크롤링하고, 전처리된 게시글 후보를 AI 탐지 큐에 전달한다. Cloudflare 우회 가능성을 초기 스파이크 스토리로 검증하고, 크롤러 기본 헬스체크를 포함한다.

> **Party Mode 반영:** Cloudflare 바이패스 스파이크 스토리를 Epic 2 첫 번째 스토리로 배치(Winston). 크롤러 에러 처리(사이트 다운, rate limit) 명시(Winston). 크롤러 출력 스키마를 Epic 1 계약과 연동(Amelia).

**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR8, FR9, FR10, FR28
**NFRs covered:** NFR10, NFR13(S3), NFR15, NFR17
**ARCH covered:** ARCH-10

---

### Epic 3: AI 기반 불법 게시글 탐지 파이프라인

시스템이 크롤러 큐에서 게시글을 소비하고 VARCO Translation + LLM으로 자동 분류하여, 신뢰도·판단 근거를 포함한 탐지 결과를 RDS에 저장한다. Epic 3 완료 기준에 Precision 사전 임계값(≥0.80) 측정을 포함한다.

> **Party Mode 반영:** Precision/Recall 사전 측정을 Epic 3 완료 기준에 추가(Murat 강력 권고). 배치 ≤ 30분 측정 포인트 Epic 3에 추가(Murat). DLQ idempotency 테스트 명시(Murat). VARCO API 계약 테스트(스키마 변경 대응) 추가(Murat).

**FRs covered:** FR11, FR12, FR13, FR14, FR15, FR16
**NFRs covered:** NFR3(배치 측정), NFR11, NFR13(Redis AOF), NFR14, NFR16

---

### Epic 4: 탐지 결과 조회 및 통계 대시보드

보안 담당자가 탐지된 불법 게시글 목록을 필터·정렬로 탐색하고, 상세 화면에서 원본 URL로 즉시 조치하며, 팀장이 주간·월간 통계로 보고 자료를 준비할 수 있다. API 스켈레톤과 대시보드 스켈레톤은 Epic 2~3과 병렬로 시작 가능하다.

> **Party Mode 반영:** API p95 ≤ 500ms 성능 측정을 Epic 4 완료 기준에 포함(Murat). E2E는 핵심 플로우 2~3개만, Component 테스트 우선(Murat). API skeleton을 Epic 2와 병렬 착수 가능(John, Amelia).

**FRs covered:** FR17, FR18, FR19, FR20, FR21, FR22, FR23, FR24, FR25, FR26, FR27, FR32
**UX covered:** UX-DR1, UX-DR2, UX-DR3, UX-DR4, UX-DR5, UX-DR6
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
**And** `api/`는 Spring Boot 3.4.x + Java 21 Gradle 프로젝트로 초기화된다 (dependencies: web, data-jpa, postgresql, actuator, lombok, validation)  
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

시스템이 지정된 커뮤니티 사이트를 1시간 주기로 자동 크롤링하고, 전처리된 게시글 후보를 AI 탐지 큐에 전달한다. Cloudflare 우회 가능성을 초기 스파이크 스토리로 검증하고, 크롤러 기본 헬스체크를 포함한다.

### SPIKE 2.1: Cloudflare 우회 가능성 검증 (타임박스: 2일)

> ⏱️ **스파이크 타임박스: 2일 (Epic 2 착수 직후)**  
> 산출물: 기술 결정 문서 (`docs/cloudflare-spike-result.md`)  
> 결과에 따라 Story 2.2의 구현체 선택이 확정됨

개발자로서,  
Playwright+stealth로 Cloudflare JS 챌린지 사이트를 우회할 수 있는지 빠르게 검증하기를 원한다,  
그래서 불가능할 경우 FlareSolverr 대안으로 전환하는 시점을 조기에 결정할 수 있다.

**Acceptance Criteria:**

**Given** Playwright+stealth 브라우저가 설정된 환경에서  
**When** tailstar.net 또는 Cloudflare 보호 사이트에 접속 요청을 보내면  
**Then** Cloudflare 챌린지 페이지를 통과하여 실제 게시글 HTML을 응답받거나, 실패 시 FlareSolverr 연동 방안을 기술 결정 문서(`docs/cloudflare-spike-result.md`)에 기록한다  
**And** 스파이크 결과에 따라 `crawler/src/browser/stealth_browser.py` 또는 `crawler/src/browser/flaresolverr.py` 중 사용할 구현체가 결정되며, 결정 내용이 `docs/cloudflare-spike-result.md`에 명시된다  
**And** 결정된 구현체에 대한 단위 테스트 1건 이상이 `crawler/tests/unit/test_browser.py`에 작성된다  
**And** FlareSolverr 선택 시 Story 2.2 AC를 해당 구현체 기준으로 팀 합의 후 업데이트한다

### Story 2.2: ProxyProvider 추상화 및 기본 크롤러 구현

개발자로서,  
ProxyProvider 인터페이스와 첫 번째 사이트 크롤러가 구현되기를 원한다,  
그래서 프록시 교체 없이 크롤러 핵심 로직을 개발하고 테스트할 수 있다.

**Acceptance Criteria:**

**Given** `crawler/src/proxy/proxy_provider.py`에 ProxyProvider Protocol이 정의될 때  
**When** `ProxyBroker` 구현체가 ProxyProvider를 상속하면  
**Then** `ProxyBroker`를 `NodeMaven` 구현체로 교체할 때 크롤러 핵심 로직(`stealth_browser.py`) 코드 수정이 불필요하다 (NFR15)  
**And** `crawler/src/sites/base_site.py`가 `parse(html: str) -> ParseResult` 추상 메서드를 정의하며, `None` 반환 대신 `ParseError`를 raise한다  
**And** `crawler/src/sites/tailstar.py`가 `BaseSite`를 상속하여 tailstar.net 게시글 목록과 본문을 파싱한다  
**And** `crawler/tests/unit/test_html_parser.py`에서 `tests/fixtures/html/sample_illegal_post.html`을 입력으로 파싱 결과를 검증한다  
**And** 사이트 다운(5xx), rate limit(429), timeout 시나리오에 대한 예외 처리가 구현되며 각 케이스에 대한 단위 테스트가 존재한다

### Story 2.3: 콘텐츠 전처리 파이프라인 구현

개발자로서,  
수집된 HTML에서 본문을 추출하고 언어 감지·중복 체크·키워드 필터가 순차적으로 실행되기를 원한다,  
그래서 AI 탐지 큐에는 관련성 높은 게시글만 전달된다.

**Acceptance Criteria:**

**Given** 크롤링으로 수집된 원본 HTML이 있을 때  
**When** 전처리 파이프라인이 실행되면  
**Then** `html_parser.py`가 광고·네비게이션을 제거하고 제목·본문·이미지 URL을 추출한다 (FR7)  
**And** `language_detector.py`가 게시글 언어를 `ko`, `zh-CN`, `zh-TW` 중 하나로 감지한다 (FR8)  
**And** `dedup_checker.py`가 게시글 본문 SHA-256 해시를 Redis DB1(`posts:dedup`)에서 조회하여 이미 처리된 게시글을 건너뛴다 (FR9)  
**And** `keyword_filter.py`가 불법 프로그램 관련 키워드(매크로, 핵, 外挂, 破解, 텔레그램 등)가 포함된 게시글만 통과시킨다 (FR10)  
**And** 전처리를 통과한 게시글만 `shared/models/crawl_event.py` 스키마로 직렬화된다  
**And** `crawler/tests/unit/test_keyword_filter.py`와 `test_dedup_checker.py`에서 각각 정탐/오탐 케이스를 검증한다

### Story 2.4: S3 원본 아카이브 및 이미지 수집

개발자로서,  
크롤링된 원본 텍스트와 이미지가 S3에 보관되기를 원한다,  
그래서 EC2 재시작 후에도 원본 데이터를 복구할 수 있다.

**Acceptance Criteria:**

**Given** 크롤링이 완료된 게시글이 있을 때  
**When** `s3_uploader.py`가 실행되면  
**Then** 원본 HTML 텍스트가 `s3://{S3_BUCKET_NAME}/raw/{site}/{YYYY-MM-DD}/{post_id}.html` 경로로 업로드된다 (FR5)  
**And** 첨부 이미지가 `s3://{S3_BUCKET_NAME}/images/{site}/{YYYY-MM-DD}/{post_id}/{filename}` 경로로 업로드된다 (FR4)  
**And** S3 업로드는 EC2 IAM Role을 사용하며 Access Key가 코드에 하드코딩되지 않는다 (NFR6)  
**And** S3 업로드 실패 시 예외를 raise하고 구조화 로그에 `correlation_id`와 함께 기록된다  
**And** S3 업로드 성공 후 `crawl_event`에 S3 원본 경로가 포함된다

### Story 2.5: APScheduler 기반 자동 크롤링 및 수동 트리거

개발자로서,  
크롤링이 1시간 주기로 자동 실행되고 Redis pub/sub으로 즉시 트리거할 수 있기를 원한다,  
그래서 긴급 상황에서 담당자가 수동으로 즉시 크롤링을 시작할 수 있다.

**Acceptance Criteria:**

**Given** `CRAWL_INTERVAL_MINUTES` 환경변수가 설정된 환경에서  
**When** `crawl_scheduler.py`가 시작되면  
**Then** APScheduler가 `CRAWL_INTERVAL_MINUTES`값 주기로 크롤링 Job을 자동 실행한다 (FR1, FR28, NFR17)  
**And** APScheduler Job에 `max_instances=1`, `misfire_grace_time=60`이 설정되어 중복 실행이 방지된다 (ARCH-10)  
**And** `trigger_listener.py`가 Redis `crawl:trigger` 채널을 구독하여 메시지 수신 시 즉시 크롤링을 실행한다 (FR6)  
**And** 크롤링 완료 후 전처리를 통과한 게시글이 Redis DB0 `posts:queue`에 LPUSH된다  
**And** APScheduler 프로세스 재시작 후 다음 주기에 자동으로 크롤링이 재개된다 (NFR10)  
**And** `crawler/tests/integration/test_crawl_pipeline.py`에서 mock 사이트를 대상으로 크롤링 → 전처리 → Redis enqueue 흐름을 검증한다  
**And** 통합 테스트 결과로 크롤 성공률 ≥95%, 중복 제거율 ≥90%를 만족해야 Epic 3 착수 조건을 충족한다

### Story 2.6: PTT·Dcard 크롤러 어댑터 구현

개발자로서,  
대만 커뮤니티 사이트 PTT와 Dcard 크롤러가 BaseSite를 상속하여 구현되기를 원한다,  
그래서 대만어(번체) 게시글을 자동 수집하여 다국어 탐지 파이프라인을 검증할 수 있다.

**Acceptance Criteria:**

**Given** `crawler/src/sites/base_site.py`의 BaseSite 추상화가 완료된 상태에서  
**When** `ptt.py`와 `dcard.py`가 구현되면  
**Then** `ptt.py`가 PTT BBS 게시판(예: Gossiping, HatePolitics) 게시글 목록과 본문을 파싱한다  
**And** `dcard.py`가 Dcard 포럼 게시글을 파싱하며, JS 렌더링이 필요한 경우 Playwright 브라우저를 사용한다  
**And** 각 사이트별 rate limit 설정(`PTT_RATE_LIMIT`, `DCARD_RATE_LIMIT`)이 환경변수로 분리되어 tailstar.net과 독립적으로 제어된다  
**And** PTT 세션 기반 인증(`.ptt.cc` 쿠키)이 처리되며, 인증 실패 시 `ParseError`를 raise한다  
**And** `crawler/tests/unit/test_ptt.py`와 `test_dcard.py`에서 `tests/fixtures/html/`의 샘플 HTML로 파싱 결과를 검증한다

### Story 2.7: tieba·52pojie·NGA 크롤러 어댑터 구현

개발자로서,  
중국 커뮤니티 사이트 tieba, 52pojie, NGA 크롤러가 구현되기를 원한다,  
그래서 중국어 게시글을 수집하여 VARCO Translation 파이프라인의 다국어 처리를 실제 데이터로 검증할 수 있다.

**Acceptance Criteria:**

**Given** ProxyProvider 추상화(Story 2.2)와 전처리 파이프라인(Story 2.3)이 완료된 상태에서  
**When** `tieba.py`, `fiftytwo_pojie.py`, `nga.py`가 구현되면  
**Then** 각 크롤러가 GFW 우회를 위해 ProxyBroker를 통한 프록시를 사용한다  
**And** 중국어 GB2312/UTF-8 인코딩이 올바르게 처리된다  
**And** tieba는 Baidu 계정 토큰 없이 공개 게시글만 수집하며, 인증 요구 게시글은 건너뛴다  
**And** 각 사이트의 크롤링 성공률이 `crawler/logs/site_stats.json`에 기록되어 실측 기반 NodeMaven 도입 시점 결정에 활용된다  
**And** 중국 사이트 차단으로 수집 실패 시 경고 로그를 남기고 다음 사이트로 진행하며 파이프라인이 중단되지 않는다  
**And** `crawler/tests/unit/test_tieba.py`에서 샘플 HTML 파싱을 검증한다

---

## Epic 3: AI 기반 불법 게시글 탐지 파이프라인

시스템이 크롤러 큐에서 게시글을 소비하고 VARCO Translation + LLM으로 자동 분류하여, 신뢰도·판단 근거를 포함한 탐지 결과를 RDS에 저장한다. Epic 3 완료 기준에 Precision 사전 임계값(≥0.80) 측정 포함.

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

### Story 3.2: VARCO Translation 연동 및 rate limit 제어

개발자로서,  
중국어·번체 게시글이 VARCO Translation API를 통해 한국어로 번역되고, API 호출량이 토큰 버킷으로 자동 제어되기를 원한다,  
그래서 rate limit 초과 없이 번역 파이프라인이 안정적으로 실행된다.

**Acceptance Criteria:**

**Given** `crawl_event`의 `language`가 `zh-CN` 또는 `zh-TW`인 게시글이 있을 때  
**When** `translate.py`가 실행되면  
**Then** VARCO Translation API를 호출하여 한국어 번역문을 반환한다 (FR11)  
**And** `language`가 `ko`인 게시글은 Translation API 호출을 건너뛴다  
**And** `token_bucket.py`가 Redis DB2(`varco:rate_limit`)를 사용하여 API 호출 전 토큰 소비를 체크하고, 토큰 부족 시 자동 대기 후 재시도한다 (FR16, NFR14)  
**And** `detection/tests/unit/test_token_bucket.py`에서 토큰 소진 → 대기 → 재충전 → 재시도 흐름을 `varco_mock.py`의 `mock_response_rate_limited.json`으로 검증한다  
**And** `varco_mock.py`가 `simulate_latency(ms)` 메서드를 지원하여 p95 기준 200ms 이상의 지연을 시뮬레이션할 수 있다  
**And** 모든 API 호출 로그에 `correlation_id`가 포함된다

### Story 3.3: VARCO LLM 분류 및 재시도·DLQ 처리

개발자로서,  
게시글이 VARCO LLM으로 불법 여부와 유형이 분류되고, 실패 시 3회 재시도 후 DLQ로 격리되기를 원한다,  
그래서 일시적 API 장애에도 데이터 유실 없이 파이프라인이 지속된다.

**Acceptance Criteria:**

**Given** 번역이 완료된(또는 한국어인) 게시글이 있을 때  
**When** `llm_classifier.py`가 실행되면  
**Then** VARCO LLM API를 호출하여 `is_illegal: bool`, `type: Enum(매크로_판매|핵_배포|계정_거래|리세마라|기타)`, `confidence: float(0~1)`, `reason: str`을 반환한다 (FR12, FR13, FR14)  
**And** API 호출 실패 시 `retry_handler.py`가 최대 3회 재시도하고, 3회 초과 시 메시지를 `posts:dlq`로 이동한다 (FR15, NFR11)  
**And** `tests/fixtures/varco/mock_response_timeout.json`을 활용한 통합 테스트에서 3회 실패 → DLQ 이동을 검증한다  
**And** DLQ 이동된 메시지는 `posts:processing`에서 제거된다  
**And** `detection/tests/integration/test_varco_pipeline.py`에서 번역 → 분류 → 저장 전체 흐름을 `varco_mock.py`로 검증한다

### Story 3.4: 탐지 결과 RDS 저장 및 스키마 계약 검증

개발자로서,  
탐지 결과가 RDS `detections` 테이블에 저장되고 중복 삽입이 방지되기를 원한다,  
그래서 동일 게시글이 재처리되어도 탐지 결과가 하나만 존재한다.

**Acceptance Criteria:**

**Given** VARCO LLM 분류 결과가 있을 때  
**When** `detection_repository.py`가 RDS에 저장을 시도하면  
**Then** `detections` 테이블에 `post_id`, `model_version`, `is_illegal`, `type`, `confidence`, `reason`, `detected_at`, `correlation_id`가 저장된다  
**And** 동일 `(post_id, model_version)` 조합으로 중복 삽입 시 `UniqueConstraintError`가 발생하고 로그에 기록된다 (V3 unique constraint)  
**And** `detection_repository.py`의 public 메서드가 write 전용(`save`, `batch_save`)만 노출되며, read 쿼리는 포함하지 않는다 (구현 규칙: read는 Spring API 레이어 전담)  
**And** `detection/tests/integration/test_varco_response_schema.py`에서 VARCO 응답 스키마가 `shared/interfaces/varco.py`의 Protocol과 일치함을 검증한다  
**And** VARCO 응답 스키마 변경 시 이 테스트가 CI에서 즉시 실패하도록 JSON Schema 핀닝이 적용된다

### Story 3.5: 배치 처리 시간 및 탐지 정확도 사전 측정

QA 담당자로서,  
Epic 3 완료 시점에 1회 배치 처리 시간과 탐지 Precision을 측정하기를 원한다,  
그래서 최종 목표치(배치 ≤30분, Precision ≥0.85) 달성 가능성을 조기에 검증할 수 있다.

**Acceptance Criteria:**

**Given** `tests/fixtures/labels/manual_label_set_v1.csv`의 ≥200건 라벨셋이 준비된 상태에서  
**When** `detection/tests/quality/test_varco_precision_recall.py`를 실행하면  
**Then** Precision ≥ 0.80, Recall ≥ 0.60을 만족한다 (Epic 3 사전 임계값 — 최종 목표 0.85/0.65의 버퍼)  
**And** 이 측정은 `varco_mock.py` 기반 오프라인 검증이며, 실제 VARCO API 결과와의 차이는 `docs/quality-gate-epic3.md`에 명시한다  
**And** 테스트 결과가 `{type: '매크로_판매'|'핵_배포'|...}` 별로 분류되어 출력된다  
**And** 크롤링 시작부터 RDS 저장 완료까지의 1회 배치 처리 시간이 로그에서 측정되어 ≤ 30분임을 확인한다 (NFR3)  
**And** 측정 결과가 `docs/quality-gate-epic3.md`에 기록된다

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
3. **Region · DNS · TLS** — AWS region (ap-northeast-2 등), 도메인 사용 여부, ACM 인증서 발급 전략
4. **Load Balancer** — API EC2 단일 인스턴스 vs ALB 도입 (HTTPS 종단 / 헬스체크 / 향후 스케일 대비)
5. **모니터링 인프라 위치** — Prometheus/Grafana 호스팅 위치 (별도 EC2 / API EC2 공존 / Managed Grafana / docker-compose)
6. **로그 수집 전략** — CloudWatch Logs 통합 / 자체 stack(Loki) / structured_logger의 stdout을 어떻게 수집할지
7. **CI → AWS 배포 파이프라인** — `terraform apply` 호출 시점, EC2 코드 배포 방식(Docker pull / SCP / CodeDeploy / SSM) — Story 5.2의 입력
8. **Backup / DR 정책** — RDS automated snapshot 보관 기간, S3 versioning, 재해 복구 RPO/RTO 목표
9. **Bootstrap 절차** — Terraform state 백엔드(S3 + DynamoDB) 자체를 어떻게 만들지 — `infra/terraform/bootstrap/` 구체 절차
10. **비용 예측** — 월 추정 (3 t3.medium EC2 + RDS + S3 + 데이터 전송), 임계값 초과 시 알림 옵션

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

개발자로서,  
4개 서브시스템의 CI 파이프라인이 통합 테스트·빌드·AWS 배포까지 자동화되기를 원한다,  
그래서 코드 푸시만으로 각 EC2에 최신 버전이 배포된다.

**Acceptance Criteria:**

**Given** main 브랜치에 코드가 push될 때  
**When** GitHub Actions 워크플로우가 실행되면  
**Then** Epic 1에서 구성한 lint·unit test에 더해 통합 테스트(`crawler/tests/integration/`, `detection/tests/integration/`)가 CI에 포함된다  
**And** `api.yml`이 `./gradlew bootJar`로 JAR를 빌드하고 Crawler EC2에 SSH 배포한다  
**And** `dashboard.yml`이 `npm run build`로 정적 파일을 빌드하고 API EC2의 Nginx에 배포한다  
**And** 모든 워크플로우에서 AWS 자격증명이 GitHub OIDC + IAM Role로 처리되며 Access Key가 사용되지 않는다 (NFR6)

### Story 5.3: AWS 프로덕션 인프라 프로비저닝

> **전제 조건:** SPIKE 5.0(배포 토폴로지 및 운영 인프라 상세 설계)이 완료된 상태에서 시작. SPIKE 결과(`docs/infrastructure-design.md`)가 본 스토리 Terraform 모듈 작성의 입력.

인프라 담당자로서,  
AWS EC2·RDS·S3·보안 그룹이 Terraform 코드로 프로덕션 환경에 맞게 구성되기를 원한다,  
그래서 시스템이 안전하게 운영 가능한 상태로 배포되며 인프라 변경이 PR 리뷰를 거친다.

**Acceptance Criteria:**

**Given** AWS 계정과 IAM 권한이 준비된 상태에서  
**When** 인프라 프로비저닝이 완료되면  
**Then** 모든 AWS 리소스가 `infra/terraform/` 코드로 정의되며 Console 수동 생성(ClickOps)이 금지된다 (architecture.md "IaC 도구: Terraform" 결정 준수)  
**And** Crawler EC2(t3.medium), Detection EC2(t3.medium), API EC2(t3.medium) 3개 인스턴스가 각각 분리된 보안 그룹으로 구성된다  
**And** RDS PostgreSQL 보안 그룹이 Detection EC2와 API EC2에서만 접근을 허용하고 퍼블릭 접근을 차단한다 (NFR7)  
**And** Redis(docker-compose on API EC2) 포트가 외부 접근을 차단하고 API EC2 내부에서만 접근된다  
**And** S3 버킷 정책이 퍼블릭 접근을 차단하고 Crawler EC2 IAM Role에만 쓰기 권한을 부여한다 (NFR8)  
**And** 각 EC2에 IAM Instance Role이 부여되어 AWS SDK가 환경변수 Access Key 없이 동작한다 (NFR6)  
**And** S3 버킷 및 RDS에 AWS CloudTrail 또는 S3 Access Logging이 활성화되어 데이터 접근 이력이 기록된다 (NFR9)  
**And** `infra/terraform/bootstrap/`을 1회 apply하여 state 백엔드(S3 + DynamoDB lock)가 생성되며, `infra/terraform/environments/{dev,prod}/`가 해당 백엔드를 사용한다  
**And** `infra/terraform/environments/dev/`와 `environments/prod/`가 동일 모듈을 다른 변수로 호출하며, 환경별 state는 분리된다  
**And** 시크릿(VARCO_API_KEY 등)은 AWS Secrets Manager 또는 SSM Parameter Store에 저장되며 `tfvars`/`tfstate`에 평문으로 포함되지 않는다 (NFR5)  
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
