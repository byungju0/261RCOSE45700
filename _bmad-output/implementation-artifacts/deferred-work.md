# Deferred Work

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
- **3-column 레이아웃 모바일 breakpoint 부재** [layouts/RootLayout.tsx:20] — sidebar 240px + rail 240px 고정으로 ~600px 미만에서 main 압착. desktop-only 전제 명시 또는 < lg 에서 rail 드로어화 필요.

## Deferred from: code review of 1-3-로컬-개발-환경-구성 (2026-04-29)

- **redis/postgres `healthcheck:` 블록 미정의** [infra/docker-compose.yml] — `up -d` 직후 컨테이너가 Listening 되기 전 의존 서비스 부팅 시 race. Story 1.4 Flyway 마이그레이션이 `service_healthy` condition을 요구하므로 그때 일괄 추가.
- **VARCO_API_KEY required-var 가드 부재** [infra/.env.example, infra/docker-compose.yml] — placeholder `your-varco-api-key-here`가 그대로 사용되면 런타임 401로 fail. crawler/detection 컨테이너 추가 시 해당 서비스 environment에 `${VARCO_API_KEY:?}` 부착.
- **postgres `/docker-entrypoint-initdb.d` 마운트 슬롯 미예약** [infra/docker-compose.yml] — Story 1.4에서 `pg_trgm`/`uuid-ossp` 등 extension 필요 시 Flyway baseline에 포함하거나 initdb 마운트 추가 결정 필요.
