---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
lastStep: 8
status: 'complete'
completedAt: '2026-04-24'
inputDocuments: ['_bmad-output/planning-artifacts/prd.md', 'tracker_기획서.md', '_bmad-output/brainstorming/brainstorming-session-2026-04-24-1430.md']
workflowType: 'architecture'
project_name: '20261R0136COSE45700'
user_name: 'Tracker'
date: '2026-04-24'
---

# Architecture Decision Document

_이 문서는 단계별 협업적 발견을 통해 구축됩니다. 각 아키텍처 결정을 함께 작업하면서 섹션이 추가됩니다._

## Project Context Analysis

### Requirements Overview

**기능 요구사항 (Functional Requirements):**

32개의 기능 요구사항이 6개 카테고리로 구성됩니다:

| 카테고리 | FR 범위 | 아키텍처 영향 |
|---------|---------|-------------|
| 콘텐츠 수집 | FR1-FR6 | Playwright+stealth, APScheduler, S3 업로드, 수동 트리거 API |
| 콘텐츠 전처리 | FR7-FR10 | 인라인 처리(옵션 A), Redis 중복 해시, 키워드 필터 |
| AI 탐지 | FR11-FR16 | VARCO Translation/LLM 순차 호출, Redis MQ, DLQ, 토큰 버킷 |
| 탐지 결과 조회 | FR17-FR22 | REST API 4종, RDS 인덱스, Redis 캐시 |
| 통계 및 분석 | FR23-FR27 | 집계 쿼리, 시계열 차트 |
| 시스템 운영 | FR28-FR32 | 환경변수 기반 설정, Prometheus/Grafana, DLQ 알람 |

**비기능 요구사항 (Non-Functional Requirements):**

| 카테고리 | 핵심 지표 | 아키텍처 영향 |
|---------|---------|-------------|
| 성능 | API ≤ 500ms(p95), 대시보드 ≤ 3초, 배치 ≤ 30분, 반영 ≤ 5분 | RDS 인덱스 전략, Redis 캐시, 비동기 큐 |
| 보안 | 환경변수 자격증명, IAM Role, VPC 격리, S3 퍼블릭 차단 | 네트워크 경계 설계, 시크릿 관리 패턴 |
| 신뢰성 | 24시간 무중단, 3회 재시도 → DLQ, Redis AOF + S3 아카이브 | 장애 격리 패턴, Watchdog, 원자적 큐 연산 |
| 통합 | VARCO 토큰 버킷, ProxyProvider 인터페이스, BRPOPLPUSH 원자성 | 추상화 레이어, 교체 비용 격리 |

**규모 및 복잡도 (Scale & Complexity):**

- 1차 기술 도메인: Full-stack (Python AI Pipeline + Java Spring API + React SPA)
- 복잡도: **High**
- 예상 아키텍처 컴포넌트: 8개 (Crawler Worker, Preprocessing Module, AI Detection Worker, MQ Manager, Rate Limiter, Spring REST API, React SPA, Monitoring Stack)

### Technical Constraints & Dependencies

| 제약 | 유형 | 영향 |
|------|------|------|
| VARCO API rate limit | 외부 API 제한 | Redis 토큰 버킷 필수, Detection Worker 직렬화 |
| AWS t3.medium ×3 | 인프라 사양 | EC2 간 메모리 공유 불가 → Redis MQ 비동기 통신 |
| GFW·Cloudflare 차단 | 외부 환경 | ProxyProvider 추상화, FlareSolverr 병행, 실측 기반 확장 |
| VARCO API 가용성 | 외부 의존성 | DLQ + 최대 3회 재시도 필수, 서비스 저하 모드(degraded mode) 설계 필요 |
| 11주 개발 일정, 3인 팀 | 프로젝트 제약 | Growth 기능(Vision, BERT, SSO) MVP 이후 이월 명확화 |
| BERT 도입 여부 미결정 | 기술 결정 보류 | 5~7주차 LLM F1 실측 후 Detection EC2 사양 결정; GPU 전환 분기점 사전 문서화 필요 |

### Cross-Cutting Concerns Identified

1. **Correlation ID 전파** — Crawler → Detection → API EC2 전 컴포넌트가 동일한 `correlation_id`를 Redis 메시지와 로그에 포함해야 함. `shared/correlation_id.py` 인터페이스 미정의 시 3-way 머지 충돌 확정. **Day 1 선행 산출물.**

2. **Redis 역할 분리** — 현재 MQ(posts:queue/processing/dlq), 중복 제거 SET(posts:dedup), 토큰 버킷(varco:rate_limit), API 캐시가 단일 Redis 인스턴스에 집중. t3.medium(4GB) OOM 시 4가지 기능 동시 장애 유발. `REDIS_MQ_DB=0`, `REDIS_DEDUP_DB=1`, `REDIS_RATELIMIT_DB=2`, `REDIS_CACHE_DB=3` 논리 분리 및 `docker-compose.yml`에 명시 필요. **Day 1 선행 산출물.**

3. **VARCO Mock 서버** — `detection/src/mocks/varco_mock.py` 없이는 통합 테스트 전체가 외부 API에 묶임. Rate limit 시뮬레이션, 실패 주입, 재시도 검증 모두 Mock 의존. **Week 1-2 필수 구축.**

4. **멱등성 보장** — `detections` 테이블에 `(post_id, model_version)` unique constraint 없으면 DLQ 재처리 시 중복 삽입 발생. Migration 파일명 규칙 팀 합의 없으면 충돌.

5. **무음 실패 방지 (Silent Failure)** — `crawler/src/parser/base_parser.py::parse()`의 반환 타입을 `Optional[ParseResult]`가 아닌 exception raise 강제로 설계. `None` 반환은 파싱 실패를 정상 흐름으로 통과시키는 최악의 버그 패턴.

6. **처리 병목 — Vision 단계** — VARCO rate limit보다 이미지 추론(VARCO Vision) 지연이 실제 처리 병목일 가능성 높음. `VISION_WORKER_COUNT` 환경변수 선행 정의 필요. MQ 큐 깊이(Queue Depth) 모니터링으로 병목 지점 실측 선행.

7. **APScheduler 중복 실행 방지** — 재시작 시 동일 Job이 두 번 실행되지 않도록 `max_instances`, `misfire_grace_time` 명시 설정 필요. Redis dedup 체크는 크롤링 완료 후가 아닌 **시작 전**에 수행해야 함.

8. **구조화 로깅 표준화** — Python(크롤러/탐지)과 Java Spring(API) 간 `{"timestamp", "service", "correlation_id", "level", "message"}` JSON 로그 스키마 팀 합의 필요.

9. **RDS 연결 풀 관리** — Detection EC2 배치 인서트와 API EC2 쿼리가 동일 RDS 연결 풀을 공유. 피크 시 Detection이 API 연결을 고갈시킬 수 있음. 연결 풀 사이즈 분리 설정 필요.

10. **프록시 추상화** — `ProxyProvider` 인터페이스 패턴으로 ProxyBroker(개발)/NodeMaven(운영) 교체 비용 격리. 중국 사이트 크롤링 성공률 SLA 정의 및 메트릭 추적 필요 (실패율 → 탐지 Recall 저하 연쇄).

## Starter Template Evaluation

### 기술 도메인

이 프로젝트는 3개의 독립 서브시스템으로 구성된 복합 시스템으로, 단일 스타터 템플릿이 아닌 서브시스템별 스캐폴딩이 적용됩니다.

### 레포 구조 결정: 모노레포

3인 팀 + 공유 `correlation_id` 모듈 필요 → 모노레포(Monorepo) 채택

```
tracker/
├── crawler/          # Python - Playwright+stealth, APScheduler, 전처리
├── detection/        # Python - VARCO 파이프라인, Redis MQ 소비자
├── api/              # Java Spring Boot 4.0.5 - REST API
├── dashboard/        # React + Vite 8 + TypeScript - SPA 대시보드
├── shared/           # Python 공유 모듈 (correlation_id.py 등)
├── infra/
│   ├── docker-compose.yml   # Redis + 로컬 개발 환경
│   └── .env.example
└── .github/
    └── workflows/    # GitHub Actions CI/CD
```

### 서브시스템별 초기화 명령

**① Python 서브시스템 (crawler, detection)**

```bash
# crawler/
pip install playwright==1.58.0 APScheduler beautifulsoup4 \
    langdetect redis boto3 playwright-stealth
playwright install chromium

# detection/
pip install redis boto3 httpx python-dotenv
```

**② Java Spring Boot 3.4.x (api/)**

```bash
curl https://start.spring.io/starter.zip \
  -d type=gradle-project \
  -d language=java \
  -d bootVersion=3.4.5 \
  -d baseDir=api \
  -d groupId=com.tracker \
  -d artifactId=tracker-api \
  -d javaVersion=21 \
  -d dependencies=web,data-jpa,postgresql,actuator,lombok,validation \
  -o api.zip && unzip api.zip
```

**③ React SPA (dashboard/)**

```bash
npm create vite@latest dashboard -- --template react-ts
cd dashboard && npm install
npm install @tanstack/react-query axios recharts \
    @radix-ui/react-select date-fns react-router-dom
```

### 스타터가 확정하는 아키텍처 결정

| 항목 | 결정 |
|------|------|
| Python 런타임 | 3.11+ |
| Java 런타임 | Java 21 LTS (Virtual Threads 지원) |
| Spring Boot | 3.4.x (Spring Framework 6.2.x, Hibernate 6.6.x, Tomcat 10.1.x) |
| Frontend 빌드 | Vite 8.0.10 (Node.js 20.19+, @vitejs/plugin-react v6) |
| API 문서화 | springdoc-openapi (Swagger UI 자동 생성) |
| React 서버 상태 | TanStack Query |
| 차트 라이브러리 | Recharts |
| 레포 구조 | 모노레포 (서브시스템별 독립 의존성) |

**Note:** 프로젝트 초기화는 첫 번째 구현 스토리여야 합니다. `shared/correlation_id.py`와 `infra/docker-compose.yml` Redis DB index 설정이 Day 1 필수 선행 산출물입니다.

## Core Architectural Decisions

### Decision Priority Analysis

**Critical Decisions (구현 선행 필요):**
- DB 마이그레이션 도구: Flyway
- RDS 인덱스 전략: 복합 인덱스 (detected_at, type, confidence)
- Redis 역할별 DB 분리: DB0~3 논리 분리
- VARCO 장애 처리 모드: 큐 대기 (Hold)

**Important Decisions (아키텍처 형태 결정):**
- 에러 응답 형식: ProblemDetail (RFC 9457)
- Correlation ID: X-Correlation-ID 응답 헤더
- 페이지네이션: Offset 기반
- 라우팅: React Router v7
- 데이터 갱신: TanStack Query 폴링 60초
- IaC 도구: Terraform (S3+DynamoDB state 백엔드, 디렉토리 분리 환경, dev 자동 / prod 수동 승인)

**Deferred Decisions (Post-MVP):**
- DLQ 알람 채널: Grafana UI만 사용 (Slack/이메일은 Growth 단계)
- 애플리케이션 인증: SSO/ID-PW (Growth 단계)
- BERT 2차 필터: Week 5-7 LLM F1 실측 후 결정
- VARCO Vision: Growth 단계 (텍스트 탐지 F1 실측 후)

### Data Architecture

| 결정 | 선택 | 근거 |
|------|------|------|
| DB 마이그레이션 | Flyway | 4개 테이블의 단순 스키마, Spring Boot 4 기본 지원, SQL 파일 기반 단순성. 파일명 규칙 `V{n}__{description}.sql`으로 팀 충돌 방지. |
| RDS 인덱스 | 복합 인덱스 | `GET /detections` p95 ≤ 500ms NFR 충족. `CREATE INDEX idx_detections_filter ON detections (detected_at DESC, type, confidence DESC)` — 날짜·유형·신뢰도 필터 조합 최적화. |
| 페이지네이션 | Offset 기반 | 내부 운영 도구 + 수천~수만 건 규모. `?page=0&size=20` 파라미터로 특정 페이지 직접 이동 가능. 커서 기반 대비 구현 복잡도 불필요. |
| Redis DB 분리 | 논리 DB 분리 | `REDIS_MQ_DB=0`, `REDIS_DEDUP_DB=1`, `REDIS_RATELIMIT_DB=2`, `REDIS_CACHE_DB=3`. t3.medium OOM 시 4가지 기능 동시 장애 방지. `docker-compose.yml` 및 `RedisConfig.java`에 명시. |

### Authentication & Security

| 결정 | 선택 | 근거 |
|------|------|------|
| MVP 인증 | VPC 네트워크 레벨만 | 내부 운영 도구. AWS 보안 그룹으로 접근 제어. 애플리케이션 레벨 인증 구현 비용 대비 효과 낮음. |
| 시크릿 관리 | 환경변수 + IAM Role | VARCO API 키·AWS 자격증명 환경변수. EC2 IAM Role로 하드코딩 금지. `.env.example` 제공, `.env` gitignore. |
| Growth 인증 | SSO 또는 ID/PW | Post-MVP. NC AI 인프라 연동 방식 협의 후 결정. |

### API & Communication Patterns

| 결정 | 선택 | 근거 |
|------|------|------|
| 에러 응답 형식 | ProblemDetail (RFC 9457) | Spring Boot 4 기본 지원. Swagger 자동 문서화 정확도 향상. 프론트엔드 에러 처리 패턴 통일. `status`, `title`, `detail`, `instance` 표준 필드. |
| Correlation ID | X-Correlation-ID 헤더 | `shared/correlation_id.py` 생성 UUID를 Redis 메시지 → 탐지 결과 → API 응답 헤더까지 전파. Crawler/Detection/API 3개 EC2 로그를 단일 ID로 추적. |
| API 문서화 | springdoc-openapi | Swagger UI 자동 생성. `GET /detections`, `GET /detections/{id}`, `GET /stats`, `POST /crawl/trigger` 4개 엔드포인트 자동 문서화. |

### Frontend Architecture

| 결정 | 선택 | 근거 |
|------|------|------|
| 데이터 갱신 | TanStack Query 폴링 (60초) | `useQuery({ refetchInterval: 60_000 })`. 크롤링 완료 후 5분 이내 반영 NFR을 60초 폴링으로 충족. WebSocket/SSE는 1시간 크롤링 주기에 과도한 구현. |
| 라우팅 | React Router v7 | `/detections`, `/detections/:id`, `/stats` URL 구조. 탐지 상세에서 원본 URL 조치 후 목록으로 복귀 시 URL 히스토리 활용. 북마크 공유 가능. |
| 상태 관리 | TanStack Query (서버 상태만) | 별도 전역 상태 관리 불필요. 서버 상태는 TanStack Query, UI 상태는 컴포넌트 로컬 state로 충분. |

### Infrastructure & Deployment

| 결정 | 선택 | 근거 |
|------|------|------|
| VARCO 장애 처리 | 큐 대기 (Hold) | VARCO 다운 시 Redis 큐에 메시지 유지. 3회 재시도 후 DLQ 격리. 복구 후 DLQ → 재처리. Redis AOF 설정으로 EC2 재시작 후 메시지 보존. Translation 스킵 시 Recall 저하 리스크보다 데이터 정합성 우선. |
| DLQ 알람 채널 | Grafana UI | MVP에서 Grafana 웹 대시보드 알람만 사용. Slack/이메일 알림은 Growth 단계에서 Grafana Alerting Contact Point 추가로 확장. |
| CI/CD | GitHub Actions | 코드 푸시 시 자동 빌드·배포. Python(crawler, detection), Java Spring(api), React(dashboard) 각각 독립 워크플로우. |
| 로컬 개발 환경 | Docker Compose | Redis + PostgreSQL 로컬 구동. `infra/docker-compose.yml`에 Redis DB index 환경변수 명시. |
| IaC 도구 | Terraform | AWS EC2/RDS/S3/SG/IAM 프로비저닝을 코드로 관리. ClickOps 금지(drift 차단), `terraform plan`으로 PR 단계 변경 미리보기 가능. CDK 대비 멀티-언어 스택(Python/Java/Node)과 무관하게 작동. AWS 외 GitHub/Datadog provider 추가 시도 동일 구조 유지. |
| Terraform state 백엔드 | S3 + DynamoDB lock | 표준 패턴. Terraform Cloud는 외부 의존 추가 — MVP 회피. state는 별도 `tracker-tfstate-{env}` S3 버킷에 저장(서버사이드 암호화 + 버전 관리), DynamoDB 테이블로 동시 apply 락. 부트스트랩(state 버킷 자체 생성)은 별도 `infra/terraform/bootstrap/` 1회성 apply로 처리. |
| 환경 분리 전략 | 디렉토리 분리 (`environments/dev/`, `environments/prod/`) | workspace는 3인 팀에서 잘못된 workspace 선택 사고 위험. 디렉토리 분리는 state·variables·backend 모두 환경별로 명시적이라 안전. |
| Terraform 시크릿 처리 | AWS Secrets Manager + SSM Parameter Store, `data` 블록 참조 | `tfvars`나 `tfstate`에 평문 시크릿 절대 금지(NFR5). 시크릿은 AWS 관리형 스토어에 저장하고 Terraform에서는 참조만. EC2는 IAM Instance Role로 런타임 조회. |
| Terraform apply 정책 | dev 자동 / prod 수동 승인 | PR 단계: `terraform plan` 결과 PR 코멘트로 자동 게시. main 머지: dev 환경은 GitHub Actions가 자동 apply. prod는 GitHub Environments 보호 규칙으로 수동 승인 게이트(Story 5.2/5.3에서 도입). |

### Decision Impact Analysis

**구현 순서 (의존성 기준):**
1. `infra/docker-compose.yml` — Redis DB index 설정, 로컬 환경 기반
2. `shared/correlation_id.py` — 3개 서브시스템 공통 의존
3. `detection/src/mocks/varco_mock.py` — 통합 테스트 선행 조건
4. `api/.../db/migration/V1__init.sql` — Flyway 초기 스키마 (인덱스 포함)
5. `api/.../DetectionRepository.java` — `(post_id, model_version)` unique constraint
6. 크롤러 → Redis → 탐지 → RDS 파이프라인
7. Spring REST API 4종
8. React SPA 4개 화면

**크로스 컴포넌트 의존성:**
- Correlation ID → 크롤러·탐지·API 동시 변경 필요 (Day 1 완료 필수)
- Flyway migration 파일명 규칙 → 팀 합의 없으면 `V{n}__` 충돌
- Redis DB index → `RedisConfig.java`와 `redis_client.py` 동시 반영 필요
- ProblemDetail 에러 형식 → 프론트엔드 에러 처리 코드와 계약

## Implementation Patterns & Consistency Rules

### 잠재적 충돌 지점 (8개 식별)

Python/Java/TypeScript 3개 언어가 혼재하는 구조에서 언어 간 계약(Contract)을 명확히 정의합니다.

### Naming Patterns

**P1. JSON API 필드 명명 — camelCase**

API 응답은 React/TypeScript 표준인 camelCase를 사용합니다. 언어별 내부 명명은 각 언어 관용을 따르되, 경계(API 계약)에서 camelCase로 통일합니다.

| 레이어 | 명명 규칙 | 예시 |
|------|---------|------|
| API JSON 응답 | camelCase | `isIllegal`, `detectedAt`, `postUrl` |
| Python 내부 (Redis 메시지) | snake_case | `is_illegal`, `detected_at` |
| DB 컬럼 (PostgreSQL) | snake_case | `is_illegal`, `detected_at` |
| Java 코드 | camelCase | `isIllegal`, `detectedAt` |

```json
// API 응답 예시 ✅
{ "isIllegal": true, "detectedAt": "2026-04-24T14:30:00Z", "confidence": 0.92 }
// ❌ snake_case 금지
{ "is_illegal": true, "detected_at": "2026-04-24T14:30:00Z" }
```

**P2. Redis 키 명명 — `{도메인}:{역할}` 콜론 계층**

```
posts:queue          # 메인 MQ (DB0)
posts:processing     # 처리 중 (DB0)
posts:dlq            # Dead Letter Queue (DB0)
posts:dedup          # 중복 해시 SET (DB1)
varco:rate_limit     # 토큰 버킷 (DB2)
cache:detections     # API 캐시 (DB3)
```

규칙: 소문자, 콜론(`:`) 구분, 축약어 금지

**P3. DB 명명 — snake_case 복수형 테이블**

```sql
-- 테이블: snake_case 복수형
sources, posts, post_images, detections

-- 인덱스: idx_{테이블}_{컬럼(들)}
idx_detections_filter, idx_posts_source_id

-- 외래키 컬럼: {참조테이블단수}_id
source_id, post_id
```

**P4. 에러 코드 — UPPER_SNAKE_CASE**

```json
{
  "type": "https://tracker.internal/errors/detection-not-found",
  "title": "Detection Not Found",
  "status": 404,
  "detail": "Detection with id=123 does not exist",
  "errorCode": "DETECTION_NOT_FOUND"
}
```

에러 코드 예시: `DETECTION_NOT_FOUND`, `INVALID_FILTER_PARAM`, `CRAWL_TRIGGER_FAILED`

### Format Patterns

**P5. 날짜/시간 — ISO 8601 UTC 문자열**

```
✅ "2026-04-24T14:30:00Z"
❌ 1745505000 (Unix timestamp)
❌ "2026-04-24 14:30:00" (커스텀 포맷)
```

- Python: `datetime.utcnow().isoformat() + "Z"`
- Java: `Instant.now().toString()`
- React: `new Date(detectedAt).toLocaleString('ko-KR')`

**P6. 구조화 로그 표준 스키마**

```json
{
  "timestamp": "2026-04-24T14:30:00Z",
  "service": "crawler",
  "level": "INFO",
  "correlation_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Post enqueued",
  "site": "tailstar.net"
}
```

`service` 허용값: `crawler`, `detection`, `api` (하드코딩 금지, 환경변수 `SERVICE_NAME`으로 주입)

### Structure Patterns

**P7. Java 패키지 구조 — 레이어별 (Spring Boot 4, Java 21)**

4개 엔드포인트의 단순 API에 레이어별 구조 채택. 기능별 구조는 도메인 복잡도 증가 시 Growth 단계에서 검토.

```
com.tracker.api
├── domain/        # JPA Entity 클래스
├── repository/    # Spring Data JPA 인터페이스
├── service/       # 비즈니스 로직
├── controller/    # REST 컨트롤러
├── dto/           # Java 21 record DTO (불변)
├── config/        # Redis, Swagger, 환경설정 Bean
└── TrackerApiApplication.java   # 루트 패키지 위치 필수
```

Java 21 record DTO 예시:
```java
public record DetectionResponse(
    Long id, boolean isIllegal, String type,
    double confidence, String reason, Instant detectedAt
) {}
```

**P8. 테스트 파일 위치**

```
crawler/tests/unit/          # Python 단위 테스트
crawler/tests/integration/   # Python 통합 테스트
detection/tests/unit/
detection/tests/integration/
api/src/test/java/com/tracker/  # Spring Boot 표준
dashboard/src/                  # *.test.tsx 코드 옆 배치 (Vite 관용)
```

### Process Patterns

**P9. API 에러 처리 — ProblemDetail 전파**

```typescript
// React 에러 처리 표준 ✅
const handleApiError = (error: ProblemDetail) => {
  if (error.errorCode === 'DETECTION_NOT_FOUND') { /* ... */ }
};
// ❌ HTTP status code만으로 분기 금지
```

**P10. Python 파이프라인 예외 처리**

```python
# ✅ parse() 실패 시 None 반환 금지 — exception raise 강제
def parse(self, html: str) -> ParseResult:
    result = self._extract(html)
    if not result:
        raise ParseError(f"Failed to parse HTML: {html[:100]}")
    return result
```

### Enforcement Guidelines

**All AI Agents MUST:**
- API JSON 응답 필드는 camelCase만 사용
- 날짜/시간은 ISO 8601 UTC 문자열만 사용
- Redis 키는 `{도메인}:{역할}` 콜론 계층 구조 준수
- 로그에 `correlation_id` 필드 항상 포함
- `parse()` 류 함수에서 `None` 반환 금지, exception raise 강제
- DB migration 파일명: `V{순번}__{설명}.sql` (예: `V1__init_schema.sql`)
- Java DTO는 `record` 타입 우선 사용

**Anti-Patterns (금지):**
```
❌ API 응답에 snake_case 필드: { "detected_at": "..." }
❌ Unix timestamp 사용: { "detectedAt": 1745505000 }
❌ Redis 키에 camelCase: "postsQueue"
❌ parse() 함수가 None 반환으로 실패 은폐
❌ correlation_id 없는 로그 메시지
❌ V2.sql 파일명 (언더스코어 2개 필수: V2__xxx.sql)
```

## Project Structure & Boundaries

> **Party Mode 검토 반영 (Winston · Amelia · Murat):**
> - `shared/models/` 추가 — Redis MQ 메시지 스키마 공유 (schema mismatch 방지)
> - `shared/interfaces/varco.py` 추가 — VARCO Protocol 계약 먼저 정의
> - `shared/config/redis_config.py` 추가 — DB 번호 상수화
> - `trigger_listener.py` → `scheduler/` 이동 + Redis pub/sub 방식 확정
> - `vision_analyzer.py stub` → `mocks/` 이동
> - `api/.../exception/` 패키지 추가
> - `infra/` 환경 분리 (dev/prod)
> - `Dockerfile` 3개 추가
> - `tests/` 크로스 컴포넌트 루트 추가 (fixtures, e2e, performance, chaos)
> - Detection → RDS 직접 write 유지 (단, write 전용 connection pool 분리, read는 API 전담)

### Complete Project Directory Structure

```
tracker/
├── .github/
│   └── workflows/
│       ├── crawler.yml
│       ├── detection.yml
│       ├── api.yml
│       └── dashboard.yml
│
├── crawler/                           # FR1-FR10: 수집 + 전처리
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── src/
│       ├── main.py
│       ├── config/
│       │   └── redis_config.py        # Redis 연결 설정 (DB0, DB1)
│       ├── scheduler/                 # FR1, FR28
│       │   ├── crawl_scheduler.py     # APScheduler (CRAWL_INTERVAL_MINUTES)
│       │   └── trigger_listener.py    # FR6: Redis pub/sub 수신 (crawl:trigger)
│       ├── sites/                     # FR1: 사이트별 크롤러
│       │   ├── base_site.py
│       │   ├── tailstar.py
│       │   ├── ptt.py
│       │   └── tieba.py
│       ├── browser/                   # FR2, FR3
│       │   ├── stealth_browser.py
│       │   └── flaresolverr.py
│       ├── proxy/                     # NFR15: ProxyProvider 추상화
│       │   ├── proxy_provider.py      # Protocol/ABC 인터페이스
│       │   └── proxy_broker.py        # ProxyBroker 구현체
│       ├── storage/                   # FR5
│       │   └── s3_uploader.py
│       ├── preprocessor/              # FR7-FR10 (옵션 A 인라인)
│       │   ├── html_parser.py
│       │   ├── language_detector.py
│       │   ├── dedup_checker.py       # Redis DB1 (REDIS_DEDUP_DB)
│       │   └── keyword_filter.py
│       └── queue/
│           └── redis_publisher.py     # posts:queue LPUSH (DB0)
│   └── tests/
│       ├── unit/
│       │   ├── test_html_parser.py
│       │   ├── test_keyword_filter.py
│       │   └── test_dedup_checker.py
│       └── integration/
│           └── test_crawl_pipeline.py
│
├── detection/                         # FR11-FR16: AI 탐지 파이프라인
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   └── src/
│       ├── main.py
│       ├── config/
│       │   └── redis_config.py        # Redis 연결 설정 (DB0, DB2)
│       ├── consumer/
│       │   ├── queue_consumer.py      # BRPOPLPUSH (DB0), Watchdog
│       │   └── watchdog.py
│       ├── pipeline/                  # FR11-FR14
│       │   ├── translate.py           # VARCO Translation
│       │   └── llm_classifier.py      # VARCO LLM
│       ├── rate_limit/                # FR16
│       │   └── token_bucket.py        # Redis DB2 (REDIS_RATELIMIT_DB)
│       ├── retry/                     # FR15, NFR11
│       │   └── retry_handler.py
│       ├── storage/
│       │   └── detection_repository.py # RDS write 전용 (read는 API 전담)
│       └── mocks/                     # 통합 테스트 + stub
│           ├── varco_mock.py          # Day 1 필수
│           └── vision_analyzer_stub.py # Growth 단계 stub
│   └── tests/
│       ├── unit/
│       │   ├── test_consumer_idempotency.py
│       │   └── test_token_bucket.py
│       ├── integration/
│       │   └── test_varco_pipeline.py
│       └── quality/                   # Precision/Recall 측정
│           ├── test_varco_precision_recall.py
│           └── test_varco_response_schema.py
│
├── api/                               # FR17-FR27, FR29-FR32
│   ├── Dockerfile
│   ├── build.gradle
│   └── src/
│       ├── main/
│       │   ├── java/com/tracker/api/
│       │   │   ├── TrackerApiApplication.java
│       │   │   ├── domain/
│       │   │   │   ├── Detection.java
│       │   │   │   ├── Post.java
│       │   │   │   ├── Source.java
│       │   │   │   └── PostImage.java
│       │   │   ├── repository/
│       │   │   │   ├── DetectionRepository.java  # (post_id, model_version) unique
│       │   │   │   └── PostRepository.java
│       │   │   ├── service/
│       │   │   │   ├── DetectionService.java
│       │   │   │   ├── StatsService.java
│       │   │   │   └── CrawlTriggerService.java  # Redis PUBLISH crawl:trigger
│       │   │   ├── controller/
│       │   │   │   ├── DetectionController.java  # FR17-FR22
│       │   │   │   ├── StatsController.java      # FR23-FR27
│       │   │   │   └── CrawlController.java      # FR6 → POST /crawl/trigger
│       │   │   ├── dto/                           # Java 21 record
│       │   │   │   ├── DetectionResponse.java
│       │   │   │   ├── DetectionFilter.java
│       │   │   │   └── StatsResponse.java
│       │   │   ├── exception/                     # 신규 (Winston)
│       │   │   │   ├── GlobalExceptionHandler.java # @ControllerAdvice
│       │   │   │   └── DetectionNotFoundException.java
│       │   │   └── config/
│       │   │       ├── RedisConfig.java           # DB0~3 분리
│       │   │       ├── SwaggerConfig.java
│       │   │       └── WebConfig.java
│       │   └── resources/
│       │       ├── application.yml
│       │       ├── application-local.yml
│       │       └── db/migration/
│       │           ├── V1__init_schema.sql
│       │           ├── V2__add_indexes.sql
│       │           └── V3__add_unique_detection.sql
│       └── test/java/com/tracker/api/
│           ├── controller/
│           └── repository/
│
├── dashboard/                         # FR17-FR27 UI
│   ├── index.html
│   ├── vite.config.ts
│   ├── package.json
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── router.tsx                 # React Router v7
│       ├── api/
│       │   ├── client.ts              # axios + X-Correlation-ID
│       │   ├── detections.ts          # TanStack Query (refetchInterval: 60s)
│       │   └── stats.ts
│       ├── pages/
│       │   ├── Dashboard/
│       │   ├── DetectionList/
│       │   ├── DetectionDetail/
│       │   └── Stats/
│       ├── components/
│       │   ├── charts/
│       │   │   ├── PieChart.tsx
│       │   │   ├── BarChart.tsx
│       │   │   └── LineChart.tsx
│       │   └── common/
│       │       ├── ErrorBoundary.tsx
│       │       └── LoadingSpinner.tsx
│       └── types/
│           └── api.ts
│
├── shared/                            # Python 공유 모듈 — Day 1 필수
│   ├── pyproject.toml                 # pip install -e shared/ 지원
│   ├── correlation_id.py
│   ├── structured_logger.py
│   ├── models/                        # Redis MQ 메시지 스키마 (신규 — Winston)
│   │   ├── crawl_event.py             # posts:queue 메시지 구조
│   │   └── detection_result.py
│   ├── interfaces/                    # VARCO Protocol 계약 (신규 — Amelia)
│   │   └── varco.py                   # Protocol class: translate/classify/analyze
│   ├── exceptions/
│   │   └── base_exception.py
│   └── config/
│       └── redis_config.py            # DB 번호 상수 (REDIS_MQ_DB=0 등)
│
├── tests/                             # 크로스 컴포넌트 테스트 루트 (신규 — Murat)
│   ├── fixtures/
│   │   ├── html/
│   │   │   ├── sample_illegal_post.html
│   │   │   └── sample_clean_post.html
│   │   ├── varco/
│   │   │   ├── mock_response_illegal.json
│   │   │   ├── mock_response_clean.json
│   │   │   ├── mock_response_rate_limited.json
│   │   │   └── mock_response_timeout.json
│   │   └── labels/
│   │       ├── manual_label_set_v1.csv  # 100개 수동 라벨셋 (ground truth)
│   │       └── label_schema.json
│   ├── e2e/
│   │   ├── test_full_pipeline_smoke.py
│   │   ├── test_detection_10_posts.py   # 데모 요구사항 자동화
│   │   ├── test_api_detection_query.py
│   │   ├── docker-compose.e2e.yml
│   │   └── conftest.py
│   ├── performance/
│   │   └── k6/
│   │       └── api_detections_load.js   # GET /detections p95 < 500ms
│   └── chaos/
│       ├── test_redis_failure.py        # kill -9 → 재연결
│       └── test_worker_crash_recovery.py # DLQ 5분 이내
│
├── infra/
│   ├── docker-compose.yml             # 기본 (dev 기본값)
│   ├── docker-compose.dev.yml         # 로컬 개발 오버라이드
│   ├── docker-compose.prod.yml        # 프로덕션 오버라이드
│   ├── prometheus/
│   │   └── prometheus.yml
│   ├── grafana/
│   │   └── dashboards/
│   │       └── tracker.json
│   └── terraform/                     # AWS IaC (Story 5.3에서 본격 구현)
│       ├── bootstrap/                 # state 백엔드 1회성 부트스트랩
│       │   └── main.tf                # S3 state 버킷 + DynamoDB lock 테이블
│       ├── modules/                   # 재사용 모듈
│       │   ├── networking/            # VPC + subnets + 보안 그룹
│       │   ├── ec2-service/           # crawler/detection/api 공통 패턴
│       │   ├── rds/                   # PostgreSQL (NFR7 보안 그룹 포함)
│       │   ├── elasticache/           # Redis (NFR8 — t3.medium, AOF on)
│       │   └── s3-frontend/           # dashboard 정적 호스팅 (CloudFront 옵션)
│       └── environments/
│           ├── dev/
│           │   ├── main.tf
│           │   ├── variables.tf
│           │   ├── terraform.tfvars   # gitignore (시크릿 변수 없도록 검증)
│           │   └── backend.tf         # S3 backend (dev tfstate)
│           └── prod/
│               └── (동일 구조, prod tfstate)
│
└── .env.example                       # 루트 공통 환경변수 템플릿
```

### Architectural Boundaries

**API 경계 (외부 진입점):**

| 엔드포인트 | 컨트롤러 | 서비스 | FR |
|-----------|---------|-------|-----|
| `GET /detections` | DetectionController | DetectionService | FR17-FR19, FR22 |
| `GET /detections/{id}` | DetectionController | DetectionService | FR20-FR21 |
| `GET /stats` | StatsController | StatsService | FR23-FR27 |
| `POST /crawl/trigger` | CrawlController | CrawlTriggerService → Redis PUBLISH `crawl:trigger` | FR6 |

**서비스 간 통신:**

| 발신 | 수신 | 채널 | 데이터 |
|------|------|------|--------|
| API CrawlTriggerService | Crawler trigger_listener | Redis pub/sub `crawl:trigger` | 트리거 신호 |
| Crawler redis_publisher | Detection queue_consumer | Redis LIST `posts:queue` (DB0) | crawl_event.py 스키마 |
| Detection detection_repository | RDS PostgreSQL | JDBC | detections 테이블 write 전용 |
| API DetectionService | RDS PostgreSQL | Spring Data JPA | detections 테이블 read 전용 |

**데이터 경계:**

| 저장소 | 쓰기 주체 | 읽기 주체 |
|-------|---------|---------|
| Redis DB0 `posts:queue` | Crawler | Detection |
| Redis DB1 `posts:dedup` | Crawler | Crawler |
| Redis DB2 `varco:rate_limit` | Detection | Detection |
| Redis DB3 `cache:detections` | API | API |
| RDS `detections` 테이블 | Detection (write) | API (read) |
| S3 | Crawler (write) | Detection (read, 원본 필요 시) |

### 데이터 흐름

```
한·중 포럼 사이트
  ↓ [Playwright+stealth + ProxyProvider]
crawler/src/sites/*.py
  ↓ [S3 원본 아카이브]
crawler/src/preprocessor/ (HTML→언어→dedup Redis DB1→키워드)
  ↓ [Redis posts:queue DB0 LPUSH, 페이로드: crawl_event.py 스키마]
detection/src/consumer/queue_consumer.py (BRPOPLPUSH)
  ↓ [VARCO Translation — 중국어만]
  ↓ [VARCO LLM 분류]
  ↓ [Redis DB2 토큰 버킷 체크]
detection/src/storage/detection_repository.py → RDS detections (write)
  ↓
api/.../DetectionController.java → RDS detections (read)
  ↓ [JSON camelCase + X-Correlation-ID]
dashboard/src/api/detections.ts (TanStack Query 60초 폴링)
  ↓
담당자 브라우저 대시보드
```

### FR 카테고리 → 디렉토리 매핑

| FR 카테고리 | 주요 파일 |
|-----------|---------|
| FR1-FR6 (수집) | `crawler/src/scheduler/`, `crawler/src/sites/`, `crawler/src/browser/` |
| FR7-FR10 (전처리) | `crawler/src/preprocessor/` |
| FR11-FR16 (AI 탐지) | `detection/src/pipeline/`, `detection/src/consumer/`, `detection/src/rate_limit/` |
| FR17-FR22 (탐지 조회) | `api/.../DetectionController.java`, `dashboard/src/pages/DetectionList/`, `DetectionDetail/` |
| FR23-FR27 (통계) | `api/.../StatsController.java`, `dashboard/src/pages/Stats/` |
| FR28-FR32 (운영) | `crawler/src/scheduler/`, `infra/`, `detection/src/retry/`, `tests/chaos/` |

### Day 1 필수 산출물 (구현 시작 전)

1. `shared/pyproject.toml` — 임포트 방식 확정
2. `shared/correlation_id.py` — 3개 서브시스템 공통 UUID
3. `shared/models/crawl_event.py` — Redis MQ 메시지 스키마
4. `shared/interfaces/varco.py` — VARCO Protocol 계약
5. `shared/config/redis_config.py` — DB 번호 상수
6. `detection/src/mocks/varco_mock.py` — 통합 테스트 선행 조건
7. `infra/docker-compose.yml` — Redis DB0~3 (`appendonly yes`) + PostgreSQL 로컬 환경
8. `tests/fixtures/` — HTML 샘플 + VARCO mock 응답 JSON

## Architecture Validation Results

### Coherence Validation ✅

모든 기술 선택이 상호 호환됩니다. Python 3.11+/Java 21/Node.js 20.19+ 런타임, Spring Boot 4.0.5/Vite 8 프레임워크, Redis 단일 인스턴스 DB 논리 분리, Jackson camelCase ↔ Python snake_case 자동 변환이 일관되게 작동합니다.

### Requirements Coverage Validation ✅

| 검증 항목 | 결과 |
|---------|------|
| FR1~FR32 전체 32개 → 아키텍처 컴포넌트 매핑 | ✅ 전체 커버 |
| NFR1~NFR17 전체 → 구현 위치 확인 | ✅ 전체 커버 |
| Precision ≥ 0.85 측정 기반 | ✅ `tests/quality/test_varco_precision_recall.py` |
| API p95 ≤ 500ms 검증 기반 | ✅ `tests/performance/k6/api_detections_load.js` |
| 데모 10개 불법 탐지 자동화 | ✅ `tests/e2e/test_detection_10_posts.py` |

### Architecture Completeness Checklist

**✅ Requirements Analysis**
- [x] 프로젝트 컨텍스트 분석 (32개 FR, 17개 NFR)
- [x] 규모/복잡도 평가 (High, 3-레이어 분산)
- [x] 기술 제약 식별 (VARCO rate limit, GFW, t3.medium)
- [x] 횡단 관심사 10개 매핑

**✅ Starter Templates**
- [x] Python 3.11+ (Playwright 1.58.0)
- [x] Spring Boot 4.0.5 + Java 21
- [x] Vite 8 + React + TypeScript
- [x] 모노레포 구조 확정

**✅ Architectural Decisions (9개)**
- [x] Flyway 마이그레이션
- [x] 복합 인덱스 + Offset 페이지네이션
- [x] Redis DB0~3 논리 분리
- [x] ProblemDetail (RFC 9457) 에러 형식
- [x] X-Correlation-ID 헤더
- [x] TanStack Query 60초 폴링
- [x] React Router v7
- [x] VARCO 장애 시 큐 대기 (Hold)
- [x] DLQ 알람: Grafana UI (MVP)

**✅ Implementation Patterns (10개)**
- [x] JSON camelCase API 계약
- [x] Redis 키 `{도메인}:{역할}` 계층
- [x] DB snake_case 복수형
- [x] ISO 8601 UTC 날짜
- [x] 구조화 로그 JSON 스키마
- [x] Java 패키지 레이어별 + Java 21 record DTO
- [x] 에러 코드 UPPER_SNAKE_CASE
- [x] 테스트 파일 위치 규칙
- [x] `parse()` exception raise 강제
- [x] Anti-pattern 목록 명시

**✅ Project Structure**
- [x] 모노레포 완전한 디렉토리 트리 정의
- [x] 서비스 간 통신 경계 (Redis pub/sub, MQ, RDS read/write 분리)
- [x] FR 카테고리 → 디렉토리 매핑 완료
- [x] Day 1 필수 산출물 8개 명시

### Gap Analysis Results

| 수준 | 항목 | 처리 |
|------|------|------|
| Important | Redis AOF `appendonly yes` docker-compose.yml 명시 필요 | 첫 번째 구현 스토리에서 처리 |
| Important | Dockerfile 3개 내용 미정 | 첫 번째 구현 스토리에서 작성 |
| Nice-to-have | BERT 도입 시 인프라 변경 절차 | Week 5-7 결정 시 별도 ADR 작성 |
| Nice-to-have | EC2 배포 스크립트 | GitHub Actions workflow로 대체 충분 |

### Architecture Readiness Assessment

**Overall Status: READY FOR IMPLEMENTATION**

**Confidence Level: High**

**핵심 강점:**
- Day 1 산출물(shared/ 모듈, varco_mock, docker-compose)이 명확히 정의되어 구현 충돌 최소화
- 32개 FR 전체가 구체적 파일/디렉토리에 매핑됨
- 외부 의존성(VARCO, 프록시) 추상화 레이어로 교체 비용 격리
- tests/ 루트 + fixtures/ 중앙화로 Precision/Recall 측정 기반 확보
- Party Mode 4-에이전트 검토로 경계 위반 및 구조 갭 사전 해소

**향후 개선 영역 (Growth 단계):**
- VARCO Vision 파이프라인 통합 (`detection/src/pipeline/vision_analyzer.py` 실구현)
- BERT 2차 필터 도입 (Week 5-7 F1 실측 후, Detection EC2 t3.large/g4dn 업사이징)
- SSO/ID-PW 애플리케이션 인증
- NodeMaven 프록시 전환
- Slack/이메일 DLQ 알람 (Grafana Contact Point 추가)

### Implementation Handoff

**AI 에이전트 가이드라인:**
- 모든 아키텍처 결정을 이 문서 기준으로 구현
- `shared/` 모듈은 반드시 Day 1에 완성 후 다른 서브시스템 작업 시작
- 새로운 기술 결정 필요 시 이 문서를 업데이트 후 진행
- Anti-pattern 목록을 코드 리뷰 체크리스트로 활용

**첫 번째 구현 우선순위:**

```bash
# 1. 모노레포 디렉토리 초기화
mkdir -p shared/models shared/interfaces shared/config shared/exceptions
mkdir -p tests/fixtures/html tests/fixtures/varco tests/fixtures/labels
mkdir -p tests/e2e tests/performance/k6 tests/chaos

# 2. shared/ 핵심 파일 (Day 1)
touch shared/pyproject.toml shared/correlation_id.py
touch shared/models/crawl_event.py shared/interfaces/varco.py
touch shared/config/redis_config.py

# 3. infra/docker-compose.yml
# Redis: appendonly yes, DB0~3 env vars
# PostgreSQL: 로컬 개발용

# 4. detection/src/mocks/varco_mock.py
# shared/interfaces/varco.py Protocol 구현

# 5. tests/fixtures/ HTML 샘플 + VARCO 응답 JSON 수집

# 이후: crawler/ → detection/ → api/ → dashboard/ 순서로 진행
```
