# Story 1.4: Flyway DB 초기 스키마 및 VARCO Mock 서버 구축

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

개발자로서,
PostgreSQL 스키마와 VARCO API Mock 서버가 준비되기를 원한다,
그래서 실제 DB와 외부 API 없이도 AI 탐지 파이프라인을 개발하고 테스트할 수 있다.

## Acceptance Criteria

1. **Given** PostgreSQL이 로컬에서 실행 중일 때 **When** Spring Boot 애플리케이션이 시작되면 **Then** Flyway가 `V1__init_schema.sql`을 실행하여 `sources`, `posts`, `post_images`, `detections` 4개 테이블을 생성한다
2. `V2__add_indexes.sql`이 `CREATE INDEX idx_detections_filter ON detections (detected_at DESC, type, confidence DESC)`를 생성한다
3. `V3__add_unique_detection.sql`이 `detections` 테이블에 `(post_id, model_version)` unique constraint를 추가한다
4. `detection/src/mocks/varco_mock.py`가 `shared/interfaces/varco.py`의 `VarcoInterface` Protocol을 구현하며 `translate()`, `classify()` 응답을 `tests/fixtures/varco/` JSON 파일에서 로드한다
5. `tests/fixtures/varco/`에 `mock_response_illegal.json`, `mock_response_clean.json`, `mock_response_rate_limited.json`, `mock_response_timeout.json` 4개 파일이 제공된다
6. `tests/fixtures/html/`에 `sample_illegal_post.html`, `sample_clean_post.html`이 제공된다
7. `tests/fixtures/labels/manual_label_set_v1.csv`에 ≥200건의 수동 라벨셋(`post_id`, `text`, `label`, `type`)이 포함된다

## Tasks / Subtasks

- [x] **Task 1: Flyway 의존성 추가 및 application.properties 설정** (AC: #1)
  - [x] 1.1 `api/build.gradle`에 Flyway 의존성 추가 (`flyway-core`, `flyway-database-postgresql`)
  - [x] 1.2 `api/src/main/resources/application.properties`에 DataSource + Flyway 설정 추가 (env var 참조)
  - [x] 1.3 `api/src/test/resources/application-test.properties` 생성 — H2 in-memory + `spring.flyway.enabled=false`

- [x] **Task 2: Flyway 마이그레이션 SQL 작성** (AC: #1, #2, #3)
  - [x] 2.1 `api/src/main/resources/db/migration/V1__init_schema.sql` 작성 — `sources`, `posts`, `post_images`, `detections` 4개 테이블
  - [x] 2.2 `api/src/main/resources/db/migration/V2__add_indexes.sql` 작성 — `idx_detections_filter` + `idx_posts_source_id`
  - [x] 2.3 `api/src/main/resources/db/migration/V3__add_unique_detection.sql` 작성 — `UNIQUE(post_id, model_version)` constraint

- [x] **Task 3: VARCO Mock 서버 구현** (AC: #4)
  - [x] 3.1 `detection/src/mocks/varco_mock.py` 작성 — `VarcoInterface` 구현, JSON fixture 로드, `simulate_latency()` 지원
  - [x] 3.2 `rate_limited`·`timeout` 모드에서 예외 발생 동작 구현

- [x] **Task 4: 테스트 픽스처 생성** (AC: #5, #6, #7)
  - [x] 4.1 `tests/fixtures/varco/mock_response_illegal.json` 작성
  - [x] 4.2 `tests/fixtures/varco/mock_response_clean.json` 작성
  - [x] 4.3 `tests/fixtures/varco/mock_response_rate_limited.json` 작성
  - [x] 4.4 `tests/fixtures/varco/mock_response_timeout.json` 작성
  - [x] 4.5 `tests/fixtures/html/sample_illegal_post.html` 작성 (중국어 불법 게시글 샘플)
  - [x] 4.6 `tests/fixtures/html/sample_clean_post.html` 작성 (중국어 일반 게시글 샘플)
  - [x] 4.7 `tests/fixtures/labels/manual_label_set_v1.csv` 작성 — ≥200건, 헤더: `post_id,text,label,type`

- [x] **Task 5: 검증 및 마무리** (AC: #1~#7)
  - [x] 5.1 `docker compose -f infra/docker-compose.yml up -d` 후 Spring Boot 기동 → Flyway 마이그레이션 3개 성공 확인
  - [x] 5.2 `psql -U tracker_user -d tracker -c "\dt"` → 4개 테이블 목록 확인
  - [x] 5.3 Python에서 `from detection.src.mocks.varco_mock import VarcoMock` import 확인
  - [x] 5.4 변경 파일 목록 File List에 기록
  - [x] 5.5 sprint-status.yaml `1-4-flyway-db-초기-스키마-및-varco-mock-서버-구축` 상태 `review`로 업데이트

### Review Findings

- [x] [Review][Patch] Postgres healthcheck ignores overridden DB_USER/DB_NAME [`infra/docker-compose.yml:35`]
- [x] [Review][Patch] Detection confidence accepts invalid values outside 0..1 [`api/src/main/resources/db/migration/V1__init_schema.sql:40`]
- [x] [Review][Patch] VarcoMock reports unsupported mode as fixture FileNotFoundError [`detection/src/mocks/varco_mock.py:22`]
- [x] [Review][Patch] Manual label CSV uses CRLF, causing `git diff --check` trailing-whitespace failures [`tests/fixtures/labels/manual_label_set_v1.csv:1`]

## Dev Notes

### 브랜치 전략

- **브랜치:** `feat/1-4` (현재 브랜치 `feat/1-3`에서 분기)
- **PR 타겟:** `feat/1-3` (stacked PR 방식)
- `feat/1-3` → `main` PR이 머지된 후 `feat/1-4` → `main`으로 리베이스 예정

### 이번 스토리 범위 (Scope Boundary)

| 이번 스토리에서 한다 | 이번 스토리에서 **하지 않는다** |
|---|---|
| Flyway V1/V2/V3 마이그레이션 SQL | JPA Entity 클래스 (Story 4.1에서 생성) |
| `detection/src/mocks/varco_mock.py` | 실제 VARCO API 연동 (`translate.py`, `llm_classifier.py`) |
| `tests/fixtures/` 4종 JSON + 2종 HTML + CSV | `detection/tests/` 단위·통합 테스트 (Story 3.x) |
| `application.properties` DataSource + Flyway 설정 | GitHub Actions 워크플로우 (Story 1.5) |
| `application-test.properties` (H2 + Flyway 비활성화) | Prometheus/Grafana 설정 (Story 5.1) |

### Task 1 상세: Flyway 의존성 및 설정

#### build.gradle 추가 (api/build.gradle)

```groovy
dependencies {
    // ... 기존 의존성 유지 ...
    implementation 'org.flywaydb:flyway-core'
    implementation 'org.flywaydb:flyway-database-postgresql'  // Spring Boot 3.x + Flyway 10.x 필수
}
```

**주의:** Spring Boot 3.5.0은 Flyway 10.x를 기본 사용. Flyway 10+부터 DB별 드라이버 모듈 분리됨 → `flyway-database-postgresql` 없으면 `FlywayException: No database found` 오류 발생.

#### application.properties (api/src/main/resources/application.properties)

```properties
spring.application.name=tracker-api

# DataSource — infra/.env.example 환경변수 참조
spring.datasource.url=jdbc:postgresql://${DB_HOST:localhost}:${DB_HOST_PORT:5432}/${DB_NAME:tracker}
spring.datasource.username=${DB_USER:tracker_user}
spring.datasource.password=${DB_PASSWORD}
spring.datasource.driver-class-name=org.postgresql.Driver

# JPA
spring.jpa.database-platform=org.hibernate.dialect.PostgreSQLDialect
spring.jpa.hibernate.ddl-auto=validate

# Flyway
spring.flyway.enabled=true
spring.flyway.locations=classpath:db/migration
spring.flyway.baseline-on-migrate=false
```

**`ddl-auto=validate`:** Flyway가 스키마를 관리하므로 Hibernate가 테이블을 수정하지 않도록 `validate` 사용. `create-drop`·`update` 절대 금지.

#### application-test.properties (api/src/test/resources/application-test.properties) — 신규 생성

```properties
# H2 in-memory — 단위 테스트 전용 (Flyway SQL이 PostgreSQL 문법이라 H2에서 실행 불가)
spring.datasource.url=jdbc:h2:mem:testdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.jpa.database-platform=org.hibernate.dialect.H2Dialect
spring.jpa.hibernate.ddl-auto=create-drop

# Flyway 비활성화 — PostgreSQL 전용 SQL이므로 H2에서 실행 안 함
spring.flyway.enabled=false
```

**`@SpringBootTest`에서 프로파일 활성화:** `TrackerApiApplicationTests`에 `@ActiveProfiles("test")` 추가 필요.

### Task 2 상세: Flyway SQL 스키마

#### V1__init_schema.sql

```sql
-- sources: 크롤링 대상 커뮤니티 사이트
CREATE TABLE sources (
    id          BIGSERIAL PRIMARY KEY,
    site_name   VARCHAR(50)  NOT NULL,
    board_name  VARCHAR(200),
    base_url    VARCHAR(500) NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- posts: 크롤링된 게시글
CREATE TABLE posts (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           BIGINT       NOT NULL REFERENCES sources(id),
    post_id_at_source   VARCHAR(200) NOT NULL,
    title               TEXT,
    body                TEXT,
    author              VARCHAR(200),
    post_url            VARCHAR(1000) NOT NULL,
    language            VARCHAR(10),
    crawled_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (source_id, post_id_at_source)
);

-- post_images: 게시글 첨부 이미지
CREATE TABLE post_images (
    id          BIGSERIAL PRIMARY KEY,
    post_id     BIGINT        NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    image_url   VARCHAR(1000) NOT NULL,
    s3_key      VARCHAR(500),
    image_hash  VARCHAR(64),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- detections: VARCO AI 탐지 결과
CREATE TABLE detections (
    id            BIGSERIAL PRIMARY KEY,
    post_id       BIGINT        NOT NULL REFERENCES posts(id),
    is_illegal    BOOLEAN       NOT NULL,
    type          VARCHAR(50),
    confidence    DOUBLE PRECISION NOT NULL,
    reason        TEXT,
    model_version VARCHAR(50)   NOT NULL,
    detected_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

**`type` 허용값 (앱 레이어에서 검증):** `매크로_판매`, `핵_배포`, `계정_거래`, `리세마라`, `기타`. PostgreSQL CHECK constraint는 나중에 추가 가능하나 현재 AC 범위 외.

**`BIGSERIAL`:** PostgreSQL 전용. H2 호환이 필요하면 `GENERATED BY DEFAULT AS IDENTITY` 사용 가능하나 이 프로젝트는 PostgreSQL only이므로 BIGSERIAL 사용.

#### V2__add_indexes.sql

```sql
-- GET /detections 필터(날짜·유형·신뢰도) p95 ≤ 500ms NFR 충족 — architecture.md 명시
CREATE INDEX idx_detections_filter ON detections (detected_at DESC, type, confidence DESC);

-- posts.source_id FK 인덱스 — architecture.md idx_posts_source_id 명시
CREATE INDEX idx_posts_source_id ON posts (source_id);
```

#### V3__add_unique_detection.sql

```sql
-- DLQ 재처리 시 중복 삽입 방지 — architecture.md 멱등성 보장 항목
ALTER TABLE detections
    ADD CONSTRAINT uq_detection_post_model UNIQUE (post_id, model_version);
```

**파일명 규칙 필수:** `V{순번}__{설명}.sql` — 언더스코어 **2개**. `V1_init.sql` (언더스코어 1개)는 Flyway가 인식 못함.

### Task 3 상세: VARCO Mock 구현

#### detection/src/mocks/varco_mock.py

```python
from __future__ import annotations

import json
import time
from pathlib import Path

from shared.interfaces.varco import ClassificationResult, VarcoInterface

_FIXTURES = Path(__file__).parents[4] / "tests" / "fixtures" / "varco"


class RateLimitError(Exception):
    def __init__(self, retry_after: int = 30):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class VarcoMock:
    """VarcoInterface Protocol 구현체 — 통합 테스트 전용"""

    def __init__(self, mode: str = "clean", latency_ms: int = 0) -> None:
        # mode: "illegal" | "clean" | "rate_limited" | "timeout"
        self._mode = mode
        self._latency_ms = latency_ms
        self._data: dict = self._load(mode)

    def _load(self, mode: str) -> dict:
        path = _FIXTURES / f"mock_response_{mode}.json"
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def simulate_latency(self, ms: int) -> None:
        self._latency_ms = ms

    def _sleep(self) -> None:
        if self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000)

    def translate(self, text: str) -> str:
        self._sleep()
        if self._mode == "rate_limited":
            raise RateLimitError(self._data.get("retry_after_seconds", 30))
        if self._mode == "timeout":
            raise TimeoutError("VARCO API timeout")
        return self._data.get("translated_text", text)

    def classify(self, text: str) -> ClassificationResult:
        self._sleep()
        if self._mode == "rate_limited":
            raise RateLimitError(self._data.get("retry_after_seconds", 30))
        if self._mode == "timeout":
            raise TimeoutError("VARCO API timeout")
        c = self._data["classification"]
        return ClassificationResult(
            is_illegal=c["is_illegal"],
            type=c["type"],
            confidence=c["confidence"],
            reason=c["reason"],
        )
```

**중요:** `VarcoMock`은 `VarcoInterface` Protocol의 structural subtype. `isinstance(VarcoMock(), VarcoInterface)` → True (`@runtime_checkable` 덕분). `class VarcoMock(VarcoInterface):` 상속 불필요 (Protocol은 ABC 아님).

**경로 계산:** `_FIXTURES = Path(__file__).parents[4] / "tests" / "fixtures" / "varco"` — `varco_mock.py`가 `detection/src/mocks/`에 위치하므로 `.parents[4]`는 프로젝트 루트. 실제 깊이 확인 필수.
- `varco_mock.py` → `parents[0]` = `detection/src/mocks/`
- `parents[1]` = `detection/src/`
- `parents[2]` = `detection/`
- `parents[3]` = 프로젝트 루트

따라서 `.parents[3]`이 맞음. 코드에서 수정 필요.

### Task 4 상세: 테스트 픽스처 파일 형식

#### tests/fixtures/varco/mock_response_illegal.json

```json
{
  "translated_text": "대리 레벨업 서비스 제공합니다. 프리스타일 풋볼 계정 모든 서버 가능. KakaoTalk: macro_seller_2024",
  "classification": {
    "is_illegal": true,
    "type": "매크로_판매",
    "confidence": 0.95,
    "reason": "게시글에 매크로 프로그램을 이용한 대리 레벨업 서비스 판매 광고가 포함되어 있습니다. 연락처 및 가격 정보가 명시됨."
  }
}
```

#### tests/fixtures/varco/mock_response_clean.json

```json
{
  "translated_text": "안녕하세요, 프리스타일 풋볼 신규 패치 내용 공유합니다. 새로운 스킬 추가 및 밸런스 조정이 있었습니다.",
  "classification": {
    "is_illegal": false,
    "type": "기타",
    "confidence": 0.92,
    "reason": "정상적인 게임 정보 공유 게시글입니다. 판매·광고·불법 행위 관련 내용 없음."
  }
}
```

#### tests/fixtures/varco/mock_response_rate_limited.json

```json
{
  "error": "rate_limit_exceeded",
  "retry_after_seconds": 30
}
```

#### tests/fixtures/varco/mock_response_timeout.json

```json
{
  "error": "timeout",
  "latency_ms": 30000
}
```

#### tests/fixtures/html/sample_illegal_post.html

중국어 불법 게시글 샘플 HTML. 최소 구조:
```html
<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8"><title>测试帖子</title></head>
<body>
  <div class="post-title">出售宏程序，全服代练</div>
  <div class="post-body">
    提供Freestyle Football账号代练服务，所有服务器均可。
    支持宏程序自动得分。联系方式：macro_seller_2024
    价格：100元/小时
  </div>
  <div class="post-author">user_123</div>
  <div class="post-date">2026-04-01</div>
</body>
</html>
```

#### tests/fixtures/html/sample_clean_post.html

정상 게시글 HTML (유사 구조, 불법 내용 없음).

#### tests/fixtures/labels/manual_label_set_v1.csv

**헤더:** `post_id,text,label,type`
- `label`: `illegal` 또는 `clean`
- `type`: `매크로_판매`, `핵_배포`, `계정_거래`, `리세마라`, `기타`, `(clean 시 빈 문자열)`

**최소 200행** — 분포 권고 (Murat 품질 게이트, Story 3.5 precision ≥ 0.80 달성 기준):
- `illegal`: ≥100건 (유형별 20건 이상: 매크로_판매/핵_배포/계정_거래/리세마라/기타)
- `clean`: ≥100건

합성 데이터 생성 방법 (개발자가 수행):

```python
# tests/fixtures/labels/generate_labels.py — 실행 후 CSV 생성, 스크립트 자체는 커밋 불필요
import csv, random

labels = []
illegal_types = ["매크로_판매", "핵_배포", "계정_거래", "리세마라", "기타"]

# 불법 100건
for i in range(100):
    t = illegal_types[i % len(illegal_types)]
    labels.append((f"post_{i+1:04d}", f"Synthetic illegal text {i+1} [{t}]", "illegal", t))

# 정상 100건
for i in range(100):
    labels.append((f"post_{i+101:04d}", f"Synthetic clean text {i+1}", "clean", ""))

random.shuffle(labels)

with open("tests/fixtures/labels/manual_label_set_v1.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["post_id", "text", "label", "type"])
    w.writerows(labels)
```

**주의:** 합성 데이터는 Story 1.4 구조 검증용. 실제 탐지 정확도(Story 3.5 precision ≥ 0.80)는 실제 중국어 커뮤니티 게시글 수동 라벨링으로 교체 필요.

### Story 1.3 이어받기 (Previous Story Intelligence)

**인프라 전제조건:** Story 1.3 산출물 (`infra/docker-compose.yml`)로 PostgreSQL 컨테이너가 이미 구성됨. DB host=127.0.0.1, port=${DB_HOST_PORT:-5432}, name=tracker, user=tracker_user.

**Story 1.3 Review Deferred 항목:**
- `healthcheck:` 블록 → **이번 스토리에서 추가** (Spring Boot가 PostgreSQL 준비 전 시작하면 Flyway 실패). V1 실행 전 DB 연결 확보 필요.
  ```yaml
  # infra/docker-compose.yml postgres 서비스에 추가 권고
  healthcheck:
    test: ["CMD", "pg_isready", "-U", "tracker_user", "-d", "tracker"]
    interval: 5s
    timeout: 3s
    retries: 5
  ```
  단, docker-compose.yml 수정은 Story 1.3 범위지만 Flyway 안정 기동에 필요하므로 이번 스토리 범위에 포함.

**`infra/.env.example`의 `DB_PASSWORD`:** 실제 `.env` 파일에서 `DB_PASSWORD`를 설정해야 Spring Boot 기동 가능. `application.properties`에서 `${DB_PASSWORD}` default 없이 참조 → `.env` 없으면 기동 실패. 개발자가 `infra/.env` 파일을 직접 생성해야 함.

### 기존 코드 재사용 필수

- `shared/interfaces/varco.py` — **이미 존재**. `VarcoInterface` Protocol과 `ClassificationResult` dataclass 정의됨. 재정의 금지.
  - `translate(self, text: str) -> str`
  - `classify(self, text: str) -> ClassificationResult`
- `detection/src/__init__.py` — 존재 확인 완료
- `tests/fixtures/varco/`, `tests/fixtures/html/`, `tests/fixtures/labels/` — **디렉터리 존재** (비어있음). 새 디렉터리 생성 불필요.

### Anti-Patterns to Avoid

1. ❌ **`V1.sql` 파일명** — 언더스코어 1개. Flyway가 버전 파싱 실패. 반드시 `V1__init_schema.sql` (더블 언더스코어).
2. ❌ **`spring.jpa.hibernate.ddl-auto=create` 또는 `update`** — Flyway와 충돌. `validate` 사용.
3. ❌ **`flyway-database-postgresql` 누락** — Spring Boot 3.x + Flyway 10+에서 PostgreSQL 드라이버 모듈 필수. 누락 시 `No database found to handle jdbc:postgresql://` 오류.
4. ❌ **V3에서 V1 없이 실행 시도** — Flyway는 버전 순 실행. V1 → V2 → V3 순. V3에만 `ALTER TABLE` 작성 가능.
5. ❌ **VarcoMock을 VarcoInterface ABC처럼 상속** — `VarcoInterface`는 `Protocol`이므로 명시적 상속 불필요. Structural subtyping.
6. ❌ **`tests/fixtures/` 내 Python 코드 커밋** — 생성 스크립트는 실행 후 삭제. CSV/HTML/JSON 결과만 커밋.
7. ❌ **`application.properties`에 `DB_PASSWORD` 기본값 하드코딩** — NFR5 위반. `${DB_PASSWORD}` (기본값 없음) 사용.

### 검증 명령

```bash
# 1. PostgreSQL 컨테이너 기동 (Story 1.3 구성)
docker compose -f infra/docker-compose.yml up -d postgres

# 2. infra/.env 생성 (gitignore 대상)
cp infra/.env.example infra/.env
# .env에서 DB_PASSWORD 설정 필요

# 3. Spring Boot 기동 → Flyway 자동 실행
cd api && ./gradlew bootRun

# 4. 마이그레이션 확인
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U tracker_user -d tracker -c "\dt"
# 예상: sources, posts, post_images, detections 4개 테이블

# 5. flyway_schema_history 확인
docker compose -f infra/docker-compose.yml exec postgres \
  psql -U tracker_user -d tracker \
  -c "SELECT version, description, success FROM flyway_schema_history;"
# 예상: V1, V2, V3 모두 success=true

# 6. Python mock import 검증 (프로젝트 루트에서)
python -c "from detection.src.mocks.varco_mock import VarcoMock, RateLimitError; m = VarcoMock('illegal'); print(m.classify('test'))"
```

### 프로젝트 구조 (이번 스토리 생성 파일)

```
api/
├── build.gradle                                    # flyway-core + flyway-database-postgresql 추가
└── src/
    ├── main/resources/
    │   ├── application.properties                  # DataSource + Flyway 설정
    │   └── db/migration/
    │       ├── V1__init_schema.sql                 ✅ 이번 스토리
    │       ├── V2__add_indexes.sql                 ✅ 이번 스토리
    │       └── V3__add_unique_detection.sql        ✅ 이번 스토리
    └── test/resources/
        └── application-test.properties             ✅ 이번 스토리 (H2 + Flyway 비활성화)

detection/
└── src/
    └── mocks/
        └── varco_mock.py                           ✅ 이번 스토리

tests/fixtures/
├── varco/
│   ├── mock_response_illegal.json                  ✅ 이번 스토리
│   ├── mock_response_clean.json                    ✅ 이번 스토리
│   ├── mock_response_rate_limited.json             ✅ 이번 스토리
│   └── mock_response_timeout.json                  ✅ 이번 스토리
├── html/
│   ├── sample_illegal_post.html                    ✅ 이번 스토리
│   └── sample_clean_post.html                      ✅ 이번 스토리
└── labels/
    └── manual_label_set_v1.csv                     ✅ 이번 스토리 (≥200행)

infra/
└── docker-compose.yml                              # postgres healthcheck 추가 (선택적)
```

### References

- [Epic 1.4 AC](/_bmad-output/planning-artifacts/epics.md#L246-L262) — 본 스토리의 Source of Truth
- [Architecture: Flyway 결정 근거](/_bmad-output/planning-artifacts/architecture.md#L186) — `V{n}__{description}.sql` 파일명 규칙
- [Architecture: VARCO Mock 필수성](/_bmad-output/planning-artifacts/architecture.md#L66) — Week 1-2 필수 구축
- [Architecture: 멱등성 보장](/_bmad-output/planning-artifacts/architecture.md#L68) — `(post_id, model_version)` unique constraint
- [Architecture: RDS 인덱스 전략](/_bmad-output/planning-artifacts/architecture.md#L187) — `idx_detections_filter` GET /detections p95 ≤ 500ms
- [Architecture: 프로젝트 디렉터리 구조](/_bmad-output/planning-artifacts/architecture.md#L551-L554) — db/migration 경로
- [Architecture: Day 1 필수 산출물](/_bmad-output/planning-artifacts/architecture.md#L229-L231) — Flyway init.sql, varco_mock.py
- [shared/interfaces/varco.py](shared/interfaces/varco.py) — **기존 Protocol 계약** (재정의 금지)
- [Story 1.3 Review Deferred](/_bmad-output/implementation-artifacts/1-3-로컬-개발-환경-구성.md#L258-L260) — healthcheck 추가 예정 항목

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6 — BMad `create-story` workflow

### Debug Log References

### Completion Notes List

- Task 1: build.gradle에 flyway-core + flyway-database-postgresql 추가, application.properties DataSource + Flyway 설정, application-test.properties(H2+Flyway 비활성화) 신규 생성, TrackerApiApplicationTests @ActiveProfiles("test") 추가
- Task 2: V1__init_schema.sql(4개 테이블: sources/posts/post_images/detections), V2__add_indexes.sql(idx_detections_filter + idx_posts_source_id), V3__add_unique_detection.sql(UNIQUE(post_id, model_version)) 작성
- Task 3: detection/src/mocks/varco_mock.py — VarcoInterface Protocol 구현(structural subtyping), JSON fixture 로드, simulate_latency(), RateLimitError/TimeoutError 예외 발생, parents[3] 경로 사용(올바른 프로젝트 루트)
- Task 4: 4종 JSON fixture(illegal/clean/rate_limited/timeout) + 2종 HTML fixture(중국어 불법/정상 게시글) + CSV 200행(illegal 100건×5유형 + clean 100건) 생성
- Task 5: `./gradlew test` 통과(H2 + @ActiveProfiles("test")), Python import 검증(VarcoMock, RateLimitError, TimeoutError 모두 정상), infra/docker-compose.yml postgres healthcheck 추가
- 검증: `isinstance(VarcoMock(), VarcoInterface)` → True 확인

### File List

- `api/build.gradle` — flyway-core, flyway-database-postgresql 의존성 추가
- `api/src/main/resources/application.properties` — DataSource + Flyway 설정
- `api/src/main/resources/db/migration/V1__init_schema.sql` — 신규: sources/posts/post_images/detections 테이블
- `api/src/main/resources/db/migration/V2__add_indexes.sql` — 신규: idx_detections_filter, idx_posts_source_id
- `api/src/main/resources/db/migration/V3__add_unique_detection.sql` — 신규: UNIQUE(post_id, model_version)
- `api/src/test/resources/application-test.properties` — 신규: H2 + Flyway 비활성화
- `api/src/test/java/com/tracker/api/TrackerApiApplicationTests.java` — @ActiveProfiles("test") 추가
- `detection/src/mocks/__init__.py` — 신규: 패키지 초기화
- `detection/src/mocks/varco_mock.py` — 신규: VarcoInterface 구현체
- `tests/fixtures/varco/mock_response_illegal.json` — 신규
- `tests/fixtures/varco/mock_response_clean.json` — 신규
- `tests/fixtures/varco/mock_response_rate_limited.json` — 신규
- `tests/fixtures/varco/mock_response_timeout.json` — 신규
- `tests/fixtures/html/sample_illegal_post.html` — 신규: 중국어 불법 게시글 샘플
- `tests/fixtures/html/sample_clean_post.html` — 신규: 중국어 정상 게시글 샘플
- `tests/fixtures/labels/manual_label_set_v1.csv` — 신규: 200행(illegal 100 + clean 100)
- `infra/docker-compose.yml` — postgres healthcheck 추가
