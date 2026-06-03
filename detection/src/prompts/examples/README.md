# few-shot 예시 코퍼스 — 포맷 계약 (Story 3-5)

이 디렉터리는 프롬프트 진화의 **few-shot 단계**를 위한 예시 코퍼스를 담는다. 누적된
**사람 검증 라벨**(`detections.human_label`, Story 3-5)에서 game·type별로 선별한 예시를
`build_fewshot_corpus.py`가 export한다.

## 파일 레이아웃

```
detection/src/prompts/examples/{game_key}.jsonl
```

- `{game_key}` = `detection/src/prompts/registry.py`의 `SOURCE_ID_TO_GAME` **값**
  (예: `lineage`, `lineage_mobile`, `aion`, `bns`, `tl`, `mixed_mobile`, `cracking_forum`).
- `games/{game_key}.md` 오버레이와 **동일 키 공간** → 미래 주입 시 같은 game_key로 묶어 베이스
  프롬프트에 보강한다.

## JSONL 레코드 포맷

한 줄당 1 예시:

```json
{"text": "리니지M 월핵 팝니다 텔레그램 @xxx", "label": "핵_치트", "reason_ko": "명시적 핵 판매 + 연락처", "tier": "T1"}
```

| 필드 | 의미 |
|---|---|
| `text` | 게시글 본문 발췌 (≤ `FEWSHOT_EXCERPT_MAX_CHARS`, 기본 500자) |
| `label` | 사람 검증 정답 type (9-type enum). `unknown`은 코퍼스에서 제외 |
| `reason_ko` | 분류 근거 (한국어) |
| `tier` | T1~T4 |

## 생성 방법

```bash
# 1) 미라벨 detections에 사람 라벨 부여 (RDS detections.human_label 컬럼)
python -m detection.scripts.label_detections --game lineage --tier T1 --limit 20

# 2) 라벨에서 game×type별 코퍼스 export (그룹당 confidence 상위 N건)
python -m detection.scripts.build_fewshot_corpus --per-group 3

# 3) 수집 현황 경량 스냅샷
python -m detection.scripts.labelset_snapshot
```

## 소비 지점 (미래 주입)

코퍼스는 `detection/src/pipeline/llm_client.py::build_system_prompt()`의 **Stage 2-B 빈 슬롯**이
소비할 예정이다. 현재 조립 순서:

```
베이스(SYSTEM_PROMPT) → 유형 가이드(Stage 2-A) → 게임 오버레이(Stage 1) → [Stage 2-B few-shot 슬롯 — 비어 있음]
```

## ⚠️ 경계 — 본 스토리(3-5)에서 하지 않는 것

- **few-shot 프롬프트 주입**: 위 Stage 2-B 슬롯에 예시를 실제로 **선택·삽입**하는 로직,
  토큰 예산 런타임 관리, few-shot 전/후 정확도 효과 측정은 **별도 미래 스토리**다.
  Story 3-5는 코퍼스 파일 생성과 본 포맷 계약까지만 담당한다 (조기 구현 시 프롬프트 캐싱
  prefix 안정성·토큰 비용 회귀 위험 — `deferred-work.md` 참조).
- 코퍼스는 베이스 9-type/confidence 루브릭을 **재정의하지 않고 예시로 보강만** 한다
  (게임 오버레이 원칙과 동일).

## 동작 중립 fallback

코퍼스 파일이 없거나 비어 있으면 베이스 프롬프트만으로 동작한다 (`registry.py`의 오버레이
fallback 철학과 일관). 따라서 라벨이 0건이어도 분류 파이프라인은 정상 작동한다.
