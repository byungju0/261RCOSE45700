# crawler

NC 게임(리니지 / 아이온 / BNS / TL 등) 사설서버·매크로·핵 탐지를 위한 한·중·대만권 게시판 크롤링.

> **전체 현황·아키텍처·운영 다이얼은 [STATUS.md](./STATUS.md) 참조.** 이 문서는 빠른 시작 가이드입니다.

---

## 빠른 시작

```bash
cd crawler

# 1) 가상환경 생성 (최초 1회)
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate

# 2) 의존성 설치
pip install -r requirements.txt

# 3) Playwright Chromium (최초 1회만)
playwright install chromium

# 4) 단위/통합 테스트 (mock, 인터넷 불필요)
pytest -q                                          # 183 passed 예상

# 5) ruff 린트
ruff check crawler/ shared/ scripts/

# 6) 실 사이트 smoke (tieba/nga 자동 제외)
python scripts/smoke_each_site.py
python scripts/smoke_each_site.py bahamut_tl    # 특정 사이트만
```

---

## 디렉터리 구조

```
crawler/                         # 이 디렉터리 (monorepo 루트의 crawler/)
├── requirements.txt             # pip 의존성
├── pytest.ini
├── STATUS.md                    # ⭐ 전체 현황 / 아키텍처 / 사이트별 진단
├── README.md                    # 이 문서 (빠른 시작)
├── src/                         # 본체
│   ├── crawl4ai_crawler.py
│   ├── storage.py · s3_uploader.py
│   ├── preprocessor/            # content_validator, dedup_checker,
│   │                            # url_dedup_checker, language_detector, serializer
│   ├── queue/                   # redis_publisher
│   ├── scheduler/               # crawl_scheduler (CrawlPipeline + APScheduler),
│   │                            # trigger_listener, candidate_scoring, crawl_job_progress
│   └── sites/                   # registry — SiteConfig + SITES dict
└── tests/                       # unit + integration (183건)

# shared/  ← monorepo 루트에 위치 (../shared/)
#   crawl_event, redis_config, logger, interfaces/llm 등 공용
#   pip install -e ../shared 로 crawler venv에 링크됨 (requirements.txt 참조)
```

---

## 운영 (Redis 필요)

```bash
# 가상환경 활성화 후 실행 (또는 .venv/bin/python 직접 사용)
source .venv/bin/activate

# 가장 단순한 형태 — 기본 60분 주기, 운영 profile 사용
REDIS_URL=redis://localhost:6379 \
python -m crawler.src.scheduler.crawl_scheduler

# EC2 운영 권장값을 명시해서 실행
REDIS_URL=redis://localhost:6379 \
CRAWL_INTERVAL_MINUTES=60 \
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
INTER_SITE_DELAY_SECONDS=15 \
INTER_BOARD_DELAY_SECONDS=3 \
ENABLE_S3_UPLOAD=false \
python -m crawler.src.scheduler.crawl_scheduler
```

전체 환경변수 목록은 [STATUS.md §5](./STATUS.md#5-운영-다이얼-환경변수) 참조.

---

## 새 사이트 추가하기

`crawler/src/sites/registry.py` 의 `SITES` dict 에 한 줄 추가하면 끝.

```python
"my_new_board": SiteConfig(
    name="신규 보드",
    description="...",
    board_urls=["https://example.com/board/page1"],
    post_url_pattern=r"https://example\.com/post/\d+",
    css_selector=".article-body",
    # 필요 시 cookies / wait_for / headers / js_code / proxy / title_keywords 등
    enabled=True,
),
```

Validator는 prefix dispatch — `my_new_*` 같은 family 추가 시 `content_validator.py` 의 `PREFIX_VALIDATORS` 에 한 줄 추가하거나, `SITE_VALIDATORS` 에 정확 매칭으로 등록.

---

## 외부 서비스 의존성

| 서비스 | 용도 | 단위 테스트에선 |
|---|---|---|
| Redis | posts:queue, dedup, URL seen, crawl:trigger | MagicMock |
| boto3 / S3 | 옵션 (ENABLE_S3_UPLOAD=true 시) | unittest.mock.patch |
| crawl4ai (Playwright) | 브라우저 자동화 | patch("...AsyncWebCrawler") |

→ **`pytest` 는 외부 서비스 없이 100% mock 으로 동작.**
→ 실 사이트 smoke 만 인터넷 + Chromium 필요.

---

## 다음 단계

- [ ] 검색엔진형 추상화 (`SearchEngineConfig`) + github 첫 도전
- [ ] detection 서비스 연동 smoke 확대 (OpenAI 멀티모달 LLM)
- [ ] 중국 IP 프록시 인프라 (nga/tieba/baidu/sogou)

자세한 로드맵은 [STATUS.md §10](./STATUS.md#10-roadmap-우선순위) 참조.
