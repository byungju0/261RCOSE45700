# 통합 실사 — A/B 실행 + T1 알림 E2E (Story 3-9)

> 3-7/3-8 관례(`docs/integration-smoke-3-*.md`)에 따라 실사 실행 절차와 결과를 캡처한다.
> 본 스토리는 **측정·검증·리허설**이며 파이프라인 신규 코드는 없다. T1 알림 경로는 **신규 코드 0**
> — 기존 백엔드 알림 시스템(V7 + NotificationEventProcessor)이 agentic 탐지와 함께 동작함을
> E2E로 **검증만** 한다.

---

## 0. 전제 — DB 마이그레이션 (운영자 `!` 실행)

로컬 dev DB가 수동 V5 drift(flyway 이력 없음, V6~V10 미적용)이므로 다음이 선행돼야 한다:

- V6 (post_url backfill), V7 (notification_outbox — 알림 4테이블), V8 (activity_log),
  V9 (human_label), V10 (agent_runs) 적용.
- Flyway baseline 정리 후 `flyway migrate`(또는 Spring API 기동 시 자동 마이그레이션).

> Claude는 마이그레이션 직접 적용이 차단됨 — 운영자가 `! <flyway/compose 명령>`으로 실행.
> 단위 테스트(메트릭·mock 결정성, 23건)는 PG 무관으로 통과한다.

```bash
# 예시 — 컨테이너 기동 + Spring 기동(자동 마이그레이션)
docker compose -f infra/docker-compose.yml --env-file infra/.env up -d redis postgres
# Spring API 기동 시 NOTIFICATION_ENCRYPTION_KEY 필수(미설정 시 기동 실패)
```

---

## 1. A/B 재분류 실행 (Task 2)

```bash
# (a) 무비용 사전 점검 — ground truth 집합/라벨 분포만
python detection/scripts/ab_compare.py --dry-run

# (b) 표본 A/B (실 OpenAI 비용 — cost_cap 일일 $5 상한)
python detection/scripts/ab_compare.py --limit 30

# (c) 전체 라벨셋
python detection/scripts/ab_compare.py
```

- 출력: `docs/ab-comparison-3-9.md`를 통째 재생성(§2 정량 표 채움) + stdout에 agreement/평균 비용 요약.
- `(post_id, model_version)` UNIQUE + ON CONFLICT DO NOTHING → **재실행 멱등**(이미 분류된 건 skip,
  추가 비용 0). 표본을 늘리려면 `--limit`를 키워 재실행.
- single `openai:{model}:{date}` + agentic `agentic:v1:mini+4o:{YYYY-MM}` 두 행이 같은 post에 공존.

### 실행 결과 캡처 (운영자 채움)

```
[INFO] ground truth judgeable 게시글: ___건
[INFO] single model_version  = openai:gpt-4o:____-__-__
[INFO] agentic model_version = agentic:v1:mini+4o:____-__
[DONE] A/B 비교표 작성 → docs/ab-comparison-3-9.md
  single agreement=____  agentic agreement=____
  agentic 평균 비용=$____  p95=$____  (PRD 평균 ≤$0.005 · p95 ≤$0.02)
```

---

## 2. 데모 리허설 (Task 6)

```bash
python detection/scripts/demo_rehearsal.py            # 오프라인 결정론적(실 OpenAI 0)
DEMO_OFFLINE=false python detection/scripts/demo_rehearsal.py   # 실 OpenAI
```

오프라인은 인터넷 없이 재현 가능(키워드 라우팅). 결과 해석은 `docs/ab-comparison-3-9.md` §5 참조.

---

## 3. T1 알림 E2E 검증 (Task 7 — 신규 코드 0)

**확인된 동작(코드 검증):** detection은 **모든 tier에서** `notification_events`(PENDING)를 적재한다
(`detection_repository.py` L159-169, tier·모드 무관, detections와 **동일 트랜잭션**). agentic 경로도
동일하게 동작한다(3-8 smoke T1에서 확인됨). 따라서 본 Task는 **검증 + 문서화**만 한다.

### 3.1 E2E 체인

| # | 단계 | 위치 | 확인 |
|---|---|---|---|
| 1 | agentic T1 탐지 저장 | `detection_repository.save` | `detections` + `agent_runs` + `notification_events(PENDING)` INSERT (동일 트랜잭션) |
| 2 | 백엔드 폴링 | `NotificationEventProcessor` `@Scheduled(fixedDelay=5000)` | PENDING → `claimed_at` 갱신(PROCESSING) |
| 3 | minTier 필터 | `NotificationRuleEvaluator.matches` | `tierRank(T1)=1`; minTier=T1이면 `tierRank(detection) > tierRank(rule)` → T1만 통과, T2~T4(rank 2~4) 필터 |
| 4 | is_illegal 게이트 | `NotificationEventProcessor` | T4(is_illegal=false) → SKIPPED. T1~T3만 룰 평가 |
| 5 | 채널 발송 | `*Adapter`(6종) | `notification_deliveries`(SUCCESS/FAILED/SKIPPED) 기록 |

채널 6종: DISCORD / SLACK_WEBHOOK / SLACK_WORKFLOW / GOOGLE_CHAT / TEAMS_WORKFLOW / GENERIC_WEBHOOK.

### 3.2 minTier=T1 룰 설정 방법

대시보드 알림 탭 UI 또는 `notification_rules` 직접 INSERT(V7 스키마):

```sql
-- 1) 채널 먼저 등록(대시보드 UI 권장 — encrypted_config가 AES/GCM 암호화됨).
--    SQL 직접 INSERT 시 encrypted_config는 NotificationSecretCrypto로 암호화된 값이어야 함.
-- 2) minTier=T1 룰
INSERT INTO notification_rules (name, enabled, event_type, channel_id, min_tier, send_mode)
VALUES ('T1 즉시 알림', true, 'DETECTION_CREATED', <channel_id>, 'T1', 'IMMEDIATE');
```

- `min_tier='T1'` → T1 탐지만 발송, T2~T4 필터(rank 비교).
- `event_type`/`send_mode`는 현재 `DETECTION_CREATED`/`IMMEDIATE`만 허용(CHECK 제약).
- `min_confidence`/`detection_type`/`source_site_name`은 선택 추가 필터(NULL=무시).

### 3.3 배포 환경변수 (application.properties L50-57)

| 환경변수 | 기본 | 비고 |
|---|---|---|
| `NOTIFICATION_ENCRYPTION_KEY` | (없음) | **필수** — 미설정 시 `NotificationSecretCrypto`가 IllegalStateException으로 **백엔드 기동 실패**. 채널 `encrypted_config`를 AES/GCM(SHA-256 키유도)로 암복호화 |
| `NOTIFICATION_SCHEDULER_ENABLED` | `true` | 폴링 마스터 스위치(미설정 시도 활성) |
| `NOTIFICATION_POLL_DELAY_MS` | `5000` | 폴링 주기 |
| `NOTIFICATION_BATCH_SIZE` | `10` | 배치당 이벤트 수 |
| `NOTIFICATION_MAX_ATTEMPTS` | `3` | 발송 재시도 한도 |
| `NOTIFICATION_PROCESSING_TIMEOUT_SECONDS` | `120` | PROCESSING 점유 타임아웃 |

### 3.4 E2E 실행 절차 (운영자)

```bash
# (1) T1 탐지 1건 생성 — agentic 경로(월핵 = 핵_치트 = T1)
DETECTION_MODE=agentic python detection/scripts/smoke_agent_pipeline.py
#   → detections(tier=T1) + agent_runs + notification_events(PENDING) 적재 확인

# (2) PG에서 이벤트 적재 확인
#   SELECT status, claimed_at FROM notification_events ORDER BY created_at DESC LIMIT 1;  → PENDING

# (3) Spring API 기동(NOTIFICATION_ENCRYPTION_KEY 설정) → 5초 내 폴링
#   minTier=T1 룰 + 채널 1개 등록되어 있어야 발송됨

# (4) 발송 이력 확인
#   SELECT status FROM notification_deliveries ORDER BY created_at DESC LIMIT 1;  → SUCCESS/FAILED
```

### 실행 결과 캡처 (운영자 채움)

```
notification_events  : status=______ (PENDING→PROCESSING→COMPLETED)
notification_deliveries: status=______ (SUCCESS/FAILED)
채널: ______  minTier 룰: T1
```

---

## 4. single 모드 회귀 절차

```bash
DETECTION_MODE=single python detection/scripts/smoke_integration_db.py
```

데모 당일 agentic 정확도 회귀 시 즉시 폴백(`docs/ab-comparison-3-9.md` §5.2). single 경로는
3-3/3-4 검증 안정 경로이며 `model_version=openai:...`로 분리 저장돼 agentic과 공존한다.

---

## 5. 범위 외 (deferred-work 참조)

- **사람 리뷰 큐(human-in-the-loop)** — 즉시 발송 설계와 충돌 → deferred.
- **T2 다이제스트 / T3 주간 리포트** — `send_mode`가 `IMMEDIATE`만 지원 → deferred.
- **90일 retention job** — deferred.
- few-shot 주입(Stage 2-B) / multi-hop / 대시보드 증거 패널 → deferred-work.

[Source: `_bmad-output/implementation-artifacts/deferred-work.md`]
