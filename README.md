# Tracker

불법 프로그램 탐지 AI — NC AI 게임 보안 담당자를 위한 자동화된 불법 프로그램 유포 탐지 시스템.

## 프로젝트 구조 개요

본 저장소는 4개 서브시스템 + 공유 모듈로 구성된 **모노레포**입니다.

```
.
├── crawler/          # Python — crawl4ai 기반 웹 크롤링 + 전처리 (APScheduler + Redis)
├── detection/        # Python — VARCO Translation/LLM 기반 AI 탐지 파이프라인
├── api/              # Java Spring Boot 3.5 — REST API (PostgreSQL + Flyway)
├── dashboard/        # React + Vite + TypeScript — 운영자 대시보드
├── shared/           # Python 공유 모듈 (CorrelationId, CrawlEvent, VarcoInterface 등)
├── infra/            # Docker Compose (Redis + PostgreSQL), Prometheus, Grafana
├── tests/            # 크로스 컴포넌트 테스트 (fixtures/e2e/performance/chaos)
└── .github/workflows/  # CI/CD 워크플로우 4종 (crawler/detection/api/dashboard)
```

## 사전 요구사항

- **Python 3.11+** (검증: 3.11, 3.12, 3.13)
- **Java 21 LTS** (Gradle Foojay Toolchain Resolver가 자동 다운로드 가능)
- **Node.js 20.19+** (LTS 권장: 20, 22)
- **Docker + Docker Compose** (로컬 Redis/PostgreSQL 환경)

> Java 21이 로컬에 없어도 `./gradlew build` 첫 실행 시 Foojay 리졸버가 자동으로 다운로드합니다.
>
> **Windows 사용자:** `bin/` 경로 대신 `Scripts\` 경로를 사용하고, `./gradlew` 대신 `gradlew.bat`을 사용하세요. 아래 명령은 macOS/Linux 기준입니다.

## 로컬 셋업

신규 팀원이 저장소를 클론한 뒤 실행하는 표준 절차입니다.

```bash
git clone <repository-url>
cd 20261R0136COSE45700

# 0) 인프라 기동 (Redis + PostgreSQL)
cp infra/.env.example infra/.env   # DB_PASSWORD 등 값 입력
docker compose -f infra/docker-compose.yml up -d

# 1) crawler 셋업 (Python venv + 의존성 + crawl4ai Chromium)
python3 -m venv crawler/.venv
crawler/.venv/bin/pip install -r crawler/requirements.txt
crawler/.venv/bin/playwright install chromium
# Linux headless 환경 추가: crawler/.venv/bin/playwright install-deps chromium

# 2) detection 셋업 (Python venv + 의존성)
python3 -m venv detection/.venv
detection/.venv/bin/pip install -r detection/requirements.txt
cp detection/.env.example detection/.env   # VARCO_API_KEY 등 값 입력

# 3) api 셋업 (Spring Boot — Gradle이 의존성 자동 다운로드, Flyway가 스키마 자동 생성)
cd api && ./gradlew build; cd ..

# 4) dashboard 셋업 (Vite + React)
cd dashboard && npm install && cd ..
```

각 서브시스템의 가상환경/의존성 캐시(`.venv/`, `node_modules/`, `.gradle/`, `build/`)는 git에서 제외되며, 위 명령으로 각 개발자 머신에서 동일하게 재현됩니다.

## 빠른 검증

각 서브시스템이 셋업되었는지 확인하는 명령:

```bash
# crawler (단위 테스트)
cd crawler && ../.venv/bin/python -m pytest tests/unit/ -q; cd ..

# detection (단위 테스트 — 외부 네트워크/실제 Redis 불필요)
cd detection && ../.venv/bin/python -m pytest tests/unit/ -q; cd ..

# api
cd api && ./gradlew build; cd ..
# 출력: BUILD SUCCESSFUL

# dashboard
cd dashboard && npm run build; cd ..
# 출력: ✓ built in <time>
```

## 서브시스템별 구현 현황

### crawler (Epic 2 — 완료)

| 모듈 | 설명 |
|------|------|
| `src/crawl4ai_crawler.py` | crawl4ai 기반 크롤러 (Chromium headless, stealth 모드) |
| `src/sites/registry.py` | SiteConfig 레지스트리 (52pojie, inven_maple, inven_lineage_classic 등) |
| `src/preprocessor/` | 언어 감지 → 키워드 필터 → 중복 제거(SHA-256 Redis) → 직렬화 |
| `src/queue/redis_publisher.py` | RedisPublisher — `posts:queue` (DB0) LPUSH |
| `src/s3_uploader.py` | S3Uploader — 원본 HTML + 이미지 아카이브 |
| `src/scheduler/` | APScheduler AsyncIOScheduler + TriggerListener(`crawl:trigger`) |

### detection (Epic 3 — 진행 중)

| 모듈 | 설명 | 상태 |
|------|------|------|
| `src/consumer/` | Redis 큐 소비자 + Watchdog | 완료 |
| `src/pipeline/translate.py` | VARCO Translation API 연동 (토큰 버킷 rate limit, DB2) | 리뷰 |
| `src/pipeline/llm_classifier.py` | VARCO LLM 분류 + RetryHandler (exponential backoff 3회) | 리뷰 |
| `src/pipeline/detection_pipeline.py` | 번역 → 분류 → RDS 저장 오케스트레이션 | 리뷰 |
| `src/mocks/varco_mock.py` | VARCO Mock 서버 (로컬/테스트 환경) | 완료 |
| RDS 저장 (Story 3-4) | 탐지 결과 PostgreSQL 저장 | 예정 |

### api (Epic 4 — 일부 완료)

| 항목 | 설명 |
|------|------|
| Spring Boot 3.5 + PostgreSQL | JPA + Flyway (V1~V4 마이그레이션 자동 적용) |
| `GET /api/detections` | 탐지 목록 조회 (페이지네이션 + 필터) |
| Swagger UI | `/swagger-ui.html` 에서 API 문서 확인 |
| 탐지 상세/수동 트리거/통계 (Story 4-2, 4-3) | 예정 |

### dashboard (Epic 4 — 완료)

| 페이지/기능 | 설명 |
|------------|------|
| Dashboard (`/`) | 탐지 현황 요약 + 차트 2종 |
| Detection List (`/detections`) | 목록 + 필터 + 키보드 네비게이션 (j/k/enter) |
| Detection Detail (`/detections/:id`) | 원문·번역문 이중 패널 (BilingualPanel) + 신뢰도 배지 |
| Stats (`/stats`) | 주간/월간 추이 LineChart + 사이트별 BarChart + 유형별 PieChart |
| 디자인 시스템 | Tailwind v4 + shadcn/ui + NC AI 브랜드 토큰 (WCAG AA) |
| MSW Mock | 백엔드 미완성 엔드포인트 대체 (개발/테스트용) |

## Redis DB 구성

| DB | 용도 | 키 패턴 |
|----|------|--------|
| DB0 | 메시지 큐 | `posts:queue`, `posts:processing`, `posts:dlq` |
| DB1 | 중복 제거 | `posts:dedup` (SHA-256 SET) |
| DB2 | Rate Limit | `varco:rate_limit:*` (토큰 버킷 Lua script) |
| DB3 | API 캐시 | `cache:detections` |

## CI/CD

`.github/workflows/` 에 4개 워크플로우가 구성되어 있습니다:

| 파일 | 트리거 | 내용 |
|------|--------|------|
| `crawler.yml` | push/PR (crawler/**) | pytest 단위·통합 테스트, flake8 |
| `detection.yml` | push/PR (detection/**) | pytest 단위·통합 테스트, flake8 |
| `api.yml` | push/PR (api/**) | Gradle build + JUnit 테스트 |
| `dashboard.yml` | push/PR (dashboard/**) | npm build + lint |

## 스프린트 현황

| Epic | 설명 | 상태 |
|------|------|------|
| Epic 1 | 프로젝트 토대 및 인프라 | **완료** |
| Epic 2 | 자동 크롤링 및 전처리 파이프라인 | **완료** |
| Epic 3 | AI 기반 탐지 파이프라인 | 진행 중 (3-4, 3-5 예정) |
| Epic 4 | 탐지 결과 조회 및 통계 대시보드 | 진행 중 (4-2, 4-3 예정) |
| Epic 5 | 운영·모니터링·프로덕션 배포 | 예정 |

자세한 스토리별 상태: [`_bmad-output/implementation-artifacts/sprint-status.yaml`](_bmad-output/implementation-artifacts/sprint-status.yaml)

## 기획·아키텍처 문서

- [PRD](_bmad-output/planning-artifacts/prd.md) — 제품 요구사항 정의서
- [Architecture](_bmad-output/planning-artifacts/architecture.md) — 시스템 아키텍처 결정 문서
- [Epics](_bmad-output/planning-artifacts/epics.md) — 에픽 및 스토리 분해
- [Sprint Status](_bmad-output/implementation-artifacts/sprint-status.yaml) — 스프린트 진행 현황
