# A/B 비교 + 비용 실측 + fast-path 튜닝 + 데모 모드 결정 (Story 3-9)

> 신·구 아키텍처(single OpenAI 단일 호출 vs agentic 멀티 에이전트)를 **동일 ground truth**로
> 비교하고, agentic 게시글당 비용을 실측하고, fast-path 임계를 튜닝하고, 데모 모드를 결정하는
> **측정·검증·리허설** 문서. 파이프라인 신규 기능은 없다(전부 3-7/3-8에서 완성).

- 작성 도구: `detection/scripts/ab_compare.py`(정량 표 생성) + `detection/scripts/demo_rehearsal.py`(리허설)
- 메트릭 순수 함수: `detection/scripts/ab_metrics.py` (단위 테스트 `tests/unit/test_ab_metrics.py`)
- 전제: V9(human_label) + V10(agent_runs) 적용 PostgreSQL + 실 `OPENAI_API_KEY` (운영자 `!` 실행)

---

## 1. 방법론 — A/B 재분류 설계

### 1.1 ground truth = human_label (Story 3-5)

운영자가 `label_detections.py`로 검증한 `detections.human_label`(9-type ∪ `unknown`)이 정답이다.
**judgeable 분모**는 `human_label IS NOT NULL AND human_label != 'unknown'` — `unknown`은 9-type과
매칭 불가라 정확도 분모에서 제외(3-5 `compute_snapshot` 규율과 동일).

### 1.2 핵심 함정 — human_label은 원본 행에만 1개

`human_label`은 라벨 당시의 detection 행(주로 single `openai:...`)에 **1개만** 붙어 있다.
A/B는 같은 게시글을 **양 모드로 재분류**한 뒤 각 모드의 `type`을 그 게시글의 `human_label`과 비교한다.
재분류로 생긴 agentic 행에는 `human_label`이 **없으므로**, "같은 행의 human_label vs type"을 보면
agentic 쪽이 비교 불가가 된다.

→ **정답:** `{post_id: human_label}` 맵을 만들고(`ab_metrics.build_label_map`), 양 모드 결과를
`post_id`로 조인한다(`ab_metrics.join_predictions`). 이것이 본 스토리의 가장 중요한 설계점이다.

### 1.3 A/B 공존은 무료

`detections.(post_id, model_version)` UNIQUE + `ON CONFLICT DO NOTHING`(detection_repository.py)으로
single `openai:{model}:{release}`와 agentic `agentic:v1:mini+4o:{YYYY-MM}`가 **같은 post에 공존**한다.
`ab_compare.py`가 두 모드를 각각 `DetectionPipeline.process`로 돌려 각자의 `model_version`으로 UPSERT한다.

> ⚠️ **행 멱등 ≠ 비용 멱등.** `ON CONFLICT DO NOTHING`은 **DB 행만** 멱등이다 — `process()`는 매 실행마다
> LLM을 **재호출**하므로(결과 INSERT만 no-op) 재실행 시 **실 OpenAI 비용이 다시 발생**한다. 또한 single
> `model_version`의 `{release}`는 `LLM_MODEL_RELEASE_DATE` 미설정 시 **실행일자(`%Y-%m-%d`)로 폴백**해
> 매일 값이 바뀐다 → 다른 날 재실행하면 같은 post에 single 행이 **중복 생성**되고 재과금된다. 표본을 다시
> 돌릴 땐 `LLM_MODEL_RELEASE_DATE`를 고정하거나, 비용이 아까우면 이미 분류된 표본은 재실행하지 말 것.

### 1.4 메트릭 정의

| 메트릭 | 정의 | 출처 |
|---|---|---|
| **agreement** | 라벨 == 예측 type 비율 (judgeable 분모) | `compute_snapshot`과 동일 의미, post_id 조인 |
| **Recall(Tier)** | TP/(TP+FN) — truth Tier 기준 | 신규 (`tier_metrics`) |
| **Precision(Tier)** | TP/(TP+FP) — pred Tier 기준 | 신규 (`tier_metrics`) |
| **confusion matrix** | `(true_tier, pred_tier)` 빈도 (T2↔T1 오분류 등) | 신규 |
| **명확 케이스 정탐율** | truth 불법(Tier≠T4) → 불법 예측 비율 | 신규 (`illegal_detection_rate`) |

type→Tier는 `tier_router.TYPE_TO_TIER` SSOT 재사용. 분모 0(해당 Tier truth/pred 0건)이면 Recall/
Precision은 `N/A`(미정의) — 0.0으로 왜곡하지 않는다.

**PRD 목표**(prd.md L74-80): Recall **T1≥0.85 / T2≥0.70 / T3≥0.55**, confusion matrix 측정 필수,
**명확 케이스 정탐율 ≥90%**.

---

## 2. 정량 결과 (운영자 실행분 — `ab_compare.py`가 자동 갱신)

> 아래 표는 V9+V10 PG + 실 OpenAI 환경에서 `python detection/scripts/ab_compare.py [--limit N]`을
> 실행하면 `ab_compare.py`가 이 파일을 **통째로 재생성**해 채운다(`render_ab_markdown`). 로컬 dev DB는
> 수동 V5 drift라 baseline 정리 후 V6~V10 적용이 선행돼야 한다(아래 §6).

<!-- AB_RESULTS_PLACEHOLDER
실행 전 상태. 실행 후 이 블록은 다음으로 대체된다:
- Agreement 표 (single vs agentic)
- Tier별 Recall/Precision + Δ 표
- 명확 케이스 정탐율 (single/agentic, PRD ≥90% 대비)
- Confusion Matrix (agentic)
- 비용 실측 표 (전체/이미지有/이미지無 × 평균·p95·최대) + escalation율
-->

판정 기준(실행 후 채울 것):
- [ ] agentic Recall T1 ≥ 0.85 / T2 ≥ 0.70 / T3 ≥ 0.55
- [ ] agentic 명확 케이스 정탐율 ≥ 90%
- [ ] agentic 평균 비용 ≤ $0.005 · p95 ≤ $0.02
- [ ] single 대비 agentic Δ Recall(특히 T1) ≥ 0 (회귀 없음)

---

## 3. 비용 실측 설계 (Task 4)

- **게시글당 비용 출처**: agentic은 `detections.cost_usd`(orchestrator가 전 스테이지 합산, 3-8).
  degrade·검증 실패 trace도 실지출 반영(3-8 리뷰 패치 `AgentResponseError` usage 보존).
- **p95는 분포 필요** — 평균만으로 불가. 게시글별 `cost_usd` 리스트에서 `ab_metrics.percentile`
  (stdlib 선형보간, numpy 불요)로 산출.
- **이미지 유/무 분리**: 해당 post의 `post_images` 행 존재 여부로 그룹화(PRD L78). `image_urls`/
  `s3_image_paths`는 `post_images.image_url`/`s3_key`에서 복원.
- **escalation율**: orchestrator `_escalated/_posts_total`(3-8 카운터, 종결 시점 집계).

### 3.1 budget degrade 마커 주의 (3-8 인수인계)

orchestrator의 예산 가드는 LLM 미호출 degrade 시 `agent_runs`에 `stage="synthesize"` +
`output.skipped="budget_exceeded"` 마커 행을 남긴다. **"synthesize 행 수 = S3 호출 수"로 세면
오류** — `agent_runs`를 직접 집계할 때는 `output.skipped='budget_exceeded'` 행을 제외해야 한다.
본 스토리는 게시글당 비용을 `detections.cost_usd`(합산 결과)에서 읽으므로 영향받지 않지만,
스테이지별 분해 분석 시 주의.

### 3.2 비용 모델 기준선 (변경 제안서 L148-161)

S1 $0.00042 + S2a $0.0058(escalate 시) + S3 $0.0080(escalate 시). escalation 35%에서 평균 ~$0.0040
✅ ≤$0.005. 3-8 실측 escalate 풀경로 $0.01143 ≤ p95 $0.02. 본 스토리가 라벨셋 표본으로 **재확인**한다.

---

## 4. fast-path 임계 튜닝 (Task 3, 권고)

`FAST_PATH_CONFIDENCE`(기본 `0.80`, `orchestrator.py:39`)는 트리아지가 `기타`·고신뢰·무링크일 때
S2/S3를 건너뛰는 임계다. **escalation율 ↔ 정확도 트레이드오프**:

- 임계 ↑(예 0.85): fast-path 적게 → escalation율 ↑ → 비용 ↑, 누락 위험 ↓(안전)
- 임계 ↓(예 0.75): fast-path 많이 → escalation율 ↓ → 비용 ↓, 정상 게시글의 미검토 위험 ↑

튜닝 절차(운영자): 몇 개 값으로 `ab_compare.py`를 재실행하여 escalation율과 정확도(특히 명확 케이스
정탐율·T1 Recall)를 관찰한다. 코드 기본값 변경은 **env로 운영 조정 가능하므로 선택** — 문서 권고로 충분.

```bash
FAST_PATH_CONFIDENCE=0.75 python detection/scripts/ab_compare.py --limit 30
FAST_PATH_CONFIDENCE=0.80 python detection/scripts/ab_compare.py --limit 30   # 기본
FAST_PATH_CONFIDENCE=0.85 python detection/scripts/ab_compare.py --limit 30
```

> ⚠️ **스윕 함정 — 실행 사이 agentic 행을 비워야 한다.** agentic `model_version`(`agentic:v1:mini+4o:{YYYY-MM}`)에는
> 임계값이 **인코딩되지 않는다**. 1차 실행이 agentic 행을 쓰고 나면, 2/3차 실행은 `ON CONFLICT DO NOTHING`으로
> INSERT가 no-op이 되고 `fetch_mode_detections`는 **1차 결과를 그대로 재독**한다 — 임계만 바꾼 §2 정확도 표가
> 전부 동일해진다(escalation율만 orchestrator 카운터라 실시간 반영돼 표가 자기모순이 된다). 따라서 각 임계 실행
> **전에** 해당 월의 agentic 행을 삭제해야 한다:
>
> ```sql
> DELETE FROM detections WHERE model_version LIKE 'agentic:v1:%';  -- 임계 변경 전 1회
> ```
>
> (자동 스윕 표 생성 — `render_ab_markdown(fast_path_sweep=...)` — 은 미배선 상태로 deferred. 현재는 위 수동
> 절차 + §2 표를 임계별로 캡처해 비교한다.)

**권장값(기본 유지 근거):** orchestrator는 escalation율이 50%를 넘으면 경고 로그로 임계 하향을
신호한다(`_ESCALATION_WARN_RATE`). 운영 트래픽은 정상 게시글(`기타`)이 다수라 0.80에서 escalation율이
낮게 유지될 것으로 기대된다. 실측 escalation율이 지속적으로 50%를 초과하면 0.75로 하향을 검토한다.
(명확 불법 위주의 데모 리허설은 본질적으로 escalation율이 높으므로 — §5 — 임계 판단의 근거로 쓰지 말 것.)

> ⚠️ 자동 임계 조정 로직은 **범위 외**(deferred). 본 스토리는 env 토글 + 문서 권고까지.

---

## 5. 데모 리허설 + single 회귀 절차 (Task 5/6)

### 5.1 오프라인 리허설 (`demo_rehearsal.py`, 실 OpenAI 0)

`DEMO_OFFLINE=true`(기본)에서 `LLMMock` 에이전트 모드가 **본문 키워드 → 시나리오** 라우팅으로 10건
각각 결정론적 verdict를 낸다(`tests/fixtures/llm/mock_agent_scenarios.json` — 명확 불법 8 + 정상 2).
인터넷 없이 흐름·UI를 재현할 수 있다.

```bash
python detection/scripts/demo_rehearsal.py            # 오프라인(기본, 결정론적)
DEMO_OFFLINE=false python detection/scripts/demo_rehearsal.py   # 실 OpenAI(비용 발생)
```

오프라인 리허설 재현 결과(mock fixture 값 — 비용은 fixture 합성치):

| 항목 | 값 |
|---|---|
| 게시글 | 10건 (명확 불법 8 + 정상 2) |
| 불법 탐지 | 8건 (T1×3, T2×2, T3×3 — 전부 정탐) |
| 정상 fast-path | 2건 (T4, triage만) |
| escalation율 | 8/10 = 80% (명확 불법 위주라 높음 — 운영 평균과 다름) |
| 평균 비용 | ~$0.008 (fixture 값; 실 비용은 §2) |

> **주의:** 데모는 명확 불법을 집중 투입하므로 escalation율·평균 비용이 운영 트래픽보다 높다.
> PRD 평균 ≤$0.005는 정상 게시글이 다수인 운영 분포에서 성립한다 — 정량 증명은 §2(`ab_compare.py`).

### 5.2 single 모드 즉시 회귀 (데모 당일 안전장치)

데모 당일 아침까지 모드 선택 가능 상태를 보장한다. agentic 정확도가 회귀하면 **1줄 토글**로 폴백:

```bash
DETECTION_MODE=single    # detection_pipeline.py:63 use_agentic 분기 — 즉시 기존 단일 호출 경로로
```

회귀 후 동작 확인(single 경로 단건):

```bash
DETECTION_MODE=single python detection/scripts/smoke_integration_db.py   # 큐→OpenAI→PG 1건
```

single 경로는 3-3/3-4에서 검증된 안정 경로다. `model_version`이 `openai:...`로 분리 저장되므로
agentic 결과와 충돌 없이 공존한다.

### 5.3 데모 모드 결정 (실행 후 확정)

§2의 판정 기준을 모두 통과하면 **agentic**으로 데모. 하나라도 미달이면 **single**로 폴백하고
사유를 아래에 기록:

- 결정: `( ) agentic   ( ) single`
- 근거:

---

## 6. 운영자 실행 전제 — 로컬 DB drift

로컬 dev DB는 수동 V5 상태(flyway 이력 없음, V6~V10 미적용). A/B 재분류·agentic 저장·human_label
조회는 **V9+V10 적용 PG가 필요**하다. Claude는 마이그레이션 직접 적용이 차단되므로 운영자가
`!`로 실행한다(flyway baseline 정리 후 V6~V10). 단위 테스트(메트릭·mock 결정성)는 PG 무관으로 통과한다.

실 실행은 `docs/integration-smoke-3-9.md`의 절차를 따른다.

---

## References

- prd.md L74-80 (Recall 목표·confusion·비용·정탐율), L266 (이미지 PII)
- sprint-change-proposal-2026-06-11.md L139-161 (설계결정·비용 모델), L240-247 (성공 기준)
- 3-8 Dev/Review (비용·카운터·budget 마커 인수인계)
- detection/scripts/{ab_compare,ab_metrics,demo_rehearsal}.py
