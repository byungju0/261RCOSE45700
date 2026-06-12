# Deferred Work

## Deferred from: Epic 2 ops polish (spec-epic-2-ops-polish, 2026-05-27)

본 polish 묶음에서 의도적으로 out-of-scope 처리한 2건. Stories 2-8 (SearchEngineConfig) 또는 신규 Story 2-13 등에서 흡수 권장.

- **Dcard `/_api/forums/{slug}/posts` JSON endpoint 직결** — 이번 fix 는 `wait_for` 제거 + 3초 delay 로 보수적 처리. Dcard 공식 JSON endpoint 가 존재 (예: `https://www.dcard.tw/_api/forums/online/posts?before=&limit=&popular=`). 직결 시 (1) 브라우저 우회 자체 불필요 (2) 페이지네이션 trivial (3) anti-bot 부담 감소. 단 현 `SiteConfig` 는 `listing → post URL pattern matching` 1-hop 모델이라 JSON endpoint 흐름을 우겨넣으면 추상화 더러워짐. Story 2-8 (SearchEngineConfig) 작업 시 같은 family 로 묶거나 Story 2-13 (Dcard JSON adapter) 신설 검토.
- **`UndetectedAdapter` 옵션 슬롯 (`SiteConfig.use_undetected`)** — 2026 기준 `BrowserConfig(enable_stealth=True)` 만으로 Cloudflare 통과 효과 미미 (puppeteer-stealth deprecated 2025-02, playwright-stealth 비슷). 현재 52pojie 가 통과되는 건 사이트가 약한 룰만 돌려서일 가능성. Cloudflare 강화 시 `crawl4ai.UndetectedAdapter` + `AsyncPlaywrightCrawlerStrategy` 조합으로 fallback 옵션 슬롯 추가 필요. Story 2-8 BrowserConfig 추상화 설계 시 같이 흡수 권장 (검색엔진형이 anti-bot 더 강함).
- **APScheduler 잡 함수 예외 핸들링 부재** — `_cleanup_url_dedup_job` / `_run_locked` 둘 다 예외 발생 시 APScheduler 가 로그만 남기고 다음 발화 대기 (기본 동작). 단 redis connection refused 같은 영구 오류 시 매 발화마다 같은 예외 반복 → 알람 없음. Story 5-1 Prometheus/Grafana 통합 시 잡 실패 카운터 + 알람 룰 추가 권장.

---

## Deferred from: Story 5-2 dev (2026-05-12 — USER 외부 종속성, Task 5 blocked)

Task 5 [USER] `/opt/app/secrets/*` + `/opt/app/.env` 작성에 필요한 외부 종속성 4종이 손에 들어오기 전까지 Task 5 / 7 / 8 진행 불가. 첫 배포 자체가 시크릿 + 백엔드 컨테이너 startup 모두 의존:

1. **VARCO API key** (`/opt/app/secrets/varco_api_key`) — Naver Cloud VARCO Translation/LLM API key 발급 필요. detection 컨테이너 사용. 누락 시 detection startup 실패 → healthcheck fail → 자동 롤백.
2. **VARCO API base URL** (`VARCO_API_BASE_URL` in `/opt/app/.env`) — 팀에서 확정된 base URL 미수령. 누락 시 `https://varco.placeholder/v1` 같은 placeholder → DNS NXDOMAIN → translate/classify 100% fail → DLQ 폭증.
3. **RDS endpoint + master password** — tracker-prod-db는 Available + `psql SELECT version()`은 통과했으나 `DB_HOST` (정확한 endpoint hostname) + `/opt/app/secrets/db_password` (master password)가 .env/시크릿 파일에 아직 미작성.
4. **백엔드 api/detection 서비스 첫 배포 검증** (다른 팀원 담당 영역) — Spring Boot api + detection 컨테이너 build/GHCR push 후 EC2에서 startup 동작 검증 필요. Flyway V1~V4 migration 첫 실행 모니터링도 본 deferred 항목과 결합 (아래 Story 5-2 dev 2026-05-07 섹션 Flyway 호환성 참조).

**진행 가능한 우회 작업 (외부 종속성 무관)**:
- deploy.yml에 quality gate 3종 추가 (pre-deploy assertion + IMAGE_TAG fail loud + smoke test, +6 LOC) — 시크릿 무관 코드 변경
- Task 6 [USER] dependabot 제거 commit — working tree 이미 제거, commit만 남음, 시크릿 무관

**Blocked**: Task 5 / Task 7 (첫 배포) / Task 8 (자동 롤백 검증) 모두 시크릿 + 첫 배포 의존.

**ADR**: 시크릿 관리 전략은 [docs/adr/0001-secret-management-strategy.md](../../docs/adr/0001-secret-management-strategy.md)에 옵션 A 채택 결정 기록 완료 (2026-05-12).

---

## Deferred from: Story 5-2 dev (2026-05-07)

- **Flyway 10 + PostgreSQL 18.3 호환성 검증** — Spring Boot 3.5 default Flyway 10.x는 PG 17까지 공식 지원. 학생 SCP가 RDS 엔진 16/17 노출 안 해 18.3 채택. V1~V4 migration이 표준 DDL이라 작동 가능성 높지만 첫 배포 시 Flyway 실행 로그 모니터링 필수. 실패 시 `api/build.gradle`에 `dependencies { implementation 'org.flywaydb:flyway-core:12.0.0' }` 식으로 Flyway 12.x 핀 추가 (5분 작업). [Story 5.2 4차 변경 노트 참조]
- ~~**architecture.md 사양 backport (Story 5-2 / 5-3 ClickOps 결과 반영)**~~ — **2026-05-11 RESOLVED (`chore/bmad-sprint-cleanup` PR)**: architecture.md Infrastructure & Deployment 섹션 + tracker_기획서.md 2.1.1.a 표 + 클라우드 표 모두 단일 EC2 t3.xlarge + PG 18.3 + SSH `.pem` only로 일괄 backport 완료. epics.md Story 5.3 AC 본문은 OBSOLETE 마커 강화(historical record 유지). epics.md Story 1.1 Spring Boot 3.4.x → 3.5.0 + docs/deployment.md L38 `environment: production` stale 표기 + Story 5-2 파일의 fingerprint 잔존 ref도 함께 정리.
- **GH repo Organization transfer 검토** — 현재 byungju0 personal repo + collaborator는 admin/Environment 권한 부여 불가능(GitHub 구조적 제약). Required reviewers / Environment 격리 / fine-grain branch protection이 필요해지면 Organization 만들고 transfer 검토. 학생 기간 종료 시점에 결정.
- **EC2 Public IP 고정 (EIP) 검토** — 현재 stop/start 시 Public IP 변경 → GH Secret `EC2_HOST` 갱신 필요. EIP allocation은 학생 SCP 권한 미확인. 운영 부담 측정 후 도입 결정.
- **mem_limit 실측 후 튜닝** — compose.prod.yml의 mem_limit는 16GB 환경에 맞춘 보수적 hard cap(crawler 4G / api 2G / detection 1G / dashboard 128M, 합 ~7G). Story 5.4 부하 시점에 `docker stats` 실측 후 조정. 특히 crawler Playwright 동시 세션이 늘어나면 4G 너머로 가능.
- **자동 배포 첫 cold-start 롤백 fallback** — `/opt/app/IMAGE_TAG` 파일 없을 때 fallback이 `latest`로 떨어져 동일 broken 이미지 가능성. 첫 배포 검증 후 known-good SHA를 수동으로 IMAGE_TAG 파일에 기록하면 해소.

## Deferred from: code review of 2-4-s3-원본-아카이브-및-이미지-수집 (2026-04-29)

- **S3 key length >1024 byte 미체크** [crawler/src/s3_uploader.py:25,56] — 현재 사이트 post_id로는 비현실적. 외부 site 추가 시 재검토.
- **Surrogate `UnicodeEncodeError`** [crawler/src/s3_uploader.py:30, crawler/src/storage.py:76] — preprocessor에서 사전 정제 가정. Story 2.3 산출물 책임.
- **이미지 `read_bytes()` 전체 적재 → OOM** [crawler/src/s3_uploader.py:61] — image_filter score threshold로 작은 이미지만 통과. 운영 측정 후 `upload_file` (multipart) 도입 재검토.
- **동시 `save()` race (`src_path.read_bytes()` + `unlink`)** [crawler/src/storage.py:57-58] — 현재 sequential 파이프라인. Story 5+ 멀티 워커 구성 시 재검토.
- **`post.json` atomic-rename 부재** [crawler/src/storage.py:75-78] — Story 2.3 산출물 (사전 존재). tmp + rename(2) 패턴은 Epic 5 운영 강화 시.
- **이미지 filename 재시도 충돌 (`img_000` 덮어쓰기)** [crawler/src/crawl4ai_crawler.py:172] — `_download_images` 재호출 시 인덱스 재시작. Story 2.3 산출물.
- **`demo.py.get_post_urls`가 board마다 fresh browser 생성** [crawler/demo.py:41-46] — demo는 throwaway, 우선순위 낮음.
- **`site`/`date`/`post_id` 비ASCII/특수문자 → 잘못된 S3 키** [crawler/src/s3_uploader.py:25,56] — 현재 site_id 모두 ASCII alphanum. 신규 사이트 도입 시 정규식 검증.
- **테스트 `clear=True` 환경 전체 비움 → 회귀 검출력 약화** [crawler/tests/unit/test_s3_uploader.py:228-242] — 패치하지 않아도 현재 pass. 테스트 위생 개선 시 함께.
- **`AWS_REGION` whitespace 미정규화** [crawler/src/s3_uploader.py:18-20] — 운영 가이드로 흡수 가능.
- **BOM (`﻿`) 미stripping** [crawler/src/s3_uploader.py:30] — downstream S3 consumer 추가 시 재검토.

## Deferred from: code review of 2-5-apscheduler-기반-자동-크롤링-및-수동-트리거 (2026-04-29)

- **Sync `redis` client을 async event loop에서 사용** [crawler/src/scheduler/crawl_scheduler.py:162-163, crawler/src/queue/redis_publisher.py:11] — 매 LPUSH/sismember/sadd가 event loop을 block. 부하 측정 후 `redis.asyncio` 전면 전환 필요. architecture-level 변경.
- **`PostStorage.save` sync (boto3 포함)** [crawler/src/scheduler/crawl_scheduler.py:119-125] — S3 업로드가 async loop을 block. Story 2.4 작업. aioboto3 또는 `asyncio.to_thread` offload 검토.
- **APScheduler graceful shutdown 부재** [crawler/src/scheduler/crawl_scheduler.py:194-196] — `shutdown(wait=False)`이 in-flight 잡 orphan, SIGTERM 핸들링 없음. NFR10 24h 무중단 트랙(Epic 5).
- **APScheduler misfire 이벤트 미로깅** [crawler/src/scheduler/crawl_scheduler.py:174-184] — misfire 발생 시 가시성 zero. Story 5.1 Prometheus/Grafana와 함께 EVENT_JOB_MISSED listener 추가.
- **`AsyncWebCrawler` 매 board마다 instantiation — Chromium cold start** [crawler/src/scheduler/crawl_scheduler.py:33-36] — 성능 개선. board 단위 → site/run 단위 lifecycle로 전환 검토.
- **`CrawlEvent.detected_at` 시맨틱 모호 (실제는 "now")** [crawler/src/preprocessor/serializer.py] — downstream Detection Worker 영향 큼. Story 3.1+에서 fetched_at vs serialized_at 분리 결정.
- **`language_detector.detect` sync — 긴 텍스트 시 event loop block** [crawler/src/scheduler/crawl_scheduler.py:117] — sync redis defer와 동일 트랙. `asyncio.to_thread` 또는 별도 워커.

## Deferred from: code review of 1-2-공유-인터페이스-계약-및-구조화-로깅-수립 (2026-04-27)

- **requirements.txt -e ../shared 상대경로** — CI 환경/컨테이너에서 경로가 깨질 수 있음. Story 1.5 CI 구성 시 절대경로 또는 workspace 기반 방식으로 교체.
- **pyproject.toml where=[".."] 비표준 설정** — setuptools가 모노레포 루트를 스캔하는 비표준 구성. 실제 배포 환경에서 검증 필요.
- **CrawlEvent.raw_text 크기 제한 없음** — 대형 게시글이 Redis에 수 MB 메시지로 전송될 수 있음. 부하 테스트 시 메시지 크기 상한 정의 필요.
- **VarcoInterface 메서드 예외 계약 없음** — translate/classify의 실패 시 예외 타입 미정의. Story 3.2 VarcoInterface 구현 시 예외 계약 문서화.
- **Redis key 상수 네임스페이스 없음** — `"posts:queue"` 등 bare string이 환경 간 충돌 가능. Story 1.3 환경 설정 시 prefix 전략 결정.
- **get_logger 멀티스레드 경쟁 조건** — `if not logger.handlers:` 체크가 thread-safe하지 않아 핸들러 중복 추가 가능. 실운영 전 검토.
- **ClassificationResult.confidence 범위 검증 없음** — `[0.0, 1.0]` 외 값 수용. Story 3.3 VARCO 연동 시 API 응답 검증 추가.
- **TrackerBaseException str() 시 correlation_id 누락** — `str(exc)` 호출 시 message만 출력. 로그 사용 가이드에 `logger.error(str(e), extra={"correlation_id": e.correlation_id})` 패턴 문서화.

## Deferred from: code review of 2-2-proxyprovider-추상화-및-기본-크롤러-구현 (2026-04-28)

- **ParseResult.image_urls 가변 리스트** — `@dataclass(frozen=True)`임에도 `image_urls: list[str]` 필드는 내용 변경 가능. 현 MVP에서는 실질적 위험 없으나, Story 2.3+ 모델 안정화 시 `tuple[str, ...]`로 전환 검토.
- **parse_list 외부 도메인 document_srl 교차 오염** — `urljoin` 처리 후 외부 도메인 링크에 `?document_srl=N`이 포함된 경우 tailstar 게시글로 오분류 가능. Story 2.5 통합 테스트 시 실제 사이트 목록 페이지로 검증.
- **test_proxy_provider.py async_playwright 동기 MagicMock 취약성** — `monkeypatch.setattr("...async_playwright", lambda: MagicMock())`이 async context manager 계약을 위반. 현 NFR15 swap 검증 목적에는 충분하나, StealthBrowser 리팩토링 시 mock 구조 재검토 필요.

## Deferred from: code review of 2-3-콘텐츠-전처리-파이프라인-구현 (2026-04-28)

- **TOCTOU race in DedupChecker** — `is_duplicate`+`mark_seen`이 비원자적(SISMEMBER 후 SADD). 단일 워커에서는 무해하나, 멀티 워커 확장 시 중복 이벤트 발행 가능. Story 2.5+ 멀티 워커 구성 시 Redis pipeline 또는 SETNX 패턴으로 원자화 필요.
- **이미지 다운로드 메모리 크기 제한 없음** — `resp.content` 전체 버퍼링으로 대용량 이미지 응답 시 OOM 가능. 운영 배포 전 `Content-Length` 가드 또는 스트리밍 다운로드로 전환 필요.
- **`_base_run_config` shared object** — `crawl4ai_crawler.py`에서 `CrawlerRunConfig` 인스턴스를 공유 참조로 사용. crawl4ai가 config 객체를 내부적으로 변경하는 경우 동시 크롤링 시 경합 가능. crawl4ai 업그레이드 시 확인.
- **conftest sys.path 조작** — `tests/conftest.py`에서 `sys.path.insert`로 임포트 해결. 패키지 미설치 환경에서 CI 실패 가능. Story 1.5 CI 구성 시 `pip install -e .` 또는 `pyproject.toml` packages 선언으로 교체.
- **이미지 다운로드 레이트 리밋 없음** — `_download_images`가 순차 루프로 HTTP 요청. 미래 병렬화 시 비제한 flood 위험. asyncio Semaphore 또는 레이트 리밋 추가 필요.
- **브라우저 기동 타임아웃 없음** — `AsyncWebCrawler.__aenter__` 진입 시 타임아웃 미설정. Chromium 기동 hang 시 무한 대기. 운영 전 asyncio.wait_for 래핑 검토.
- **dedup 텍스트 Unicode 정규화 없음** — 동일 게시글이 NFC/NFD 또는 trailing whitespace 차이로 다른 SHA-256 해시 생성. 실운영 중복률 측정 후 필요 시 `unicodedata.normalize('NFC', text.strip())` 추가.
- **disabled 사이트 이미지 필터 과도한 확장(nga, pojie)** — `_nga_image_filter`에서 `"img"` 3글자 substring 매칭, `_pojie_image_filter`에서 유사 문제. Story 2.7 사이트 활성화 시 서브도메인 앵커링으로 수정 필요.
- **PTT post_id extractor `.html` suffix 포함** — 기본 `post_id_extractor`가 PTT URL에서 `M.1681234567.A.123.html` 반환. Story 2.6 PTT 구현 시 전용 extractor 정의 필요.
- **빈 raw_text CrawlEvent 발행** — `CrawlResult.markdown`이 빈 문자열인 경우 `raw_text=""`인 이벤트가 발행됨. Story 2.5 파이프라인에서 빈 이벤트 필터링 또는 경고 로그 추가 검토.
- **`CrawlerRunConfig` 수동 필드 복사** — css_selector 사용 시 `CrawlerRunConfig` 8개 필드를 수동 복사. crawl4ai 신규 필드 추가 시 silently drop됨. 라이브러리 업그레이드 시 수동 확인 필요.

## Deferred from: code review of 2-1-cloudflare-우회-가능성-검증 (2026-04-27)

- **하드코딩된 `Chrome/124` User-Agent 봇 탐지 지문화** — `crawler/src/browser/stealth_browser.py:15`. 이번 스파이크의 의도적 선택이나, 시간이 지남에 따라 구버전 UA로 봇 탐지율 증가. playwright 버전 핀 갱신 시 함께 업데이트 필요. Story 2.2+ 추적.
- **`Stealth().use_async(async_playwright())` 내부 CM 진입/탈출 보장 여부** — `crawler/src/browser/stealth_browser.py:57`. playwright-stealth 2.x 라이브러리가 `async_playwright()` CM을 올바르게 진입/탈출하는지 소스 검증 필요. 통합 테스트에서 Chromium 프로세스 누수 모니터링.
- **`response=None` 시 불충분한 오류 메시지** — `crawler/src/browser/stealth_browser.py:91`. `"unexpected HTTP status None"` 메시지로는 "서버 응답 없음" 원인 파악 불가. Story 2.2 리파인 시 개선.
- **`crawler/__init__.py` 추가로 잠재적 패키지 임포트 경로 충돌** — `crawler/__init__.py`. 모노레포 구조에서 의도된 배치이나, 배포 환경에서 동명 PyPI 패키지와 충돌 가능성 검토 필요.

## Deferred from: code review (Epic 4 프론트엔드, 2026-04-28)

- **RecentAlertList "High confidence" 헤딩 미스매치** [components/tracker/RecentAlertList.tsx:21] — heading은 high-confidence를 암시하지만 query에 confidence 필터 없음. 제품 결정: 헤딩을 "Recent"로 변경 vs query에 minConfidence 추가. 백엔드 필터 지원 후 결정.
- **Hero correlation pill (unique·중복) mock 데이터** [pages/Dashboard/index.tsx Hero] — `count - floor(count*0.3)` / `floor(count*0.3)` 산술은 fabricated. 실제 backend grouping 필드 추가 후 재구현 또는 제거.
- **REVIEWED_FRACTION 0.25 mock 라벨링** [pages/Dashboard/index.tsx:13] — 진척도 25% 고정 mock. Stats API에 reviewed count 필드 추가 시 swap.
- **Today timestamp 자정 롤오버** [pages/Dashboard/index.tsx:31] — `new Date()` 렌더 시점 1회 계산. TanStack Query refetch 시 갱신되지만 60s 폴링 사이에 자정 넘으면 표시 잔류. dataUpdatedAt + ticking state로 교체 필요.
- **FreshnessIndicator/NewDetectionsBadge 제거 회귀** [layouts/Topbar.tsx, layouts/RootLayout.tsx] — 새 Topbar에 freshness 표시 + 수동 트리거 후 새 탐지 알림 없음. Hero 시스템 상태 줄에 dataUpdatedAt 연결 또는 컴포넌트 복원 결정 필요.
- ~~**3-column 레이아웃 모바일 breakpoint 부재** [layouts/RootLayout.tsx:20] — sidebar 240px + rail 240px 고정으로 ~600px 미만에서 main 압착. desktop-only 전제 명시 또는 < lg 에서 rail 드로어화 필요.~~ **[해소 — Story 4.7 (2026-05-13) PIVOT]** Tailwind `md` 768px breakpoint 분기 + Sidebar 햄버거 → vaul drawer + DetectionList 카드 뷰 + FilterBar bottom Drawer 도입으로 해결.

## Deferred from: code review of 1-1-모노레포-구조-초기화-및-서브시스템-스캐폴딩 (2026-04-29)

- **`build/` 패턴 무앵커** [`.gitignore`:27] — `api/build/`가 의도이나 미래 서브시스템의 `build/` 디렉토리도 자동 무시 가능. Story 1.5 CI 추가 시 앵커 필요 여부 재검토.
- **`dist/` 패턴 무앵커** [`.gitignore`:23] — `dashboard/dist/`가 의도이나 다른 서브시스템에서 `dist/` 규칙 채택 시 충돌 가능. 배포 아티팩트 전략 확정 시 `/dashboard/dist/`로 앵커링.

## Deferred from: code review of 1-3-로컬-개발-환경-구성 (2026-04-29)

- **redis/postgres `healthcheck:` 블록 미정의** [infra/docker-compose.yml] — `up -d` 직후 컨테이너가 Listening 되기 전 의존 서비스 부팅 시 race. Story 1.4 Flyway 마이그레이션이 `service_healthy` condition을 요구하므로 그때 일괄 추가.
- **VARCO_API_KEY required-var 가드 부재** [infra/.env.example, infra/docker-compose.yml] — placeholder `your-varco-api-key-here`가 그대로 사용되면 런타임 401로 fail. crawler/detection 컨테이너 추가 시 해당 서비스 environment에 `${VARCO_API_KEY:?}` 부착.
- **postgres `/docker-entrypoint-initdb.d` 마운트 슬롯 미예약** [infra/docker-compose.yml] — Story 1.4에서 `pg_trgm`/`uuid-ossp` 등 extension 필요 시 Flyway baseline에 포함하거나 initdb 마운트 추가 결정 필요.

## Deferred from: code review of 3-1-redis-큐-소비자-및-watchdog-구현 (2026-04-29)

- **Watchdog LREM/RPUSH 비원자성 (D1, decision-needed→defer)** [detection/src/consumer/watchdog.py:64-77] — race window는 ms 단위 + 단일 Watchdog MVP. Story 3.5 측정 후 발생률 기반 재결정.
- **같은 `post_id` 중복 메시지 LREM 오제거 가능성 (D3, decision-needed→defer)** [detection/src/consumer/queue_consumer.py:45, watchdog.py:65,76] — DedupChecker(SHA-256) + Story 3.4 DB UniqueConstraint 이중 안전망 존재. 단일 post_id 충돌 빈도 사실상 0.
- **`mark_processing` 침묵 실패** [detection/src/consumer/watchdog.py:35-45] — spec 명시 의도이나 정상 처리 중 메시지가 즉시 stale 판정되는 race window. spec 설계 유지.
- **`processing_time` TTL = stale 임계치 동일(300s)** [detection/src/consumer/watchdog.py:17] — VARCO 5분 초과 처리 시 stale 오판. Story 3.2 VARCO SLA 측정 후 TTL 분리 검토.
- **`run_forever` 예외 처리 부재** [detection/src/consumer/queue_consumer.py:64-65, watchdog.py:97-99] — Connection Error 시 프로세스 종료. Story 5.3 supervisor/restart 정책 확정 시 보완.
- **`brpoplpush` Redis 6.2+ deprecated** [detection/src/consumer/queue_consumer.py:32-36] — spec 명시 사용. 후속 라이브러리 업그레이드 시 `BLMOVE` 마이그레이션.
- **Watchdog 첫 스캔 60초 지연** [detection/src/consumer/watchdog.py:97-99] — 부팅 직후 잔존 stale 메시지 60초 방치. MVP 영향 미미.
- **다중 Watchdog 인스턴스 race 보호 부재** [detection/src/consumer/watchdog.py:62-77] — `get → incr` 비원자. spec 단일 Watchdog 가정. Epic 5 분산 락 검토.
- **환경변수 모듈 임포트 시점 캡처** [detection/src/consumer/queue_consumer.py:14-15, watchdog.py:16-19] — 통합 테스트 도입 시 함수형 전환.
- **`LRANGE 0 -1` 풀스캔** [detection/src/consumer/watchdog.py:49] — 운영 부하 발생 시 페이징/SCAN 도입.
- **단일 `redis.Redis` 메인/데몬 스레드 공유** [detection/src/main.py:22-29] — connection pool 명시 크기 미설정.
- **SIGTERM/SIGINT graceful shutdown 부재** [detection/src/main.py] — Story 5.3 시그널 핸들러 + drain 로직.
- **`_MAX_RETRIES` env 외부화 / off-by-one naming** [detection/src/consumer/watchdog.py:19] — 후속 개선.
- **`int(os.environ.get(...))` 검증 부재** [detection/src/consumer/queue_consumer.py:15, watchdog.py:17-18] — 운영 misconfig 가드 추가.
- **Watchdog `RPUSH` 재투입 우선순위 (poison priority inversion)** [detection/src/consumer/watchdog.py:75] — backoff 정책 도입 시 LPUSH 또는 별도 retry queue 검토.
- **`pytest.ini` 옵션 부재 / `process_fn` 시그니처 단순** — `addopts` 미정의, Story 3.2에서 비동기/컨텍스트 전달 필요 시 변경.

## Deferred from: code review of 1-5-github-actions-기본-ci-파이프라인-구성 (2026-04-29)

- **Branch Protection strict merge gate / AC #5** [docs/ci-setup.md:17] — Story 1.5의 4개 workflow는 `paths:` 필터가 있어 required check로 직접 등록하면 무관 경로 PR에서 skipped check가 pending으로 남을 수 있다. Strict PR merge blocking은 Story 5.2에서 항상 실행되는 `ci-aggregator.yml` 또는 동등한 required check 설계로 처리한다.


## Deferred from: dev of 5-3-aws-프로덕션-인프라-프로비저닝 (2026-05-04) — _OBSOLETE_

> **2026-05-06 — 본 섹션 + 다음 PIVOT 섹션 모두 obsolete.** Story 5-3이 ClickOps로 전환되며 Terraform 자체가 폐기됨(commit `13d96a9`). 아래 항목들은 모두 Terraform 코드 가정 기반이라 더 이상 추적 대상 아님. 기록 보존만 목적. 새로운 ClickOps 환경에서의 deferred 항목은 본 파일 맨 아래 `Deferred from: Story 5-3 ClickOps PIVOT (2026-05-06)` 참조.

- **dev 환경 실 apply 미실행** [Task 10.6, 13.1~13.5] — 본 세션은 코드/CI/문서까지(Option A). bootstrap 1회 apply 및 dev 환경 apply, SSM Session Manager 접속 검증, RDS SG 격리 검증, 24시간 비용 측정은 별도 ops 세션에서 수행. AC #1·#12·#19 일부의 실제 동작 확인 항목.
- **GitHub repository Variables/Environments 등록 미실행** [`.github/workflows/terraform.yml`] — `AWS_TF_ROLE_DEV` / `AWS_TF_ROLE_PROD` Variables, `prod` Environment + reviewers 설정은 Console 작업이라 실 apply 후 수행. 등록 전까지 PR plan-dev / apply-* 잡은 OIDC assume 실패.
- **Secrets Manager 시크릿 값 1회 주입 미실행** [`infra/terraform/modules/secrets/`] — `tracker/{env}/varco-api-key`, `tracker/{env}/proxy-credentials`는 placeholder만 생성. `aws secretsmanager put-secret-value`로 1회 주입 필요. RDS 비밀번호는 `random_password`가 자동 처리.
- **GHA Terraform Role 와일드카드 액션** [`infra/terraform/modules/iam/main.tf` `MutateInfraResources` statement] — `ec2:*` `rds:*` 등 service-level write + `Resource: "*"`. 학생 프로젝트 운영 부담 절충. 장기 운영 전환 시 액션·ARN 단위로 좁혀 Checkov `CKV_AWS_111` 정식 통과 처리. 현재는 `.checkov.yml`에서 skip.
- **OIDC provider thumbprint placeholder** [`infra/terraform/modules/iam/main.tf:resource "aws_iam_openid_connect_provider"`] — AWS provider v6 + GitHub IdP는 AWS-trusted CA 라이브러리로 검증되며 thumbprint는 retained but not used 상태. placeholder(`ffff...`)로 유지. 회전 영향 없음(초기 노트 정정). 출처: AWS IAM OIDC verify-thumbprint 문서, hashicorp/terraform-provider-aws#35112.
- **EBS encryption region 단위 멱등성** [`infra/terraform/modules/security-baseline/main.tf:aws_ebs_encryption_by_default`] — region 단위 자원이라 dev/prod 양쪽에서 동일 값 set 시 idempotent하지만 drift 시 마지막 apply 환경의 값을 따른다. 단일 환경에서만 정의하고 다른 환경은 data source로 참조하는 구조로 옮길지 검토.
- **bootstrap state 로컬 보관** [`infra/terraform/bootstrap/`] — bootstrap 자체는 자기 state를 자기가 만든 버킷에 두는 chicken-and-egg 문제로 로컬 보관. 1Password 등 안전한 백업 정책 별도 운영. 잘못 destroy 시 dev/prod 전체 state 손실.
- **VPC CIDR 충돌 사전 점검 미수행** [`infra/terraform/environments/dev/variables.tf` `10.20.0.0/16`, prod `10.30.0.0/16`] — 회사/학교 다른 VPC와 peering 또는 VPN 연결 가능성을 고려한 CIDR 회피 미검증. dev/prod간 CIDR 분리는 했으나 외부 환경과의 충돌 검증은 실 apply 시점에 확인.
- **Performance Insights 비활성** [`infra/terraform/modules/rds/main.tf`] — db.t4g.micro 미지원이라 `false`. 운영 모니터링 강화 시 인스턴스 클래스 업그레이드 + 활성화.
- **CloudTrail 데이터 이벤트 미수집** [`infra/terraform/modules/security-baseline/main.tf:aws_cloudtrail`] — 학생 예산 절감을 위해 management events만. S3/Secrets 객체 수준 감사가 필요해지면 `data_resource` 추가 + 비용 협의.
- **NAT 운영 방식 fallback 미구현** [`infra/terraform/modules/networking/main.tf` `nat_strategy = "instance"|"gateway"`] — 변수 분기만 보존, 실제 `instance`/`gateway` 분기 구현은 미완. 트래픽 증가 또는 발표 데모 직전 도입 결정 시 모듈 확장.
- **EC2 접근 백업 방식 (SPIKE 5.0 #12)** — SSM Session Manager 단독 구현. 대규모 장애 시 EC2 진입 백업(예: 임시 IP 화이트리스트 SSH 룰 토글 워크플로우)은 한계 발생 시 별도 검토.
- **terraform-aws-modules `iam` 미사용** [`infra/terraform/modules/iam/main.tf`] — IAM은 자체 리소스 정의로 작성. 추후 `terraform-aws-modules/iam/aws`의 oidc-provider / iam-assumable-role-with-oidc 서브모듈 도입 검토 가능.
- **RDS Secrets Manager `manage_master_user_password` 미사용** [`infra/terraform/modules/rds/main.tf`] — RDS 모듈 7.x의 AWS-관리형 비밀번호 회전 기능 대신 `random_password` 직접 주입. tfstate에 평문 password 저장 트레이드오프 수용. 회전 자동화 도입 시 모듈 옵션 전환.
- **dev/prod CloudTrail trail 중복** [`infra/terraform/modules/security-baseline/main.tf:aws_cloudtrail`] — env별로 별도 trail 생성. multi-region이라 한 환경 trail로 충분할 수도 있으나 명확한 분리 + 비용 영향 미미라 유지. 비용 점검 후 통합 검토 가능.
- **Graviton4(r8g) 업그레이드 검토** [`infra/terraform/environments/{dev,prod}/main.tf`] — 본 스토리는 architecture.md backport(PR #18) 준수해 r6g.large/t4g.medium/t4g.large(Graviton2)로 박음. 그러나 2026-05 기준 Seoul region에서 r8g(Graviton4) 가용 + on-demand 가격이 r7g와 같고 30% 빠름. 단 t8g는 일부 region 제한 가능성. 다음 architecture decision 갱신 시 PM 합의 + 비용 재산정 후 r6g→r8g(crawler) / t4g→m8g(detection/api) 검토 가치. 메모리 우선 결정(crawler r6g.large 16GB)은 변하지 않으므로 동일 RAM 등급 인스턴스 매핑.
- **GitHub Actions Node 20 EOL (2026-04)** — Node 20은 2026-04 EOL 도달. 워크플로우의 모든 액션을 Node 24 지원 버전으로 갱신 완료(checkout v6, github-script v8, setup-terraform v4, configure-aws-credentials v6, setup-tflint v6). 기존 4종 워크플로우(crawler/detection/api/dashboard.yml)는 Story 5.2 strict CI 합류 시점에 동일 갱신 필요.

## Deferred from: dev of 5-3-aws-프로덕션-인프라-프로비저닝 — PIVOT 추가 (2026-05-04)

학생 계정 SCP 제약으로 architecture 전면 재설계 후 추가 deferred.

- **Crawler RAM 16GB → 4GB 다운그레이드** [`infra/terraform/environments/dev/main.tf:module "ec2_crawler"`] — 학생 계정 t3.medium(4GB)이 최대. `memory/project_crawler_ram_priority.md`(8~16GB 권장) 충족 불가. Story 5.4 부하 측정으로 다음 중 택1: ① Chromium + FlareSolverr 별도 EC2 분리 ② swap 4GB 추가 ③ `--single-process` 등 헤드리스 옵션 최적화 ④ APScheduler 동시 worker 1 강제.
- **EC2 메모리 합 12GB (4×3)** — Detection/API도 4GB로 축소. Spring Boot + Redis docker-compose 동거(API)와 VARCO LLM 호출 동시 처리(Detection) 메모리 압박 가능. Story 5.4에서 측정.
- **`aws_ebs_encryption_by_default` 미생성** [`infra/terraform/modules/security-baseline/main.tf`] — 학생 계정 권한 부족 보수적 가정으로 코드 비활성. 학교 region default 정책에 의존(콘솔에서 EC2 → "EBS encryption" 확인 필요). default off라면 EBS 볼륨 암호화 안 됨 → 콘솔 1회 enable 또는 학교 관리자 요청.
- **VPC Flow Logs 미생성** [`infra/terraform/modules/networking/main.tf`] — Default VPC에 Flow Logs 자원 추가 권한 부족 가능성으로 비활성. NFR9 감사 요구 위반. 학교 organization 레벨 Flow Logs 또는 콘솔 1회 enable로 보강 필요.
- **CloudTrail 미생성** [`infra/terraform/modules/security-baseline/main.tf`] — 학생 계정 권한 부족 가정. 학교 organization trail이 모든 학생 계정 이벤트를 기록하고 있는지 확인 필요. 없다면 NFR9 감사 요구 충족 X — 학교 관리자에게 organization trail 활성 요청.
- **AWS Budgets 미생성** [`infra/terraform/modules/security-baseline/main.tf`] — 학생 계정 권한 부족 가정. 학교 사전 설정 budget 한도 확인 필요(보통 학생당 $50~100/월). Cost Explorer로 사후 모니터링.
- **VPC Gateway Endpoint(S3) 미생성** [`infra/terraform/modules/networking/main.tf`] — Default VPC 라우트 테이블 수정 권한 불확실로 제외. EC2→S3 트래픽이 IGW를 통과하나 동일 region이라 비용 영향 미미.
- **CloudWatch Log Group 14일 retention 미설정** — Flow Logs/CloudTrail 미생성으로 자동 미생성. RDS export logs(`postgresql`/`upgrade`)는 default(영구)로 적재될 수 있음 — 콘솔에서 retention 1회 설정 권장.
- **MFA 운영 절차** — `<mfa-required-scp>` 정책으로 모든 IAM 사용자 액션이 MFA 인증 필요. README + Story Dev Notes에 절차 명시되어 있으나 팀원 onboarding 시 반복 안내 필요. CI 워크플로우는 OIDC라 MFA 우회됨(IAM Role assume 자체에 MFA 조건 없으면).
- **prod 환경 미사용 — portfolio 코드만 보존** [`infra/terraform/environments/prod/`] — 학생 계정 1개로 prod 분리 의미 없음. CI workflow apply-prod 잡 `if: false` 비활성. README + main.tf 헤더에 미사용 명시. 졸업 후 실 production 계정 확보 시 git history에서 PIVOT 이전 코드 복원.
- **architecture.md / epics.md / 기획서.md backport 필요** — 본 PIVOT으로 architecture.md Infrastructure & Deployment(L221-L256) + Project Structure(L669-L685) + epics.md Epic 5 + 기획서.md 10.1 결정값이 코드와 불일치. PR #18로 backport한 결정의 다수가 학생 계정 PIVOT으로 갱신됨. PM/팀(@byungju0, @erdmee) 합의 후 별도 PR로 backport 처리.
- **publicly_accessible=true RDS 정기 점검** — SG inbound 5432 source 매핑 + `rds.force_ssl=1` parameter group이 정상 동작하는지 월 1회 검증. 콘솔 RDS → Connectivity & security 탭에서 publicly accessible 상태 + Security group 룰 확인 + `psql -h <endpoint> -U tracker_admin --no-password` (TLS 없이) 시도 시 거절되는지 검증.
- **EC2 Instance Profile / OIDC Provider 생성 권한 미검증** — `<iam-advanced-policy>` 정책으로 가능 가정. 실제 apply 시 권한 거부 메시지 발생 가능. 그 경우 시나리오 Q(EC2 Role 비활성화 + 시크릿 user_data 주입 또는 Secrets Manager 미사용)로 다운그레이드 필요. apply 1차 시도 후 결과에 따라 결정.
- **CI OIDC + <mfa-required-scp> 충돌 가능성** [`infra/terraform/modules/iam/main.tf:aws_iam_role.github_actions`] — GitHub Actions OIDC는 `sts:AssumeRoleWithWebIdentity` 호출. 학생 계정 SCP가 모든 sts:AssumeRole에 MFA 강제하면 CI 자동 apply가 영구 차단될 가능성. 우리 코드의 assume_role_policy에는 MFA 조건 없음(OIDC sub claim 매칭만)이지만 account-wide SCP 우선 적용. apply 후 GitHub Actions PR plan 시도해서 검증 필요. 차단 시 대응: ① CI 자동 apply 영구 비활성 + 사용자가 CloudShell에서 수동 apply ② 학교 관리자에게 OIDC Role의 MFA 우회 요청 (보통 거절).
- **bootstrap state 파일 보관 — CloudShell 사용 시 추가 risk** — CloudShell 종료 시 home 디렉토리 1GB 제한 + 일정 기간 미사용 시 자동 wipe. bootstrap apply 후 즉시 `terraform.tfstate` 로컬 다운로드 + 안전한 곳(1Password 등) 백업 필수. 백업 안 하면 dev 환경 destroy 시 잔여 자원 manual cleanup 필요.
- **IAM Access Key 발급 차단 가능성** — 학교가 보안상 IAM 사용자 Access Key 발급을 막아둔 경우 로컬 + MFA 토큰 옵션(README Option B) 사용 불가 → CloudShell만 가능. apply 시도 전 IAM 콘솔에서 "Create access key" 버튼 활성 여부 확인 필요.
- **콘솔에서 EC2 launch wizard 외 인스턴스 타입 화이트리스트** — `<instance-type-allow-policy>` + `<t3-extra-allow-policy>` 정책 본문 조회 권한 부족으로 정확한 화이트리스트 미확정. 콘솔 EC2 launch wizard 드롭다운에 t3.{nano,micro,small,medium}만 표시되었으나 다른 타입(예: c5.large)은 시도 시 거부 예상. instance_type validation은 4종으로 좁혀둠 — 추가 타입 필요 시 학교 관리자 문의.

## Deferred from: Story 5-3 ClickOps PIVOT (2026-05-06)

학생 IAM 사용자(`<student-iam-user>`)에서 Terraform 자격증명 통로 0개(IAM Access Key 차단 + CloudShell deny + IAM Role 생성 deny) 확인되어 Terraform IaC 폐기 + ClickOps 전환. 위 두 섹션의 deferred 항목들은 모두 Terraform 코드 가정 기반이라 더 이상 유효하지 않음. ClickOps 환경에서 새로 발생하는 deferred:

- **인프라 변경 추적 불가** — ClickOps는 누가 언제 무엇을 바꿨는지 코드로 남지 않음. CloudTrail organization trail이 학교 측에 활성되어 있다면 그것에 의존, 없으면 변경 이력 0. 발표 자료엔 ClickOps 시점 스크린샷으로 대체.
- **인프라 재현성 0** — 학생 계정 자체에서 자원이 destroy되거나 학기 종료 후 계정 회수되면 동일 환경 재현 불가. 졸업 후 개인 계정에서는 git history(`b7e24d3`, `bd172d9`)의 Terraform 코드로 1회 apply 시 재현 가능.
- **IAM Role 생성 불가 → EC2 SSM 접속 가능성 미확정** — 학교가 미리 만든 EC2 Trust Role(예: `LabRole`, `voclabs`)이 있는지 확인 필요. 있고 `AmazonSSMManagedInstanceCore` 정책이 붙어있으면 SSM 접속 가능. 없으면 EC2 IAM Role 0 → SSM 불가 → 외부 22 SSH 키 또는 EC2 접속 자체 포기.
- **Secrets Manager 접근 권한 미확정** — 위 EC2 Role이 `secretsmanager:GetSecretValue` 권한도 가지고 있는지 따로 확인 필요. 권한 없으면 VARCO API key + RDS 비밀번호를 EC2 user_data에 임시 평문으로 박는 방법(보안 trade-off) 또는 환경변수 직접 주입.
- **RDS 보안 그룹 인바운드 검증** — ClickOps로 RDS 만들 때 publicly_accessible=true 강제되므로 SG 인바운드를 EC2 SG ID 한정으로 좁히는 게 유일한 방어선. 콘솔에서 SG 룰 정확히 입력하는지 1회 검증 필요(인터넷에서 직접 5432 접속 시도 → 거절 확인).
- **rds.force_ssl=1 parameter group** — RDS 콘솔에서 custom parameter group 만들고 적용해야 평문 접속 차단. ClickOps 절차에서 빠뜨리기 쉬움 — 데모 전 체크리스트.
- **인스턴스 종료 후 비용 누수** — 학기 종료 후 EC2 stop이 아니라 terminate, RDS도 final snapshot 후 delete, S3도 비우고 delete. ClickOps는 자동 destroy가 없어 수동 정리 필수. 학교 사전 설정 budget 한도 초과 시 강제 종료될 수도 있음.
- **재현 가능성을 위한 ClickOps 절차 문서화** — 콘솔에서 만든 자원의 정확한 설정값(EC2 AMI ID, SG 룰, RDS 파라미터 등)을 별도 markdown 문서로 캡처해두는 게 졸업 후 재현/발표 자료에 유리. `docs/clickops-runbook.md` 같은 형식으로 남기는 걸 권장.

## Deferred from: code review of 5-1-prometheus-메트릭-수집-및-grafana-대시보드-구성 (2026-05-12)

- **APScheduler max_instances skip 관측 부재** [crawler/src/scheduler/crawl_scheduler.py:229] — Story 5.1은 `EVENT_JOB_MISSED` 기반 misfire 로깅을 추가했지만, 긴 크롤 실행으로 `max_instances=1` 제한에 걸리는 skip은 별도 이벤트(`EVENT_JOB_MAX_INSTANCES`) 경로라 이번 리스너로는 잡히지 않을 수 있다. 기존 스케줄러 동작의 운영 가시성 개선 항목으로 후속 모니터링 스토리에서 검토.

## Deferred from: code review of sprint-change-proposal-2026-05-19 / PR #46 (2026-05-20)

- **dedup_checker whitespace-only difference로 해시 변동** [crawler/src/preprocessor/dedup_checker.py:22-23] — `sha256(text.encode())` 는 trailing newline 차이도 다른 해시로 본다. crawl4ai 재크롤 시 markdown 표현이 미세하게 달라지면 dedup 누락. 별도 정규화 스토리에서 `text.strip()` 또는 whitespace collapse 적용.
- **trigger_listener reconnect storm (5s fixed back-off)** [crawler/src/scheduler/trigger_listener.py:66-71] — 네트워크 partition 시 5초 고정 backoff로 로그 spam. exponential backoff + jitter는 별도 stability 항목.
- **이미지 확장자 결정에 Content-Type 미사용** [crawler/src/crawl4ai_crawler.py:289] — URL `?` 앞 path suffix 만으로 결정하여 extensionless CDN URL은 `.jpg` 기본값. Content-Type 기반 보정은 별도 storage 정밀도 항목.
- **PTT/Dcard validator marker 튜닝 (False positive 가능성)** [crawler/src/preprocessor/content_validator.py:126-148] — 4-header 부분 일치 / `## #` 본문 매칭이 quoted text 에서 오탐 가능. 운영 데이터 수집 후 정량화하여 튜닝.

## Deferred from: 3-layer adversarial review of spec-3-2-cleanup-varco-translation (2026-05-27)

본 cleanup PR은 deletion 범위에 충실. 아래 항목은 Story 3-3 또는 별도 cleanup pass로 이월.

- **`VarcoMock.translate()` dead method + mock_response_rate_limited.json / timeout.json 고아 fixture** [detection/src/mocks/varco_mock.py, tests/fixtures/varco/] — Story 3-3에서 `llm_mock.py` 전면 대체 시 함께 정리.
- **README.md doc drift — Translator 마케팅 문구 잔존** [README.md L21,51,109,141,149] — Story 3-3 머지 후 일괄 doc cleanup pass.
- **architecture.md L702 `varco.py # Protocol class: translate/classify/analyze` 잔존** [_bmad-output/planning-artifacts/architecture.md:702] — Story 3-3에서 shared/interfaces/llm.py로 rename 시 갱신.
- **`varco_client.py::__init__` 와 `classify()` 의 VARCO_CLASSIFY_TIMEOUT_SEC 이중 읽기** [detection/src/pipeline/varco_client.py:23,31] — pre-existing 코드 패턴. Story 3-3에서 varco_client.py 전체가 llm_client.py로 대체되며 자연 해소.
- **infra/compose.prod.yml + deploy.yml의 `varco_api_key` Docker secret mount 잔존** [infra/compose.prod.yml:65,84,139, .github/workflows/deploy.yml:219] — Story 3-3에서 OpenAI secret으로 교체 시 함께 정리.
- **detection/tests/integration/ 디렉터리 사실상 비어있음 (consumer→pipeline→retry→DLQ 통합 커버리지 0)** — Story 3-3 AC에 `test_llm_pipeline.py` 신설 명시되어 있음. 진행 시 자연 복구.
- **stale Redis 키 `varco:rate_limit:translate` 운영 정리 (production migration)** — 본 PR은 feature 브랜치 단계라 운영 영향 없음. 운영 배포 전 stale 키 삭제 1회 필요 시 Story 3-3 또는 5-2 deploy 단계에 포함.
- **DetectionPipeline.process()에서 번역 완료 log 제거에 따른 관측성 갭** — Story 3-3에서 LLM 호출 + Tier 라우팅 log로 자연 복구.
- **detection_pipeline.py가 `event.language`나 빈 raw_text guard 없음** — interim 상태. Story 3-3 LLMClient 호출 경로에서 guard 또는 OpenAI 측 처리에 위임.

## Deferred from: Story 3-5 재정의 (2026-06-02 — few-shot 데이터 수집으로 전환)

Story 3-5를 "정확도 사전 측정"에서 **"few-shot 학습용 라벨 데이터 수집 기반"**으로 재정의(운영자 create-story 결정: "데이터를 모아서 나중에 few-shot learning을 구현할 방향"). 재정의 3-5는 라벨 수집(RDS 컬럼)·코퍼스 export·경량 스냅샷까지만 담당. 아래는 원안에서 빠져 미래로 이월된 항목.

- **정식 정확도 측정 (≥300 라벨셋 + Tier별 confusion matrix + 비용/p95)** — 원 Story 3.5 AC. ≥300건 라벨셋(Tier별 ≥75, 이미지 첨부 ≥50), 전체 Precision ≥0.80 / T1 Recall ≥0.80 / T2 ≥0.65 / T3 ≥0.50 게이트, Tier별 confusion matrix(T1/T2/T3/T4 × predicted), 게시글당 평균 비용(USD)·p95 latency·이미지 유무 분리 집계, 라이브 검증(≥30건 실 OpenAI) 별도 기록, 1회 배치 ≤30분(NFR3). **재정의 3-5의 `labelset_snapshot.py`(overall agreement + 커버리지 카운트)는 이 정식 측정의 경량 선행 버전** — 라벨이 ≥300건 누적되면 별도 "측정 스토리"에서 confusion matrix/비용/p95로 승격. 산출물: `docs/quality-gate-epic3.md` / `docs/quality-gate-epic3-live.md`. [Source: epics.md#Story 3.5 원안, PRD Success Criteria L73-78]
- **few-shot 프롬프트 주입 (Stage 2-B 실제 구현)** — 재정의 3-5는 `detection/src/prompts/examples/{game_key}.jsonl` 코퍼스 **생성**과 포맷 계약(`examples/README.md`)까지만. `detection/src/pipeline/llm_client.py::build_system_prompt()`의 Stage 2-B 빈 슬롯에 예시를 실제로 **선택·삽입**하는 로직 + 토큰 예산 런타임 관리 + few-shot 전/후 정확도 효과 측정은 **별도 미래 스토리**. 라벨 품질·코퍼스 충분성을 본 뒤 주입 위치/형식 결정(조기 구현 시 프롬프트 캐싱 prefix 안정성·토큰 비용 회귀 위험). [연결: 3-0 closure 이미지/번역 spot-check + 라벨셋 확장]
- **Spring API / 대시보드 라벨링 연동** — human_label RDS 컬럼은 backend-connected이나, 재정의 3-5는 detection 측 쓰기(CLI)까지만. `DetectionResponse.humanLabel` 노출 + 목록 `humanLabel` 필터 + 대시보드 인-앱 라벨링 UI는 **Epic 4 follow-up**. CLI 라벨링이 운영 부담이 되면 우선순위 상향.

## Deferred from: Epic 3 멀티 에이전트 재정의 (2026-06-11 — Correct Course)

단일 호출 → 비용 차등 멀티 에이전트 재정의(`sprint-change-proposal-2026-06-11.md`). 본 기수 범위는 에이전트 골격(3-7) + 심층 경로(3-8) + A/B·리허설(3-9) + T1 알림(3-10). 아래는 의도적으로 본 기수에서 제외하고 미래로 이월한 항목.

- **multi-hop 링크 추적** — 본 기수는 **1-hop fetch만**(FR12-B). 링크 페이지에서 발견한 추가 링크를 다시 따라가는 multi-hop은 anti-bot·SSRF 표면 확대 + 안전·법무 리스크 + 타임라인 사유로 제외. LinkTracer가 수집한 2차 링크는 증거(`indicators`)로만 기록하고 추적하지 않는다. 1-hop 운영 데이터로 가치가 확인되면 depth-제한 multi-hop을 별도 스토리로 승격. [연결: 3-7 LinkTracer]
- **사람 리뷰 큐 (human-in-the-loop)** — PRD § 탐지 오류 관리: "T1 오탐이 무고한 사용자에게 알림 가는 걸 막으려 운영자 승인 후 발송." 현재 백엔드 알림 시스템(`NotificationEventProcessor`)은 룰 매칭 시 **즉시 발송**하며 승인 단계가 없다. 승인 워크플로우는 (a) 발송 보류 상태 + (b) 프론트 승인/거부 UI + (c) 승인 후 dispatch 분기 신설이 필요 — 현 즉시 발송 설계와 충돌하므로 별도 설계 스토리. 데모에는 불필요(룰로 T1 즉시 발송으로 충분). [Source: PRD § 탐지 오류 관리, 구 Story 3.6/3.10]
- **T2 일일 다이제스트 / T3 주간 리포트 알림** — FR16-NEW-2 중 T2/T3 알림. 현재 백엔드 알림 룰은 `send_mode=IMMEDIATE`만 지원(`notification_rules` CHECK 제약). 다이제스트/주간 배치 발송은 `send_mode` 확장 + 스케줄러 추가가 필요한 미래 스토리. T1 즉시 알림은 기존 시스템으로 이미 동작. [Source: epics.md#Story 3.6 이력 AC, V7__notification_outbox.sql]
- **Tier별 90일 retention archive job** — 구 Story 3-6의 FR16-NEW-3. `retention/tier_retention_job.py`(T2·T3·T4 90일 후 S3 archive 이동 + `detections.archived_at` + Flyway V_retention) 미구현. 크롤 볼륨이 낮아 보존 기간 내 폐기 압력이 없어 전수 저장만 유지. 운영 데이터 누적으로 저장 부담 발생 시 승격. [Source: epics.md#Story 3.6 이력 AC, PRD FR16-NEW-3]
- **few-shot 프롬프트 주입 (Stage 2-B) — 재확인** — 멀티 에이전트 재정의에서도 여전히 defer. S1 TriageAgent 프롬프트에 Story 3-5 코퍼스를 정적 주입하는 것은 시간 여유 시 stretch goal(3-9 이후). 위 "Story 3-5 재정의" 항목과 동일 작업이며, 주입 지점이 `build_system_prompt()` Stage 2-B에서 트리아지 에이전트 프롬프트로 이동했다는 점만 갱신.
- **대시보드 증거 패널 (agent_runs 노출)** — `agent_runs`(V10)의 스테이지별 trace(링크 fetch 결과·이미지 판독 근거·스테이지 비용)를 탐지 상세 화면에 보여주는 UI는 **Epic 4 follow-up**. 본 기수는 trace를 RDS에 기록만 하고 대시보드는 기존 detections 5필드만 표시(계약 불변). 데모에서 "왜 불법으로 판정했는가"의 증거 추적성을 보여주려면 우선순위 상향 검토.
- **링크 fetch JS 렌더링** — LinkTracer는 httpx + html2text(정적 HTML)만. JS 실행이 필요한 SPA형 배포 페이지는 본문 수집 불가(제목·메타데이터만). crawl4ai/Chromium 도입은 detection 컨테이너 부담 + 안전 리스크로 제외. 정적 fetch로 놓치는 비율이 높으면 별도 headless fetch 트랙 검토.
- **재시도 시 stage 결과 재사용 캐시** — RetryHandler가 메시지 단위로 재시도할 때 이미 완료된 LLM stage 결과를 Redis(`agentrun:{post_id}` TTL 1h)에 캐시해 비용 중복을 막는 최적화. 3-8 stretch. 미구현 시 재시도가 전 stage를 재호출하나, 큐 볼륨이 낮아 비용 영향 제한적.

## Deferred from: code review of story 3-7 (2026-06-11)

3-layer 적대적 코드 리뷰(Blind Hunter / Edge Case Hunter / Acceptance Auditor)에서 defer 분류된 항목.

- **LinkTracer 규칙 판정 불가 시 gpt-4o-mini 요약 fallback 미구현** — Task 7 명세는 "page_title+발췌 텍스트가 규칙으로 판정 불가할 때만 mini 요약 호출"을 절충안으로 포함했으나, 현 규칙 엔진(`_detect_indicators`)은 항상 boolean 판정을 산출해 "판정 불가" 트리거 조건 자체가 정의되지 않음. 3-8 Synthesizer가 link_trace 증거를 소비하는 설계와 함께 결정(증거 품질이 부족하면 그때 mini 요약 추가). [연결: 3-7 link_tracer.py `_detect_indicators`]
- **DNS rebinding TOCTOU 잔여 리스크 (IP 핀 미적용)** — `validate_url()`이 해석한 IP와 httpx가 fetch 시 재해석하는 IP가 다를 수 있음(rebinding 윈도우). 코드 docstring에 2차 방어(fetch 직전 재검증)로 문서화된 설계 결정. 보완 옵션: (a) 해석 IP로 직접 접속하는 IP-핀 custom transport + Host 헤더 유지, (b) 운영 `LINK_TRACE_PROXY` egress 프록시에서 사설망 차단 정책. 운영 배포 전 (b) 권장. [연결: 3-7 link_fetch_guard.py `validate_url`]
