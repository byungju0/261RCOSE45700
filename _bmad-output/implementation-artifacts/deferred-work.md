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

## Deferred from: code review (2026-04-28)

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
