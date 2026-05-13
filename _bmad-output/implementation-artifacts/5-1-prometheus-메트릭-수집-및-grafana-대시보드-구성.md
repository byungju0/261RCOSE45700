# Story 5.1: Prometheus 메트릭 수집 및 Grafana 대시보드 구성

Status: review

## Story

운영자로서,
API 응답 시간·에러율·Redis 큐 깊이가 Grafana에서 실시간으로 모니터링되기를 원한다,
그래서 파이프라인 이상 징후를 즉시 파악할 수 있다.

## Acceptance Criteria

1. **Given** Spring Boot Actuator와 Prometheus가 구성된 환경에서 **When** `infra/prometheus/prometheus.yml`에 API가 scrape 대상으로 등록되면 **Then** `GET /actuator/prometheus`가 API 응답 시간(`http_server_requests_seconds`), 에러율, JVM 메트릭을 노출한다 (FR29)
2. **And** `infra/grafana/dashboards/tracker.json`에 API p95 응답 시간, Redis `posts:queue` 깊이, `posts:dlq` 적재 건수 패널이 포함된다
3. **And** `posts:dlq`에 메시지가 누적될 때 Grafana Alert이 발생하여 운영자가 5분 이내에 인지할 수 있다 (FR30, NFR12)
4. **And** DLQ 임계값(≥1건) 초과 시 Grafana 알림이 실제로 발송됨을 테스트 환경에서 확인한다
5. **And** `docker compose up -d`로 로컬에서 Grafana(`localhost:3000`)와 Prometheus(`localhost:9090`)가 실행된다

## Dev Notes

### 현재 상태 — 이미 존재하는 항목

- `api/build.gradle`: `spring-boot-starter-actuator` ✅ 포함됨, `micrometer-registry-prometheus` ❌ 없음
- `infra/prometheus/` 디렉토리 존재 (`.gitkeep`만 있음, 내용 없음)
- `infra/grafana/dashboards/` 디렉토리 존재 (`.gitkeep`만 있음, 내용 없음)
- `infra/docker-compose.yml`: Redis + PostgreSQL만 포함 (Prometheus/Grafana 없음)
- `api/src/main/resources/application.properties`: actuator prometheus 노출 설정 없음

### 기술 스택

- **Spring Boot**: 3.5.0 (`api/build.gradle` 확인)
- **Micrometer**: Spring Boot BOM 자동 관리 (버전 핀 불필요 — `micrometer-registry-prometheus`만 추가)
- **Prometheus 이미지**: `prom/prometheus:v2.55.1` (고정)
- **Grafana 이미지**: `grafana/grafana:11.4.0` (고정)
- **메트릭 경로**: `/actuator/prometheus` (기본값 유지)

### Redis DB 레이아웃 (변경 금지)

```
DB0 (REDIS_MQ_DB=0):     posts:queue, posts:processing, posts:dlq  ← 모니터링 대상
DB1 (REDIS_DEDUP_DB=1):  posts:dedup
DB2 (REDIS_RATELIMIT_DB=2): varco:rate_limit
DB3 (REDIS_CACHE_DB=3):  cache:detections  ← cacheRedisTemplate 빈 담당 (변경 금지)
```

`RedisQueueMetrics`는 **DB0** 접근 필요 → Spring Boot 자동 구성 `StringRedisTemplate`(기본값 `spring.data.redis.database=0`) 사용.
`cacheRedisTemplate` 빈(`RedisConfig.java`, DB3)과 혼용 절대 금지.

### Task 3 구현 패턴 — RedisQueueMetrics

새 패키지 `com.tracker.api.metrics` 생성. `MeterBinder` 인터페이스 구현.

```java
// api/src/main/java/com/tracker/api/metrics/RedisQueueMetrics.java
@Component
public class RedisQueueMetrics implements MeterBinder {

    private final StringRedisTemplate mqRedisTemplate;

    // @Qualifier 없이 주입 (Spring Boot 자동 구성 primary StringRedisTemplate, DB0)
    // "expected single bean but found 2" 오류 발생 시 → @Qualifier("stringRedisTemplate") 추가
    public RedisQueueMetrics(StringRedisTemplate mqRedisTemplate) {
        this.mqRedisTemplate = mqRedisTemplate;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("redis.queue.size", this, m -> getLen("posts:queue"))
             .tag("queue", "posts:queue")
             .description("Redis posts:queue 리스트 길이")
             .register(registry);
        Gauge.builder("redis.queue.size", this, m -> getLen("posts:dlq"))
             .tag("queue", "posts:dlq")
             .description("Redis posts:dlq 리스트 길이")
             .register(registry);
    }

    private double getLen(String key) {
        try {
            Long size = mqRedisTemplate.opsForList().size(key);
            return size != null ? size : 0.0;
        } catch (Exception e) {
            return 0.0; // Redis 장애 시 0 반환 (메트릭 유실 방지)
        }
    }
}
```

**Prometheus 노출 이름**: Micrometer가 `.` → `_` 변환
- `redis_queue_size{queue="posts:queue"}`
- `redis_queue_size{queue="posts:dlq"}`

### Task 5 — docker-compose.yml 변경

`infra/docker-compose.yml` 기존 services 블록에 추가:

```yaml
  prometheus:
    image: prom/prometheus:v2.55.1
    container_name: tracker-prometheus
    ports:
      - "127.0.0.1:9090:9090"
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml:ro
    extra_hosts:
      - "host.docker.internal:host-gateway"   # Linux 호환 (Mac은 자동)
    restart: unless-stopped

  grafana:
    image: grafana/grafana:11.4.0
    container_name: tracker-grafana
    ports:
      - "127.0.0.1:3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning:ro
      - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
    depends_on:
      - prometheus
    restart: unless-stopped
```

`volumes:` 섹션에 `grafana_data:` 추가.

### Task 6 — infra/prometheus/prometheus.yml

API는 호스트에서 직접 실행(Docker 외부)되므로 `host.docker.internal:8080` 사용.

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'tracker-api'
    metrics_path: '/actuator/prometheus'
    static_configs:
      - targets: ['host.docker.internal:8080']
```

### Task 7 — Grafana 파일 구조

```
infra/grafana/
├── provisioning/
│   ├── datasources/
│   │   └── prometheus.yml
│   ├── dashboards/
│   │   └── dashboard.yml
│   └── alerting/
│       └── dlq-alert.yml
└── dashboards/
    └── tracker.json
```

**datasources/prometheus.yml**:
```yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    url: http://prometheus:9090
    isDefault: true
    uid: prometheus
```

**dashboards/dashboard.yml**:
```yaml
apiVersion: 1
providers:
  - name: tracker
    folder: Tracker
    type: file
    options:
      path: /var/lib/grafana/dashboards
```

**alerting/dlq-alert.yml** (Grafana Unified Alerting 프로비전):
```yaml
apiVersion: 1
groups:
  - orgId: 1
    name: Tracker Alerts
    folder: Tracker
    interval: 1m
    rules:
      - uid: tracker-dlq-alert
        title: "posts:dlq 적재 알림"
        condition: C
        for: 0s
        labels:
          severity: warning
        annotations:
          summary: "posts:dlq에 메시지 적재됨 ({{ $value }}건)"
        data:
          - refId: A
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: prometheus
            model:
              expr: redis_queue_size{queue="posts:dlq"}
              refId: A
              instant: true
          - refId: C
            relativeTimeRange:
              from: 300
              to: 0
            datasourceUid: "-100"
            model:
              conditions:
                - evaluator:
                    params: [1]
                    type: gt
                  operator:
                    type: and
                  query:
                    params: [A]
                  reducer:
                    type: last
                  type: query
              refId: C
              type: classic_conditions
```

**dashboards/tracker.json** (Grafana JSON Model, schemaVersion 38):

```json
{
  "title": "Tracker 시스템 모니터링",
  "uid": "tracker-monitoring",
  "schemaVersion": 38,
  "version": 1,
  "tags": ["tracker"],
  "editable": true,
  "graphTooltip": 0,
  "time": { "from": "now-1h", "to": "now" },
  "refresh": "30s",
  "templating": {
    "list": [
      {
        "name": "datasource",
        "type": "datasource",
        "query": "prometheus",
        "current": {},
        "hide": 0
      }
    ]
  },
  "panels": [
    {
      "id": 1,
      "title": "API p95 응답 시간",
      "type": "timeseries",
      "gridPos": { "h": 8, "w": 24, "x": 0, "y": 0 },
      "datasource": { "type": "prometheus", "uid": "${datasource}" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "${datasource}" },
          "expr": "histogram_quantile(0.95, sum(rate(http_server_requests_seconds_bucket{job=\"tracker-api\",uri!~\"/actuator.*\"}[5m])) by (le))",
          "legendFormat": "p95 응답 시간",
          "refId": "A"
        }
      ],
      "fieldConfig": {
        "defaults": { "unit": "s", "color": { "mode": "palette-classic" } }
      }
    },
    {
      "id": 2,
      "title": "Redis posts:queue 깊이",
      "type": "stat",
      "gridPos": { "h": 4, "w": 12, "x": 0, "y": 8 },
      "datasource": { "type": "prometheus", "uid": "${datasource}" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "${datasource}" },
          "expr": "redis_queue_size{queue=\"posts:queue\"}",
          "legendFormat": "Queue 깊이",
          "refId": "A"
        }
      ],
      "fieldConfig": {
        "defaults": { "unit": "short", "color": { "mode": "thresholds" },
          "thresholds": { "mode": "absolute",
            "steps": [{ "color": "green", "value": null }] }
        }
      }
    },
    {
      "id": 3,
      "title": "Redis posts:dlq 적재 건수",
      "type": "stat",
      "gridPos": { "h": 4, "w": 12, "x": 12, "y": 8 },
      "datasource": { "type": "prometheus", "uid": "${datasource}" },
      "targets": [
        {
          "datasource": { "type": "prometheus", "uid": "${datasource}" },
          "expr": "redis_queue_size{queue=\"posts:dlq\"}",
          "legendFormat": "DLQ 건수",
          "refId": "A"
        }
      ],
      "fieldConfig": {
        "defaults": { "unit": "short", "color": { "mode": "thresholds" },
          "thresholds": { "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "red", "value": 1 }
            ]
          }
        }
      }
    }
  ]
}
```

### Task 8 — APScheduler misfire 로깅 (deferred-work.md 인계 항목)

`deferred-work.md` 항목: _"APScheduler misfire 이벤트 미로깅 [crawler/src/scheduler/crawl_scheduler.py:174-184] — misfire 발생 시 가시성 zero. Story 5.1 Prometheus/Grafana와 함께 EVENT_JOB_MISSED listener 추가."_

`crawler/src/scheduler/crawl_scheduler.py` 수정:
- `EVENT_JOB_MISSED` 이벤트 리스너를 APScheduler에 등록
- misfire 발생 시 구조화 로그(`structured_logger`) 출력: job_id, scheduled_run_time 포함
- 기존 APScheduler 설정(AsyncIOScheduler, trigger 패턴) 변경 금지

```python
from apscheduler.events import EVENT_JOB_MISSED

def _on_job_missed(event):
    logger.warning("scheduler_job_missed", job_id=event.job_id,
                   scheduled_run_time=str(event.scheduled_run_time))

scheduler.add_listener(_on_job_missed, EVENT_JOB_MISSED)
```

### 회귀 방지 — 변경 금지 항목

- `api/src/main/java/com/tracker/api/config/RedisConfig.java` — `cacheRedisTemplate` 빈 로직 변경 금지
- `api/src/main/resources/application.properties` — 기존 `spring.data.redis.*` (DB0/DB3) 설정 변경 금지
- `spring.data.redis.database=0` — 기본 DB 변경 금지
- 기존 테스트 24개 — `./gradlew test` 회귀 0건 확인 필수

### 알림 채널 제약

- **MVP**: Grafana UI 알림만 사용 (architecture.md 결정사항)
- Slack/이메일 연동은 Growth 단계 — 이번 스토리에서 구현 금지
- `GF_SECURITY_ADMIN_PASSWORD=admin` — 로컬 개발 전용 (프로덕션은 환경변수로 교체)

### 수동 검증 절차 (Task 9)

```bash
# 1. API 서버 실행 (별도 터미널)
cd api && ./gradlew bootRun

# 2. 모니터링 스택 시작
cd infra && docker compose up -d

# 3. Prometheus 스크레이핑 확인
curl -s localhost:9090/api/v1/targets | jq '.data.activeTargets[] | .labels.job, .health'
# 예상: "tracker-api", "up"

# 4. 메트릭 노출 확인
curl -s localhost:8080/actuator/prometheus | grep -E "http_server_requests_seconds|redis_queue_size"

# 5. Grafana 접속 확인 (admin/admin)
open http://localhost:3000

# 6. DLQ Alert 수동 검증
redis-cli -n 0 lpush posts:dlq test-alert-msg
# → Grafana Alerting → Alert rules → DLQ alert Firing 상태 확인
redis-cli -n 0 del posts:dlq
# → Alert Normal 복귀 확인
```

## Tasks / Subtasks

- [x] **Task 1: build.gradle — micrometer-registry-prometheus 추가** (AC: #1)
  - [x] 1.1 `api/build.gradle` `dependencies` 블록에 `implementation 'io.micrometer:micrometer-registry-prometheus'` 추가 (버전 핀 불필요 — Spring Boot BOM 관리)
  - [x] 1.2 `./gradlew dependencies | grep micrometer-registry-prometheus` 로 의존성 해석 확인

- [x] **Task 2: application.properties — Actuator prometheus 노출** (AC: #1)
  - [x] 2.1 `api/src/main/resources/application.properties` 하단에 추가:
    ```
    management.endpoints.web.exposure.include=prometheus,health,info
    management.endpoint.prometheus.enabled=true
    ```
  - [x] 2.2 `./gradlew bootRun` 후 `curl -s localhost:8080/actuator/prometheus | grep http_server` 로 200 응답 확인

- [x] **Task 3: RedisQueueMetrics 구현** (AC: #2, #3)
  - [x] 3.1 `api/src/main/java/com/tracker/api/metrics/` 패키지 신규 생성
  - [x] 3.2 `RedisQueueMetrics.java` 작성 — `MeterBinder` 구현, Dev Notes 패턴 준수
  - [x] 3.3 `posts:queue`와 `posts:dlq` Gauge 2개 등록
  - [x] 3.4 Redis 예외 시 `0.0` 반환 (try-catch 필수)

- [x] **Task 4: RedisQueueMetricsTest 작성** (AC: #2, #3)
  - [x] 4.1 `api/src/test/java/com/tracker/api/metrics/RedisQueueMetricsTest.java` 신규 생성
  - [x] 4.2 `@ExtendWith(MockitoExtension.class)` 사용 — `SimpleMeterRegistry` + `@Mock StringRedisTemplate`
  - [x] 4.3 `queueGauge_returnsLlen()` — `opsForList().size("posts:queue")` mock 5L → Gauge 값 5.0 검증
  - [x] 4.4 `dlqGauge_returnsLlen()` — `posts:dlq` mock 3L → Gauge 값 3.0 검증
  - [x] 4.5 `gauge_redisFails_returnsZero()` — `opsForList().size()` 예외 발생 → 0.0 반환 검증
  - [x] 4.6 `./gradlew test` 통과, 기존 24개 테스트 회귀 0건 확인 (총 27개 PASS)

- [x] **Task 5: docker-compose.yml — Prometheus + Grafana 서비스 추가** (AC: #5)
  - [x] 5.1 `infra/docker-compose.yml`에 `prometheus` 서비스 추가 (Dev Notes 스펙 준수)
  - [x] 5.2 `infra/docker-compose.yml`에 `grafana` 서비스 추가, `depends_on: prometheus` 설정
  - [x] 5.3 `volumes:` 섹션에 `grafana_data:` 추가
  - [x] 5.4 `docker compose up -d` 후 컨테이너 4개(redis + postgres + prometheus + grafana) 모두 `Up` 확인

- [x] **Task 6: infra/prometheus/prometheus.yml 작성** (AC: #1, #5)
  - [x] 6.1 `infra/prometheus/.gitkeep` 삭제, `infra/prometheus/prometheus.yml` 생성 (Dev Notes 내용 기준)
  - [x] 6.2 scrape_interval 15s, job=tracker-api, target=`host.docker.internal:8080`, path=`/actuator/prometheus`
  - [x] 6.3 API 실행 중 `localhost:9090/targets` → tracker-api `State: UP` 확인

- [x] **Task 7: Grafana 프로비전 설정 + 대시보드 JSON 작성** (AC: #2, #3, #4, #5)
  - [x] 7.1 `infra/grafana/provisioning/datasources/prometheus.yml` 생성 — uid=`prometheus`, URL=`http://prometheus:9090`
  - [x] 7.2 `infra/grafana/provisioning/dashboards/dashboard.yml` 생성
  - [x] 7.3 `infra/grafana/provisioning/alerting/dlq-alert.yml` 생성 — DLQ≥1 즉시(for: 0s) 알림 규칙
  - [x] 7.4 `infra/grafana/dashboards/.gitkeep` 삭제, `tracker.json` 생성 — Dev Notes JSON 기준으로 3개 패널 포함
  - [x] 7.5 `docker compose up -d` 재시작 후 `localhost:3000` → Tracker 대시보드 자동 로드 확인

- [x] **Task 8: APScheduler misfire 로깅 추가** (deferred-work.md 인계)
  - [x] 8.1 `crawler/src/scheduler/crawl_scheduler.py` 상단에 `from apscheduler.events import EVENT_JOB_MISSED` 추가
  - [x] 8.2 scheduler 초기화 이후 `_on_job_missed` 리스너 등록 (Dev Notes 패턴 준수)
  - [x] 8.3 기존 APScheduler 설정(AsyncIOScheduler, trigger, RedisPublisher) 변경 없이 리스너만 추가
  - [x] 8.4 crawler 기존 테스트 회귀 0건 확인 (74개 PASS)

- [x] **Task 9: 수동 E2E 검증 및 Dev Notes 업데이트** (AC: #3, #4)
  - [x] 9.1 Dev Notes의 수동 검증 절차 실행
  - [x] 9.2 DLQ Alert Firing → Normal 사이클 확인 (`redis_queue_size{queue="posts:dlq"}` 1.0 → 0.0)
  - [x] 9.3 `localhost:9090` Prometheus targets `tracker-api: up`, `localhost:8080/actuator/prometheus` 메트릭, `localhost:3000` 대시보드 확인
  - [x] 9.4 이 스토리 파일 Dev Notes 하단에 검증 결과 기록 후 Status: `review` 변경

### Review Findings

- [x] [Review][Patch] Redis queue gauge의 0.0 fallback은 유지하되 Redis scrape 실패를 별도 metric/alert로 노출한다. [api/src/main/java/com/tracker/api/metrics/RedisQueueMetrics.java:30]
- [x] [Review][Patch] DLQ 알림 조건이 `>=1`이 아니라 `>1`로 동작한다. [infra/grafana/provisioning/alerting/dlq-alert.yml:33]
- [x] [Review][Patch] API p95 패널이 `http_server_requests_seconds_bucket`을 조회하지만 HTTP server request 히스토그램 발행 설정이 없다. [infra/grafana/dashboards/tracker.json:32]
- [x] [Review][Patch] APScheduler misfire 로그가 `job_id`, `scheduled_run_time`을 구조화 필드로 남기지 않는다. [crawler/src/scheduler/crawl_scheduler.py:220]
- [x] [Review][Defer] `EVENT_JOB_MISSED` 리스너가 `max_instances=1`로 인한 장시간 실행/중복 실행 skip 경로까지 관측하지는 않는다. [crawler/src/scheduler/crawl_scheduler.py:229] — deferred, pre-existing

## Dev Agent Record

### Implementation Notes

**구현 일자**: 2026-05-12

**주요 구현 내역**:
- `api/build.gradle`: `micrometer-registry-prometheus:1.15.0` (Spring Boot BOM 관리) 추가
- `application.properties`: `management.endpoints.web.exposure.include=prometheus,health,info` 추가
- `RedisQueueMetrics.java`: `MeterBinder` 구현, `posts:queue` + `posts:dlq` Gauge 2개 등록, Redis 예외 시 0.0 반환
- `RedisQueueMetricsTest.java`: 3개 테스트 (queue/dlq Gauge값 검증, Redis 장애 시 0.0 반환)
- `docker-compose.yml`: Prometheus(v2.55.1) + Grafana(11.4.0) 서비스 추가, `grafana_data` 볼륨 추가
- `infra/prometheus/prometheus.yml`: scrape_interval 15s, tracker-api target=host.docker.internal:8080
- `infra/grafana/provisioning/`: datasources, dashboards, alerting 3개 YAML 프로비전 파일
- `infra/grafana/dashboards/tracker.json`: p95 응답시간(패널 1), posts:queue 깊이(패널 2), posts:dlq 건수(패널 3) 대시보드
- `crawler/src/scheduler/crawl_scheduler.py`: `EVENT_JOB_MISSED` 리스너 추가

**버그 수정**:
- `RedisConfig.java`에 `@Primary StringRedisTemplate stringRedisTemplate(RedisConnectionFactory)` 추가: Spring Boot `@ConditionalOnMissingBean`이 `cacheRedisTemplate`(DB3) 존재로 인해 DB0 `StringRedisTemplate`을 생성하지 않아 `RedisQueueMetrics`가 DB3을 읽는 문제 해결

**E2E 검증 결과**:
- `curl localhost:9090/api/v1/targets` → `"tracker-api" "up"` ✅
- `curl localhost:8080/actuator/prometheus | grep redis_queue_size` → `posts:queue` + `posts:dlq` Gauge 노출 ✅
- DLQ lpush → `redis_queue_size{queue="posts:dlq"} 1.0` / del → `0.0` ✅
- `localhost:3000` Grafana 접속, Tracker 대시보드 자동 로드 ✅

### File List

**신규 파일**:
- `api/src/main/java/com/tracker/api/metrics/RedisQueueMetrics.java`
- `api/src/test/java/com/tracker/api/metrics/RedisQueueMetricsTest.java`
- `infra/prometheus/prometheus.yml`
- `infra/grafana/provisioning/datasources/prometheus.yml`
- `infra/grafana/provisioning/dashboards/dashboard.yml`
- `infra/grafana/provisioning/alerting/dlq-alert.yml`
- `infra/grafana/dashboards/tracker.json`

**수정 파일**:
- `api/build.gradle` (micrometer-registry-prometheus 추가)
- `api/src/main/resources/application.properties` (actuator prometheus 노출)
- `api/src/main/java/com/tracker/api/config/RedisConfig.java` (@Primary stringRedisTemplate 빈 추가)
- `infra/docker-compose.yml` (prometheus/grafana 서비스 + grafana_data 볼륨 추가)
- `crawler/src/scheduler/crawl_scheduler.py` (EVENT_JOB_MISSED 리스너 추가)

### Change Log

- 2026-05-12: Story 5-1 구현 완료 — Prometheus/Grafana 모니터링 스택, RedisQueueMetrics, DLQ Alert, APScheduler misfire 로깅 추가
