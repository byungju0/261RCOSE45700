# Crawler — Project Status

> NC 게임(리니지/아이온/BNS/TL 등) 사설서버·매크로·핵 탐지를 위한 한·중·대만권 게시판 크롤링 인프라.
> 이 문서는 현재 코드의 **상태·기능·운영 다이얼·남은 작업** 을 한 페이지로 정리합니다.

마지막 갱신: 2026-06-08

---

## 1. 한눈에

- **안정 보드**: 11곳 (인벤 2 + PTT Lineage + Bahamut NC 8)
- **운영 수집 profile**: `MAX_POSTS_PER_BOARD=30`, priority budget, detail concurrency 3, 52pojie serial
- **인프라**: URL 중복 차단, 본문 SHA256 dedup, 공지·인증벽·캡차 자동 분류, inter-site delay
- **테스트**: 183 unit/integration passed, ruff clean
- **detection(LLM)**: 별도 서비스에서 OpenAI 멀티모달 LLM 분류와 RDS 저장 처리

---

## 2. 아키텍처

```
                    ┌────────────────────────────────────┐
                    │   SiteConfig (사이트별 설정)         │
                    │   ─────────────────────              │
                    │   board_urls, post_url_pattern      │
                    │   css_selector, image_filter        │
                    │   cookies / wait_for / headers      │
                    │   js_code / delay_before_return     │
                    │   scan_full_page / virtual_scroll   │
                    │   simulate_user / user_agent_mode   │
                    │   title_keywords (NC 키워드 사전필터)│
                    │   proxy                              │
                    └────────────────┬───────────────────┘
                                     │
                                     ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ ① 게시판 listing → 게시글 URL N건                            │
   │    _fetch_post_urls(...)                                     │
   │    title_keywords 매칭 안 되면 즉시 drop (fetch 비용 절감)   │
   └────────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ ② Cross-run URL 중복 확인 — UrlDedupChecker.has_seen(url)    │
   │    Redis ZSET "posts:seen_urls", TTL 7일                     │
   │    이미 본 URL → skipped_seen_url (fetch 안 함)              │
   └────────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ ③ Crawl4AICrawler.fetch(url, site_options)                  │
   │    crawl4ai (Playwright + stealth) → CrawlResult             │
   └────────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ ④ content_validator.validate(site_id, markdown, url)         │
   │    kind ∈ {real, sticky, auth_wall, captcha, empty,          │
   │             short, error, unknown}                           │
   │    real 만 ⑤로 진행                                          │
   └────────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ ⑤ DedupChecker (본문 SHA256) → 중복이면 skip                 │
   │ ⑥ language_detector (langdetect)                             │
   │ ⑦ PostStorage (disk + 옵션 S3)                               │
   │ ⑧ to_crawl_event → CrawlEvent JSON                          │
   │ ⑨ RedisPublisher.enqueue("posts:queue")                      │
   │ ⑩ DedupChecker.mark_seen + UrlDedupChecker.mark_seen         │
   └────────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
                          [Detection 서비스]
                          (별도 — OpenAI 멀티모달 LLM + RDS 저장)
```

각 사이트 사이 `INTER_SITE_DELAY_SECONDS` (±25% jitter) 휴식, 같은 사이트의 보드 사이 `INTER_BOARD_DELAY_SECONDS` 휴식 → anti-bot rate limit 회피.

---

## 3. 사이트별 현황

### 🟢 안정 작동 (NC 데이터 흐름)

| site_id | 지역 | 보드 | NC real/run | 비고 |
|---|---|---|---|---|
| `inven_maple` | KR | inven /board/maple/2298 | 5/5 | 비교군 (NEXON, NC 아님) |
| `inven_lineage_classic` | KR | inven /board/lineageclassic/6482 | 5/5 | NC |
| `ptt` | TW | ptt /bbs/Lineage/ | 5/5 | over18 폼 js_code 자동 클릭 |
| `bahamut_lineage` | TW | bsn=842 | 3/5 | 天堂Lineage |
| `bahamut_lineage_m` | TW | bsn=25908 | 3/5 | 天堂M |
| `bahamut_lineage_w` | TW | bsn=71905 | 3/5 | 天堂W |
| `bahamut_lineage_classic` | TW | bsn=84452 | 4/5 | 天堂經典版 |
| `bahamut_aion` | TW | bsn=9856 | 3/5 | 永恆紀元 |
| `bahamut_aion2` | TW | bsn=82913 | 3/5 | AION2 |
| `bahamut_bns` | TW | bsn=12980 | 4/5 | 劍靈 |
| `bahamut_tl` | TW | bsn=33317 | 4/5 | 王權與自由 (TL) |

### 🟡 도달은 되나 NC 글 없음

| site_id | 지역 | 진단 | 처방 |
|---|---|---|---|
| `ptt_mobile_game` | TW | 동일 — Mobile-game 보드 1페이지에 NC 글 없음 | 동일 |

### 🔴 차단·실패

| site_id | 지역 | 원인 | 비고 |
|---|---|---|---|
| `52pojie` | CN | 0/5 — Windows 크랙 사이트라 NC 게임과 무관 | NC 타겟에선 우선순위 ↓ |
| `tieba` | CN | HTTP 403 anti-bot | 중국 본토 IP 필요 |
| `nga` | CN | HTTP 403 anti-bot | 중국 본토 IP 필요 |

### ⚫ 미구현 (검색엔진형 — 별도 추상화 필요)

`SiteConfig` 는 board → post URL 의 1-hop 게시판형. 검색엔진형은 query → 결과 → 외부 링크의 2-hop이라 `SearchEngineConfig` 신설 필요.

타겟: github, reddit, bing, baidu, sogou, duckduckgo_cn, bilibili, facebook (via Bing)

---

## 4. 핵심 인프라

### `SiteConfig` (`crawler/src/sites/registry.py`)

게시판 한 곳을 정의하는 dataclass. 모든 사이트별 동작은 이 필드로 표현됨.

| 필드 | 용도 |
|---|---|
| `board_urls`, `post_url_pattern` | listing URL + 게시글 URL 정규식 |
| `css_selector`, `image_filter`, `post_id_extractor` | 추출 |
| `cookies`, `headers`, `proxy` | 접근 옵션 |
| `wait_for`, `page_timeout`, `delay_before_return_html` | 렌더 대기 |
| `js_code`, `c4a_script` | 페이지 인터랙션 (PTT over18 자동 클릭 등) |
| `scan_full_page`, `scroll_delay`, `virtual_scroll_config`, `wait_until` | 동적 페이지 |
| `simulate_user`, `user_agent_mode` | anti-bot 흉내 |
| `exclude_social_media_links`, `exclude_external_links` | 링크 노이즈 제거 |
| `title_keywords` | **혼합 보드에서 NC 키워드 사전 필터** |
| `enabled`, `note` | 메타 |

### Validator (`crawler/src/preprocessor/content_validator.py`)

본문 → `PostValidation(is_real_user_post, kind, reason)`.

| kind | 의미 | enqueue 여부 |
|---|---|---|
| `real` | 진짜 사용자 글 | ✅ |
| `sticky` | 공지/导航/공식 행사 | ❌ |
| `auth_wall` | 로그인/연령 인증 인터스티셜 | ❌ |
| `captcha` | Cloudflare/캡차 챌린지 | ❌ |
| `empty` | 본문 0자 | ❌ |
| `short` | 본문 50자 미만 (Bahamut 200자) | ❌ |
| `error` | 4xx/5xx 페이지 | ❌ |
| `unknown` | 사이트 마커 미발견 (보수적 스킵) | ❌ |

**Prefix dispatch**: `bahamut_*` / `ptt_*` / `inven_*` family 가 자동으로 같은 validator 사용 → 새 보드 추가 시 등록 코드 0.

### UrlDedupChecker (`crawler/src/preprocessor/url_dedup_checker.py`)

Redis ZSET 기반 cross-run URL 중복 차단. **fetch 자체를 막아** 대역폭/시간 절감.
- `has_seen(url)` / `mark_seen(url)`
- `cleanup_older_than(age_seconds)` — 주기적 청소
- 기본 TTL: 7일

### DedupChecker (`crawler/src/preprocessor/dedup_checker.py`)

본문 SHA256 dedup. URL 은 달라도 본문이 같으면 (재발행/스크랩) 중복 처리.

---

## 5. 운영 다이얼 (환경변수)

| 변수 | 기본 | 의미 |
|---|---|---|
| `SERVICE_NAME` | `crawler` | 로그용 |
| `LOG_LEVEL` | `DEBUG` | INFO/WARNING 등 |
| `MAX_POSTS_PER_BOARD` | `30` | 보드 listing 당 최대 raw 후보 수 |
| `CRAWL_PRIORITY_BUDGET_ENABLED` | `true` | 제목 hard filter 대신 priority budget 적용 |
| `CRAWL_P3_DEFAULT_CAP_PER_BOARD` | `1` | 일반 source P3 샘플 cap |
| `CRAWL_P3_MIXED_CAP_PER_BOARD` | `5` | PTT mixed source P3 샘플 cap |
| `CRAWL_P3_52POJIE_CAP_PER_BOARD` | `1` | 52pojie P3 샘플 cap |
| `CRAWL_DETAIL_FETCH_CONCURRENCY` | `3` | 운영 detail fetch 기본 병렬성 |
| `CRAWL_DETAIL_SOURCE_CONCURRENCY` | `52pojie=1` | 민감 source serial 처리 |
| `CRAWL_DETAIL_FETCH_STAGGER_SECONDS` | `0.25` | detail batch 시작 stagger |
| `CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES` | `0` | Cloudflare retry 기본 off |
| `CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS` | `0` | source cooldown 기본 off |
| `CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS` | `0` | challenge cooldown 기본 off |
| `CRAWL_INTERVAL_MINUTES` | `60` | APScheduler 주기 |
| `INTER_SITE_DELAY_SECONDS` | `15` | 사이트 전환 휴식 (±25% jitter) |
| `INTER_BOARD_DELAY_SECONDS` | `3` | 보드 전환 휴식 (±25% jitter) |
| `REDIS_URL` | `redis://localhost:6379` | Redis endpoint |
| `ENABLE_S3_UPLOAD` | (unset=off) | true/1/yes → S3 미러 업로드 |
| `S3_BUCKET_NAME` | (none) | ENABLE_S3_UPLOAD=true 시 필수 |
| `AWS_REGION` | (none) | 옵션 |
| `SMOKE_INTER_SITE_DELAY` | `12` | smoke 스크립트의 사이트 간 휴식 |

### 운영 시나리오 (참고)

| 모드 | `MAX_POSTS_PER_BOARD` | `CRAWL_INTERVAL_MINUTES` | 예상 결과 |
|---|---|---|---|
| 운영 기본 | 30 + priority budget | 60 | EC2 1대 기준 안정/비용 균형 |
| EC2 빠른 실험 | 30 + priority budget | 60 | `CRAWL_DETAIL_FETCH_CONCURRENCY=4`만 1단계 실험 |
| 저부하 | 30 + priority budget | 120 | 2시간 주기, 비용/부하 절감 |
| 로컬 probe | 별도 | 수동 | `DETAIL_PROBE_FAST_MODE=1`, `DETAIL_PROBE_CONCURRENCY=10` |

UrlDedupChecker 덕분에 인터벌 단축해도 같은 URL 재fetch 안 함.

---

## 6. 폴더 구조

```
crawler/                              # monorepo 루트의 crawler/ 디렉터리
├── requirements.txt                  # pip 의존성 (pip install -r requirements.txt)
├── pytest.ini
├── .gitignore
├── README.md                         # 빠른 시작·실행 방법
├── STATUS.md                         # ← 이 문서
├── src/
│   ├── crawl4ai_crawler.py           # crawl4ai 래퍼 (BrowserConfig + 옵션)
│   ├── s3_uploader.py                # S3 업로드 (boto3, IAM 역할)
│   ├── storage.py                    # PostStorage (disk + S3)
│   ├── preprocessor/
│   │   ├── content_validator.py      # 사용자 글 vs 공지·차단 판별
│   │   ├── dedup_checker.py          # 본문 SHA256 dedup
│   │   ├── language_detector.py      # langdetect 래퍼
│   │   ├── url_dedup_checker.py      # cross-run URL dedup
│   │   └── serializer.py             # CrawlResult → CrawlEvent
│   ├── queue/
│   │   └── redis_publisher.py        # posts:queue LPUSH
│   ├── scheduler/
│   │   ├── crawl_scheduler.py        # CrawlPipeline + APScheduler
│   │   ├── trigger_listener.py       # Redis pub/sub 수동 트리거
│   │   ├── candidate_scoring.py      # 후보 URL 우선순위 점수 계산
│   │   └── crawl_job_progress.py     # 크롤 진행 상태 추적 (Redis)
│   └── sites/
│       └── registry.py               # SITES dict + SiteConfig + 헬퍼
└── tests/
    ├── conftest.py
    ├── unit/                         # 11개 모듈, 161건
    └── integration/                  # 파이프라인 E2E, 22건

# shared/  ← monorepo 루트 (../shared/)에 위치, pip install -e ../shared 로 링크됨
#   ├── correlation_id.py
#   ├── structured_logger.py
#   ├── config/redis_config.py
#   ├── exceptions/base_exception.py
#   ├── models/crawl_event.py
#   └── interfaces/llm.py
└── scripts/
    └── smoke_each_site.py            # 실 사이트 smoke 테스트 (수동 실행)
```

---

## 7. 실행 / 테스트 / smoke

```bash
cd crawler
source .venv/bin/activate     # .venv 없으면: python3 -m venv .venv && pip install -r requirements.txt

# 전체 테스트 (mock 기반, 인터넷 불필요)
pytest -q                           # 183 passed

# ruff 린트
ruff check crawler/ shared/ scripts/

# 실 사이트 smoke (전체 — tieba/nga 자동 제외)
python scripts/smoke_each_site.py

# 특정 사이트만
python scripts/smoke_each_site.py bahamut_tl

# 운영 (Redis 필요)
REDIS_URL=redis://localhost:6379 \
MAX_POSTS_PER_BOARD=30 \
CRAWL_PRIORITY_BUDGET_ENABLED=true \
CRAWL_P3_DEFAULT_CAP_PER_BOARD=1 \
CRAWL_P3_MIXED_CAP_PER_BOARD=5 \
CRAWL_P3_52POJIE_CAP_PER_BOARD=1 \
CRAWL_DETAIL_FETCH_CONCURRENCY=3 \
CRAWL_DETAIL_SOURCE_CONCURRENCY=52pojie=1 \
CRAWL_DETAIL_FETCH_STAGGER_SECONDS=0.25 \
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=0 \
CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS=0 \
CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS=0 \
CRAWL_INTERVAL_MINUTES=60 \
python -m crawler.src.scheduler.crawl_scheduler
```

---

## 8. 이번 사이클까지 마친 주요 작업

1. **레지스트리 NC 재타겟** — Bahamut 단일 `bahamut`(원신) → NC 8개 게임 site_id 로 분리
2. **PTT** — C_Chat 보드에서 NC Lineage 보드로 교체 + over18 폼 js_code 자동 통과
3. **`title_keywords`** — 혼합 보드(PTT Mobile-game)의 listing 단계 사전 필터
4. **`UrlDedupChecker`** — Redis ZSET 기반 cross-run URL 중복 차단 (Tier 1)
5. **`content_validator`** — 8-kind 분류 + prefix dispatch (`bahamut_*` 등)
6. **Bahamut validator** — chrome 마커 의존 제거, **길이 기반** 으로 전환 (셀렉터 결과 호환)
7. **Inter-site / inter-board delay** — 환경변수 + ±25% jitter (Bahamut rate limit 해결)
8. **모던 crawl4ai 옵션** 11개 SiteConfig 필드 노출 (scan_full_page, virtual_scroll_config, simulate_user, user_agent_mode, c4a_script 등)
9. **Smoke retry-once** — 일시 anti-bot 회복
10. **인프라 정리** — .gitignore, ruff 설정, __pycache__ 청소

---

## 9. Known Issues / Limitations

| 항목 | 영향 | 대응 |
|---|---|---|
| Tieba/NGA HTTP 403 (한국 IP) | NC 중국권 데이터 불가 | 중국 residential 프록시 인프라 필요 |
| PTT Mobile-game 1페이지에 NC 글 0 | 시간당 0~2건 누락 가능 | 페이지네이션 또는 검색 source 보강 |
| 52pojie NC 무관 | NC 타겟엔 무용 | NC 외 외掛 일반 데이터 필요 시 유지, NC 전용엔 제외 |
| 검색엔진형 (github/reddit/bing/baidu/...) 미구현 | 광범위 recall 못 함 | `SearchEngineConfig` 추상화 신설 |
| crawler→detection 운영 smoke 부족 | 수집 후 분류·저장까지의 실운영 검증이 약함 | Redis queue 기반 end-to-end smoke 확대 |

---

## 10. Roadmap (우선순위)

1. **검색엔진형 추상화 + github** — 가장 쉬운 검색엔진. 추상화 검증용
2. **ptt_mobile_game 페이지네이션** — 작은 fix
3. **crawler→detection end-to-end smoke** — Redis queue 입력부터 OpenAI 분류, RDS 저장까지 검증
4. **검색엔진형 확장** — reddit, bing, duckduckgo_cn
5. **프록시 풀 통합** — 중국 IP 확보 후 nga/tieba/baidu/sogou 가동
6. **per-board `last_seen_post_id`** (Tier 2 dedup) — 페이지네이션 효율 ↑

---

## 11. 참고

- crawl4ai 공식 문서: <https://docs.crawl4ai.com/>
- LLM extraction strategy: `LLMExtractionStrategy` (현재 미사용, detection 서비스가 분류 담당)
- 본 리포의 디자인 원칙: **크롤은 빠르고 단순하게, 분류·저장은 detection 서비스로 분리**
