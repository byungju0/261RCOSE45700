# Crawling Research and Redesign Notes

작성일: 2026-06-05

목적: 현재 크롤링 구조를 코드 기준으로 정리하고, "화면에 뜨는 데이터 수가 적다"는 피드백의 원인을 분석하며, 불법 프로그램 탐지 목적에 맞는 수집량 확대/재설계 방향과 참고자료를 기록한다.

## 1. 현재 구조 요약

현재 크롤러는 `crawler` Python 서비스가 담당한다. 핵심 구현은 `crawler/src/scheduler/crawl_scheduler.py`, 실제 브라우저 fetch 래퍼는 `crawler/src/crawl4ai_crawler.py`, 사이트별 설정은 `crawler/src/sites/registry.py`에 있다.

전체 흐름은 다음과 같다.

1. `SiteConfig`에서 활성 사이트와 `board_urls`, `post_url_pattern`, `css_selector`, `title_keywords` 등을 읽는다.
2. `_fetch_post_urls()`가 게시판 listing 페이지를 Crawl4AI/Playwright로 열고 링크를 추출한다.
3. `title_keywords`가 있으면 링크 제목이 키워드와 매칭되는 URL만 fetch 대상으로 남긴다.
4. `UrlDedupChecker`가 이미 처리한 URL이면 fetch 자체를 생략한다.
5. `Crawl4AICrawler.fetch()`가 게시글 본문과 이미지를 수집한다.
6. `content_validator.validate()`가 실제 사용자 글인지 판정한다. `real`만 다음 단계로 간다.
7. `DedupChecker`가 본문 SHA256 중복을 제거한다.
8. `PostStorage`가 원문을 로컬/S3에 저장한다.
9. `to_crawl_event()`가 `CrawlEvent` JSON을 만들고 `posts:queue`에 enqueue한다.
10. `detection` 서비스가 Redis queue를 소비해 LLM 분류 후 RDS에 저장한다.
11. Spring API와 React dashboard가 탐지 결과를 조회해 보여준다.

중요 코드 지점:

- `crawler/src/scheduler/crawl_scheduler.py`
  - `MAX_POSTS_PER_BOARD` 기본값: 30
  - `_fetch_post_urls()`: listing에서 게시글 URL 추출
  - `title_keywords` 불일치 URL drop
  - 사이트/보드/게시글 순차 처리
  - validator에서 `real`만 enqueue
- `crawler/src/sites/registry.py`
  - 현재 활성 사이트와 혼합 보드의 `title_keywords` 설정
  - `tieba`, `nga`는 anti-bot/계정 장벽으로 disabled
- `shared/models/crawl_event.py`
  - strict schema. unknown field가 있으면 consumer가 실패한다.
- `api/src/main/java/com/tracker/api/repository/DetectionRepository.java`
  - 목록 조회는 `confidence >= 0.70` 및 `illegal = true`만 반환한다.

## 2. 현재 수집량이 작아지는 직접 원인

### 2.1 후보 발견량이 작다

`MAX_POSTS_PER_BOARD=30`이고, 대부분의 사이트가 첫 listing 페이지 중심으로 동작한다. 페이지네이션, 검색 쿼리 기반 discovery, sitemap/Common Crawl 기반 seed 확장은 아직 없다.

따라서 "크롤링을 많이 했는데 화면에 적게 뜬다"기보다는, 코드상 현재 크롤러 자체가 보수적으로 적은 후보만 본다.

### 2.2 `title_keywords`가 recall을 줄인다

Dcard, PTT Mobile-game 같은 혼합 보드는 `title_keywords`가 설정되어 있고, 제목에 NC 게임 키워드가 없으면 fetch 전에 버린다.

이 정책은 비용 절감에는 좋지만 불법 프로그램 탐지 목적에는 위험하다. 불법 프로그램 판매/배포 글은 제목에 직접 게임명이나 "핵", "매크로"를 쓰지 않고 우회 표현, 은어, 이미지, 외부 연락처만 둘 수 있다.

현재 방식:

```python
if keywords_lower and not any(k in link_title.lower() for k in keywords_lower):
    continue
```

이 조건은 "후보 점수 낮음"이 아니라 "수집하지 않음"으로 처리한다. 그래서 혼합 보드에서 잠재적 탐지 대상이 누락될 수 있다.

### 2.3 모든 게시글 fetch가 순차 실행된다

`_process_board()`에서 URL 목록을 받은 뒤 게시글을 하나씩 `await self._process_post(...)`한다. EC2 1개 환경에서 무제한 병렬은 피해야 하지만, 현재는 병렬성이 거의 없어 수집량을 늘리면 실행 시간이 선형으로 늘어난다.

### 2.4 validator가 너무 보수적으로 큐 진입을 막는다

`content_validator`는 `real`, `sticky`, `auth_wall`, `captcha`, `empty`, `short`, `error`, `unknown`을 구분한다. 현재 pipeline은 `real`만 enqueue한다.

큐 오염 방지에는 좋지만, selector 변화나 사이트별 chrome 제거 때문에 `unknown`이 되는 글이 생기면 모두 탐지 대상에서 사라진다. 불법 탐지는 희귀 이벤트라 `unknown` 중 일부를 샘플링해 분석하는 구조가 필요하다.

### 2.5 화면은 더 좁게 필터링된다

API 목록 조회는 `confidence >= 0.70`이고 `illegal = true`인 detection만 반환한다. 즉 화면 수는 다음 중 가장 마지막 단계의 수다.

발견 후보 수 -> fetch 성공 수 -> validator real 수 -> queue enqueue 수 -> LLM 처리 수 -> 불법 판정 수 -> confidence 0.70 이상 수

따라서 화면 count만 보고 크롤러 수집량을 판단하면 안 된다. 별도의 funnel metric이 필요하다.

## 3. 현재 사이트 구성에 대한 판단

현재 안정적으로 수집되는 주력은 Inven, PTT Lineage, Bahamut NC 전용 보드들이다. 이들은 실제 게임 커뮤니티 데이터에는 적합하지만, 불법 프로그램 판매/배포 탐지에는 너무 일반 게시판 중심일 수 있다.

불법 프로그램 탐지 목적이라면 source category를 넓혀야 한다.

- 게임 전용 커뮤니티: 현재 구조 유지
- 혼합 게임 커뮤니티: keyword hard filter를 priority scoring으로 변경
- 크랙/리버싱/cheat 커뮤니티: 52pojie 같은 일반 크랙 사이트는 NC relevance가 낮으므로 source score가 필요
- 검색 기반 source: Bing, Baidu/Sogou, DuckDuckGo, GitHub, Reddit 등은 별도 `SearchEngineConfig` 필요
- 판매/배포 landing page: 게시판형 crawler만으로는 부족하므로 search seed와 external link 추적 필요

## 4. 참고자료와 시사점

### 4.1 Crawl4AI Deep Crawling

출처: https://docs.crawl4ai.com/core/deep-crawling/

핵심 내용:

- BFS, DFS, BestFirst 방식으로 seed URL에서 여러 depth를 탐색할 수 있다.
- `max_depth`, `max_pages`, `include_external` 같은 제한을 걸 수 있다.
- keyword scoring과 best-first 탐색을 결합하면 모든 링크를 무작정 따라가지 않고 관련성 높은 후보부터 볼 수 있다.

우리에게 주는 시사점:

- 현재 `board_urls -> post_urls` 1-hop 구조를 보완할 수 있다.
- 단, EC2 1개 환경에서는 `include_external=True`와 큰 `max_depth`는 비용/시간 폭발 위험이 있다.
- 우선은 기존 보드 페이지네이션과 제한된 best-first만 적용하는 것이 현실적이다.

### 4.2 Crawl4AI Multi-URL Crawling

출처: https://docs.crawl4ai.com/advanced/multi-url-crawling/

핵심 내용:

- `arun_many()`와 dispatcher를 통해 여러 URL을 효율적으로 처리할 수 있다.
- `MemoryAdaptiveDispatcher`, `RateLimiter`를 사용하면 메모리와 rate limit을 고려한 병렬 처리가 가능하다.

우리에게 주는 시사점:

- 현재 게시글 fetch가 순차라서 수집량 증가 시 실행 시간이 빠르게 늘어난다.
- EC2 1대 기준으로 browser fetch concurrency를 2~3 정도로 제한하고, source별 rate limit을 유지하는 방식이 적절하다.

### 4.3 Crawl4AI URL Seeding

출처: https://docs.crawl4ai.com/core/url-seeding/

핵심 내용:

- sitemap, Common Crawl, query 기반 seed 수집을 지원한다.
- `max_urls`, cache TTL, query/BM25 같은 제한과 랭킹 개념을 사용할 수 있다.

우리에게 주는 시사점:

- 게시판 첫 페이지 중심 수집의 한계를 넘으려면 seed discovery 계층이 필요하다.
- 검색 기반 수집은 노이즈가 크므로 바로 LLM으로 보내지 않고 cheap prefilter와 priority queue를 거쳐야 한다.

### 4.4 Crawl4AI Domain Mapping

출처: https://docs.crawl4ai.com/core/domain-mapping/

핵심 내용:

- 특정 domain의 구조와 링크 관계를 파악하는 데 사용할 수 있다.

우리에게 주는 시사점:

- 새로운 커뮤니티/판매 사이트를 발견했을 때 board/list/detail 구조를 빠르게 파악하는 도구로 쓸 수 있다.
- 운영 crawler에 바로 넣기보다는 source onboarding/smoke 단계에서 유용하다.

### 4.5 Crawl4AI LLM-free Extraction

출처: https://docs.crawl4ai.com/extraction/no-llm-strategies/

핵심 내용:

- CSS/XPath 기반 JSON extraction으로 LLM 없이 구조화 추출이 가능하다.

우리에게 주는 시사점:

- title, author, reply count, external links, attachment links, contact text 같은 cheap metadata를 LLM 전에 추출할 수 있다.
- LLM 비용을 줄이려면 "전수 LLM"보다 "cheap extraction + scoring + selective LLM"이 맞다.

### 4.6 Crawl4AI BrowserConfig/SDK

출처: https://docs.crawl4ai.com/complete-sdk-reference/

핵심 내용:

- `text_mode`, `light_mode`, `avoid_ads`, `avoid_css` 등 성능 최적화 옵션이 있다.

우리에게 주는 시사점:

- 이미지가 중요하지 않은 source는 text 중심으로 가볍게 돌리고, 이미지/스크린샷은 고위험 후보에만 적용하는 전략이 가능하다.

### 4.7 Crawl4AI Proxy/Security

출처: https://docs.crawl4ai.com/advanced/proxy-security/

핵심 내용:

- proxy configuration을 지원한다.

우리에게 주는 시사점:

- Tieba/NGA 같은 중국권 anti-bot source는 proxy만으로 해결되지 않을 수 있다.
- 계정/실명/휴대폰 장벽이 있는 source는 비용과 법적/운영상 리스크가 커서 당장 1순위로 두지 않는 것이 맞다.

### 4.8 AWS EC2 Pricing

출처: https://aws.amazon.com/ec2/pricing/on-demand/

핵심 내용:

- On-Demand는 실행 시간 기준 과금이다.
- T 계열 인스턴스는 CPU credit/Unlimited 설정에 따라 비용과 성능 리스크가 있다.
- 일반적으로 일정량의 data transfer out free tier가 있지만, 조건과 리전 정책 확인이 필요하다.

우리에게 주는 시사점:

- Playwright 병렬성을 무작정 올리면 CPU/memory/credit 문제가 생긴다.
- browser concurrency는 2~3부터 시작하고, source별 rate limit과 run duration을 모니터링해야 한다.

### 4.9 AWS RDS Pricing

출처: https://aws.amazon.com/rds/pricing/

핵심 내용:

- instance hour, storage, backup, I/O, data transfer가 비용 요소다.

우리에게 주는 시사점:

- 모든 raw body와 이미지를 RDS에 장기 보관하면 비용이 커진다.
- RDS에는 metadata와 detection summary를 두고, raw text/image는 S3 또는 로컬 archive에 두는 구조가 낫다.
- 정상(T4) 데이터는 retention을 짧게 가져가는 정책을 고려해야 한다.

### 4.10 Underground Marketplace Crawling Research

출처: https://publications.sba-research.org/publications/undergroundmarketplaces.pdf

핵심 내용:

- underground marketplace는 transient하고, 일반 웹/포럼/정상 서비스 위에 숨어 있을 수 있다.
- 단순 naive crawler만으로는 충분한 coverage를 얻기 어렵다.

우리에게 주는 시사점:

- 정해진 게임 게시판만 보는 방식은 불법 프로그램 탐지 coverage가 낮을 수 있다.
- discovery, source scoring, entity/contact signal 추출이 필요하다.

### 4.11 Illicit Market Detection with Language Models

출처: https://arxiv.org/abs/2507.22912

핵심 내용:

- sales-related document detection과 illicit category classification을 단계적으로 결합한다.
- bitcoin/email/IP/metadata/structure 같은 engineered features를 함께 사용한다.

우리에게 주는 시사점:

- 우리도 바로 "불법 프로그램인가?"만 묻기보다 먼저 "판매/배포/거래 의도가 있는가?"를 cheap classifier 또는 regex score로 잡는 것이 좋다.
- contact, price, download, update, subscription, proof/review 같은 feature가 중요하다.

### 4.12 Automated Discovery of Cyber Threats from the Internet

출처: https://arxiv.org/abs/2109.06932

핵심 내용:

- clear web, social web, dark web 등 다양한 source에서 ML 기반 discovery와 ranking을 사용한다.

우리에게 주는 시사점:

- crawler는 단순 수집기가 아니라 "발견 -> 랭킹 -> 분석" pipeline이어야 한다.
- source별 품질과 yield를 측정해 우선순위를 계속 조정해야 한다.

### 4.13 Content Moderation/Undesired Content Detection

출처: https://arxiv.org/abs/2208.03274

핵심 내용:

- taxonomy, labeling instruction, data quality, active learning이 중요하다.
- rare/undesired content 탐지는 단순 keyword matching만으로 부족하다.

우리에게 주는 시사점:

- false negative를 줄이려면 keyword miss 샘플과 validator unknown 샘플을 사람이 확인하는 feedback loop가 필요하다.
- human label을 수집하고 prompt/keyword/source score를 계속 갱신해야 한다.

### 4.14 Game Cheat Community Research

출처:

- https://dspace.networks.imdea.org/handle/20.500.12761/1514
- https://suarez-tangil.networks.imdea.org/papers/2021esorics-cheaters.pdf

핵심 내용:

- MPGH, UnknownCheats 같은 game cheating community에서는 author, reply, download, reputation, attachment metadata가 의미 있는 signal이 된다.

우리에게 주는 시사점:

- 게시글 본문만 저장하면 부족하다.
- author/handle, reply count, view count, download/attachment link, external contact, reputation 같은 metadata를 저장해야 한다.
- 단, binary/attachment 다운로드는 법적/보안 리스크가 있으므로 운영 infra에서는 metadata만 저장하는 것이 안전하다.

### 4.15 Cheat Selling Website Study

출처: https://wrap.warwick.ac.uk/id/eprint/188803/

핵심 내용:

- game cheat 판매 웹사이트 자체가 별도 시장을 이룬다.

우리에게 주는 시사점:

- 일반 게임 커뮤니티만으로는 판매 사이트/landing page를 놓칠 수 있다.
- source category에 `cheat_seller`, `forum`, `marketplace`, `general_game_board`, `search_result` 같은 구분이 필요하다.

## 5. 우리가 내린 설계 방향

현재 구조를 바로 전면 교체하기보다 단계적으로 바꾼다. 핵심 원칙은 다음과 같다.

1. title keyword를 hard filter로 쓰지 말고 priority score로 쓴다.
2. 더 많이 수집하되, 비싼 LLM은 고위험 후보 위주로 쓴다.
3. 검색/딥크롤은 제한된 seed와 max page/depth 안에서만 쓴다.
4. source별 yield를 측정해 돈이 안 되는 source는 낮은 우선순위로 내린다.
5. 화면 count와 crawler count를 분리해서 funnel을 관측한다.

## 6. 제안하는 새 파이프라인

### 6.1 Discovery Layer

입력:

- 기존 `SiteConfig.board_urls`
- page rule로 확장한 게시판 페이지
- 검색 쿼리 seed
- sitemap/Common Crawl seed
- 사람이 추가한 seed URL

출력:

- `CandidatePost`

예상 필드:

```python
CandidatePost(
    url: str,
    title: str,
    board_url: str,
    source_id: str,
    source_category: str,
    matched_keywords: list[str],
    risk_signals: list[str],
    priority: str,  # P0/P1/P2/P3/P4
    score: float,
    discovery_reason: str,
)
```

### 6.2 Cheap Scoring Layer

LLM 전에 regex/metadata 기반 점수를 계산한다.

신호 예시:

- 판매/거래: `판매`, `팝니다`, `문의`, `분양`, `임대`, `대여`, `체험판`, `후기`, `인증`
- 가격/구독: `원`, `만원`, `월정액`, `구독`, `충전`, `月`
- 연락처: `Telegram`, `텔레그램`, `Discord`, `QQ`, `WeChat`, `Kakao`, `오픈채팅`
- cheat/automation: `매크로`, `오토`, `자동사냥`, `헬퍼`, `外挂`, `外掛`, `辅助`, `inject`, `loader`, `bypass`, `undetected`, `ESP`, `wallhack`
- 배포/다운로드: `다운로드`, `download`, `배포`, `更新`, `버전`, `loader`

### 6.3 Priority Buckets

- `P0`: 판매/배포/연락처/가격 신호가 명확한 후보
- `P1`: NC 게임명 + cheat/automation 신호
- `P2`: NC 전용 보드 일반 글
- `P3`: 혼합 보드에서 keyword miss지만 샘플링한 글
- `P4`: validator unknown/short 샘플

처리 정책:

- `P0/P1`: LLM 우선 처리
- `P2`: 일정량 처리
- `P3/P4`: 낮은 비율로 샘플링해 false negative 확인

### 6.4 Detection Layer

현재 LLM pipeline은 유지하되, `CrawlEvent`에 priority와 risk metadata를 넘긴다. prompt에는 source category와 matched signals를 함께 제공한다.

### 6.5 Feedback Loop

human label과 false negative 분석 결과를 바탕으로 다음을 갱신한다.

- keyword dictionary
- risk signal regex
- source priority
- validator policy
- LLM prompt/few-shot examples

## 7. 코드 수정 계획

### Phase 1. 관측성 추가

목표: 왜 적은지 수치로 확인한다.

추가/수정:

- `PipelineStats` 확장
- board 단위 stats 추가
- `crawl_runs`, `crawl_board_stats` DB migration 추가
- API에 crawl funnel endpoint 추가
- dashboard에 수집 현황/소스 상태 표시

필요 metric:

- `found_urls`
- `keyword_filtered`
- `sampled_keyword_miss`
- `seen_url_skipped`
- `fetched`
- `validator_real`
- `validator_unknown`
- `validator_sticky`
- `validator_blocked`
- `dedup_skipped`
- `enqueued`
- `failed`
- `duration_ms`

### Phase 2. title keyword 정책 변경

목표: 혼합 보드에서 후보를 너무 일찍 버리지 않는다.

수정:

- `_fetch_post_urls()`를 `_discover_candidates()`로 변경
- 반환값을 `list[str]`에서 `list[CandidatePost]`로 변경
- `title_keywords` 불일치는 drop이 아니라 `P3` 후보로 둔다.
- `P3_SAMPLE_RATE` 환경변수 추가

### Phase 3. 페이지네이션 추가

목표: 기존 안정 source에서 후보량을 싸게 늘린다.

수정:

- `SiteConfig`에 `max_pages`, `pagination_kind`, `pagination_template` 또는 page generator 추가
- Inven/PTT/Bahamut부터 2~5페이지 확장
- Dcard는 full scan/search URL 실험 후 적용

### Phase 4. 제한 병렬 처리

목표: EC2 1대에서 실행 시간을 줄이되 차단/메모리 리스크를 통제한다.

수정:

- source별 semaphore 또는 global `CRAWL_FETCH_CONCURRENCY=2~3`
- Crawl4AI `arun_many()`/dispatcher 적용 검토
- source별 delay/rate limit 유지

### Phase 5. Event/DB metadata 확장

목표: 탐지와 분석에 필요한 후보 metadata를 보존한다.

수정:

- `CrawlEvent` v2 필드 추가
- `to_crawl_event()` 수정
- detection repository에서 posts/detections/crawl metadata 저장
- Flyway migration 추가
- strict schema 변경 시 backward compatibility 고려

추가 후보 필드:

- `title`
- `board_url`
- `source_category`
- `candidate_priority`
- `matched_keywords`
- `risk_signals`
- `discovery_reason`

### Phase 6. 검색엔진형 source 추가

목표: 게시판 첫 페이지 밖의 판매/배포 후보를 발견한다.

수정:

- `SearchEngineConfig` 신설
- query template 관리
- search result dedup
- search result source category 저장
- P0/P1 중심 LLM 처리

초기 query 예시:

- `"리니지" "매크로" "텔레그램"`
- `"天堂M" "外掛" "購買"`
- `"AION" "辅助" "QQ"`
- `"TL" "macro" "discord"`
- `"Lineage" "bot" "undetected"`

## 8. 비용 관점의 운영 원칙

현재 인프라는 EC2 1개 + RDS 1개다. 따라서 다음 원칙을 둔다.

1. Playwright concurrency는 2~3부터 시작한다.
2. `MAX_POSTS_PER_BOARD`는 10에서 바로 100으로 올리지 않고 20 정도부터 올린다.
3. Deep crawl은 `max_pages`, `max_depth`, source allowlist가 있을 때만 사용한다.
4. 검색 결과는 바로 LLM에 보내지 않고 cheap scoring을 거친다.
5. 이미지 다운로드와 멀티모달 LLM은 P0/P1 중심으로 제한한다.
6. binary/attachment는 다운로드하지 않고 URL/metadata만 저장한다.
7. RDS에는 metadata와 결과를 저장하고 raw text/image는 S3/local archive로 분리한다.
8. 정상(T4) 또는 저위험 데이터는 retention을 짧게 설정한다.

## 9. 최종 판단

현재 피드백의 핵심 원인은 "크롤러가 작동하지 않는다"가 아니다. 현재 크롤러는 의도적으로 보수적으로 설계되어 있다.

하지만 우리의 목표가 불법 프로그램 탐지라면, 현재 설계는 너무 선택적이다. 특히 다음 정책들이 recall을 낮춘다.

- 게시판 첫 페이지 중심
- 보드당 10개 제한
- `title_keywords` hard drop
- `real` 외 validator 결과 전부 skip
- 검색/외부 seed 없음
- 화면은 고신뢰 불법만 표시

따라서 앞으로의 방향은 "더 많이 긁기"가 아니라 "더 넓게 발견하고, 싸게 점수화하고, 비싼 분석을 선택적으로 수행하는 구조"다.

우선순위는 다음과 같다.

1. crawl funnel metric을 먼저 만든다.
2. `title_keywords`를 hard filter에서 priority score로 바꾼다.
3. 기존 안정 보드 페이지네이션으로 후보량을 늘린다.
4. cheap risk signal scorer를 추가한다.
5. `CrawlEvent`와 DB에 candidate metadata를 확장한다.
6. 검색엔진형 discovery를 별도 source로 추가한다.

## 10. 추가 검증 조사

작성일: 2026-06-05

목적: 위 판단이 외부 연구/실무 사례와 맞는지 추가로 확인했다.

### 10.1 판단 검증 결과

추가 조사 결과, 우리의 판단은 대체로 맞다.

특히 다음 방향은 여러 자료와 일치한다.

1. keyword hard filter만으로는 희귀/우회 콘텐츠 탐지 recall이 낮아질 수 있다.
2. crawler는 단순 수집기가 아니라 focused discovery와 ranking 구조를 가져야 한다.
3. 불법/유해 콘텐츠 탐지는 active learning, human review, labeling loop가 중요하다.
4. LLM 전수 분류보다 cheap metadata/regex/feature extraction 후 selective LLM이 비용 측면에서 유리하다.
5. game cheat 탐지는 게시글 본문뿐 아니라 attachment, download count, author, reply, reputation, source category metadata가 중요하다.

### 10.2 Focused Crawling 연구

출처: https://link.springer.com/article/10.1186/s13635-017-0064-5

핵심 내용:

- focused crawler는 topic relevance를 추정해 어떤 hyperlink를 따라갈지 선택한다.
- surface web과 dark web 모두에서 classifier-guided hyperlink selection을 사용한다.
- 링크 주변 evidence, parent page classifier, destination page classifier를 함께 고려한다.

우리 판단과의 관계:

- 우리가 제안한 `CandidatePost` + priority score 구조와 맞다.
- 단순 `board_urls -> first page -> 10 posts` 구조는 focused crawler라기보다 fixed-source sampler에 가깝다.
- 불법 프로그램 탐지 목적이면 link/title/body/context 기반 ranking이 필요하다.

### 10.3 Focused Crawler의 Best-First/Seed 전략

출처: https://en.wikipedia.org/wiki/Focused_crawler

핵심 내용:

- focused crawling은 seed URL에서 시작해 topic relevance가 높은 링크를 우선 탐색한다.
- search engine 결과나 high quality seed URL을 시작점으로 쓰는 전략이 흔하다.
- DOM/text/link context를 이용해 crawler를 guide할 수 있다.

우리 판단과의 관계:

- 검색엔진형 `SearchEngineConfig`와 seed pool을 별도로 두자는 판단을 뒷받침한다.
- keyword를 drop 조건으로만 쓰기보다 ranking feature로 써야 한다.

### 10.4 Real-World Content Moderation과 Active Learning

출처: https://arxiv.org/abs/2208.03274

핵심 내용:

- real-world undesired content detection은 taxonomy, labeling instruction, data quality, active learning pipeline이 함께 필요하다.
- rare events를 포착하기 위한 active learning이 중요하다.

우리 판단과의 관계:

- `P3` keyword-miss sample, `P4` validator-unknown sample을 일부 남겨 human review하는 방향이 타당하다.
- 지금처럼 `unknown`을 전부 버리면 false negative를 학습할 기회가 없다.
- 화면에는 고신뢰 불법만 보여도 되지만, 운영/학습용 review queue는 따로 필요하다.

### 10.5 Proactive Content Moderation의 비용/확장성

출처: https://link.springer.com/article/10.1140/epjds/s13688-024-00505-x

핵심 내용:

- 대규모 proactive moderation은 cost efficiency와 scalability가 중요하다.
- active learning 기법으로 성능 개선을 탐색한다.

우리 판단과의 관계:

- EC2 1개 + RDS 1개 환경에서 전수 Playwright/전수 LLM은 맞지 않는다.
- cheap scoring과 selective LLM을 쓰자는 판단이 비용 관점에서 합리적이다.

### 10.6 Illicit Marketplace Detection 연구

출처: https://arxiv.org/abs/2507.22912

핵심 내용:

- 다양한 플랫폼의 illicit marketplace content는 언어가 계속 변하고 source 구조도 이질적이다.
- hierarchical classification을 사용한다.
- document structure, Bitcoin address, email, IP, metadata 같은 engineered features를 LLM/embedding과 함께 쓴다.

우리 판단과의 관계:

- 한 번에 "불법 프로그램인가?"만 분류하지 말고, 먼저 sales/distribution intent를 cheap하게 잡는 구조가 맞다.
- contact/price/download/update/review signal을 feature로 뽑아야 한다.
- source별 구조 차이를 metadata로 남기는 것이 중요하다.

### 10.7 Information Extraction in Illicit Web Domains

출처: https://usc-isi-i2.github.io/papers/kejriwal17-www.pdf

핵심 내용:

- illicit domain에서는 high recall과 high precision을 동시에 얻기 어렵다.
- domain knowledge, recognizer, surrounding context를 활용한다.

우리 판단과의 관계:

- strict keyword filter는 precision을 올릴 수 있지만 recall을 낮출 위험이 크다.
- keyword miss 샘플링과 context feature 추출을 같이 해야 한다.

### 10.8 Game Cheat Forum 연구

출처:

- https://dspace.networks.imdea.org/handle/20.500.12761/1514
- https://suarez-tangil.networks.imdea.org/papers/2021esorics-cheaters.pdf

핵심 내용:

- MPGH와 UnknownCheats 같은 game cheating forum은 수백만 게시글 규모다.
- 연구는 attachment, attachment file type, download count, game association, author/reply 같은 forum metadata를 활용한다.
- injector는 cheat payload를 게임 프로세스에 주입하는 핵심 도구로 다뤄진다.

우리 판단과의 관계:

- 현재 `CrawlEvent`가 body/image URL 중심인 것은 부족하다.
- `author`, `reply_count`, `view_count`, `attachment_links`, `download_count`, `external_links`, `game_association` 같은 필드가 필요하다.
- 단, 운영 infra에서 binary attachment를 직접 다운로드하는 것은 보안/법적 리스크가 있으므로 metadata 중심 수집이 맞다.

### 10.9 Game Cheat Selling Market 조사

출처:

- https://wrap.warwick.ac.uk/id/eprint/188803/
- https://www.eurekalert.org/news-releases/1061994
- https://www.wired.com/story/inside-the-multimillion-dollar-grey-market-for-video-game-cheats/

핵심 내용:

- game cheat는 dedicated selling website, reseller, Discord/community, forum 등 다양한 채널에서 유통된다.
- 일부 연구/보도는 80개 안팎의 cheat selling website와 큰 시장 규모를 언급한다.

우리 판단과의 관계:

- 일반 게임 커뮤니티 board만으로는 판매 사이트와 reseller 네트워크를 놓친다.
- source category를 `general_game_board`, `cheat_forum`, `seller_site`, `reseller_social`, `search_result`로 나누는 것이 맞다.
- 검색 기반 discovery와 external link 추적이 필요하다.

### 10.10 상용 Brand/Marketplace Monitoring 사례

출처:

- https://www.marketplacemonitor.online/
- https://clusterforensics.com/
- https://edghaz.com/
- https://extralt.com/
- https://merchanthq.io/

핵심 내용:

- 상용 모니터링 제품들은 대부분 여러 플랫폼을 지속적으로 scan하고, listing/image/seller/price/contact/network signal을 구조화한다.
- evidence archive, seller/entity mapping, risk scoring, analyst oversight를 강조한다.

우리 판단과의 관계:

- 우리가 생각한 `raw crawl -> enrichment -> risk score -> analyst/review -> enforcement-ready evidence` 흐름과 유사하다.
- 단순 detection list보다 source evidence와 seller/entity graph가 장기적으로 중요하다.

### 10.11 추가 조사 후 보정된 결론

기존 결론을 크게 바꿀 필요는 없다. 오히려 다음 항목은 우선순위를 더 높여야 한다.

1. `title_keywords` hard drop 제거
2. candidate metadata 보존
3. cheap scoring layer 추가
4. source category와 source health/yield 측정
5. keyword miss/validator unknown sampling
6. search seed + focused crawling 도입
7. binary download 금지, attachment metadata만 저장

반대로 다음은 당장 1순위가 아니다.

1. proxy rotation 대규모 도입
2. 중국권 blocked source 강행
3. 무제한 deep crawl
4. LLM 전수 분석
5. RDS에 raw artifact 대량 저장

## 11. 설계 항목별 상세 검증

작성일: 2026-06-05

목적: 우리가 제안한 설계 항목을 하나씩 외부 사례/논문/공식 문서 기준으로 검증한다. 각 항목은 효과, 비용, 성능 리스크를 함께 본다.

### 11.1 `title_keywords` hard filter 제거 및 priority ranking

검증 대상:

- 현재: 제목 키워드 불일치 후보를 listing 단계에서 drop
- 제안: drop하지 않고 priority score/P3 샘플로 보존

근거:

- Focused crawling 연구는 topic relevance를 추정해 hyperlink follow 여부와 우선순위를 정한다. 즉 키워드는 "버릴지 말지"의 단일 조건이 아니라 relevance ranking feature로 쓰는 쪽에 가깝다.
  - 출처: https://link.springer.com/article/10.1186/s13635-017-0064-5
- Improved Best-First focused crawling 연구는 harvest rate와 media type 등을 relevance 판단 feature로 사용하고, 다른 topic search algorithm보다 harvest rate와 submitted links 측면에서 더 좋은 성능을 보였다고 보고한다.
  - 출처: https://manu44.magtech.com.cn/Jwk_infotech_wk3/EN/10.11925/infotech.1003-3513.2013.07-08.04
- Microsoft Research의 focused crawling 연구는 link priority를 예측하고, 큰 breadth-first crawl 후 post-filtering은 network traffic을 크게 늘리는 비용이 있다고 지적한다.
  - 출처: https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/tang_cikm05.pdf

효과 판단:

- 우리 판단이 맞다. keyword를 hard filter로 쓰면 precision은 좋아지지만 recall이 낮아진다.
- 불법 프로그램 글은 은어, 외부 연락처, 이미지, 우회 제목을 쓸 수 있으므로 "제목에 NC 키워드 없음 = 무관"으로 처리하면 위험하다.

비용 판단:

- hard drop을 제거하면 fetch 후보 수와 LLM 후보 수가 늘 수 있다.
- 그래서 모든 keyword-miss를 fetch하면 안 되고, `P3_SAMPLE_RATE` 같은 sampling rate와 cheap scoring이 반드시 같이 필요하다.

성능 판단:

- listing 단계에서는 후보 객체만 만들고, 본문 fetch는 priority별 budget으로 제한해야 한다.
- 예상 구현: `title_keywords` 매칭 후보는 P1/P2, 불일치 후보는 P3로 두고 보드별 최대 샘플 수를 둔다.

판정:

- 채택. 단, "drop 제거" 단독 적용은 금지. priority budget/sampling과 함께 적용해야 한다.

### 11.2 `CandidatePost` metadata 보존

검증 대상:

- 현재: URL만 넘기고 title/link context 대부분 소실
- 제안: `title`, `board_url`, `matched_keywords`, `risk_signals`, `source_category`, `priority`, `discovery_reason` 저장

근거:

- Illicit marketplace detection 연구는 document structure, embedded patterns, email/IP/Bitcoin address, metadata를 language model embedding과 함께 사용한다.
  - 출처: https://arxiv.org/abs/2507.22912
- Game cheat forum 연구는 MPGH/UnknownCheats의 attachment name, file type, download count, game association, author/reply 같은 metadata를 활용한다.
  - 출처: https://dspace.networks.imdea.org/handle/20.500.12761/1514
  - 출처: https://suarez-tangil.networks.imdea.org/papers/2021esorics-cheaters.pdf
- Dark web marketplace 조사 프레임워크는 vendor account와 listing 정보를 함께 수집해 분석한다.
  - 출처: https://www.mdpi.com/2078-2489/9/8/186

효과 판단:

- 우리 판단이 맞다. 본문만 저장하면 판매자/연락처/다운로드/첨부/반응 지표를 놓친다.
- 특히 game cheat 탐지는 "본문 문장"보다 attachment/download/reputation/source가 더 강한 신호가 될 수 있다.

비용 판단:

- metadata는 텍스트/숫자 중심이라 RDS 저장 비용이 낮다.
- 반대로 이미지/첨부/binary를 원본으로 저장하면 비용과 보안 리스크가 커진다.

성능 판단:

- listing extraction 단계에서 title/reply/view 정도를 뽑으면 추가 Playwright fetch 없이 candidate ranking에 도움된다.
- CrawlEvent strict schema 때문에 shared model, detection, DB migration을 함께 변경해야 한다.

판정:

- 강하게 채택. Phase 2 전에 최소 `CandidatePost` 내부 모델부터 도입하는 것이 좋다.

### 11.3 Cheap scoring layer

검증 대상:

- 현재: validator 통과 후 대부분 LLM으로 감
- 제안: regex/CSS/XPath/metadata 기반 cheap scoring 후 selective LLM

근거:

- Crawl4AI LLM-free extraction은 CSS/XPath/Regex extraction이 LLM API 호출 없이 빠르고 반복 가능하며, 수천 페이지에도 적합하다고 설명한다.
  - 출처: https://docs.crawl4ai.com/extraction/no-llm-strategies/
- Crawl4AI LLM extraction 문서는 LLM 기반 extraction이 schema 기반보다 느리고 비용이 더 크다고 명시한다.
  - 출처: https://docs.crawl4ai.com/extraction/llm-strategies/
- FrugalGPT는 LLM 비용 절감을 위해 prompt adaptation, approximation, cascade를 제안한다. 모델 가격 구조 차이가 크기 때문에 cascade가 비용 절감에 의미 있다고 본다.
  - 출처: https://arxiv.org/abs/2305.05176
- OpenAI API pricing 기준으로 저가 모델과 고가 모델의 1M token 가격 차이가 크다. 예: `gpt-5-nano`는 입력 $0.05/output $0.40, `gpt-5`는 입력 $1.25/output $10.00, `gpt-5-pro`는 입력 $15/output $120 수준이다.
  - 출처: https://platform.openai.com/docs/pricing/

효과 판단:

- 우리 판단이 맞다. 비용 제한 환경에서는 LLM 전수 분류보다 cheap scoring + LLM cascade가 합리적이다.
- Regex 신호는 완벽한 classifier가 아니라 priority signal로 써야 한다.

비용 판단:

- Regex/CSS extraction은 CPU 비용만 들고 API 비용이 없다.
- LLM 호출 수를 P0/P1 중심으로 줄이면 API 비용을 직접 줄일 수 있다.

성능 판단:

- cheap scorer는 비동기 크롤러의 병목이 되지 않을 가능성이 높다.
- 다만 regex dictionary가 커지면 false positive가 늘 수 있으므로 source별 score weight와 feedback loop가 필요하다.

판정:

- 강하게 채택. LLM 전 단계에 반드시 둔다.

### 11.4 Source category와 source yield 측정

검증 대상:

- 현재: site별 성공/실패 로그는 있으나 source yield를 운영 지표로 보기 어렵다.
- 제안: `source_category`, `found_urls`, `fetched`, `enqueued`, `illegal_rate`, `cost_per_visible_detection` 등 측정

근거:

- CTI crawler architecture 연구는 clear web, social web, dark web source를 나누고, ML crawler와 language model ranking의 2단계를 제안한다.
  - 출처: https://arxiv.org/abs/2109.06932
- inTIME CTI framework는 security blog, forum, social media, underground forum/marketplace 등 다양한 source를 threat intelligence source로 본다.
  - 출처: https://www.mdpi.com/2079-9292/10/7/818
- 상용 CTI/brand monitoring 제품들은 evidence graph, seller risk score, platform coverage, listing/seller/price/image signal을 강조한다. 이는 source와 entity를 분리해 보는 구조와 맞다.
  - 출처: https://www.zerofox.com/solutions/cyber-threat-intelligence/search-portal/
  - 출처: https://edghaz.com/
  - 출처: https://merchanthq.io/

효과 판단:

- 우리 판단이 맞다. source yield가 없으면 어디에 EC2/LLM 예산을 써야 하는지 알 수 없다.
- 예: `general_game_board`는 volume은 높고 illegal rate는 낮을 수 있고, `seller_site`는 volume은 낮지만 illegal rate는 높을 수 있다.

비용 판단:

- 측정 테이블 자체의 RDS 비용은 낮다.
- 하지만 모든 candidate를 장기 저장하면 RDS가 커질 수 있으므로 aggregate stats + sampled candidates 중심이 좋다.

성능 판단:

- board/run 단위 aggregate는 성능 부담이 작다.
- per-candidate full logging은 별도 retention 정책이 필요하다.

판정:

- 강하게 채택. Phase 1 최우선.

### 11.5 Keyword miss/validator unknown sampling과 active learning

검증 대상:

- 현재: keyword miss와 validator unknown은 대부분 사라짐
- 제안: 일부 샘플을 review/LLM/human label 대상으로 남김

근거:

- Real-world undesired content detection 연구는 rare events를 포착하기 위한 active learning pipeline을 중요 요소로 본다.
  - 출처: https://arxiv.org/abs/2208.03274
- Rare-class active learning 연구는 rare class가 5% 미만처럼 매우 적을 때 active learning/acquisition strategy가 중요하다고 본다.
  - 출처: https://huggingface.co/papers/2305.02459
- Active learning with label quality control 연구는 labeling resource를 가치 있는 unlabeled sample과 mislabeled 가능 sample에 할당해 labeling cost를 줄이는 방향을 제안한다.
  - 출처: https://pmc.ncbi.nlm.nih.gov/articles/PMC10496030/
- Cost-sensitive active learning 연구들은 annotation cost가 sample마다 다를 수 있고, budget 안에서 informative query를 선택해야 한다고 본다.
  - 출처: https://link.springer.com/article/10.1007/s10994-019-05781-7
  - 출처: https://www.ijcai.org/proceedings/2017/261

효과 판단:

- 우리 판단이 맞다. 희귀한 불법 게시글을 찾으려면 "버린 것 중 일부"를 봐야 한다.
- 단, active learning은 만능이 아니고 random sampling baseline과 비교해야 한다.

비용 판단:

- human review 비용이 생긴다.
- 하지만 전수 review보다 P3/P4 샘플링이 훨씬 싸다.

성능 판단:

- 운영 pipeline과 review pipeline을 분리해야 한다.
- 화면에는 고신뢰 결과만 보여주고, 내부 학습 queue에는 P3/P4 샘플을 둔다.

판정:

- 채택. 단, 첫 버전은 단순 stratified random sampling으로 시작하고, 나중에 active learning으로 고도화한다.

### 11.6 Search seed와 focused crawling

검증 대상:

- 현재: 게시판형 `SiteConfig` 중심
- 제안: `SearchEngineConfig`, query seed, focused crawl, seed pool 도입

근거:

- CTI crawler architecture는 clear/social/dark web을 대상으로 machine-learning based crawler와 language-model ranking을 결합한다.
  - 출처: https://arxiv.org/abs/2109.06932
- Focused crawler 일반 설명과 연구들은 seed URL과 search result를 출발점으로 relevance 높은 link를 따라가는 방식을 사용한다.
  - 출처: https://en.wikipedia.org/wiki/Focused_crawler
  - 출처: https://link.springer.com/article/10.1186/s13635-017-0064-5
- Crawl4AI URL seeding은 sitemap/Common Crawl/query 기반 seed 수집을 지원한다.
  - 출처: https://docs.crawl4ai.com/core/url-seeding/

효과 판단:

- 우리 판단이 맞다. cheat seller/reseller/landing page는 일반 게시판 첫 페이지에 없을 가능성이 높다.
- 검색 seed 없이는 source coverage가 좁다.

비용 판단:

- 검색 seed는 노이즈가 크다. 바로 deep crawl/LLM으로 연결하면 비용이 터진다.
- query별 max_urls, domain allow/deny list, priority score가 필수다.

성능 판단:

- 초기에는 query당 상위 N개만 저장하고, P0/P1 signal이 있는 페이지만 fetch한다.
- search discovery는 scheduled crawl과 별도 주기로 느리게 돌리는 것이 좋다.

판정:

- 채택. 단, Phase 6 이후. Phase 1~3의 observability와 scoring 없이는 위험하다.

### 11.7 제한 병렬 처리와 Crawl4AI dispatcher

검증 대상:

- 현재: 게시글 fetch 순차 처리
- 제안: concurrency 2~3, source별 rate limit, Crawl4AI `arun_many()`/dispatcher 검토

근거:

- Crawl4AI `arun_many()` 문서는 dispatcher가 concurrency, rate limiting, memory-based adaptive throttling을 처리한다고 설명한다.
  - 출처: https://docs.crawl4ai.com/api/arun_many/
- Crawl4AI Multi-URL Crawling 문서는 `MemoryAdaptiveDispatcher`, `SemaphoreDispatcher`, `RateLimiter`를 통해 concurrency와 pacing을 다룬다.
  - 출처: https://docs.crawl4ai.com/advanced/multi-url-crawling/
- Crawl4AI release note는 `MemoryAdaptiveDispatcher`가 available memory에 따라 concurrency를 조정하고 built-in rate limiting을 포함한다고 설명한다.
  - 출처: https://docs.crawl4ai.com/blog/releases/0.5.0/
- AWS EC2 pricing은 T2/T3/T4g Unlimited CPU credits가 추가 과금될 수 있음을 명시한다.
  - 출처: https://aws.amazon.com/ec2/pricing/on-demand/

효과 판단:

- 순차 fetch를 제한 병렬로 바꾸면 run duration은 줄어든다.
- 하지만 Playwright는 메모리/CPU가 무거워서 EC2 1대에서 큰 concurrency는 위험하다.

비용 판단:

- T 계열 EC2에서 CPU credit 초과 시 과금 또는 throttling 리스크가 있다.
- concurrency 2~3부터 시작하고 CloudWatch CPU credit/메모리를 봐야 한다.

성능 판단:

- source별 anti-bot rate limit이 있으므로 global concurrency와 per-source delay를 함께 둬야 한다.
- Bahamut/Dcard 같은 동적 사이트와 static-like 사이트를 같은 concurrency로 취급하면 안 된다.

판정:

- 채택. 단, 관측 지표 추가 후 점진 적용.

### 11.8 Raw artifact는 S3/local archive, RDS는 metadata 중심

검증 대상:

- 현재: posts body는 RDS에 저장되고, 원문/S3 archive 옵션이 있음
- 제안: RDS는 metadata/detection summary 중심, raw text/image는 S3/local archive 중심

근거:

- AWS RDS pricing은 instance, storage, backup, I/O, data transfer가 비용 요소다.
  - 출처: https://aws.amazon.com/rds/pricing/
- AWS S3 pricing은 storage, request, retrieval, data transfer 등으로 과금되며 storage class/lifecycle을 선택할 수 있다.
  - 출처: https://aws.amazon.com/s3/pricing
- S3 storage class 문서는 Standard, IA, Glacier 계열 등 access pattern에 맞는 storage class를 제공한다.
  - 출처: https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html

효과 판단:

- 우리 판단이 맞다. RDS에 raw image/large body를 오래 쌓으면 DB backup/storage/I/O 비용과 query 성능에 악영향이 있다.
- RDS는 목록/필터/집계용 metadata에 집중하는 편이 좋다.

비용 판단:

- S3도 request/retrieval 비용이 있으므로 작은 object를 무한히 많이 만들면 request overhead가 생긴다.
- 그래도 raw artifact 장기 보관은 RDS보다 object storage/lifecycle이 맞다.

성능 판단:

- 화면 목록은 RDS metadata로 빠르게 처리하고, 상세 원문은 필요할 때 S3/local path를 참조한다.
- T4/정상 데이터는 retention을 짧게 가져간다.

판정:

- 채택. 단, 당장 body column 제거는 하지 않고 retention/archive 정책부터 둔다.

### 11.9 Binary/attachment 직접 다운로드 금지

검증 대상:

- 제안: cheat binary/attachment는 직접 다운로드하지 않고 URL/metadata만 저장

근거:

- Game cheat forum 연구는 attachment metadata를 분석하지만, 운영 제품에서 무분별한 binary 수집은 보안/법적 리스크가 크다.
  - 출처: https://suarez-tangil.networks.imdea.org/papers/2021esorics-cheaters.pdf
- Activision 관련 보도에서는 cheat로 위장한 malware/dropper가 유통된 사례가 소개된다.
  - 출처: https://arstechnica.com/gadgets/2021/04/activision-warns-of-malware-masquerading-as-cheats-for-call-of-duty-warzone/

효과 판단:

- metadata만으로도 탐지/우선순위 판단에는 상당한 가치가 있다.
- binary 분석은 별도의 sandbox/legal approval이 있는 별도 pipeline이어야 한다.

비용 판단:

- binary 다운로드/저장은 storage, malware scanning, sandbox 비용을 만든다.
- EC2 crawler에 직접 받으면 보안 사고 리스크가 비용보다 더 크다.

성능 판단:

- attachment URL, filename, extension, size, download count만 추출하면 crawler 부담이 낮다.

판정:

- 강하게 채택. 운영 crawler에서는 binary download 금지.

### 11.10 탐지 목록과 수집/검토 funnel 분리

검증 대상:

- 현재: 화면은 high-confidence illegal detection만 노출
- 제안: user-facing detection list와 operator-facing crawl funnel/review queue 분리

근거:

- Content moderation 연구들은 자동화와 human review/active learning을 함께 다룬다.
  - 출처: https://arxiv.org/abs/2208.03274
- 상용 marketplace/brand monitoring 제품들은 detection feed뿐 아니라 evidence, seller/entity, risk score, analyst workflow를 강조한다.
  - 출처: https://www.marketplacemonitor.online/
  - 출처: https://clusterforensics.com/
  - 출처: https://edghaz.com/

효과 판단:

- 현재 화면 count는 크롤러 성능 지표가 아니다.
- 운영자는 `found -> fetched -> real -> enqueued -> classified -> visible` funnel을 봐야 한다.

비용 판단:

- dashboard/API 추가 비용은 낮다.
- 하지만 per-candidate review UI까지 만들면 제품 범위가 커지므로 먼저 aggregate funnel부터 만든다.

성능 판단:

- 집계 endpoint는 DB index와 aggregate table로 처리해야 한다.
- detection list query에 모든 수집 stats를 join하지 않는다.

판정:

- 채택. Phase 1에서 aggregate funnel API부터 만든다.

### 11.11 설계별 최종 채택 매트릭스

| 설계 항목 | 효과 근거 | 비용 리스크 | 성능 리스크 | 결론 |
|---|---|---:|---:|---|
| `title_keywords` hard drop 제거 | focused crawling/ranking 연구와 일치 | 중간 | 중간 | 채택, sampling 필수 |
| `CandidatePost` metadata | illicit market/game cheat 연구와 일치 | 낮음 | 낮음 | 강하게 채택 |
| cheap scoring layer | Crawl4AI/FrugalGPT/LLM pricing 근거 | 낮음 | 낮음 | 강하게 채택 |
| source yield metric | CTI architecture/source category와 일치 | 낮음 | 낮음 | 최우선 채택 |
| P3/P4 sampling | active learning/rare class 연구와 일치 | 중간 | 낮음 | 채택 |
| search seed/focused crawl | CTI/focused crawler 사례와 일치 | 중간~높음 | 중간 | 후순위 채택 |
| 제한 병렬 fetch | Crawl4AI dispatcher 공식 지원 | 중간 | 중간~높음 | 관측 후 점진 채택 |
| S3 archive/RDS metadata | AWS pricing 구조상 타당 | 낮음~중간 | 낮음 | 채택 |
| binary download 금지 | game cheat malware 리스크 | 낮음 | 낮음 | 강하게 채택 |
| detection/funnel 화면 분리 | moderation/monitoring workflow와 일치 | 낮음 | 낮음 | 채택 |

### 11.12 검증 후 실행 순서 보정

조사 후 실행 순서는 다음이 가장 합리적이다.

1. `crawl_runs`, `crawl_board_stats` 같은 aggregate observability 추가
2. `CandidatePost` 내부 모델 도입
3. `title_keywords`를 drop에서 score로 변경하고 P3 sampling 추가
4. cheap risk signal scorer 추가
5. 기존 안정 보드 페이지네이션 2~3페이지부터 적용
6. 제한 병렬 fetch를 concurrency 2부터 실험
7. `CrawlEvent`/DB metadata 확장
8. review queue 또는 내부 검토 화면 추가
9. search seed/focused crawling 추가
10. source yield 기반 budget allocator 추가

중요한 보정:

- search seed/focused crawling은 효과가 크지만 노이즈와 비용도 크므로, Phase 1~4 없이 바로 들어가면 위험하다.
- concurrency 개선은 수집량보다는 run duration 개선책이다. 후보 발견량을 늘리는 핵심은 아니다.
- active learning은 첫 버전부터 복잡하게 만들지 말고 stratified random sampling으로 시작한다.

## 12. 추가로 더 조사할 주제

작성일: 2026-06-05

지금까지의 조사는 crawler architecture와 수집량 확대 방향을 검증하는 데 초점이 있었다. 구현 전에 더 조사하면 좋은 빈칸은 다음과 같다.

### 12.1 크롤링 법무/컴플라이언스 기준

왜 필요한가:

- 불법 프로그램 탐지를 위해 공개 웹을 수집하더라도, 사이트 ToS, robots.txt, 접근제어 우회, 개인정보/연락처 저장, 저작권 이슈가 생길 수 있다.
- 특히 proxy rotation, CAPTCHA 우회, 로그인 필요한 사이트 수집은 기술 문제가 아니라 법무/운영 리스크다.

확인한 근거:

- robots.txt는 기술적으로 voluntary standard지만, 법적 분쟁에서 good faith/bad faith 판단 자료로 쓰일 수 있다.
  - 출처: https://datatracker.ietf.org/doc/html/rfc9309
  - 출처: https://en.wikipedia.org/wiki/Robots.txt
- 웹 스크래핑은 공개 데이터 여부, ToS 동의 여부, 접근제어 우회 여부, 서버 부하, 개인정보 수집 여부에 따라 리스크가 달라진다.
  - 출처: https://legalclarity.org/is-web-scraping-legal-a-look-at-the-law/

추가 조사 질문:

- 우리 source별 robots.txt/ToS 상태는 어떤가?
- 로그인/연령인증/캡차 우회가 필요한 source는 운영 대상에서 제외할 것인가?
- contact signal 탐지를 위해 Telegram/Discord/QQ/Kakao ID를 저장할 때 개인정보/민감정보 정책은 어떻게 둘 것인가?
- source별 allowlist/denylist와 rate-limit policy를 문서화해야 하는가?

실행 제안:

- `docs/crawling-compliance-policy.md`를 별도로 만든다.
- source registry에 `access_policy`, `robots_policy`, `requires_login`, `captcha_risk`, `pii_risk` 필드를 추가하는 방안을 검토한다.

### 12.2 Source reliability와 information credibility scoring

왜 필요한가:

- 불법 프로그램 탐지는 false positive가 사업적으로 민감하다.
- 같은 문장이라도 source 신뢰도, 반복 등장, 독립 출처 corroboration 여부에 따라 판단 confidence가 달라져야 한다.

확인한 근거:

- FIRST CTI curriculum은 cyber threat intelligence에서 source evaluation과 information reliability를 중요한 tradecraft로 다룬다.
  - 출처: https://www.first.org/global/sigs/cti/curriculum/source-evaluation
- OpenCTI도 source reliability와 information quality 평가를 CTI의 핵심 요소로 설명한다.
  - 출처: https://docs.opencti.io/latest/usage/reliability-confidence/
- Admiralty Code 계열은 source reliability(A-F)와 information credibility(1-6)를 분리한다.
  - 출처: https://en.wikipedia.org/wiki/Intelligence_source_and_information_reliability

추가 조사 질문:

- 우리 source별 reliability 등급은 어떻게 줄 것인가?
- 신규 source는 기본 low reliability로 시작하고 evidence가 쌓이면 올릴 것인가?
- 같은 Telegram ID/판매 문구/URL이 여러 source에서 반복되면 confidence를 어떻게 보정할 것인가?
- LLM confidence와 source credibility를 분리해서 저장할 것인가?

실행 제안:

- `sources` 또는 별도 `source_profiles` 테이블에 `reliability_rating`, `source_category`, `last_reviewed_at` 추가 검토.
- detection confidence와 intelligence confidence를 분리한다.

### 12.3 CTI 표준 모델(STIX/TAXII) 적용 여부

왜 필요한가:

- 지금은 게시글 detection 중심이지만, 장기적으로는 URL, domain, handle, Telegram ID, file hash, seller entity 같은 indicator graph가 필요할 수 있다.
- 외부 CTI 도구나 분석 포맷과 연결하려면 표준 모델을 참고하는 것이 좋다.

확인한 근거:

- STIX는 cyber threat information을 구조화해 표현하는 표준이고, TAXII는 이를 교환하는 프로토콜이다.
  - 출처: https://www.mitre.org/sites/default/files/publications/taxii.pdf
  - 출처: https://www.first.org/resources/papers/munich2016/wunder-stix-taxii-Overview.pdf
- STIX/TAXII 기반 CTI sharing은 다양한 보안 도구에서 threat indicator exchange에 사용된다.
  - 출처: https://www.ndss-symposium.org/wp-content/uploads/2024-228-paper.pdf

추가 조사 질문:

- 우리 탐지 대상의 핵심 entity는 무엇인가? post, source, URL, account, contact handle, seller, file, image?
- STIX를 그대로 도입할 필요가 있는가, 아니면 내부 entity model만 참고하면 되는가?
- `indicator`, `observed_data`, `relationship` 같은 개념을 어느 정도 차용할 것인가?

실행 제안:

- 당장 STIX/TAXII 구현은 하지 않는다.
- 대신 metadata schema 설계 때 CTI entity/relationship 모델을 참고한다.

### 12.4 실제 source 후보 목록과 yield 검증

왜 필요한가:

- 아키텍처가 좋아도 source가 부실하면 수집량과 탐지율은 늘지 않는다.
- 지금 source는 일반 게임 커뮤니티 중심이라 cheat seller/source discovery가 부족하다.

추가 조사 질문:

- NC 관련 불법 프로그램이 실제로 많이 등장하는 언어권/source는 어디인가?
- forum, seller site, reseller social, GitHub, Discord invite aggregator, Telegram 공개 채널 검색 결과 중 무엇이 현실적으로 접근 가능한가?
- 한국/대만/중국/영어권 query별로 실제 검색 결과 품질은 어떤가?
- search result 상위 20개에서 P0/P1 signal 비율은 어느 정도인가?

실행 제안:

- 별도 `source-discovery-spike`를 만든다.
- 각 query/source별로 `top20 result`, `accessible`, `blocked`, `risk_signals`, `estimated_yield`, `legal_risk`를 표로 기록한다.

### 12.5 비용 산정 모델의 실제 숫자화

왜 필요한가:

- 지금 문서는 비용 원칙은 있지만, "한 달에 얼마 늘어나는지" 계산식은 아직 없다.
- 설계 선택마다 EC2 시간, RDS storage, S3 object/request, LLM token 비용이 다르게 움직인다.

확인한 근거:

- EC2는 instance hour와 CPU credit/T 계열 Unlimited 리스크가 있다.
  - 출처: https://aws.amazon.com/ec2/pricing/on-demand/
- RDS는 instance, storage, backup, I/O, data transfer 비용이 있다.
  - 출처: https://aws.amazon.com/rds/pricing/
- S3는 storage class, request, retrieval, transfer 비용 구조를 가진다.
  - 출처: https://aws.amazon.com/s3/pricing
- OpenAI API는 모델별 input/output token 가격 차이가 크므로 cascade/selective LLM의 비용 효과가 크다.
  - 출처: https://platform.openai.com/docs/pricing/

추가 조사 질문:

- 현재 1회 run의 평균 fetched/enqueued/classified/token/image 수는 얼마인가?
- `MAX_POSTS_PER_BOARD=20`, 페이지 3개, concurrency 2 적용 시 월 비용은 얼마나 변하는가?
- P0/P1만 LLM 처리할 때와 전수 LLM 처리할 때 비용 차이는 얼마인가?
- raw text/image retention 30/90/365일별 S3/RDS 비용은 얼마인가?

실행 제안:

- `docs/crawling-cost-model.xlsx` 또는 markdown table로 비용 계산표를 만든다.
- 실제 운영 metric이 생기면 추정치를 실측치로 바꾼다.

### 12.6 평가 지표와 offline benchmark

왜 필요한가:

- 수집량을 늘려도 precision이 너무 떨어지면 운영 가치가 낮다.
- 반대로 precision만 높이면 불법 프로그램 글을 놓친다.

추가 조사 질문:

- crawler 변경 전후를 어떤 metric으로 비교할 것인가?
- visible detection count가 아니라 candidate recall proxy를 어떻게 만들 것인가?
- 사람이 라벨링한 benchmark set을 몇 건부터 만들 것인가?
- source별 precision/recall, cost per true positive, false negative sample rate를 어떻게 추정할 것인가?

실행 제안:

- `labelset`을 source/priority bucket별로 stratified sampling한다.
- 최소 200~500건 규모의 초기 benchmark를 만든다.
- metric:
  - `candidate_yield_per_run`
  - `enqueued_per_run`
  - `illegal_rate_by_bucket`
  - `precision@P0/P1`
  - `cost_per_confirmed_illegal`
  - `time_to_detection`

### 12.7 Adversarial/evasion pattern 조사

왜 필요한가:

- 불법 프로그램 판매자는 키워드, 이미지, 연락처, 링크를 우회할 수 있다.
- 현재 keyword dictionary만으로는 쉽게 회피된다.

추가 조사 질문:

- 실제 cheat seller들이 쓰는 은어/초성/이미지-only/링크-shortener 패턴은 무엇인가?
- Telegram/Discord/QQ/WeChat/Kakao 연락처를 어떻게 변형 표기하는가?
- 이미지 안 텍스트 OCR이 필요한 비율은 어느 정도인가?
- URL shortener, invite link, mirror domain을 어떻게 정규화할 것인가?

실행 제안:

- false negative review에서 evasion pattern을 계속 추출한다.
- OCR은 바로 전수 적용하지 말고 P0/P1 이미지 후보에만 실험한다.

### 12.8 데이터 보존/삭제 정책

왜 필요한가:

- 불법/정상/미확인 데이터를 모두 장기 보관하면 비용과 개인정보 리스크가 커진다.

추가 조사 질문:

- T4 정상 데이터는 며칠 보관할 것인가?
- P3/P4 sampled but non-illegal 데이터는 언제 삭제할 것인가?
- evidence로 보존해야 하는 불법 의심 데이터는 원문/스크린샷/이미지 URL 중 무엇인가?
- 사용자가 삭제된 원글을 요청할 때 우리 archive를 유지해도 되는가?

실행 제안:

- `DATA_POLICY.md`에 crawler artifact retention 정책을 추가한다.
- tier별 retention:
  - T1/T2: 장기 보존 후보
  - T3: 중기 보존
  - T4/P3/P4 non-hit: 단기 보존

## 13. 다음 조사 우선순위

가장 먼저 더 조사할 것은 다음 4개다.

1. **Source discovery spike**
   - 실제로 불법 프로그램 후보가 나오는 source/query를 찾아야 한다.
   - 설계보다 source 품질이 수집량을 좌우한다.

2. **비용 계산표**
   - EC2/RDS/S3/LLM 비용을 run volume과 token 수 기준으로 숫자화해야 한다.
   - 그래야 `MAX_POSTS_PER_BOARD`, 페이지네이션, LLM selective ratio를 결정할 수 있다.

3. **컴플라이언스/접근 정책**
   - robots.txt, ToS, 로그인/캡차 우회, contact handle 저장 정책을 정해야 한다.
   - proxy rotation을 기술 선택지로만 보면 위험하다.

4. **평가 benchmark**
   - 변경 효과를 판단할 라벨셋이 필요하다.
   - 특히 P3/P4 샘플이 실제로 false negative를 잡는지 확인해야 한다.

## 14. 4대 우선 조사 실행 결과

작성일: 2026-06-05

범위:

- 실제 source 후보/yield
- 비용 산정
- 컴플라이언스/운영 정책
- 평가 benchmark

주의:

- 이번 조사는 공개 검색 결과와 공식 문서/논문/상용 제품 설명을 기반으로 했다.
- 불법 프로그램 파일, attachment, binary는 다운로드하지 않았다.
- 로그인/캡차/우회 접속이 필요한 source는 접근하지 않았다.

### 14.1 Source discovery spike 결과

기존 판단:

- 일반 게임 커뮤니티 first-page crawling만으로는 불법 프로그램 탐지 recall이 낮을 가능성이 있다.
- `SearchEngineConfig`와 source category가 필요하다.

조사 결과:

이 판단은 강하게 맞다. 공개 검색 결과에서 일반 게임 커뮤니티보다 훨씬 신호가 강한 source 유형이 바로 확인됐다.

샘플 source category:

| category | 공개 검색에서 확인된 형태 | 신호 | 운영 판단 |
|---|---|---|---|
| `seller_site` | Lineage 2 bot/assistant 공식 판매 사이트 | pricing, Telegram, Discord, support, automation feature | P0/P1 후보. 단, 상세 크롤은 robots/ToS 확인 후 |
| `cheat_forum` | 대만/중국권 Discuz 기반 天堂M 外掛/助手 포럼 | forum board, download, purchase, tutorial, support, Discord/Telegram | 기존 게시판형 crawler와 잘 맞음 |
| `boosting_rmt_site` | Lineage2 boosting/adena/character marketplace | price, payment, Discord, delivery | 불법 프로그램은 아니지만 illegal economy signal로 별도 tier 필요 |
| `telegram_index` | Telegram channel index/analytics 페이지 | channel metadata, subscribers, views | 직접 Telegram crawling 전의 안전한 seed source |
| `general_game_board` | Reddit/Inven/PTT/Bahamut 일반 게시판 | 낮은 direct seller signal | broad monitoring용. yield는 낮을 가능성 |

공개 검색에서 보인 예시:

- `l2reviver.net`: Lineage 2 자동화/assistant 성격, Telegram/Discord contact, automation feature가 명확함.
  - 출처: https://l2reviver.net/
- `adrenalinebot.com`: Lineage 2 bot 판매/지원 성격, Telegram/Facebook/Skype 등 contact signal.
  - 출처: https://adrenalinebot.com/en/
- `bbs.lineagem.shop`: 天堂M 外掛/輔助 Discuz forum, 구매/다운로드/커뮤니티 메뉴.
  - 출처: https://bbs.lineagem.shop/forum.php?gid=1
- `gdlmg.net`: 天堂M助手/外掛 forum, Discord/Telegram tutorial, 구매/다운로드 메뉴.
  - 출처: https://www.gdlmg.net/forum.php?fid=78&filter=typeid&mod=forumdisplay&typeid=42
- `spottaken.com`: Lineage2 boosting/adena/character trading style marketplace, Discord/payment signal.
  - 출처: https://www.spottaken.com/
- `telemetr.me/content/lineage2trade`: Telegram channel index page. channel stats/preview를 seed로 활용 가능.
  - 출처: https://telemetr.me/content/lineage2trade

해석:

- 기존 NC game board를 더 많이 보는 것보다, `seller_site`와 `cheat_forum` source discovery가 훨씬 높은 yield를 낼 가능성이 크다.
- 특히 대만/중국권 Discuz forum은 현재 `52pojie`/forum형 parser와 유사해 구현 난이도가 낮을 수 있다.
- Lineage 2 bot/seller site는 페이지 수가 적고 signal이 강하므로 deep crawl보다 domain-limited shallow crawl이 적합하다.

추가로 필요한 source discovery query:

| 언어 | query seed |
|---|---|
| 한국어 | `리니지 매크로 텔레그램`, `리니지 자동사냥 디스코드`, `리니지M 매크로 구매`, `아이온 오토 프로그램` |
| 번체중문 | `天堂M 外掛 購買`, `天堂M 輔助 Discord`, `天堂M 助手 Telegram`, `劍靈 外掛 輔助` |
| 간체중문 | `天堂M 外挂 购买`, `手游辅助 Telegram`, `剑灵 辅助 QQ`, `AION 辅助` |
| 영어/러시아권 | `Lineage 2 bot Telegram`, `Lineage 2 adrenaline bot`, `Aion bot Discord`, `Blade Soul bot macro` |

실행 제안:

1. `source_candidates` 문서를 따로 만들고 후보 source를 표로 관리한다.
2. 각 source에 `category`, `language`, `game`, `accessibility`, `robots_status`, `risk_signals`, `estimated_yield`, `legal_risk`를 기록한다.
3. 첫 구현 대상은 `cheat_forum`과 `seller_site` 중 공개 접근 가능하고 robots/ToS 리스크가 낮은 곳으로 제한한다.

### 14.2 비용 산정 조사 결과

현재 로컬/운영 구조:

- `infra/compose.prod.yml` 기준 단일 EC2 `t3.xlarge` 16GB로 보강된 상태.
- crawler container `mem_limit=4g`, detection `1g`, api JVM도 같은 host에 존재한다.
- 문서상 월 EC2 예산 추정은 약 `$124`, 전체 budget `$215` 안쪽으로 기록되어 있다.
- detection 기본 모델은 `LLM_MODEL` unset 시 `gpt-4o`.
- `LLM_DAILY_COST_CAP_USD` 기본값은 `$5`.
- `LLM_SEND_IMAGES=false`가 기본이라 현재는 text-only 중심으로 동작한다.

공식 가격 근거:

- OpenAI API pricing 기준:
  - `gpt-5`: input `$1.250` / 1M tokens, output `$10.000` / 1M tokens
  - `gpt-5-mini`: input `$0.250`, output `$2.000`
  - `gpt-5-nano`: input `$0.050`, output `$0.400`
  - Batch API는 비동기 처리 시 50% 할인 옵션이 있다.
  - 출처: https://openai.com/api/pricing
- AWS EC2는 instance hour, T 계열 CPU credit/Unlimited 정책, data transfer 등이 비용 요소다.
  - 출처: https://aws.amazon.com/ec2/pricing/on-demand/
- AWS RDS는 instance, storage, backup, I/O, data transfer가 비용 요소다.
  - 출처: https://aws.amazon.com/rds/pricing/
- AWS S3는 storage class, request, retrieval, lifecycle에 따라 비용이 달라진다.
  - 출처: https://aws.amazon.com/s3/pricing
  - 출처: https://aws.amazon.com/s3/cost-optimization/

LLM 비용 계산식:

```text
cost_per_post =
  (input_tokens * input_price_per_1m + output_tokens * output_price_per_1m) / 1_000_000

monthly_llm_cost =
  posts_classified_per_day * cost_per_post * 30
```

예시 가정:

- 게시글 1건 평균 input 3,000 tokens
- output 300 tokens

| 모델 | 1건 비용 | 1,000건 비용 | 10,000건 비용 |
|---|---:|---:|---:|
| `gpt-5` | 약 `$0.00675` | 약 `$6.75` | 약 `$67.50` |
| `gpt-5-mini` | 약 `$0.00135` | 약 `$1.35` | 약 `$13.50` |
| `gpt-5-nano` | 약 `$0.00027` | 약 `$0.27` | 약 `$2.70` |

해석:

- 분류/triage가 주목적이면 `gpt-5-nano` 또는 mini-classifier를 1차로 쓰는 cascade가 비용상 매우 유리하다.
- 현재 코드의 `PRICING` table은 `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini` 중심이라 최신 모델 가격을 반영해야 한다.
- `estimate_cost_usd()`가 미등록 모델을 `gpt-4o` 가격으로 fallback하므로, `LLM_MODEL=gpt-5-nano`로 바꿔도 비용 추정이 과대 계산될 수 있다.

EC2/성능 비용 해석:

- `t3.xlarge` 16GB라서 concurrency 2 정도는 실험 여지가 있다.
- 하지만 crawler container는 Playwright Chromium 때문에 4GB limit이고, redis/api/detection이 같은 host에 있다.
- concurrency 증가는 "후보 발견량 증가"가 아니라 "run duration 단축"에 가깝다.
- source 수와 page 수가 늘어나는 순간 CPU credit/메모리/anti-bot risk를 같이 봐야 한다.

실행 제안:

1. `detection/src/rate_limit/cost_cap.py`의 `PRICING`에 현재 사용 모델을 추가한다.
2. `LLM_MODEL` 기본값을 분류용 저가 모델로 바꿀지 검토한다.
3. 비용 산정용 metric을 저장한다:
   - `input_tokens`
   - `output_tokens`
   - `images_sent`
   - `model`
   - `candidate_priority`
   - `source_category`
4. Batch API는 실시간성이 낮아도 되는 P3/P4 review queue에만 검토한다.

### 14.3 컴플라이언스/접근 정책 조사 결과

핵심 결론:

- 공개 웹 수집 자체보다 위험한 것은 `접근제어 우회`, `CAPTCHA 우회`, `로그인/계정 생성`, `proxy rotation으로 차단 회피`, `개인 연락처 장기 보관`, `서버에 과도한 부하`다.

근거:

- robots.txt는 RFC 9309로 표준화된 Robots Exclusion Protocol이다. 법 그 자체는 아니지만, crawler의 good faith를 판단하는 운영 기준이 될 수 있다.
  - 출처: https://datatracker.ietf.org/doc/html/rfc9309
- web scraping 관련 법적 리스크는 공개 데이터 여부만으로 결정되지 않고, ToS, 접근제어 우회, server burden, copyright, privacy가 함께 고려된다.
  - 출처: https://legalclarity.org/is-web-scraping-legal-a-look-at-the-law/
- OpenCTI/FIRST 계열 CTI 방법론은 source reliability와 confidence를 분리하고, 정보 출처/품질을 명시적으로 평가한다.
  - 출처: https://www.first.org/global/sigs/cti/curriculum/source-evaluation
  - 출처: https://docs.opencti.io/latest/usage/reliability-confidence/

source별 policy 필드 제안:

```python
access_policy: Literal[
    "public_ok",
    "robots_disallow",
    "tos_no_scrape",
    "login_required",
    "captcha_required",
    "blocked_do_not_bypass",
]
pii_policy: Literal[
    "no_contact_seen",
    "contact_metadata_only",
    "contact_hash_only",
    "do_not_store_contact",
]
```

운영 원칙:

1. 로그인/계정/실명/휴대폰 인증이 필요한 source는 기본 제외한다.
2. CAPTCHA/403을 proxy rotation으로 강행하지 않는다.
3. robots.txt와 ToS 상태를 source registry에 기록한다.
4. Telegram/Discord/QQ/Kakao handle은 원문과 분리해 metadata로 저장하고 retention을 둔다.
5. binary/attachment는 다운로드하지 않는다.
6. rate limit은 source별로 conservative하게 둔다.

실행 제안:

- `docs/crawling-compliance-policy.md` 신설.
- `SiteConfig` 또는 별도 `SourceProfile`에 compliance fields 추가.
- crawler log에 `access_policy`와 `compliance_decision`을 남긴다.

### 14.4 평가 benchmark 조사 결과

핵심 결론:

- visible detection count는 평가 지표가 아니다.
- focused crawling에서는 harvest rate, precision/recall, cost per confirmed hit, time-to-detection을 봐야 한다.

근거:

- focused crawling 문헌은 harvest ratio/rate를 주요 평가 지표로 사용한다. 관련 페이지를 얼마나 많이 fetch하고, 무관 페이지를 얼마나 피했는지를 본다.
  - 출처: https://www.dline.info/jio/fulltext/v1n1/1.pdf
  - 출처: https://cs.brynmawr.edu/Courses/cs380/fall2006/prelim.pdf
- rare class/active learning 연구는 희귀 양성 클래스 발견과 분류를 동시에 최적화하기 어렵다고 본다.
  - 출처: https://www.research.ed.ac.uk/en/publications/finding-rare-classes-active-learning-with-generative-and-discrimi/
- rare class에서는 accuracy보다 precision/recall, PR curve, false negative cost가 중요하다.
  - 출처: https://arxiv.org/abs/2007.01905

초기 benchmark 설계:

샘플링 단위:

- source category
- priority bucket
- language
- validator kind

초기 라벨셋:

| bucket | 샘플 수 | 목적 |
|---|---:|---|
| P0 seller/contact/price | 100 | high-risk precision 확인 |
| P1 game + cheat signal | 100 | 핵심 탐지 bucket 확인 |
| P2 NC board general | 100 | 일반 커뮤니티 baseline |
| P3 keyword miss sample | 100 | hard filter 제거 효과 확인 |
| P4 validator unknown/short | 100 | validator false negative 확인 |

권장 최소 규모:

- 초기 500건
- 각 건 label:
  - `illegal_program`
  - `private_server`
  - `rmt_boosting`
  - `normal_discussion`
  - `unclear`
  - `not_relevant`

운영 metric:

```text
candidate_yield_per_run
fetch_success_rate
validator_real_rate
harvest_rate = relevant_candidates / fetched_candidates
precision_by_bucket
illegal_rate_by_source_category
cost_per_confirmed_illegal
time_to_detection
false_negative_rate_from_P3_P4_sample
```

실행 제안:

1. 먼저 `crawl_board_stats`와 `candidate_priority`를 저장한다.
2. dashboard에 visible detection count와 별도로 crawl funnel을 만든다.
3. P3/P4 sampling을 켠 뒤 human label 500건을 만든다.
4. 변경 전후 비교:
   - current baseline: existing board first-page + title hard filter
   - experiment A: title score + P3 sampling
   - experiment B: pagination 3 pages
   - experiment C: seller/cheat_forum source 추가

### 14.5 이번 조사로 바뀐 우선순위

기존 우선순위에서 `source discovery`의 중요도를 더 올린다.

이전:

1. observability
2. CandidatePost
3. title score
4. cheap scoring
5. pagination
6. search seed

보정 후:

1. observability
2. CandidatePost
3. source discovery spike table
4. title score/P3 sampling
5. cheap scoring
6. seller_site/cheat_forum source onboarding
7. pagination
8. concurrency 2 실험
9. search seed/focused crawl 자동화

이유:

- 실제 검색 결과에서 seller/bot/forum source가 바로 확인됐다.
- 일반 보드 pagination만 늘리는 것보다 high-yield source 추가가 더 큰 효과를 낼 가능성이 높다.
- 단, source onboarding 전에 compliance check와 robots/ToS/rate limit 기록이 필요하다.

## 15. Source 접근성 smoke 방식 검증

작성일: 2026-06-05

질문:

- source별로 `plain_http`, `plain_browser`, `proxy_browser`를 테스트하고, robots/ToS/rate-limit/proxy 필요 여부를 표로 남기는 방식이 제대로 된 접근인가?

결론:

- 맞다. 다만 단순 접속 성공/실패만 보면 부족하고, robots 체크, rate limiting, source seed 품질, harvest rate, proxy 성공률/비용을 함께 기록해야 한다.

근거:

- Crawl4AI는 다중 URL 크롤링에서 `arun_many()`, `MemoryAdaptiveDispatcher`, `RateLimiter`를 제공하며, robots.txt 확인 옵션도 지원한다. 이는 source별 접근성/부하/차단을 측정하고 점진적으로 병렬화하는 방식과 맞다.
  - 출처: https://docs.crawl4ai.com/advanced/multi-url-crawling/
- Crawl4AI 최신 문서 기준 proxy 설정은 `CrawlerRunConfig.proxy_config`로 per-request 적용하는 방식이 권장된다. 즉 source별 proxy policy를 두는 구조와 맞다.
  - 출처: https://docs.crawl4ai.com/api/parameters/
- focused crawling 연구에서 seed selection은 harvest rate와 topic coverage에 큰 영향을 준다. IBM Research는 크고 다양한 seed set이 harvest rate와 topic coverage를 개선한다고 보고한다.
  - 출처: https://research.ibm.com/publications/finding-seeds-to-bootstrap-focused-crawlers
- focused crawler 문헌은 harvest ratio/rate를 주요 평가 지표로 사용한다. 따라서 source smoke도 단순 200 OK가 아니라 관련 후보를 얼마나 얻는지 봐야 한다.
  - 출처: https://www.dline.info/jio/fulltext/v1n1/1.pdf
- Scrapy의 broad crawl 문서도 robots.txt, throttling, domain별 설정을 broad crawling의 기본 운영 요소로 다룬다.
  - 출처: https://doc.scrapy.org/en/latest/topics/broad-crawls.html
- Bright Data 문서는 anti-bot blocking 대응이 target별로 다르며, managed unblocker 계열은 Cloudflare/Akamai/DataDome 등 대응을 제공한다고 설명한다. 이는 "프록시를 먼저 전역 적용"보다 "target별 성공률/비용 테스트"가 맞다는 근거다.
  - 출처: https://docs.brightdata.com/scraping-automation/concepts/how-bright-data-handles-blocking
- Bright Data Proxy Manager 문서는 proxy endpoint/port 설정을 제공한다. 현재 코드의 `brd.superproxy.io:33335` 구성과 같은 계열이다.
  - 출처: https://docs.brightdata.com/proxy-networks/proxy-manager/configuration
- robots.txt는 RFC 9309로 표준화된 Robots Exclusion Protocol이다. source onboarding 시 robots 상태를 기록하는 것이 맞다.
  - 출처: https://datatracker.ietf.org/doc/html/rfc9309

보정된 smoke matrix:

| 단계 | 목적 | proxy | 기록할 것 |
|---|---|---|---|
| `robots_check` | 크롤 허용/제한 확인 | 없음 | robots reachable, allow/disallow, sitemap |
| `plain_http` | 정적 접근 가능성 확인 | 없음 | status, redirect, body length, title, block marker |
| `plain_browser` | JS/anti-bot 없는 브라우저 접근 확인 | 없음 | success, body length, links found, captcha/auth marker |
| `proxy_browser` | 지역/IP 차단 여부 확인 | source별 optional | success delta, latency, captcha/auth marker, traffic cost |
| `post_probe` | listing이 실제 게시글로 이어지는지 확인 | source policy 따름 | candidate URLs, post fetch success, validator kind |
| `yield_estimate` | source 가치 판단 | 없음/필요 시 proxy | harvest proxy, risk signals, expected P0/P1 rate |

판정 기준:

| 결과 | policy |
|---|---|
| plain browser로 접근되고 P0/P1 후보가 나옴 | `proxy_policy=none`, onboarding 우선 |
| plain은 막히고 proxy에서만 열림, robots/ToS 리스크 낮음 | `proxy_policy=optional_or_required`, 비용 검토 |
| proxy에서도 captcha/login/실명/휴대폰 요구 | `blocked_do_not_bypass` |
| 200 OK지만 후보/게시글 추출 거의 없음 | low-yield, 후순위 |
| 접근은 되지만 robots/ToS가 명확히 제한 | compliance review 전 보류 |

중요한 보정:

- proxy smoke는 "마지막 단계"여야 한다. 먼저 plain 접근과 robots/ToS를 확인한다.
- proxy 성공률은 source별로 측정해야 한다. 특정 proxy provider의 평균 성공률은 우리 target 성공률을 보장하지 않는다.
- 200 OK는 충분하지 않다. 게시글 URL 추출 수, post fetch 성공, risk signal 수, validator 결과까지 봐야 한다.
- smoke 결과는 `source_candidates` 또는 `source_profiles`로 지속 관리해야 한다.

## 16. Source smoke 방식에 대한 반대 의견과 한계

작성일: 2026-06-05

질문:

- `robots_check -> plain_http -> plain_browser -> proxy_browser -> post_probe -> yield_estimate` 방식이 정말 맞는가?
- 반대 의견이나 실패 가능성은 없는가?

결론:

- 방식 자체는 맞지만, smoke 결과를 "운영 성공 보장"으로 해석하면 안 된다.
- 이 방식은 source onboarding의 최소 검증 절차이지, 장기 안정성/법적 안전성/탐지 품질을 보장하지 않는다.

### 16.1 반대 의견 1: smoke 성공은 장기 성공을 보장하지 않는다

근거:

- anti-bot 시스템은 IP reputation, browser fingerprint, TLS/HTTP2 fingerprint, cookie age, interaction pattern 등을 함께 본다.
- 첫 1~5회 접근은 성공해도, 반복 접근/스케줄링/패턴 누적 후 차단될 수 있다.
- proxy provider 평균 성공률은 target별 성공률을 보장하지 않는다.

시사점:

- smoke 결과에는 `first_access_success`와 별도로 `repeat_access_success`를 기록해야 한다.
- 최소 3회 이상, 시간 간격을 둔 재시도 결과를 저장한다.
- source policy는 `onboard`가 아니라 `trial_onboard`부터 시작한다.

### 16.2 반대 의견 2: headless browser는 너무 비싸고 무겁다

근거:

- headless browser scraping은 CPU, memory, crash recovery, memory leak, version drift 등 운영 부담이 크다.
  - 출처: https://www.grepsr.com/blog/headless-browsers-web-scraping/
  - 출처: https://www.browserless.io/blog/headless-chrome
- Playwright/Puppeteer 기반 장기 scraper는 memory leak과 zombie process 관리가 필요하다.
  - 출처: https://www.firecrawl.dev/glossary/web-scraping-apis/prevent-memory-leaks-web-scrapers

시사점:

- 모든 source를 `plain_browser`로 처리하면 비용이 커진다.
- smoke 단계는 다음 순서가 맞다:
  1. `plain_http`
  2. static HTML parsing
  3. 필요한 source만 `plain_browser`
  4. 막힌 source만 `proxy_browser`
- `browser_required`를 source profile에 기록해야 한다.

### 16.3 반대 의견 3: robots.txt 확인은 충분조건이 아니다

근거:

- robots.txt는 advisory protocol이며 강제 접근제어는 아니다. 하지만 법적 분쟁에서 notice/good faith 판단에 영향을 줄 수 있다.
  - 출처: https://datatracker.ietf.org/doc/html/rfc9309
  - 출처: https://arxiv.org/abs/2503.06035
- robots.txt가 없거나 허용하더라도 ToS, copyright, privacy, server burden 이슈는 남는다.
- robots.txt만으로 사이트 운영자의 실제 scraping consent를 완전히 판단하기 어렵다는 연구도 있다.
  - 출처: https://arxiv.org/abs/2505.21733

시사점:

- `robots_allowed=true`를 `legal_ok=true`로 해석하면 안 된다.
- source profile에 `robots_status`, `tos_status`, `access_control_status`, `pii_risk`를 분리해 저장한다.

### 16.4 반대 의견 4: proxy는 비용과 법무 리스크를 키운다

근거:

- proxy는 rate limit/IP block을 완화할 수 있지만, CAPTCHA/로그인/실명/휴대폰 장벽을 해결하지 못할 수 있다.
- free proxy는 privacy/security risk가 크다는 연구가 있다.
  - 출처: https://arxiv.org/abs/2403.02445
- managed unblocker/proxy는 성공률을 높일 수 있지만 비용이 크고, target별로 실제 성공률을 확인해야 한다.
  - 출처: https://docs.brightdata.com/scraping-automation/concepts/how-bright-data-handles-blocking

시사점:

- free proxy는 사용하지 않는다.
- proxy는 source별 opt-in이어야 한다.
- `proxy_browser` 성공만으로 onboarding하지 않고, `proxy_cost_per_successful_candidate`를 계산한다.
- login/captcha/실명/휴대폰 요구 source는 `blocked_do_not_bypass`로 둔다.

### 16.5 반대 의견 5: seed/source discovery는 편향될 수 있다

근거:

- focused crawling에서 seed selection은 harvest rate와 topic coverage에 큰 영향을 준다.
  - 출처: https://research.ibm.com/publications/finding-seeds-to-bootstrap-focused-crawlers
- 좋은 seed만 고르면 특정 언어/지역/source category로 편향될 수 있다.
- search engine 결과는 개인화, 지역, 인덱싱 편향, SEO spam 영향을 받는다.

시사점:

- source discovery table은 언어권과 source category를 나눠 관리한다.
- seed는 `KR`, `TW`, `CN`, `EN/RU`를 분리해 수집한다.
- high-yield source만 추적하면 일반 커뮤니티 early signal을 놓칠 수 있으므로 broad monitoring source도 일부 유지한다.

### 16.6 반대 의견 6: yield가 높아도 목표와 다를 수 있다

근거:

- seller/boosting/RMT/private server source는 signal이 강하지만, 모두 "불법 프로그램"은 아니다.
- Lineage private server, boosting, RMT, bot/assistant, macro, cheat loader는 서로 다른 정책 판단이 필요하다.

시사점:

- taxonomy를 먼저 나눠야 한다:
  - `illegal_program`
  - `macro_automation`
  - `private_server`
  - `rmt_boosting`
  - `normal_discussion`
  - `unclear`
- high-yield source onboarding 전에 detection type/tier 정의를 보강한다.

### 16.7 보정된 최종 입장

source smoke matrix는 채택한다. 단, 다음 제한을 붙인다.

1. smoke는 source onboarding의 최소 조건이지 충분 조건이 아니다.
2. browser/proxy는 마지막 단계로만 사용한다.
3. robots, ToS, access control, PII risk를 분리 기록한다.
4. 반복 접근 성공률과 rate-limit 결과를 본다.
5. proxy 비용은 successful candidate 기준으로 계산한다.
6. source discovery는 언어권/source category별로 균형을 둔다.
7. taxonomy를 먼저 보강해 RMT/private server와 illegal program을 분리한다.

따라서 올바른 구현 순서는 다음과 같다.

1. `source_candidates.yml` 작성
2. robots/ToS/access policy 수동 기록
3. `plain_http` smoke
4. 필요한 경우만 `plain_browser`
5. 막힌 경우만 `proxy_browser`
6. 같은 source를 시간 간격 두고 반복 smoke
7. `post_probe`와 `yield_estimate`
8. `trial_onboard`
9. 운영 metric으로 1~2주 검증 후 정식 onboard

## 17. 추가 조사: 소셜/이미지/운영 대안/보존 리스크

작성일: 2026-06-05

이번 추가 조사는 기존 source smoke/proxy 논의에서 빠진 주변 리스크를 확인했다.

### 17.1 Telegram/Discord는 별도 고위험 source로 봐야 한다

조사 결과:

- Telegram 공개 채널은 CTI/OSINT 연구에서 실제로 쓰인다. 공개 채널 16개, 365k messages를 사용한 Telegram 기반 cyber threat early detection 연구도 있다.
  - 출처: https://arxiv.org/abs/2512.21380
- Telegram의 악성/사기/clone channel 생태계를 분석한 연구도 있다.
  - 출처: https://arxiv.org/abs/2111.13530
- 하지만 Telegram scraping은 public/private boundary, platform terms, GDPR/개인정보 이슈가 복잡하다.
  - 출처: https://telegramscraper.shop/blog/is-telegram-scraping-legal
- Discord는 Terms of Service에서 scraping without written consent를 금지한다.
  - 출처: https://discord.com/terms
- Discord는 public server scraping과 self-bot/proxy manipulation을 명시적으로 문제 삼은 사례를 안내한다.
  - 출처: https://support.discord.com/hc/en-us/articles/360039598252

해석:

- Telegram/Discord는 high-signal source일 수 있지만, 지금 crawler가 직접 들어갈 source로 바로 취급하면 위험하다.
- 특히 Discord는 직접 scraping 대상에서 제외하는 것이 맞다. 공개 웹에 노출된 invite/index/landing page metadata만 seed로 쓰는 정도가 안전하다.
- Telegram도 직접 client scraping보다 `telemetr`, 공개 index, 판매 사이트에 노출된 Telegram handle metadata부터 수집하는 것이 안전하다.

정책 제안:

- `social_direct_scrape=false`를 기본값으로 둔다.
- Discord는 `blocked_do_not_scrape_platform`으로 둔다.
- Telegram은 `public_index_only`부터 시작한다.
- handle은 원문 body와 분리하고, 필요하면 hash/partial masking을 검토한다.

### 17.2 이미지/OCR은 필요하지만 전수 적용하면 비용이 커진다

조사 결과:

- 이미지 moderation/OCR API들은 이미지/비디오 내 텍스트 추출과 moderation을 대규모로 제공한다.
  - 출처: https://sightengine.com/
  - 출처: https://www.imagemoderationapi.com/detection/ocr-text-detection.php
- 불법 판매자는 텍스트 대신 이미지 안에 가격/연락처를 넣을 수 있으므로 OCR은 recall 개선에 도움이 될 수 있다.

반대/비용:

- OCR API 또는 vision LLM 전수 적용은 비용이 급격히 증가할 수 있다.
- 이미지 다운로드/저장은 S3 request/storage 비용과 개인정보/저작권 리스크를 같이 만든다.

정책 제안:

- OCR은 P0/P1 후보 중 `image_count > 0`이고 text signal이 불충분할 때만 적용한다.
- 처음에는 OCR 결과를 별도 field로 저장하고, 원본 이미지는 기존 S3 retention 정책을 따른다.
- 이미지-only 탐지율을 benchmark에 별도로 둔다.

### 17.3 Managed scraping/browser API는 대안이지만 지금 당장 기본값은 아니다

조사 결과:

- self-hosted Playwright는 infra 비용만 보면 싸지만, proxy, anti-bot, browser crash, monitoring, maintenance cost가 숨어 있다.
  - 출처: https://knowledgesdk.com/blog/playwright-vs-api-scraping
  - 출처: https://knowledgesdk.com/blog/headless-browser-vs-api
  - 출처: https://www.browserless.io/browserless-vs-self-managed
- managed scraping/browser API는 anti-bot/proxy/browser 운영 부담을 줄일 수 있지만, request/credit 기반 비용과 vendor lock-in, schema debugging 한계가 있다.
  - 출처: https://fastcrw.com/blog/self-hosting-vs-cloud-scraping-cost
  - 출처: https://pagebolt.dev/blog/headless-browser-api-comparison

해석:

- 현재 우리는 EC2 1대 + Crawl4AI가 이미 있으므로 self-hosted를 유지하는 것이 합리적이다.
- 다만 특정 source가 high-yield인데 Playwright/proxy로 불안정하면 managed browser/scraping API를 "source-specific fallback"으로 검토할 수 있다.

정책 제안:

- 기본 path: self-hosted Crawl4AI
- fallback path: managed API only for high-yield blocked source
- 판단 metric:
  - `cost_per_successful_candidate`
  - `cost_per_confirmed_illegal`
  - `maintenance_hours_saved`
  - `debuggability`

### 17.4 데이터 최소화와 retention은 더 중요해진다

조사 결과:

- CTI 수집에는 privacy, computer crime laws, intellectual property concerns가 따른다.
  - 출처: https://cti.threatmanual.com/module-2-data-sources-and-collection/legal-and-ethical-considerations
- OSINT platform 중에는 personal data를 disk에 쓰지 않는 zero-retention architecture를 강조하는 사례도 있다.
  - 출처: https://osint.ph/blog/zero-retention-architecture
- OSINT privacy policy 사례들은 public endpoint에서 나온 데이터라도 retention, deletion/anonymization 정책을 둔다.
  - 출처: https://osint.ph/privacy
- public-interest OSINT guideline은 transparency, accountability, data protection policy, proportionality를 강조한다.
  - 출처: https://obsint.eu/guidelines-for-public-interest-osint-investigations/

해석:

- source coverage를 넓히면 연락처/계정/이미지/댓글 등 개인성 데이터가 늘어난다.
- 따라서 recall 개선과 동시에 data minimization/retention을 강화해야 한다.

정책 제안:

- P3/P4 non-hit raw data는 짧은 retention.
- contact handle은 별도 table + masking/hash option.
- 불법 확정/고위험 evidence만 장기 보존.
- `infra/DATA_POLICY.md`에 crawler artifact tier별 retention을 추가한다.

### 17.5 Binary/attachment metadata만 저장한다는 판단은 유지

조사 결과:

- CTI manual은 malware sample/proprietary data 수집이 IP/legal/privacy 리스크를 만들 수 있다고 설명한다.
  - 출처: https://cti.threatmanual.com/module-2-data-sources-and-collection/legal-and-ethical-considerations
- MISP는 malware-sample 자체를 표현할 수 있지만, 이는 별도 threat intelligence platform과 handling rule이 있는 환경을 전제한다.
  - 출처: https://www.misp-project.org/objects.pdf
- MISP architecture도 attachment/sample/logs를 disk에 저장한다고 설명한다. 즉 sample 저장은 별도 보안 운영 이슈다.
  - 출처: https://www.misp-project.org/2026/02/11/misp-architecture-choices.html/

해석:

- 지금 EC2 crawler에서 cheat binary나 attachment를 직접 다운로드하면 안 된다.
- attachment URL, filename, extension, advertised version, download count, hash if available 정도만 metadata로 저장한다.

정책 제안:

- `download_binary=false` hard policy.
- attachment metadata schema만 추가.
- binary 분석은 별도 sandbox/legal approval 이후 별도 project로 분리.

### 17.6 Evidence integrity와 재현성도 고려해야 한다

조사 결과:

- OSINT 조사에서는 evidence authenticity, metadata, access time, audit trail이 중요하다는 실무 논의가 많다.
  - 참고: https://www.reddit.com/r/OSINT/comments/1o9i7yn/curious_about_evidence_integrity_from_an_osint/
- 단, 모든 원문과 화면 녹화를 장기 보존하면 저장 비용과 privacy risk가 커진다.

해석:

- 우리 시스템은 법 집행용 증거 보존 시스템은 아니지만, 탐지 근거를 설명할 수 있어야 한다.
- 따라서 원문 전문 장기 보존보다 `accessed_at`, `source_url`, `canonical_url`, `screenshot_hash(optional)`, `raw_s3_key`, `parser_version`, `model_version`을 남기는 것이 현실적이다.

정책 제안:

- high-risk detection만 screenshot 또는 rendered HTML snapshot을 보존한다.
- low-risk/T4는 summary + metadata 중심으로 저장한다.
- parser/model/source profile version을 detection과 함께 저장한다.

### 17.7 추가 조사 후 보정된 원칙

1. Discord 직접 scraping은 하지 않는다. 공개 웹 index/landing page만 seed로 쓴다.
2. Telegram 직접 수집은 후순위다. 우선 공개 index와 seller page에 노출된 handle metadata만 쓴다.
3. OCR은 P0/P1 이미지 후보에만 selective 적용한다.
4. managed scraping API는 default가 아니라 high-yield blocked source의 fallback이다.
5. data minimization과 retention을 crawler redesign의 필수 요구사항으로 올린다.
6. binary/attachment 다운로드 금지 원칙은 유지한다.
7. evidence integrity는 full archive보다 metadata/version/audit 중심으로 시작한다.

## 18. 목표 범위: 개인정보 탈취 전 단계까지의 유통 경로 파악

작성일: 2026-06-05

우리가 원하는 목표:

- 불법 게임 프로그램이 실제로 어디서 발견되고, 어떻게 홍보되고, 어떤 연락/구매/다운로드 경로로 이어지는지 파악한다.
- 단, 피해자의 개인정보가 탈취되거나 악성 파일이 실행되는 단계까지 들어가지 않는다.
- 즉, "유통 경로와 위험 신호를 식별하는 CTI/OSINT"가 목표이며, "구매/다운로드/실행/침투 검증"은 목표가 아니다.

### 18.1 공개 자료에서 확인되는 유통 체인

게임 cheat/macro/bot 계열 위협은 대체로 다음 흐름으로 유통된다.

```text
1. 홍보/노출
   검색 결과, YouTube, 포럼, Reddit, seller site, Telegram/Discord mention

2. 신뢰 형성
   "undetected", "안전", "후기", "vouch", "support", "Discord/Telegram 상담", 가격표

3. 연락/구매 유도
   Telegram, Discord, QQ, WeChat, Kakao, email, payment/crypto

4. 다운로드/설치 유도
   loader, installer, zip, password-protected archive, MediaFire/GitHub/Discord CDN/사이트 다운로드

5. 실행 전 요구사항
   관리자 권한, 보안 프로그램 예외, anti-virus disable, game account login, license key

6. 실행 후 위험
   credential theft, Discord token theft, browser password/cookie theft, wallet theft, RAT/dropper
```

우리 시스템이 파악할 범위는 1~4의 "다운로드 링크/파일 metadata가 보이는 지점"까지다. 5~6은 직접 수행하지 않는다.

### 18.2 근거

- Activision은 Call of Duty: Warzone cheat로 위장한 malware/dropper 사례를 공개했다. cheat를 bait로 사용해 더 파괴적인 payload를 설치하는 흐름이 설명된다.
  - 출처: https://research.activision.com/publications/2021/03/cheating-cheaters-malware-delivered-as-call-of-duty-cheats
- Ars Technica도 같은 캠페인에 대해 cheat로 위장한 malware installer가 유통됐다고 보도했다.
  - 출처: https://arstechnica.com/gadgets/2021/04/activision-warns-of-malware-masquerading-as-cheats-for-call-of-duty-warzone/
- ThreatLocker는 2026년 fake game cheat/utility가 infostealer를 전달하고 Discord, Roblox, crypto wallet 등을 노린 캠페인을 관측했다.
  - 출처: https://www.threatlocker.com/blog/powercat-malware-campaign-fake-game-cheats-deliver-infostealer-targeting-discord-roblox-and-crypto-wallets
- Kaspersky는 fake installers, forums, Discord, MediaFire 등을 통한 gamer-targeting stealer campaign을 설명했다.
  - 출처: https://www.kaspersky.com/blog/gen-z-gaming-report-2025
- Acronis는 fake game sites, fake YouTube channels, Discord distribution을 통해 Electron-based stealers가 유통된 사례를 분석했다.
  - 출처: https://www.acronis.com/en-us/tru/posts/threat-actors-go-gaming-electron-based-stealers-in-disguise/
- Telegram에는 cybercriminal activity channel이 대규모로 존재한다는 연구가 있다.
  - 출처: https://arxiv.org/abs/2409.14596
- GitHub fake-star 연구는 game cheats, pirated software, crypto bots로 위장한 malware repository가 fake stars로 홍보될 수 있음을 보고했다.
  - 출처: https://arxiv.org/abs/2412.13459

### 18.3 우리가 수집할 수 있는 안전한 관측 지점

| 단계 | 수집 가능 정보 | 수집 여부 | 비고 |
|---|---|---|---|
| 홍보/노출 | page URL, title, source category, search query, language | 수집 | 안전한 metadata |
| 신뢰 형성 | 가격, 후기/vouch, undetected claim, update/version, support 문구 | 수집 | risk signal로 저장 |
| 연락 유도 | Telegram/Discord/QQ/WeChat/Kakao/email handle | 제한 수집 | masking/hash/retention 필요 |
| 구매 유도 | price, subscription, crypto/payment mention | 수집 | 결제 진행 금지 |
| 다운로드 유도 | download URL, filename, extension, advertised version, file host | metadata만 수집 | 파일 다운로드 금지 |
| 실행 요구 | admin 권한, AV disable, whitelist, loader instruction 문구 | 텍스트만 수집 | 실행/검증 금지 |
| 실행 후 탈취 | token/password/cookie/wallet theft | 직접 확인 금지 | 외부 보고서의 IOC만 참조 |

### 18.4 명확한 멈춤선

하지 않는다:

- cheat/bot/macro를 구매하지 않는다.
- binary, zip, loader, installer, APK를 다운로드하지 않는다.
- password-protected archive를 열지 않는다.
- 파일을 실행하지 않는다.
- sandbox에서라도 개인정보 탈취를 유도하지 않는다.
- Discord/Telegram에 자동 계정으로 가입해 메시지를 긁지 않는다.
- CAPTCHA, login, 실명/휴대폰 인증을 우회하지 않는다.
- stolen credential, token, cookie, wallet data를 수집하지 않는다.

한다:

- 공개 웹 page와 listing metadata를 수집한다.
- 다운로드 링크가 "존재한다"는 metadata를 기록한다.
- filename/extension/version/host/contact/price signal을 기록한다.
- 외부 보안 보고서의 malware family/IOC는 출처와 함께 참조한다.
- high-risk 후보는 screenshot/hash/accessed_at/parser_version/model_version으로 증거성을 남긴다.

### 18.5 제품 관점의 목표 정의

우리 시스템의 목표는 다음 질문에 답하는 것이다.

1. 어떤 source category에서 NC 게임 관련 불법 프로그램 신호가 많이 나오는가?
2. 어떤 게임/언어권/플랫폼에서 판매/배포 신호가 강한가?
3. 어떤 연락 채널과 file host가 반복적으로 등장하는가?
4. 어떤 source가 실제 P0/P1 후보를 많이 내는가?
5. 어떤 후보가 개인정보 탈취형 malware 위험으로 이어질 가능성이 높은가?

이 질문에 답하기 위해 필요한 것은 파일 실행이 아니라, 유통 경로 metadata와 risk signal이다.

### 18.6 설계에 반영할 필드

`CandidatePost` 또는 `CrawlEvent v2`에 다음 필드를 검토한다.

```python
distribution_stage: Literal[
    "promotion",
    "seller_page",
    "contact_redirect",
    "purchase_instruction",
    "download_metadata",
    "execution_instruction",
]
risk_signals: list[str]
contact_channels: list[str]        # masked/hash option
payment_signals: list[str]
download_hosts: list[str]
attachment_metadata: list[dict]    # url, filename, extension, size_if_visible only
claims: list[str]                  # undetected, safe, no-ban, bypass, auto-farm 등
stop_reason: str                   # no_download_policy, login_required, captcha, etc.
```

### 18.7 결론

우리가 추적할 것은 "유통 체인"이지 "악성코드 실행 결과"가 아니다.

따라서 crawler redesign은 다음 방향이 맞다.

1. high-yield seller/forum/source discovery를 강화한다.
2. contact/payment/download metadata를 구조화한다.
3. binary download와 platform 직접 scraping은 금지한다.
4. 개인정보 탈취 가능성은 외부 CTI 보고서와 metadata signal로 추정한다.
5. 탐지 결과에는 항상 `source`, `accessed_at`, `distribution_stage`, `stop_reason`을 남긴다.

## 19. 프로그램 내용 파악 범위

작성일: 2026-06-05

추가 목표:

- 가능하면 불법 프로그램이 "무엇을 하는 프로그램인지"도 파악한다.
- 단, 파일 다운로드/실행/동적 분석 없이 공개적으로 드러난 정보만 사용한다.

### 19.1 파악할 수 있는 내용

안전하게 파악 가능한 정보:

| 구분 | 예시 | 수집 방식 |
|---|---|---|
| 대상 게임 | Lineage, Lineage M, AION, BNS, TL | page title/body/query/source |
| 프로그램 유형 | macro, bot, helper, auto-farm, loader, bypass, private server tool | 판매 문구/기능 설명 |
| 주요 기능 | 자동사냥, 자동부활, 순간이동, 다계정, 알림, 자동구매, ESP, wallhack | 공개 설명/OCR |
| 지원 환경 | PC, Android emulator, 32/64-bit, server/region | 게시글/판매 페이지 |
| 버전/업데이트 | v1.0.27.5, 2026-06 update 등 | 제목/공지/다운로드 metadata |
| 배포 형태 | installer, loader, APK, zip, script, cloud phone, license key | 파일명/확장자/설명 |
| 구매 모델 | 월정액, lifetime, trial, subscription, key/license | 가격표/결제 안내 |
| 위험 claim | undetected, no-ban, bypass, anti-cheat safe | 판매 문구 |
| 실행 요구사항 | 관리자 권한, 백신 예외, emulator, Telegram bot 연동 | 공개 instruction |
| 연락/지원 | Telegram, Discord, QQ, WeChat, Kakao, email | contact metadata |

### 19.2 하지 않을 것

프로그램 내용을 더 알고 싶더라도 다음은 하지 않는다.

- 파일 다운로드
- 압축 해제
- installer/loader/APK/script 실행
- sandbox 동적 분석
- license key 구매
- 판매자에게 문의
- Discord/Telegram 비공개 채널 가입
- anti-cheat bypass 동작 검증
- 개인정보/토큰/쿠키/지갑 탈취 여부 직접 검증

### 19.3 안전한 추론 방식

프로그램 내용은 다음 근거 수준으로 분류한다.

| evidence level | 의미 |
|---|---|
| `claimed_by_seller` | 판매자/게시글이 주장한 기능 |
| `shown_in_screenshot` | 공개 스크린샷/OCR에 보이는 기능 |
| `filename_metadata` | 파일명/확장자/버전명에서 추론 |
| `external_report` | 보안 업체/게임사/뉴스 보고서에 언급 |
| `unverified` | 단서가 약해 확정 불가 |

중요:

- 판매자 claim은 사실일 수도 있고 과장일 수도 있다.
- 따라서 "이 프로그램은 X 기능을 가진다"가 아니라 "공개 페이지는 X 기능을 주장한다"로 저장한다.

### 19.4 분류 taxonomy 초안

프로그램 내용을 다음 taxonomy로 나눈다.

```text
automation_macro
auto_farming_bot
multi_account_control
combat_helper
notification_assistant
private_server_tool
loader_or_injector
anti_cheat_bypass_claim
game_memory_modification
account_or_payment_abuse
unknown_or_unclear
```

불법 프로그램 탐지와 직접 관련이 큰 bucket:

- `automation_macro`
- `auto_farming_bot`
- `loader_or_injector`
- `anti_cheat_bypass_claim`
- `game_memory_modification`

별도 정책 판단이 필요한 bucket:

- `private_server_tool`
- `rmt_boosting`
- `notification_assistant`
- `multi_account_control`

### 19.5 설계 필드 제안

`CandidatePost` 또는 `CrawlEvent v2`에 다음 필드를 추가 검토한다.

```python
program_family: str | None
program_type: str | None
target_games: list[str]
claimed_features: list[str]
supported_platforms: list[str]
distribution_format: list[str]   # loader, installer, apk, zip, script, cloud_phone
version_claims: list[str]
anti_detection_claims: list[str]
execution_requirements: list[str]
evidence_level: str
content_confidence: float
```

### 19.6 LLM/OCR 활용 방식

LLM에는 다음 질문을 던진다.

```text
이 페이지가 설명하는 프로그램은 무엇인가?
대상 게임은 무엇인가?
주장하는 기능은 무엇인가?
판매/배포/다운로드/연락 신호가 있는가?
파일 다운로드나 실행 없이 확인 가능한 evidence만 사용하라.
주장(claim)과 확인된 사실(observed fact)을 분리하라.
```

OCR은 다음 경우에만 선택적으로 사용한다.

- P0/P1 후보
- 이미지가 있고 본문 text signal이 부족함
- 가격표/기능표/연락처가 이미지에 있을 가능성이 있음

### 19.7 결론

프로그램 내용은 "정적·공개 정보 기반"으로 최대한 파악한다.

가능한 답:

- "이 페이지는 Lineage 2 자동사냥 bot을 판매한다고 주장한다."
- "공개 설명상 Telegram 연동, 자동부활, 다계정 제어 기능을 제공한다고 주장한다."
- "다운로드 링크는 보이지만 no-download policy 때문에 파일은 수집하지 않았다."

피해야 할 답:

- "실제로 실행해보니 계정을 탈취한다."
- "우회 기능이 실제로 동작한다."
- "파일 내부 구조를 확인했다."

즉, 프로그램 내용 파악은 가능하지만, 항상 `claim/evidence/stop_reason`을 함께 남겨야 한다.

## 20. 프록시 보안 설정 조사와 권장 구조

작성일: 2026-06-05

질문:

- 프록시는 어떻게 설정하는 것이 좋은가?
- 현재 코드 안에서 처리해도 되는가?
- 더 보안적으로 안전한 운영 구조는 무엇인가?

### 20.1 결론

프록시는 코드 안에서 source별로 설정하는 것이 맞다. 다만 다음 원칙을 지켜야 한다.

1. 전역 proxy default를 두지 않는다.
2. source별 `proxy_policy`를 둔다.
3. proxy credential은 코드/env/log에 노출하지 않는다.
4. free/open proxy는 사용하지 않는다.
5. residential proxy provider는 KYC/consent/compliance 정책을 확인한다.
6. proxy는 차단 우회 목적의 마지막 단계로만 사용한다.
7. login/captcha/실명/휴대폰 장벽은 proxy로 강행하지 않는다.

### 20.2 코드 관점

Crawl4AI는 proxy 설정을 공식 지원한다.

- Crawl4AI 문서는 `CrawlerRunConfig.proxy_config`를 통한 per-request proxy 설정을 권장한다.
  - 출처: https://docs.crawl4ai.com/advanced/proxy-security/
- `BrowserConfig`에도 global proxy 설정이 있지만, source별 정책을 적용하려면 run/request 단위가 더 적합하다.
  - 출처: https://docs.crawl4ai.com/api/parameters/
- Playwright도 proxy를 browser launch 또는 browser context 단위로 지원한다.
  - 출처: https://playwright.dev/docs/network
  - 출처: https://playwright.dev/docs/api/class-browsertype

현재 코드 상태:

- `crawler/src/sites/registry.py`에 `_brightdata_cn_proxy()`가 있다.
- `BRIGHTDATA_CN_USERNAME`, `BRIGHTDATA_CN_PASSWORD`를 읽는다.
- server는 `http://brd.superproxy.io:33335`다.
- 현재 proxy가 붙은 source는 `tieba`, `nga`뿐이고 둘 다 `enabled=False`다.

보정 제안:

- 현재처럼 `SiteConfig.proxy`에 dict를 직접 넣는 구조는 유지 가능하다.
- 다만 다음 단계에서는 `proxy_policy`와 `proxy_profile`을 분리한다.

```python
proxy_policy: Literal[
    "none",
    "optional",
    "required_cn_residential",
    "managed_unblocker_candidate",
    "blocked_do_not_bypass",
]
proxy_profile: str | None  # brightdata_cn, oxylabs_cn, managed_browser 등
```

### 20.3 provider와 제품 유형

#### Raw proxy

특징:

- 현재 코드가 쓰는 방식.
- Playwright/Crawl4AI browser traffic을 proxy server로 보낸다.
- 구현 난이도가 낮다.

적합한 경우:

- 지역/IP 차단 여부 확인
- source smoke test
- 낮은 수준의 rate limit 우회

한계:

- CAPTCHA, fingerprint, login, 실명/휴대폰 인증은 해결하지 못할 수 있다.
- target별 성공률을 직접 측정해야 한다.

#### Managed Unlocker API

Bright Data Web Unlocker는 proxy rotation, anti-bot challenge, CAPTCHA solving을 한 API call 안에서 처리한다고 설명한다.

- 출처: https://docs.brightdata.com/scraping-automation/web-unlocker/introduction
- 출처: https://docs.brightdata.com/scraping-automation/web-unlocker/features

중요:

- Bright Data Web Unlocker API는 Playwright/Puppeteer 같은 third-party browser automation 용도가 아니라고 문서에 명시되어 있다.
- clean HTML/JSON을 받아 parsing하는 source에 적합하다.

#### Managed Browser API / Unblocking Browser

Bright Data Browser API와 Oxylabs Unblocking Browser는 browser automation까지 provider가 관리하는 방식이다.

- Bright Data Browser API:
  - 출처: https://docs.brightdata.com/scraping-automation/scraping-browser
- Oxylabs Unblocking Browser:
  - 출처: https://developers.oxylabs.io/scraper-apis/unblocking-browser

적합한 경우:

- high-yield source인데 자체 Playwright + raw proxy가 계속 실패할 때
- anti-bot/fingerprint 문제가 핵심일 때

한계:

- 비용이 높다.
- vendor lock-in과 debugging 한계가 있다.
- 현재 예산/학생 인프라에서는 기본값으로 두기 어렵다.

### 20.4 보안 리스크: free/open proxy 금지

무료/open proxy는 사용하지 않는다.

근거:

- NDSS/학술 연구는 free web proxy가 privacy/security risk를 가진다고 보고한다.
  - 출처: https://www.ndss-symposium.org/ndss-paper/auto-draft-486/
  - 출처: https://arxiv.org/abs/2403.02445
- open proxy 대규모 연구에서는 TLS MitM와 binary modification/RAT injection 사례가 보고됐다.
  - 출처: https://arxiv.org/abs/1806.10258
- free proxy는 traffic logging, content injection, malware, cookie theft 같은 리스크가 있다.

정책:

- free proxy list 사용 금지.
- unknown open proxy 사용 금지.
- proxy provider는 KYC/consent/compliance 문서를 확인한다.

### 20.5 residential proxy compliance

residential proxy는 법무/윤리 리스크가 있으므로 provider sourcing 정책을 확인해야 한다.

근거:

- Bright Data는 residential network access policy와 KYC/compliance를 설명한다.
  - 출처: https://docs.brightdata.com/proxy-networks/residential/network-access
  - 출처: https://brightdata.com/trustcenter/kyc
- Bright Data residential proxy 문서는 approved applications를 통한 consent model을 설명한다.
  - 출처: https://docs.brightdata.com/proxy-networks/residential/introduction
- Oxylabs는 ethical proxy acquisition framework와 consenting/rewarded individuals를 언급한다.
  - 출처: https://oxylabs.io/legal/ethics-code
- 중국 residential proxy 연구는 residential proxy network가 local network에 보안 리스크를 만들 수 있음을 보고한다.
  - 출처: https://arxiv.org/abs/2209.06056

정책:

- provider의 KYC/consent/compliance 자료가 없는 residential proxy는 사용하지 않는다.
- 중국 residential proxy는 특히 보수적으로 접근한다.
- source별 필요성이 확인된 경우에만 켠다.

### 20.6 credential 관리

프록시 credential은 시크릿이다.

근거:

- AWS Secrets Manager best practice는 secret 저장, rotation, least privilege, monitoring을 권장한다.
  - 출처: https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html
- Docker secrets는 서비스를 명시적으로 grant한 경우에만 `/run/secrets`로 노출된다.
  - 출처: https://docs.docker.com/reference/compose-file/secrets/
- Docker docs는 secrets를 env var로 직접 설정하지 않는 설계를 설명한다.
  - 출처: https://docs.docker.com/engine/swarm/secrets/
- OWASP Secrets Management Cheat Sheet는 secret이 로그에 남지 않아야 한다고 한다.
  - 출처: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html

현재 인프라 제약:

- 학생 AWS 계정에서는 Secrets Manager 통로가 막혀 있어, 현재 프로젝트는 Docker secrets + EC2 `/opt/app/secrets` 파일 정책을 사용한다.
- 이 정책은 `infra/DATA_POLICY.md`와 ADR 0001에 정리되어 있다.

권장 구조:

- `/opt/app/secrets/brightdata_cn_username`
- `/opt/app/secrets/brightdata_cn_password`
- crawler container에만 mount
- api/detection/dashboard에는 mount하지 않음
- compose `environment`에 proxy credential 직접 주입 금지
- logs에 proxy URL 전체 출력 금지

### 20.7 logging/observability 보안

기록해야 하는 것:

- `proxy_profile`: `brightdata_cn`
- `proxy_used`: true/false
- `proxy_policy`: optional/required 등
- `proxy_result`: success/blocked/captcha/login/tunnel_failed
- `latency_ms`
- `bytes_estimated`
- `source_id`

기록하지 말아야 하는 것:

- proxy username
- proxy password
- full proxy URL
- provider API key
- session token
- contact handle 원문은 정책에 따라 masking/hash

로그 예시:

```json
{
  "source_id": "tieba",
  "proxy_profile": "brightdata_cn",
  "proxy_used": true,
  "proxy_result": "blocked_login_required",
  "status": 403
}
```

금지 예시:

```text
http://username:password@brd.superproxy.io:33335
```

### 20.8 IP allowlist와 인증

provider별로 IP allowlist 또는 username/password authentication을 지원한다.

- Bright Data Proxy Manager는 allowlist IP와 token/API key 기반 설정을 제공한다.
  - 출처: https://docs.brightdata.com/proxy-networks/proxy-manager/faqs
  - 출처: https://docs.brightdata.com/api-reference/proxy-manager/ui-allowlist-ips
- Bright Data는 allowlist가 비어 있으면 irregular activity로 block될 수 있어 allowlisting을 권장한다.
  - 출처: https://docs.brightdata.com/proxy-networks/faqs
- Oxylabs는 IP whitelist를 지원하지만 AWS 같은 환경에서는 username/password auth를 권장한다.
  - 출처: https://developers.oxylabs.io/help-center/products-and-features/how-can-i-whitelist-ips

우리 상황:

- EC2 public IP가 고정 Elastic IP인지 확인 필요.
- 고정 IP면 provider dashboard에서 allowlist 가능.
- IP가 바뀔 수 있으면 username/password auth가 현실적이다.

권장:

- provider dashboard에서 가능하면 EC2 public IP allowlist.
- username/password auth도 유지.
- credential rotation 절차를 문서화.

### 20.9 rotation/session 정책

모든 요청마다 proxy를 회전하는 것은 항상 좋은 전략이 아니다.

이유:

- browser fingerprint와 IP 지역/언어가 불일치하면 더 의심스러울 수 있다.
- session continuity가 필요한 사이트는 잦은 회전이 실패율을 올린다.
- proxy traffic 비용이 증가한다.

권장:

- source별 sticky session을 기본으로 둔다.
- Accept-Language와 proxy region을 맞춘다.
- CN source에는 CN profile, TW source에는 TW/nearby profile, global seller site는 proxy 없음부터 시작.
- 429/503/rate-limit에서만 backoff 또는 profile 변경.

### 20.10 source별 권장 policy

| source type | 기본 proxy policy | 이유 |
|---|---|---|
| Inven/PTT/Bahamut | `none` | 현재 접근 가능, proxy 불필요 |
| Dcard | `none` 또는 `optional` | SPA/anti-bot 상태만 smoke |
| 52pojie | `none` 우선 | 현재 enabled, proxy 없음 |
| seller_site | `none` 우선 | 공개 landing page 가능성 높음 |
| cheat_forum Discuz | `none` 우선, 막히면 `optional` | forum형 parser 가능 |
| Tieba/Baidu/NGA | `blocked_do_not_bypass` 또는 `required_cn_residential_trial` | 기존 PoC 실패/로그인/실명 장벽 |
| Discord | `blocked_do_not_scrape_platform` | ToS 리스크 |
| Telegram | `public_index_only` | 직접 client scraping 후순위 |

### 20.11 구현 권장 순서

1. `ProxyProfile` 모델 추가
2. `SourceProfile.proxy_policy` 추가
3. proxy credential은 Docker secrets로 crawler에만 mount
4. `CrawlOptions`에서 proxy dict 직접 보관 대신 profile resolver 사용
5. Crawl4AI proxy를 가능하면 `CrawlerRunConfig.proxy_config`로 이동
6. proxy URL redaction helper 추가
7. source access smoke에 `proxy_result` 기록
8. provider dashboard에서 EC2 IP allowlist 가능 여부 확인
9. Bright Data raw proxy로 source별 smoke
10. high-yield blocked source만 managed browser/unlocker 후보로 승격

### 20.12 최종 권장안

현 시점 최선:

- 새 provider를 바로 도입하지 않는다.
- 현재 Bright Data raw proxy path를 source smoke에 연결한다.
- proxy는 전역 기본값이 아니라 source별 opt-in으로 둔다.
- free/open proxy는 금지한다.
- credential은 Docker secrets로 crawler에만 mount한다.
- logs에는 proxy credential을 절대 남기지 않는다.
- login/captcha/실명/휴대폰 인증 장벽은 우회하지 않는다.
- high-yield source에서 raw proxy가 실패할 때만 managed browser/API를 검토한다.

## 21. 프록시 추가 조사: 비용, 성능, 탐지 저항, 운영 리스크

### 21.1 이번 추가 조사의 질문

앞 절에서는 "어떻게 안전하게 프록시를 붙일 것인가"를 정리했다.

이번 추가 조사는 더 현실적인 질문이다.

1. 프록시를 붙이면 실제로 수집량이 늘어나는가?
2. 어떤 경우에는 돈만 쓰고 성공률이 안 오르는가?
3. 우리처럼 EC2 1대 + RDS 1대 + Docker Compose 운영에서는 어떤 비용 방어선이 필요한가?
4. 불법 프로그램 유통 경로 파악이라는 목표에서 어디까지 접근하고 어디서 멈춰야 하는가?

### 21.2 결론 요약

프록시는 "수집량 증가 장치"가 아니라 "접근 실패 원인 중 IP/지역/평판 문제를 분리해서 검증하는 장치"로 봐야 한다.

프록시가 도움이 되는 경우:

- 특정 지역에서만 보이는 공개 페이지
- datacenter IP 또는 AWS IP가 차단되는 공개 페이지
- 같은 사이트에 낮은 속도로 접근해도 IP 평판 때문에 403/429가 반복되는 경우
- 로그인 없이 볼 수 있는 forum/list/detail HTML인데 지역/IP 제한만 있는 경우

프록시가 별 도움이 안 되는 경우:

- 로그인이 필요한 자료
- CAPTCHA, 휴대폰 인증, 실명 인증이 필요한 자료
- JavaScript/browser fingerprint challenge가 핵심인 사이트
- bot protection이 IP 외에도 TLS fingerprint, HTTP header consistency, browser fingerprint, behavior, cookie/session을 같이 보는 사이트
- platform ToS상 자동 수집 리스크가 큰 Discord/Telegram private channel류

따라서 우리 설계는 다음이 맞다.

- `proxy_policy=none` 기본값 유지
- source smoke로 실패 원인을 분류
- IP/지역 문제일 때만 raw proxy trial
- raw proxy로 성공률이 의미 있게 오르면 source별 opt-in
- fingerprint/challenge/login/phone barrier면 우회 개발이 아니라 `blocked_do_not_bypass`
- managed unblocker/browser는 마지막 단계, 비용 상한을 걸고 실험

### 21.3 왜 프록시만으로는 부족한가

최근 bot 방어 제품은 단순히 IP만 보지 않는다.

Cloudflare Bot Management 문서는 bot detection engine이 heuristics, JavaScript detections, machine learning, anomaly detection 등을 조합한다고 설명한다. 입력 신호에는 header, session characteristic, browser signal이 포함된다.

- 출처: https://developers.cloudflare.com/bots/concepts/bot-detection-engines/

DataDome 문서도 signature, behavior, reputation 기반 탐지를 나눈다. 여기에는 TLS fingerprint, browser fingerprint, HTTP header, abnormal behavior, IP reputation, datacenter/residential/free proxy 여부가 포함된다.

- 출처: https://docs.datadome.co/docs/ai-detection

이 말은 중요하다.

프록시를 바꿔도 다음이 어색하면 여전히 막힐 수 있다.

- AWS/Playwright/browser fingerprint mismatch
- 중국 IP인데 `Accept-Language: ko-KR` 또는 timezone이 한국/UTC로 보이는 문제
- 같은 source 안에서 매 요청 IP가 바뀌는 session continuity 붕괴
- HTTP header 순서/값이 실제 브라우저와 다른 문제
- 너무 빠른 페이지 전환, 반복적 list/detail 패턴
- cookie/session을 보존하지 않는 요청 구조

그래서 우리 정책은 "더 많이 우회"가 아니라 "더 정확히 실패 원인을 기록"하는 쪽이어야 한다.

### 21.4 비용 구조에서 제일 위험한 부분

Bright Data 공식 pricing FAQ 기준으로 residential proxy bandwidth는 request header + request data + response header + response data 합산으로 계산된다.

- 출처: https://brightdata.com/pricing/proxy-network/residential-proxies

또 Bright Data pricing FAQ에는 daily usage spend limit을 bandwidth 또는 money 기준으로 둘 수 있고, 한도 초과 시 zone이 suspend될 수 있다고 나온다.

- 출처: https://brightdata.com/pricing/proxy-network/residential-proxies

즉 비용은 "요청 수"보다 "받아온 byte"에 더 민감하다.

우리에게 특히 위험한 패턴:

- Playwright로 이미지/폰트/동영상까지 로드
- list page를 너무 자주 재방문
- detail page의 full snapshot을 계속 저장
- 같은 URL을 proxy 경유로 반복 retry
- 실패한 source를 무제한 재시도
- managed browser/unlocker를 general crawler처럼 사용

비용 절감 원칙:

- proxy smoke는 HTML/text 중심으로 시작
- image/font/media request 차단 옵션 검토
- per-source daily cap
- per-run proxy byte cap
- failed source retry budget
- managed browser/API는 high-yield source의 POC에만 사용
- provider dashboard spend limit 필수

### 21.5 우리 인프라 기준 비용 방어선

현재 우리는 EC2 1대, RDS 1대, Docker Compose 기반이다.

따라서 proxy 비용은 AWS 고정비보다 더 쉽게 튈 수 있다.

권장 방어선:

| 항목 | 권장값 |
|---|---|
| 기본 proxy | off |
| source별 proxy | allowlist 방식 |
| daily proxy spend | provider dashboard에서 강제 제한 |
| crawler 내부 cap | source/run 단위 byte/request/time cap |
| retry | exponential backoff + max retry |
| media load | proxy 경유 시 image/font/media 차단 우선 |
| managed browser/API | 별도 feature flag |
| 실험 기간 | 1-3일 smoke 후 유지/폐기 |

추가로 비용 로그는 최소한 아래 단위로 남겨야 한다.

```json
{
  "source": "tieba_lineage",
  "proxy_profile": "brightdata_cn",
  "proxy_policy": "required_cn_residential_trial",
  "requests": 42,
  "success": 9,
  "blocked": 22,
  "bytes_estimated": 1842201,
  "duration_ms": 99120,
  "cost_bucket": "proxy_smoke",
  "decision": "stop_or_continue"
}
```

정확한 비용은 provider dashboard가 기준이지만, crawler 내부에도 근사 byte와 request 수가 있어야 "왜 돈이 나갔는지"를 추적할 수 있다.

### 21.6 provider 선택 기준

지금 당장 새 provider를 늘릴 필요는 낮다.

다만 비교 기준은 명확히 잡아야 한다.

| 기준 | 봐야 할 것 | 이유 |
|---|---|---|
| compliance | KYC, opt-in residential sourcing | 연구/보안 목적에서 평판 리스크 감소 |
| spend control | daily/monthly cap, dashboard usage | 예산 폭주 방지 |
| geo targeting | CN/TW/HK/JP/KR 가능 여부 | 중국/대만/한국 커뮤니티 접근 검증 |
| sticky session | session 유지 기간/제어 | 로그인 없는 forum traversal에도 안정성 필요 |
| protocol | HTTP/HTTPS/SOCKS5, Playwright 호환 | Crawl4AI/Playwright 연결 |
| logs | provider usage export/API | 비용 계측 자동화 |
| support | blocked target 대응 가이드 | smoke 실패 분석 |
| managed option | browser/unlocker 별도 제공 | raw proxy 실패 시 후속 실험 |

Bright Data는 residential network가 explicit opt-in 모델이라고 설명하고, KYC/compliance process도 안내한다.

- 출처: https://docs.brightdata.com/proxy-networks/residential/introduction
- 출처: https://brightdata.com/pricing/proxy-network/residential-proxies

Oxylabs는 Dashboard API, HTTP/3 residential/mobile support, sticky session 관련 업데이트를 공지하고 있다.

- 출처: https://oxylabs.io/

다만 provider 공식 문서는 판매 목적도 있으므로, 실제 판단은 우리 source smoke 결과로 해야 한다.

### 21.7 raw proxy, Web Unlocker, Browser API의 경계

제품 선택을 혼동하면 비용이 커진다.

| 방식 | 장점 | 단점 | 우리 권장 |
|---|---|---|---|
| raw proxy | 코드 통제 쉬움, 비용 상대적으로 예측 가능 | fingerprint/challenge 해결 못할 수 있음 | 1차 smoke |
| Web Unlocker/API | retry/challenge 일부 처리, HTML 획득 쉬움 | request/result 과금, crawler 제어 감소 | high-yield 실패 source만 |
| Browser API/Headless Browser | browser-level site에 유리 | 가장 비싸고 lock-in 큼 | 최후순위 POC |

Bright Data pricing FAQ도 scraping에는 Web Unlocker를 추천하지만, 여기에는 CAPTCHA solving/automated retries가 포함된다고 설명한다.

- 출처: https://brightdata.com/pricing/proxy-network/residential-proxies

우리 윤리/보안 경계에서는 이 지점이 중요하다.

CAPTCHA solving을 자동화해서 protected area에 들어가는 것은 우리 목적과 맞지 않을 수 있다. 따라서 Web Unlocker/Browser API를 쓰더라도 public page access smoke로만 제한하고, login/phone/real-name/captcha wall은 중단 사유로 남긴다.

### 21.8 robots.txt, ToS, rate limit

프록시를 쓰더라도 polite crawling 원칙은 더 중요해진다.

MDN은 robots.txt가 crawler 접근 규칙을 전달하는 파일이라고 설명한다.

- 출처: https://developer.mozilla.org/en-US/docs/Web/Security/Practical_implementation_guides/Robots_txt

CJARS scraping guideline은 ToS, privacy policy, robots.txt, crawl-delay를 검토하고, parallel worker 수를 제한하며, target 서버에 부담을 주는 반복 실행을 금지해야 한다고 정리한다.

- 출처: https://cjars.org/wp-content/uploads/scraping_guidelines-20250908_final.pdf

우리 적용:

- source 등록 시 `robots_checked_at`, `tos_risk`, `crawl_delay` 메타데이터 추가 검토
- `robots.txt`가 명시적으로 막는 경로는 수집 제외 또는 별도 검토
- crawl-delay가 있으면 source별 delay에 반영
- worker 수는 source당 1-2부터 시작
- 403/429는 실패로 기록하고 무한 재시도 금지
- proxy 사용은 rate-limit 회피가 아니라 지역/IP 문제 검증에 한정

### 21.9 중국/대만/한국 소스에서의 특수 리스크

중국권 source 접근에는 세 가지 문제가 섞인다.

1. 지역/IP 차단
2. 로그인/실명/휴대폰 인증 장벽
3. 개인정보/플랫폼 규정 리스크

중국 PIPL 조문은 개인 정보 처리가 합법성, 정당성, 필요성, 선의 원칙을 따라야 하며 오도/사기/강박이 없어야 한다고 규정한다.

- 출처: https://en.spp.gov.cn/2021-12/29/c_948419.htm

우리 적용:

- 전화번호, 계정 ID, 개인 프로필 등 개인정보성 필드는 수집 최소화/마스킹
- 판매자 연락처는 유통 경로 증거로 필요한 경우에만 저장
- private chat 진입, 구매, 결제, 다운로드, 실행은 금지
- 공용 검색 결과/공개 게시글/공개 랜딩 페이지만 후보
- CN proxy를 쓰더라도 login/real-name barrier는 중단

### 21.10 source smoke 판정 기준

프록시 도입 전에 모든 source에 대해 같은 smoke format을 돌려야 한다.

판정 예시:

| 결과 | 의미 | 후속 |
|---|---|---|
| `ok_no_proxy` | proxy 불필요 | proxy off |
| `ok_proxy_only` | IP/지역 문제 가능성 | source별 proxy trial |
| `blocked_403_no_proxy_and_proxy` | IP 외 문제 가능 | header/browser/fingerprint 여부만 기록 |
| `captcha` | challenge barrier | bypass 금지, 중단 |
| `login_required` | 인증 barrier | 중단 |
| `phone_or_realname_required` | 고위험 인증 barrier | 중단 |
| `js_render_required` | rendering 필요 | Playwright/no proxy 우선 |
| `fingerprint_suspected` | managed API 없이는 어려움 | high-yield면 POC 후보 |
| `tos_high_risk` | 플랫폼 정책 리스크 | 제외 또는 수동 검토 |

성공률 metric:

- listing fetch success rate
- detail URL extraction count
- detail fetch success rate
- candidate post count
- illegal-program-risk candidate count
- duplicate rate
- blocked/error rate
- estimated bytes
- estimated cost
- manual review hit rate

### 21.11 우리 코드 설계에 추가 반영할 점

앞 절의 구현 순서에 다음을 추가한다.

1. `SourceAccessResult` 또는 `SourceSmokeResult` 테이블/파일 추가
2. `blocked_reason` enum 추가
3. `proxy_used`, `proxy_profile`, `proxy_region`, `proxy_bytes_estimated` 기록
4. `robots_policy`와 `tos_risk` 메모 필드 추가
5. source별 `max_proxy_requests_per_run` 추가
6. source별 `max_proxy_bytes_per_day` 추가
7. Playwright route에서 proxy 사용 시 image/font/media block option 검토
8. `redact_proxy_url()`를 logging formatter 레벨에 적용
9. 실패 retry는 source별 budget으로 제한
10. dashboard에는 "proxy로 늘어난 수집량"과 "proxy 비용 대비 후보 증가량"을 같이 노출

중요한 KPI는 단순 `fetch_success_rate`가 아니다.

우리 목표 KPI:

```text
cost_per_new_candidate
cost_per_relevant_candidate
cost_per_confirmed_distribution_path
```

즉, 프록시 비용을 썼는데 후보만 늘고 실제 불법 프로그램 유통 경로 증거가 안 늘면 실패다.

### 21.12 반대 의견과 우리 판단

반대 의견 1: "프록시를 쓰면 더 많이 가져올 수 있으니 적극적으로 써야 한다."

- 일부 맞다.
- 하지만 bot 방어는 IP 외 신호를 많이 보며, free/residential/datacenter proxy 자체가 탐지 신호가 될 수 있다.
- 비용도 bandwidth 기반이라 Playwright traffic이 커질 수 있다.
- 따라서 opt-in + smoke + cap이 맞다.

반대 의견 2: "Managed Unlocker를 쓰면 개발 시간을 줄일 수 있다."

- high-yield source에는 맞다.
- 그러나 CAPTCHA solving/retry 자동화는 윤리/법적 경계가 애매해질 수 있다.
- 또한 request/result 과금이라 대량 후보 탐색에는 부적합할 수 있다.
- 따라서 POC 전용으로 둔다.

반대 의견 3: "중국 source는 CN residential proxy 없이는 의미 없다."

- 일부 source에는 맞을 수 있다.
- 하지만 tieba/nga의 실제 병목이 IP가 아니라 login/phone/real-name이면 proxy로 해결하면 안 된다.
- 먼저 no-proxy vs CN-proxy smoke로 원인을 분리해야 한다.

반대 의견 4: "Discord/Telegram이 실제 유통 채널이면 들어가야 한다."

- 공개 invite page, public indexed post, seller landing page는 볼 수 있다.
- 하지만 private room join, 계정 생성, 대화, 구매, 파일 요청은 운영/법적 리스크가 커진다.
- 우리 목표는 개인정보 탈취 전 경로 파악이므로 public evidence + stop_reason으로 충분한 경우가 많다.

### 21.13 업데이트된 최종 권장안

프록시 관련 다음 액션은 구현 전에 이 순서가 좋다.

1. source smoke runner 작성
2. 현재 enabled source를 proxy 없이 측정
3. disabled CN source를 no-proxy로 재측정
4. 기존 Bright Data CN raw proxy가 있다면 같은 source를 낮은 cap으로 재측정
5. `ok_proxy_only`인 source만 proxy opt-in 후보
6. `captcha/login/phone/realname`은 우회 금지로 제외
7. provider dashboard spend limit 설정 확인
8. crawler 내부 request/byte/time cap 추가
9. 비용 대비 후보 증가량을 문서/대시보드로 비교
10. 그 후에도 높은 가치가 남는 source만 managed browser/API POC

현재 판단:

- 수집량을 늘리는 1순위는 proxy가 아니라 hard filter 완화와 candidate preservation이다.
- proxy는 2순위로, 접근 실패 source의 원인 분리와 지역 제한 source 검증에 쓴다.
- 비용/보안상 프록시는 전역 기본값이 아니라 source-level controlled experiment로 써야 한다.

## 22. 비용 없이 먼저 할 수 있는 최선의 개선안

### 22.1 원칙

우리 상황에서는 돈을 쓰는 방법이 최후 수단이어야 한다.

현재 인프라는 EC2 1대, RDS 1대이고 이미 crawler, detection, api, dashboard가 한 서버에서 돈다. 따라서 외부 proxy, managed browser, paid scraping API를 붙이기 전에 먼저 코드/수집 전략/필터링/계측을 고쳐야 한다.

현재 문제의 핵심은 "인터넷 전체에 접근하지 못해서 수집량이 적다"라기보다, 접근 가능한 곳에서도 너무 일찍 버리고, 너무 적게 가져오고, 수집 실패 원인을 충분히 기록하지 않는다는 점이다.

### 22.2 무비용 1순위: hard filter를 soft scoring으로 바꾸기

현재 mixed board에서는 `title_keywords`가 hard filter로 동작한다.

문제:

- 제목에 NC/game keyword가 없으면 본문이 관련 있어도 버려진다.
- 불법 프로그램 글은 일부러 은어, 약어, 이미지, 외부 링크만 쓰는 경우가 많다.
- "매크로", "外挂", "사설서버" 같은 직접 키워드만으로는 유통 글을 넓게 잡기 어렵다.

개선:

- listing 단계에서는 버리지 않는다.
- keyword match는 `priority_score`에만 반영한다.
- 낮은 점수 후보도 일정 비율 sample로 저장한다.
- detail fetch 이후 본문/링크/이미지 alt/text/domain까지 보고 판단한다.

기대 효과:

- 프록시 없이도 후보 수가 바로 늘어난다.
- false positive는 늘 수 있지만, 후보 보존 후 downstream scoring으로 줄일 수 있다.
- 현재 "화면에 뜨는 데이터가 적다"는 피드백에는 가장 직접적이다.

### 22.3 무비용 2순위: `MAX_POSTS_PER_BOARD=10` 제한 재조정

현재 scheduler는 board당 최대 post 수를 환경변수 `MAX_POSTS_PER_BOARD`로 제한하고 기본값이 10이다.

문제:

- 활성 source가 많아도 source당 10개면 총 후보 풀이 작다.
- 일부 board는 첫 페이지 최신글이 잡담/공지/거래글 위주일 수 있다.
- 불법 프로그램 유통 글은 최신 10개 안에 없을 가능성이 높다.

개선:

- 기본값을 10에서 30 또는 50으로 올리는 실험
- source별 limit 분리
- high-yield source는 더 많이, low-yield source는 적게
- 실행 시간과 DB 증가량을 같이 측정

주의:

- 무작정 100 이상으로 올리면 EC2/DB/LLM 비용이 뒤에서 터질 수 있다.
- 먼저 candidate 저장까지만 늘리고, LLM/detection은 priority queue로 제한한다.

### 22.4 무비용 3순위: 더 깊은 페이지 수집

현재 많은 forum source는 사실상 첫 listing 중심으로 움직인다.

개선:

- page 1만 보지 말고 page 2-5까지 후보 URL 수집
- 단, 모든 detail을 바로 fetch하지 않고 candidate URL inventory부터 만든다.
- 오래된 페이지는 낮은 priority로 두고 sample한다.

기대 효과:

- 최신글 편향이 줄어든다.
- 유통 글이 며칠/몇 주 유지되는 forum에서는 발견률이 오른다.

### 22.5 무비용 4순위: 키워드 사전 확장

현재 `_NC_GAME_KEYWORDS`는 게임명/회사명 중심이고, 불법 프로그램 유통 신호는 상대적으로 적다.

확장해야 할 축:

| 축 | 예시 |
|---|---|
| 기능 | macro, bot, auto, 자동, 매크로, 外挂, 外掛, 辅助, 脚本, script |
| 판매 | 판매, 구매, 대여, 월정액, 인증키, license, 卡密, 购买, 出售 |
| 유통 | download, 下载, 링크, 텔레그램, 디스코드, QQ, WeChat |
| 회피 | anti-ban, undetected, bypass, 防封, 免封, 무정지 |
| 게임별 은어 | 리니지/아이온/블소/TL 별 클래스명, 서버명, 재화명 |

중요:

- 이 키워드는 hard filter가 아니라 scoring feature로 쓴다.
- 직접 불법 키워드가 없어도 외부 링크/domain/가격/연락처 패턴으로 후보화한다.

### 22.6 무비용 5순위: URL/domain/link 기반 후보화

불법 프로그램 유통 글은 본문보다 외부 링크가 더 강한 신호일 수 있다.

수집해야 할 feature:

- external domain
- shortener 사용 여부
- Telegram/Discord/QQ/WeChat mention
- file hosting 링크
- seller landing page 링크
- 반복 등장하는 domain
- 같은 seller contact가 여러 source에 등장하는지

장점:

- 언어가 달라도 신호가 유지된다.
- 본문이 짧아도 유통 경로를 잡을 수 있다.
- 개인정보를 탈취하기 전 단계까지만 경로를 파악한다는 목표와 잘 맞는다.

### 22.7 무비용 6순위: 수집 실패 원인 계측

프록시를 쓰기 전에 "왜 못 가져왔는지"부터 알아야 한다.

필요한 `blocked_reason`:

- `ok`
- `empty_content`
- `http_403`
- `http_404`
- `http_429`
- `timeout`
- `captcha`
- `login_required`
- `phone_required`
- `realname_required`
- `js_render_required`
- `parser_failed`
- `validator_rejected`
- `duplicate_url`
- `duplicate_body`

이 계측이 있어야 다음 판단이 가능하다.

- 프록시가 필요한 문제인가?
- parser 문제인가?
- validator가 너무 빡센가?
- detail URL 추출이 적은가?
- source 자체가 low-yield인가?

### 22.8 무비용 7순위: 화면 표시 필터와 수집량 분리

현재 화면에 뜨는 수가 적다는 피드백은 두 가지가 섞여 있을 수 있다.

1. 실제 수집 후보가 적다.
2. 수집은 했지만 API/dashboard에서 high-confidence illegal만 보여준다.

따라서 dashboard/API에서 다음 숫자를 분리해서 보여줘야 한다.

- fetched listing count
- extracted URL count
- fetched detail count
- candidate post count
- validator rejected count
- duplicate count
- detection processed count
- illegal true count
- confidence >= 0.70 count
- displayed count

이렇게 해야 "크롤러가 적게 가져온다"와 "탐지/표시 필터가 적게 보여준다"를 구분할 수 있다.

### 22.9 무비용 8순위: validator를 이중화

현재 `content_validator.validate()`에서 `real`만 통과시키는 구조는 noise를 줄이는 데 좋지만, 초기 발견 단계에서는 너무 보수적일 수 있다.

개선:

- storage용 validator와 detection용 validator를 분리
- `candidate`, `uncertain`, `real`, `spam`, `blocked` 같은 등급화
- `real`만 화면/탐지로 보내지 말고, `candidate`도 저비용 queue에 저장
- LLM/detection은 priority로 제한

기대 효과:

- 수집량과 후보량이 늘어난다.
- 완전한 쓰레기 데이터는 계속 줄일 수 있다.

### 22.10 무비용 9순위: source yield benchmark

모든 source를 똑같이 다루면 비용과 시간이 낭비된다.

source별로 다음 metric을 매일 저장한다.

```text
source
listing_success_rate
urls_extracted
details_fetched
candidates_saved
duplicates
validator_rejected
illegal_candidates
confirmed_distribution_paths
runtime_seconds
```

이후 source를 세 등급으로 나눈다.

- A: 수집 잘 되고 관련 후보도 나오는 source
- B: 수집은 되지만 관련 후보가 적은 source
- C: 막히거나 noise만 많은 source

프록시는 C에 바로 쓰는 게 아니라, A/B에서 더 확장할 수 없는지 먼저 본다. C 중에서도 "막혀 있지만 가치가 검증된 source"만 나중에 proxy 후보가 된다.

### 22.11 무비용 10순위: 로컬 실험 순서

코드 반영 전 로컬에서 다음 순서로 실험할 수 있다.

1. 현재 설정으로 1회 실행해 baseline 저장
2. `MAX_POSTS_PER_BOARD=30`으로 실행
3. title hard filter를 끈 dry-run 실행
4. page depth를 2-3으로 늘린 dry-run 실행
5. candidate URL 수, detail fetch 수, validator rejected 수 비교
6. DB 저장 전 JSONL로 candidate inventory만 저장
7. 상위 100개를 사람이 빠르게 검토
8. keyword/scoring 사전 보정
9. detection queue로 보낼 priority threshold 결정
10. 그 뒤에만 운영 반영

### 22.12 지금 당장 우선순위

가장 현실적인 순서:

1. 계측 추가: 어디서 버려지는지 숫자로 확인
2. `title_keywords` hard filter 제거 또는 soft scoring화
3. candidate preservation 추가
4. source별/page별 수집량 증가
5. 키워드/링크/domain feature 확장
6. validator를 등급형으로 변경
7. dashboard에서 수집량/탐지량/표시량 분리
8. source yield benchmark
9. 그래도 특정 고가치 source가 IP 문제로 막힐 때만 proxy smoke
10. paid managed option은 마지막

한 줄 결론:

프록시보다 먼저 할 수 있는 최선은 "더 많이 우회"가 아니라 "이미 접근 가능한 공개 데이터에서 너무 일찍 버리지 않고, 후보를 보존하고, 어디서 줄어드는지 계측하는 것"이다.

## 23. 실험 브랜치 적용 기록

### 23.1 브랜치

- 브랜치: `crawler-candidate-preservation-exp`
- 목적: 비용 없이 수집 후보량을 늘리는 1차 실험

### 23.2 1차 반영 내용

코드에 먼저 반영한 것은 가장 작은 무비용 개선이다.

1. `title_keywords` hard filter 제거
   - 기존: 혼합 보드에서 제목 키워드가 없으면 fetch 전에 버림
   - 변경: 제목 키워드는 우선순위 feature로만 사용
   - 효과: 제목에 직접 키워드가 없는 은어/외부 링크 중심 글도 후보로 남음

2. 키워드 매칭 후보 우선 정렬
   - 관련 제목 후보를 먼저 fetch
   - 키워드 미매칭 후보도 같은 limit 안에서 최신순으로 보존

3. `MAX_POSTS_PER_BOARD` 기본값 상향
   - 기존 기본값: `10`
   - 변경 기본값: `30`
   - 운영에서는 환경변수로 다시 조정 가능

4. listing 단계 계측 추가
   - 처리 board 수: `listing_boards`
   - listing에서 선택된 URL 수: `listing_urls_selected`
   - title keyword가 있는 source는 total/selected/matched/unmatched 로그 출력

5. 회귀 테스트 보강
   - `title_keywords`가 options로 전달되는지 확인
   - 키워드 미매칭 후보가 필터링되지 않고 남는지 확인

### 23.3 아직 하지 않은 것

아직 1차 실험에는 포함하지 않았다.

- `CandidatePost` 별도 저장 모델
- validator 등급화
- page depth 자동 확장
- 외부 링크/domain feature 저장
- dashboard/API에 수집량/탐지량/표시량 분리 노출
- proxy smoke

### 23.4 다음 구현 후보

다음으로 가장 자연스러운 순서:

1. `_fetch_post_urls` 결과에 `discovered_total`, `keyword_matched`, `keyword_unmatched`를 구조화해서 `PipelineStats`에 반영
2. `validator_rejected`를 kind별로 dashboard/API에서 볼 수 있게 전달
3. candidate inventory JSONL dry-run 모드 추가
4. page depth를 source별로 안전하게 확장

## 24. 실제 로컬 크롤링 검증 방법 조사

### 24.1 질문

우리가 지금 필요한 것은 pytest가 아니다.

pytest는 mock 기반으로 코드 계약을 확인하는 데 필요하지만, "실제로 공개 사이트에서 후보가 얼마나 늘어나는가"는 확인하지 못한다. 이번 단계에서 필요한 것은 실제 브라우저 기반 smoke crawl이다.

### 24.2 공식 문서 기준

Crawl4AI 공식 설치 문서는 기본 설치 후 Playwright browser 설치가 필요하다고 안내한다.

- 출처: https://docs.crawl4ai.com/basic/installation/

Crawl4AI quickstart는 `AsyncWebCrawler`, `BrowserConfig`, `CrawlerRunConfig`, `CacheMode`를 사용해 실제 URL을 crawl하고 markdown을 생성하는 흐름을 설명한다.

- 출처: https://docs.crawl4ai.com/core/quickstart/

Crawl4AI 설치/진단 문서는 `crawl4ai-setup`, `crawl4ai-doctor`, 그리고 `example.com` crawl로 환경을 검증하는 흐름을 제시한다.

- 출처: https://docs.crawl4ai.com/core/installation/

Playwright 공식 문서도 browser install과 headless browser 실행을 별도 단계로 다룬다.

- 출처: https://playwright.dev/docs/browsers
- 출처: https://playwright.dev/docs/ci

결론:

- `pytest`는 실제 크롤링 검증이 아니다.
- 실제 검증은 Playwright Chromium이 실행되고, 공개 사이트에 네트워크 접근하고, Crawl4AI가 listing/detail을 실제로 가져오는 smoke script로 해야 한다.

### 24.3 우리가 겪은 로컬 문제와 의미

실행 시도 결과:

```bash
python3 -c "import crawl4ai"
```

초기 상태에서는 `crawl4ai`가 설치되어 있지 않았다.

따라서 다음을 수행했다.

```bash
python3 -m venv .venv
cd crawler
../.venv/bin/pip install -r requirements.txt pytest pytest-asyncio
../.venv/bin/python -m playwright install chromium
```

첫 번째 설치 실패 원인:

- `crawler/requirements.txt` 안의 `-e ../shared`는 `crawler` 디렉터리 기준 경로다.
- repo root에서 `pip install -r crawler/requirements.txt`를 실행하면 `../shared`가 잘못 해석된다.
- 따라서 `cd crawler` 후 설치해야 한다.

Crawl4AI 실행 실패 원인:

```text
PermissionError: Operation not permitted: '/Users/jmac/.crawl4ai'
```

Crawl4AI 내부 코드를 확인하면 기본 cache/db directory가 `Path.home()/.crawl4ai`다. 다만 환경변수 `CRAWL4_AI_BASE_DIRECTORY`로 기준 디렉터리를 바꿀 수 있다.

우리 sandbox/workspace 환경에서는 home directory write가 제한되므로 다음처럼 workspace 내부로 돌려야 한다.

```bash
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
../.venv/bin/python scripts/smoke_each_site.py ptt_mobile_game
```

그 다음 실패 원인:

```text
BrowserType.launch: Target page, context or browser has been closed
...
exception while trying to kill process: Error: kill EPERM
```

이는 Playwright Chromium이 뜨긴 했지만, 현재 실행 sandbox가 browser process control/kill을 제한해서 발생한 문제로 보는 것이 맞다. Playwright 문서도 CI/headless 환경에서 browser launch 오류는 browser debug log를 켜고 확인하라고 안내한다.

- 출처: https://playwright.dev/docs/ci

따라서 Codex sandbox 안에서는 실제 browser smoke가 막힐 수 있고, 이 경우 사용자의 일반 로컬 터미널 또는 승인된 unsandboxed 실행이 필요하다.

### 24.4 실제 로컬 smoke 실행 명령

repo 기준 권장 실행:

```bash
cd /Users/jmac/Desktop/261RCOSE45700
python3 -m venv .venv
cd crawler
../.venv/bin/pip install -r requirements.txt pytest pytest-asyncio
../.venv/bin/python -m playwright install chromium
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py ptt_mobile_game
```

다른 source:

```bash
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py dcard

CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py bahamut_tl
```

### 24.5 smoke에서 봐야 하는 지표

이번 실험에서 가장 중요한 출력:

```text
키워드매칭 N건/미매칭 M건
```

의미:

- `키워드매칭`: 기존 hard filter에서도 살아남았을 후보
- `미매칭`: 기존 hard filter에서는 버려졌지만 이제 보존되는 후보

즉 `미매칭 M건`이 0보다 크면 이번 변경이 실제로 수집 후보를 늘리고 있다는 뜻이다.

추가로 봐야 할 것:

- 게시판 fetch 성공 여부
- 패턴 매칭 URL 수
- 게시글 fetch 성공 수
- validator kind breakdown
- `real/N`
- `auth_wall`, `captcha`, `empty`, `short`, `sticky` 비율

### 24.6 왜 `example.com` smoke도 필요할 수 있는가

Crawl4AI 공식 설치 문서는 `example.com` 같은 단순 페이지를 먼저 crawl해 설치/브라우저 문제가 없는지 확인하라고 안내한다.

- 출처: https://docs.crawl4ai.com/core/installation/

따라서 문제가 생기면 순서는 이렇게 가야 한다.

1. `example.com` crawl 성공 여부 확인
2. 성공하면 Crawl4AI/Playwright 설치는 정상
3. 그 다음 `ptt_mobile_game` 같은 실제 source smoke
4. source만 실패하면 site-specific issue
5. browser launch부터 실패하면 local runtime/sandbox issue

### 24.7 권장 결론

우리 검증 절차는 다음이 맞다.

1. pytest는 코드 계약 확인용으로만 유지
2. 실제 수집량 평가는 `scripts/smoke_each_site.py`로 수행
3. Crawl4AI cache/db는 `CRAWL4_AI_BASE_DIRECTORY`로 workspace 내부에 둠
4. browser launch가 sandbox에서 막히면 일반 로컬 터미널 또는 unsandboxed 실행 필요
5. 첫 smoke는 mixed board인 `ptt_mobile_game`, `dcard`, `dcard_online`부터 수행
6. 결과는 `키워드매칭/미매칭`, 패턴 매칭 URL 수, validator kind breakdown으로 판단

핵심:

실제 검증은 "테스트가 통과했는가"가 아니라 "이 변경으로 공개 사이트에서 새 후보 URL이 얼마나 더 살아났는가"를 보는 것이다.

## 25. MacBook Codex/Sandbox 환경에서 Playwright 실제 크롤링을 어떻게 처리하는가

### 25.1 질문

MacBook에서 Codex 같은 sandboxed coding agent가 Playwright/Crawl4AI 실제 브라우저를 실행할 때, 사람들이 어떻게 처리하는가?

우리가 겪은 증상:

```text
BrowserType.launch: Target page, context or browser has been closed
exception while trying to kill process: Error: kill EPERM
```

### 25.2 조사 결론

이 문제는 우리 코드만의 문제가 아니라 macOS sandbox + Chromium/Playwright 조합에서 실제로 보고되는 문제다.

OpenAI Codex GitHub issue에 거의 같은 사례가 있다.

- macOS Apple Silicon
- Codex Desktop default sandboxed command/runtime path
- Playwright Chromium launch
- Chromium startup crash
- `MachPortRendezvousServer` permission denied
- 일부 launch variant에서 `kill EPERM`
- 같은 Playwright script가 escalated permissions outside sandbox에서는 성공

출처:

- https://github.com/openai/codex/issues/21292

해당 이슈의 핵심 문장:

- Codex Desktop의 macOS sandbox 안에서 Chromium이 macOS Mach bootstrap permission error로 시작 중 crash
- 기본 Playwright Chromium headless shell, full Chrome for Testing, `channel: chromium`, 일부 disable feature flag 모두 해결하지 못함
- escalated permissions outside sandbox에서는 성공

따라서 우리가 본 `kill EPERM`은 사이트 차단이 아니라 Codex/macOS sandbox가 브라우저 프로세스 제어를 막은 것으로 보는 게 맞다.

### 25.3 왜 이런 일이 생기는가

Codex CLI/agent류는 macOS에서 Apple Seatbelt sandbox를 사용한다는 설명이 있다.

- 출처: https://www.mintlify.com/openai/codex/concepts/sandboxing
- 출처: https://www.mintlify.com/openai/codex/architecture/sandboxing

Claude Code 문서도 비슷하게 permission과 sandbox를 분리해서 설명한다. Permission은 agent가 어떤 tool을 시도할 수 있는지 제어하고, sandbox는 Bash와 child process의 filesystem/network access를 OS 레벨에서 제한한다.

- 출처: https://code.claude.com/docs/en/permissions

즉 "명령 실행을 허용했다"와 "그 child process인 Chromium이 macOS 내부 서비스를 정상적으로 등록/종료할 수 있다"는 별개의 문제다.

Playwright 공식 문서 기준으로도 Playwright는 브라우저 instance를 launch하거나 기존 browser endpoint에 connect할 수 있다.

- 출처: https://playwright.dev/docs/api/class-browsertype

이 말은 sandbox 안에서 직접 launch가 막히면, 실무적으로는 다음 중 하나로 우회하지 않고 "정상 실행 경로"를 바꿔야 한다는 뜻이다.

### 25.4 사람들이 쓰는 현실적 대응 방식

조사 결과 대응은 대략 네 가지다.

#### 방식 A. Escalated/unsandboxed command로 Playwright 실행

Codex issue #21292의 관찰과 가장 일치한다.

특징:

- Codex가 직접 Playwright command를 실행하되, sandbox 밖 권한으로 실행
- 우리 도구에서는 `sandbox_permissions=require_escalated` 승인 필요
- 가장 단순하고 현재 repo 구조를 그대로 쓸 수 있음

장점:

- 코드 변경이 거의 없음
- Crawl4AI/Playwright smoke script 그대로 사용 가능
- 이번처럼 실제 크롤링 검증에 가장 빠름

단점:

- 사용자 승인이 필요
- 브라우저가 일반 사용자 권한으로 실행됨
- 민감한 파일/계정/브라우저 프로필과 분리해야 함

권장 안전장치:

- workspace 내부 전용 `CRAWL4_AI_BASE_DIRECTORY`
- Playwright 전용 임시 profile
- login/profile/cookie 사용 금지
- download 금지
- 공개 페이지 smoke만 실행

#### 방식 B. 사용자가 Mac 터미널에서 직접 실행

가장 보수적인 방식이다.

Codex는 명령과 기대 출력만 알려주고, 사용자가 Terminal.app/iTerm에서 실행한다.

장점:

- Codex sandbox 문제가 없음
- 사용자가 OS 권한 prompt를 직접 통제
- 장기적으로 안전한 운영 습관

단점:

- Codex가 실시간으로 결과를 직접 못 봄
- 사용자가 출력 복사/공유 필요

권장 명령:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py ptt_mobile_game
```

#### 방식 C. 외부 브라우저를 먼저 띄우고 Playwright가 connect

Playwright 공식 API에는 기존 browser endpoint에 연결하는 `connect`, Chromium CDP endpoint에 연결하는 `connectOverCDP`가 있다.

- 출처: https://playwright.dev/docs/api/class-browsertype

개념:

1. 사용자가 sandbox 밖에서 Chrome/Chromium을 remote debugging port로 실행
2. Codex/sandbox 안의 script는 새 브라우저를 launch하지 않고 `connectOverCDP`로 붙음

예시 개념:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/crawler-smoke-profile \
  --no-first-run \
  --no-default-browser-check
```

그 뒤 Python/Node Playwright가:

```python
browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9222")
```

장점:

- sandbox 안에서 Chromium launch를 하지 않음
- 브라우저 프로세스 권한 문제를 줄일 수 있음

단점:

- 우리 Crawl4AI wrapper는 현재 직접 connectOverCDP 구조가 아님
- 별도 smoke script를 새로 짜야 함
- remote debugging port는 보안상 localhost 전용/짧은 시간만 사용해야 함

주의:

- 개인 Chrome profile을 쓰면 안 된다.
- 반드시 임시 `--user-data-dir` 사용.
- remote debugging port는 외부 노출 금지.

#### 방식 D. Browser MCP/agent browser plugin 사용

일부 agent 환경은 Playwright 직접 실행 대신 browser plugin/MCP/browser CLI를 쓴다.

조사상 Claude/Codex 커뮤니티에서 Playwright MCP, Browser CLI, agent browser 같은 흐름이 언급된다.

- 출처: https://www.reddit.com/r/ClaudeCode/comments/1rw9vsi/pro_tip_just_ask_claude_to_enable_playwright/
- 출처: https://www.reddit.com/r/ClaudeAI/comments/1scics4/browser_cli_a_tokenefficient_browser_tool_for_ai/

장점:

- agent가 브라우저를 직접 제어하기 쉬움
- screenshot/console/network 확인에 적합

단점:

- 우리 Crawl4AI 기반 crawler smoke와는 다름
- 수집량 측정 자동화에는 별도 연결 코드 필요
- Codex Desktop에서도 Playwright MCP 관련 승인/권한 이슈가 보고됨

출처:

- https://github.com/openai/codex/issues/15753

### 25.5 우리 상황에서 가장 맞는 방법

목표가 "대시보드 UI 테스트"가 아니라 "실제 공개 사이트에서 후보 URL 수가 늘었는지"이므로, Browser plugin보다는 smoke script가 맞다.

권장 순서:

1. Codex가 코드와 smoke script를 준비
2. 사용자가 Mac 터미널에서 직접 smoke 실행
3. 출력의 `키워드매칭/미매칭`, `real/N`, kind breakdown을 공유
4. Codex가 결과를 해석하고 코드 조정
5. 필요할 때만 Codex escalated command로 직접 smoke 실행

Codex가 직접 실행해야 한다면:

- `require_escalated` 승인 필요
- command는 `../.venv/bin/python scripts/smoke_each_site.py <site>`처럼 좁게 제한
- `CRAWL4_AI_BASE_DIRECTORY`는 workspace 내부로 지정
- 개인 브라우저 profile 사용 금지

### 25.6 우리가 이미 확인한 것과 일치성

우리 실행 결과:

```text
CRAWL4_AI_BASE_DIRECTORY 없을 때:
PermissionError: '/Users/jmac/.crawl4ai'

CRAWL4_AI_BASE_DIRECTORY 지정 후:
BrowserType.launch ... browser has been closed
exception while trying to kill process: Error: kill EPERM
```

해석:

- 첫 번째는 Crawl4AI cache/db directory가 home directory라 sandbox filesystem policy에 막힌 것
- 두 번째는 Playwright/Chromium launch가 macOS sandbox process/Mach permission에 막힌 것

OpenAI Codex issue #21292와 증상이 거의 같다.

따라서 "코드를 고치면 해결"할 문제가 아니라 "실행 경로를 바꿔야 하는 문제"다.

### 25.7 최종 권장안

MacBook + Codex sandbox 기준 실제 크롤링 smoke는 이렇게 운영한다.

1. 설치/코드 수정은 Codex sandbox 안에서 가능
2. Crawl4AI cache는 workspace 안으로 강제
3. 실제 Playwright browser launch는 다음 중 하나:
   - 사용자 터미널 직접 실행
   - Codex escalated command 승인
   - 별도 외부 browser/CDP 연결용 smoke script 작성
4. 개인 Chrome profile, 로그인 세션, 다운로드, private channel 접근은 사용하지 않음
5. smoke 결과는 수집량 metric만 본다.

가장 현실적인 명령:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py ptt_mobile_game
```

핵심 판단:

- `pytest`는 로컬 mock test
- `smoke_each_site.py`는 실제 크롤링 test
- Codex macOS sandbox 안에서 Playwright launch가 막히는 것은 알려진 문제
- MacBook에서는 사용자가 터미널에서 직접 실행하거나, Codex escalated 실행을 승인하는 방식이 정석에 가깝다.

## 26. 실제 smoke 결과: ptt_mobile_game

### 26.1 실행

사용자 Mac 터미널에서 실행:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py ptt_mobile_game
```

### 26.2 결과 요약

출력 요약:

```text
대상 사이트: ['ptt_mobile_game']
페이지 OK (html 10,669자, 링크 31개 중 패턴 매칭 5건, 키워드매칭 0건/미매칭 9건)
게시글 5개 검증 시도
[1] real text=1,643자
[2] real text=1,541자
[3] real text=2,388자
[4] real text=976자 이미지 5개
[5] real text=2,457자
summary: board OK, real/N 5/5, kinds real:5
```

해석:

- 게시판 listing fetch 성공
- 게시글 detail fetch 성공
- validator 기준 실사용자 글 5/5 성공
- 차단/captcha/login/empty 문제 없음
- `키워드매칭 0건/미매칭 9건`이므로 예전 hard filter였으면 이 보드에서는 fetch 후보가 거의 0개였을 가능성이 높다.
- 이번 soft-priority 변경으로 기존에 버리던 미매칭 후보를 실제로 살렸다.

### 26.3 중요한 발견

이 smoke는 우리가 세운 판단을 지지한다.

프록시나 유료 API 없이도 수집 후보량을 늘릴 여지가 있었다.

특히 `ptt_mobile_game` 같은 혼합 보드는 제목에 NC/불법 프로그램 키워드가 없더라도 실제 게시글로 fetch 가능한 후보가 존재한다. 기존 구조는 그런 후보를 listing 단계에서 버리고 있었다.

### 26.4 출력 문구 보정

초기 smoke 출력에서 `패턴 매칭 5건`과 `미매칭 9건`이 같이 보여 혼동이 있었다.

원인:

- `패턴 매칭 5건`은 실제로는 검증 대상으로 선택된 상위 5개 수였다.
- `키워드매칭/미매칭`은 전체 후보 기준이었다.

스크립트 보정:

- `pattern_matched_total`: 전체 패턴 매칭 후보 수
- `matched`: 검증 대상으로 선택한 후보 URL
- 출력 문구를 `패턴 매칭 N건, 검증 선택 M건`으로 변경

### 26.5 다음 smoke 후보

다음은 같은 방식으로 mixed/SPA source를 확인한다.

```bash
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py dcard

CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py dcard_online
```

보고 싶은 것:

- 패턴 매칭 전체 후보 수
- 검증 선택 수
- 키워드매칭/미매칭 비율
- real/N
- validator kind breakdown

현재 1차 결론:

`title_keywords` hard filter 제거는 실제 수집 후보를 늘리는 방향이 맞다.

## 27. 실제 smoke 결과: dcard

### 27.1 실행

사용자 Mac 터미널에서 실행:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py dcard
```

### 27.2 결과 요약

listing 결과:

```text
[dcard] Dcard (game)
board_urls[0] = https://www.dcard.tw/f/game
wait_for=css:article
페이지 OK (html 409,455자, 링크 49개 중 패턴 매칭 17건, 검증 선택 5건, 키워드매칭 0건/미매칭 17건)
```

detail 결과:

```text
https://www.dcard.tw/f/game/p/261609258
Wait condition failed: Timeout after 45000ms waiting for selector 'article'
```

### 27.3 해석

Dcard는 listing 단계에서는 성공했다.

- html 409,455자
- 전체 링크 49개
- 게시글 패턴 매칭 17건
- 검증 선택 5건
- 키워드매칭 0건
- 미매칭 17건

이것도 `title_keywords` hard filter 제거가 효과적이라는 증거다. 예전 구조라면 키워드매칭 0건이라 후보가 거의 사라졌을 가능성이 높다.

하지만 detail 단계에서 실패했다.

실패 원인:

- `SiteConfig.wait_for="css:article"`이 listing과 detail 모두에 재사용됨
- listing에서는 article selector가 등장해 성공
- detail page에서는 같은 selector가 45초 안에 만족되지 않아 timeout

즉, 이 문제는 proxy 문제가 아니다.

`후보 추출은 성공했는데 상세 fetch의 wait_for 조건이 너무 특정적`인 문제다.

### 27.4 코드 반영

`dcard_online`은 이미 과거에 같은 이유로 selector 의존을 끊고 `delay_before_return_html=3.0`을 쓰고 있었다.

따라서 `dcard`도 같은 방식으로 맞췄다.

변경:

```python
# before
wait_for="css:article"

# after
delay_before_return_html=3.0
```

의도:

- listing/detail 모두에서 selector timeout을 피한다.
- Dcard React hydration 시간을 짧게 기다린 뒤 링크/본문을 회수한다.
- aggressive scroll/networkidle은 계속 쓰지 않는다.

### 27.5 재실행 명령

다시 확인할 명령:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py dcard
```

확인할 것:

- listing이 계속 `패턴 매칭 17건` 근처로 잡히는가
- detail 5개가 timeout 없이 fetch 되는가
- `real/N`이 몇 개인가
- 실패한다면 kind가 `empty`, `short`, `auth_wall`, `fetch_error` 중 무엇인가

현재 판단:

- Dcard 수집량 병목은 proxy가 아니라 `wait_for` 재사용 문제였다.
- 이 문제를 고치면 Dcard에서도 미매칭 후보를 실제 detail fetch로 넘길 수 있다.

### 27.6 수정 전 baseline 추가 결과

붙여넣은 실제 출력 기준으로, 수정 전 `wait_for=css:article` 상태에서도 Dcard는 완전히 막힌 source가 아니었다.

요약:

```text
페이지 OK
패턴 매칭 17건
검증 선택 5건
키워드매칭 0건/미매칭 17건
real/N = 4/5
kinds = real:4 fetch_error:1
elapsed = 121.0s
```

해석:

- listing fetch는 안정적으로 성공했다.
- keyword hard filter 제거 효과도 확인됐다.
- 17개 후보 모두 title keyword 미매칭이므로 기존 hard filter라면 버려졌을 가능성이 높다.
- detail fetch는 5개 중 4개가 성공했고 1개만 `css:article` wait timeout으로 실패했다.
- 첫 URL은 retry까지 포함해 약 90초를 소비했다.

이 baseline은 `wait_for` 제거 필요성을 더 강하게 뒷받침한다.

수정 후 기대:

```text
wait_for=—
delay_before_return_html=3.0
fetch_error 감소
elapsed 감소
real/N 유지 또는 개선
```

현재 코드 확인:

```text
dcard.wait_for = None
dcard.delay_before_return_html = 3.0
```

따라서 다음 재실행 출력의 header는 아래처럼 나와야 한다.

```text
wait_for=—  selector=—
```

### 27.7 수정 후 재실행 결과

수정 후 재실행 출력:

```text
[dcard] Dcard (game)
wait_for=—  selector=—
페이지 OK (html 634,146자, 링크 75개 중 패턴 매칭 17건, 검증 선택 5건, 키워드매칭 0건/미매칭 17건)
real/N = 5/5
kinds = real:5
elapsed = 51.6s
```

중간에 한 번 Cloudflare JS challenge가 발생했다.

```text
Blocked by anti-bot protection: Cloudflare JS challenge
```

하지만 동일 URL retry에서 성공했다.

해석:

- `wait_for=css:article` 제거가 정상 반영됐다.
- 첫 번째 detail URL의 45초 timeout 문제가 사라졌다.
- 수정 전 baseline: `real/N=4/5`, `fetch_error=1`, `elapsed=121.0s`
- 수정 후: `real/N=5/5`, `fetch_error=0`, `elapsed=51.6s`
- Dcard는 proxy 없이도 현재 공개 접근에서 수집 가능하다.
- 일시적인 Cloudflare JS challenge는 있었지만 retry로 회복 가능한 수준이다.

결론:

- Dcard 병목은 proxy가 아니라 detail fetch wait condition이었다.
- `title_keywords` hard filter 제거와 Dcard `wait_for` 제거는 모두 실제 smoke에서 효과가 확인됐다.

## 28. 실제 smoke 결과: dcard_online

### 28.1 실행 결과

사용자 Mac 터미널에서 실행:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py dcard_online
```

기존 `/f/online` 결과:

```text
[dcard_online] Dcard (online)
board_urls[0] = https://www.dcard.tw/f/online
wait_for=—  selector=—
페이지 OK (html 286,106자, 링크 33개 중 패턴 매칭 0건, 검증 선택 0건, 키워드매칭 0건/미매칭 0건)
패턴 미스 — 첫 6개 링크 샘플:
  https://www.dcard.tw/f
  https://www.dcard.tw/forum/all
  https://www.dcard.tw/forum/popular
  https://www.dcard.tw/f/relationship
```

해석:

- 페이지 fetch 자체는 성공했다.
- 하지만 게시글 URL이 0건이다.
- 따라서 `dcard_online`은 차단 문제가 아니라 source URL이 더 이상 우리가 의도한 게시글 listing으로 동작하지 않는 문제다.

### 28.2 웹 확인

웹에서 Dcard `線上遊戲` topic 페이지를 확인했다.

- 출처: https://www.dcard.tw/topics/%E7%B7%9A%E4%B8%8A%E9%81%8A%E6%88%B2

확인 내용:

- `線上遊戲` topic은 약 460개 게시글과 78 followers를 가진 topic으로 표시된다.
- 여러 forum의 게시글이 topic 아래에 모인다.
- 예시로 `天堂 Lineage`, `AION2`, `內掛電腦線上遊戲` 같은 우리 관심과 가까운 텍스트가 보인다.

따라서 `dcard_online`은 `/f/online` 고정 게시판보다 topic source로 보는 것이 맞다.

### 28.3 코드 반영

`dcard_online` 변경:

```python
# before
board_urls=["https://www.dcard.tw/f/online"]
post_url_pattern=r"https://www\.dcard\.tw/f/online/p/\d+"

# after
board_urls=["https://www.dcard.tw/topics/%E7%B7%9A%E4%B8%8A%E9%81%8A%E6%88%B2"]
post_url_pattern=r"https://www\.dcard\.tw/f/[A-Za-z0-9_-]+/p/\d+"
```

이유:

- topic page는 여러 forum의 관련 글을 모으므로 forum slug가 `online`으로 고정되지 않는다.
- `/f/game/p/...`, `/f/mobilegame/p/...`, `/f/talk/p/...` 같은 URL이 섞일 수 있다.
- source 자체가 `線上遊戲` topic이므로 pattern은 여러 forum slug를 허용해야 한다.

### 28.4 재실행 기준

다시 실행:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py dcard_online
```

기대:

```text
board_urls[0] = https://www.dcard.tw/topics/%E7%B7%9A%E4%B8%8A%E9%81%8A%E6%88%B2
패턴 매칭 N건
검증 선택 5건
```

판단:

- 패턴 매칭이 0보다 크면 source URL 교체가 성공
- `real/N`이 높으면 실제 수집 source로 유지
- topic 특성상 NC 게임 직접 매칭은 낮을 수 있으므로, keyword hard filter는 계속 쓰면 안 됨

### 28.5 topic 전환 후 재실행 결과

topic 전환 후 실제 smoke:

```text
[dcard_online] Dcard (topic: 線上遊戲)
board_urls[0] = https://www.dcard.tw/topics/%E7%B7%9A%E4%B8%8A%E9%81%8A%E6%88%B2
wait_for=—  selector=—
페이지 OK (html 904,851자, 링크 82개 중 패턴 매칭 29건, 검증 선택 5건, 키워드매칭 0건/미매칭 29건)
real/N = 2/5
kinds = unknown:3 real:2
elapsed = 47.9s
```

해석:

- source URL 전환은 성공했다.
- `/f/online`의 패턴 매칭 0건에서 topic의 패턴 매칭 29건으로 개선됐다.
- 모든 후보가 title keyword 미매칭이므로 hard filter 제거 효과가 다시 확인됐다.
- 5개 detail fetch는 모두 성공했다.
- `unknown` 3개는 fetch 실패가 아니라 validator 기준이 너무 좁아서 생겼다.

unknown 예시:

```text
https://www.dcard.tw/f/werewolf/p/261604959 text=593자
https://www.dcard.tw/f/werewolf/p/261527207 text=1,023자
https://www.dcard.tw/f/board_game/p/261375442 text=1,663자
사유: Dcard 카테고리/시간 마커 미발견
```

이 글들은 Dcard topic이 여러 forum의 post URL을 모으기 때문에 기존 `## #카테고리`/시간 marker가 markdown에 남지 않을 수 있다.

### 28.6 validator 보정

Dcard validator에 fallback을 추가했다.

조건:

- URL이 Dcard 게시글 형식:
  - `https://www.dcard.tw/f/<forum_slug>/p/<post_id>`
- 본문 길이가 300자 이상
- generic guard에서 empty/short/captcha/auth_wall이 아닌 경우

판정:

```text
real: Dcard 게시글 URL + 충분한 본문 길이
```

이유:

- listing URL pattern이 이미 Dcard post URL임을 보장한다.
- topic page에서는 forum slug가 `game`이 아닐 수 있다.
- markdown extraction에서 Dcard category/time chrome이 빠져도 본문은 충분히 회수된다.
- 후보 보존 단계에서는 지나치게 보수적으로 버리는 것보다 real로 넘겨 downstream scoring에 맡기는 편이 낫다.

수정 후 기대:

```text
dcard_online real/N: 2/5 -> 최대 5/5
unknown 감소
```

재실행 명령:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py dcard_online
```

### 28.7 validator 보정 후 재실행 결과

validator 보정 후 실제 smoke:

```text
[dcard_online] Dcard (topic: 線上遊戲)
페이지 OK (html 981,658자, 링크 82개 중 패턴 매칭 29건, 검증 선택 5건, 키워드매칭 0건/미매칭 29건)
real/N = 5/5
kinds = real:5
elapsed = 52.4s
```

중간에 Cloudflare JS challenge가 한 번 있었다.

```text
Blocked by anti-bot protection: Cloudflare JS challenge
```

동일 URL retry에서 성공했다.

보정 전/후 비교:

| 상태 | 패턴 매칭 | real/N | kinds | elapsed |
|---|---:|---:|---|---:|
| `/f/online` | 0 | - | - | 7.0s |
| topic 전환 후 | 29 | 2/5 | unknown:3 real:2 | 47.9s |
| validator 보정 후 | 29 | 5/5 | real:5 | 52.4s |

결론:

- `dcard_online`은 source URL 교체와 validator 보정으로 실제 수집 source가 됐다.
- proxy 없이도 접근 가능하다.
- `키워드매칭 0건/미매칭 29건`이므로 hard filter 제거 효과가 매우 크다.
- Cloudflare challenge는 간헐적으로 발생하지만 retry로 회복 가능하다.

## 29. 현재까지 mixed source smoke 종합

### 29.1 결과 표

| source | 이전 병목 | 변경 | smoke 결과 |
|---|---|---|---|
| `ptt_mobile_game` | title keyword hard filter | soft priority | 미매칭 9건, real 5/5 |
| `dcard` | title hard filter + detail `wait_for` timeout | soft priority + selector 의존 제거 | 미매칭 17건, real 5/5 |
| `dcard_online` | `/f/online` 패턴 0건 + validator unknown | topic source + Dcard URL/body fallback | 미매칭 29건, real 5/5 |

### 29.2 핵심 결론

초기 피드백인 "화면에 뜨는 데이터 수가 적다"의 원인은 적어도 mixed source에서는 proxy나 유료 수집 인프라 부족이 아니었다.

확인된 원인:

1. listing 단계에서 title keyword hard filter로 너무 일찍 버림
2. Dcard detail page에 listing용 `wait_for`를 재사용
3. `/f/online` source URL이 실제 게시글 listing을 내지 않음
4. Dcard topic/multi-forum URL에 validator가 너무 보수적

확인된 개선:

- 접근 가능한 공개 데이터만으로 후보 수 증가
- PTT/Dcard 모두 proxy 없이 smoke 성공
- mixed source 3개 모두 `키워드매칭 0건`인데도 실제 게시글 회수 성공

### 29.3 다음 실험

이제 5개 smoke로는 부족하다.

다음 단계는 source당 검증 게시글 수를 환경변수로 조정하는 것이다.

권장:

```bash
SMOKE_POSTS_PER_SITE=15
SMOKE_POSTS_PER_SITE=30
```

측정:

- pattern matched
- selected
- real/N
- fetch_error
- Cloudflare challenge retry count
- elapsed
- source별 duplicate/noise 비율

이 다음에야 운영 기본값 `MAX_POSTS_PER_BOARD=30`이 실제로 안전한지 판단할 수 있다.

## 30. SMOKE_POSTS_PER_SITE=15 실험 결과

### 30.1 실험 조건

```bash
SMOKE_POSTS_PER_SITE=15 CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py ptt_mobile_game

SMOKE_POSTS_PER_SITE=15 CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/smoke_each_site.py dcard
```

`smoke_each_site.py`에 `SMOKE_POSTS_PER_SITE` 환경변수를 추가해 `_diagnose_board(limit=)` 과 `smoke_site(posts_per_site=)` 양쪽에 전달되도록 했다.

### 30.2 ptt_mobile_game 결과

| 항목 | 값 |
|---|---|
| 패턴 매칭 | **9건** (15 요청했으나 첫 페이지 최대) |
| 검증 시도 | 9건 |
| real/N | 5/9 |
| sticky | 4/9 (44%) |
| fetch_error | 0건 |
| Cloudflare challenge | 없음 |
| elapsed | 61.8s |

결론:

- `MAX_POSTS_PER_BOARD=30`으로 올려도 listing page에서 꺼낼 수 있는 후보가 **첫 페이지 9건이 상한**이다.
- 실질적 병목은 limit이 아니라 첫 페이지 게시글 수다. 후보를 더 늘리려면 pagination이 필요하다.
- sticky 비율 44%는 pin된 공지가 많다는 뜻이다. listing 단계에서 제외하면 real 비율이 올라간다.
- fetch 안정성 면에서는 문제 없음. rate-limit·차단 없음.

### 30.3 dcard 결과

| 항목 | 값 |
|---|---|
| 패턴 매칭 | 17건 |
| 검증 선택 | 15건 |
| real/N | **15/15** |
| fetch_error | 0건 |
| Cloudflare challenge | 1회 (retry 성공) |
| elapsed | **130.1s** |
| 게시글당 평균 | ~8.7s |

결론:

- 15건 완전 안정. 차단·rate-limit 없음.
- Cloudflare challenge는 간헐적으로 발생하지만 retry로 회복된다.
- 30건으로 올리면 단순 계산 ~260s/site. 순차 실행 구조에서 site 수가 늘면 전체 run 시간 문제가 된다.

### 30.4 종합 판단

| source | first-page 상한 | real/N@15 | fetch 안정성 | 주요 병목 |
|---|---|---|---|---|
| `ptt_mobile_game` | 9건 (당시) | 5/9 | ✅ | ~~pagination 부재~~ → §34 완료 |
| `dcard` | 17건 | 15/15 | ✅ | 순차 실행 시 elapsed |

`MAX_POSTS_PER_BOARD=30`은 fetch 안정성 면에서 안전하다. ~~PTT는 pagination 없이는 9건이 한계~~ → §34에서 `prev_page_link_text` 동적 pagination 구현으로 3페이지 × 최대 20건 확보.

다음 우선순위:

1. listing funnel 계측 (`discovered_total/keyword_matched/keyword_unmatched`) → 어디서 줄어드는지 수치로 확인 ✅ §31 완료
2. validator kind별 집계 → `sticky`가 몇 건 버려지는지 운영에서 관측 ✅ §32 완료
3. candidate inventory dry-run 모드 ✅ §33 완료
4. pagination ✅ §34 완료 (bahamut/PTT/inven 전부 3페이지)

## 31. ListingResult 구조화 + PipelineStats 확장 (§23.4 1번 구현)

### 31.1 변경 내용

`_fetch_post_urls`가 `list[str]`을 반환하던 것을 `ListingResult` dataclass로 교체했다.

```python
@dataclass(frozen=True)
class ListingResult:
    urls: list[str]
    discovered_total: int        # limit 적용 전 전체 후보 수
    keyword_matched: int         # 키워드 매칭 후보 수
    keyword_unmatched: int       # 키워드 미매칭 후보 수 (보존된 수)
    candidates: list[PostUrlCandidate] = field(default_factory=list)
    next_board_url: str | None = None  # 동적 pagination용 다음 페이지 URL (§34)
```

`PipelineStats`에 세 필드를 추가했다:

```python
listing_discovered_total: int = 0   # limit 적용 전 전체 후보 수
listing_keyword_matched: int = 0    # 키워드 매칭 후보 수 (우선순위 feature)
listing_keyword_unmatched: int = 0  # 키워드 미매칭 후보 수 (보존된 수)
```

`_process_board`에서 board 단위로 이 값들을 누적한다.

파이프라인 완료 로그:

```
파이프라인 완료: 보드=%d 리스팅발견=%d 리스팅선택=%d kw매칭=%d kw미매칭=%d 시도=%d 큐=%d ...
```

### 31.2 이 변경으로 알 수 있는 것

운영 로그에서 board별로 다음을 확인할 수 있다:

- `discovered_total` vs `listing_urls_selected`: limit 때문에 버린 후보가 있는지
- `keyword_matched` vs `keyword_unmatched`: 제목 키워드가 실제로 몇 건 히트하는지
- `keyword_unmatched`가 `discovered_total`과 같으면: 해당 source는 제목에서 NC 게임 언급 없이 글을 올린다는 신호

### 31.3 아직 남은 것

- validator kind별 집계 (`skipped_sticky/blocked/unknown` 이미 있음, API/dashboard로 노출 필요)
- `GET /api/crawl/stats` endpoint 추가
- board별 stats 분리 (현재는 run 전체 합산만)

## 32. validator kind별 집계 + GET /api/crawl/stats + dashboard funnel (§30.4 item 2, §31.3 구현)

### 32.1 변경 내용

`PipelineStats`의 `skipped_sticky/blocked/unknown` 등 funnel 수치를 run 완료 시 Redis에 저장하고, Spring API와 React dashboard에서 조회할 수 있게 했다.

#### 32.1.1 Redis 저장

`shared/config/redis_config.py`에 키 상수 추가:

```python
REDIS_KEY_CRAWL_STATS_LATEST: str = "crawl:stats:latest"
```

`CrawlJobProgressStore`에 `store_pipeline_stats()` 추가:

```python
def store_pipeline_stats(self, stats: dict[str, int | str]) -> None:
    data = {**stats, "recordedAt": stats.get("recordedAt") or _now()}
    self._redis.set(REDIS_KEY_CRAWL_STATS_LATEST, json.dumps(data), ex=_JOB_TTL_SECONDS * 7)
```

`CrawlPipeline.run()` 완료 직전에 호출:

```python
if self._progress_store is not None:
    self._progress_store.store_pipeline_stats({
        "listingBoards": stats.listing_boards,
        "listingDiscoveredTotal": stats.listing_discovered_total,
        "listingUrlsSelected": stats.listing_urls_selected,
        "listingKeywordMatched": stats.listing_keyword_matched,
        "listingKeywordUnmatched": stats.listing_keyword_unmatched,
        "attempted": stats.attempted,
        "enqueued": stats.enqueued,
        "skippedSeenUrl": stats.skipped_seen_url,
        "skippedDedup": stats.skipped_dedup,
        "skippedEmpty": stats.skipped_empty,
        "skippedSticky": stats.skipped_sticky,
        "skippedBlocked": stats.skipped_blocked,
        "skippedUnknown": stats.skipped_unknown,
        "failed": stats.failed,
    })
```

TTL은 `_JOB_TTL_SECONDS * 7` (42시간). 매일 크롤링이 실행되면 갱신된다.

#### 32.1.2 Spring API

`CrawlPipelineStatsResponse` record DTO 추가:

```java
public record CrawlPipelineStatsResponse(
    int listingBoards, int listingDiscoveredTotal, int listingUrlsSelected,
    int listingKeywordMatched, int listingKeywordUnmatched,
    int attempted, int enqueued,
    int skippedSeenUrl, int skippedDedup, int skippedEmpty,
    int skippedSticky, int skippedBlocked, int skippedUnknown,
    int failed, String recordedAt
) {}
```

`CrawlTriggerService.getLatestPipelineStats()` 추가: `crawl:stats:latest` 키에서 JSON을 읽어 DTO로 변환. Redis에 값이 없으면 모두 0인 빈 응답을 반환한다.

`CrawlController`에 endpoint 추가:

```
GET /api/crawl/stats
```

#### 32.1.3 React dashboard

`types/api.ts`에 `CrawlPipelineStatsResponse` 타입 추가.

`api/stats.ts`에 `useCrawlPipelineStatsSuspenseQuery()` 훅 추가 (`/crawl/stats` 폴링).

`pages/Stats/index.tsx` 하단에 funnel 카드 추가:

| 항목 | 내용 |
|---|---|
| 보드 | listing board 수 |
| 후보 발견 | `listingDiscoveredTotal` |
| 선택 | `listingUrlsSelected` (kw매칭 N건 표시) |
| 시도 | `attempted` |
| 큐 적재 | `enqueued` (강조) |
| 스킵 breakdown | URL중복/본문중복/공지·캡차/빈글·미확인 |
| 실패 | `failed` (>0이면 빨간색) |

### 32.2 이 변경으로 알 수 있는 것

dashboard에서 다음을 확인할 수 있다:

- listing 단계에서 몇 건이 선택되는지 (후보 발견 vs 선택)
- 키워드 매칭이 실제로 얼마나 기여하는지 (`kw매칭 N건`)
- validator가 어느 종류로 버리는지 (sticky/blocked/unknown 분리)
- 탐지로 이어지지 않는 이유가 수집 부족인지 dedup 탓인지

### 32.3 아직 남은 것

- board별 stats 분리 (현재는 run 전체 합산만)
- job별 stats 히스토리 (현재는 최근 run 1건만 보관)

## 33. candidate inventory JSONL dry-run 모드 (§30.4 item 3 구현)

### 33.1 변경 내용

`CRAWL_DRY_RUN=1` 환경변수를 설정하면 실제 detail fetch/저장/enqueue 없이 listing 단계 결과만 JSONL로 덤프한다.

`crawl_scheduler.py`에 추가된 상수:

```python
_DRY_RUN = os.environ.get("CRAWL_DRY_RUN", "").lower() in ("1", "true", "yes")
_DRY_RUN_OUTPUT_DIR = Path(os.environ.get("CRAWL_DRY_RUN_OUTPUT_DIR", "output"))
_DRY_RUN_SESSION_TS = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
```

`ListingResult`에 `candidates` 필드 추가:

```python
@dataclass(frozen=True)
class ListingResult:
    urls: list[str]
    discovered_total: int
    keyword_matched: int
    keyword_unmatched: int
    candidates: list[PostUrlCandidate] = field(default_factory=list)  # dry-run 용
```

`_fetch_post_urls()`에서 `candidates=candidates` 포함해 반환.

`_process_board`에서 dry-run 분기:

```python
if _DRY_RUN:
    self._dump_dry_run_candidates(site_id, board_url, listing)
    return
```

`_dump_dry_run_candidates()` 출력 형식 (JSONL 한 줄 예시):

```json
{"site_id": "bahamut_lineage", "board_url": "https://forum.gamer.com.tw/B.php?bsn=842", "url": "https://forum.gamer.com.tw/C.php?bsn=842&snA=12345", "title": "天堂帳號出售", "keyword_matched": true, "selected": true}
```

필드:

| 필드 | 내용 |
|---|---|
| `site_id` | 사이트 ID |
| `board_url` | listing page URL |
| `url` | 후보 게시글 URL |
| `title` | listing에서 추출한 제목 |
| `keyword_matched` | title_keywords 히트 여부 |
| `selected` | MAX_POSTS_PER_BOARD 제한 이내에 포함됐는지 |

### 33.2 사용법

```bash
CRAWL_DRY_RUN=1 python -m crawler.src.main
# output/dry_run_20260605_030000.jsonl 생성
```

`CRAWL_DRY_RUN_OUTPUT_DIR` 환경변수로 출력 경로 변경 가능 (기본: `output/`).

### 33.3 이 변경으로 할 수 있는 것

- 실제 크롤링 없이 listing 단계 후보 현황 파악
- site별·board별 keyword_matched 비율 확인
- `selected=false` 후보를 보고 limit 조정 판단
- pagination 추가 전후 후보 수 비교

## 34. Pagination: SiteConfig max_pages + _expand_page_urls (§30.4 item 4 구현)

### 34.1 배경

§30.2에서 `ptt_mobile_game`이 첫 페이지 9건으로 상한이 묶였다. Bahamut 등 다른 포럼도 첫 페이지만 수집하고 있다. listing page가 제공하는 URL 수가 늘어나야 `MAX_POSTS_PER_BOARD=30`이 의미를 가진다.

Crawl4AI v0.8.x 공식 문서 확인 결과: `CrawlerRunConfig`에 pagination 전용 파라미터가 없고, 정적 URL 생성 후 `arun()` 반복이 권장 기본 방식이다.

### 34.2 변경 내용

#### 34.2.1 SiteConfig 필드 추가

```python
max_pages: int = 1
page_url_template: str | None = None   # 정적 URL 생성. 예: "{base}?p={page}"
prev_page_link_text: str | None = None # 동적 탐색. 링크 텍스트 매칭 (PTT 上頁 등)
```

- `max_pages=1` (기본): 기존 동작 그대로. 하위 호환 유지.
- **정적 모드** (`page_url_template` 설정): 페이지 2~`max_pages`를 `_expand_page_urls()` 로 미리 생성. bahamut/inven에 사용.
- **동적 모드** (`prev_page_link_text` 설정): 각 페이지 fetch 결과 링크에서 해당 텍스트 포함 링크를 다음 board_url로 사용. PTT처럼 URL을 미리 알 수 없는 경우에 사용.
- 두 필드가 동시 설정될 경우 동적 모드(`prev_page_link_text`)가 우선한다.

#### 34.2.2 _expand_page_urls()

```python
def _expand_page_urls(board_url: str, site: SiteConfig) -> list[str]:
    if site.max_pages <= 1 or not site.page_url_template:
        return [board_url]
    urls = [board_url]
    for page in range(2, site.max_pages + 1):
        urls.append(site.page_url_template.format(base=board_url, page=page))
    return urls
```

`_process_site()` 에서 board_url마다 `_expand_page_urls()` 결과를 순회한다.

#### 34.2.3 bahamut 시리즈 적용

상세 smoke 이력은 §34.4 참고. 최종 확정된 구현 (`_make_bahamut_nc_site()` 팩토리):

```python
board_urls=[f"https://forum.gamer.com.tw/B.php?bsn={bsn}"],
post_url_pattern=(
    r"https://forum\.gamer\.com\.tw/C\.php\?"
    r"(?!.*[&]last=\d)"
    r"(?=.*\bbsn=\d+)"
    r"(?=.*\bsnA=\d+)"
),
max_pages=3,
page_url_template=f"https://forum.gamer.com.tw/B.php?bsn={bsn}&page={{page}}",
```

- board_url: `B.php?bsn=N` (파라미터 순서: bsn 먼저 — HTML 소스 기준)
- page 2+: `B.php?bsn=N&page=2` 형태 (실제 HTML에서 확인한 순서)
- `post_url_pattern`: page 2+ C.php 링크에 `bPage=N` 파라미터가 앞에 붙는 구조를 lookahead로 처리. `last=1` ("마지막 댓글로") 링크는 dedup 불가하여 제외.
- `_BAHAMUT_BSN_RE` / `_BAHAMUT_SNA_RE`: 기존 `bsn=(\d+)&snA=(\d+)` 단일 regex를 분리, `last=1` 같은 중간 파라미터 있어도 각각 추출 가능.

bahamut 8개 사이트 (lineage/lineage_m/lineage_w/lineage_classic/aion/aion2/bns/tl) 모두 이 팩토리를 공유하므로 일괄 적용된다.

### 34.3 PTT pagination (2026-06-05 완료)

#### 34.3.1 구조 분석

PTT는 파일시스템 기반 URL (`index.html`, `index1366.html`, `index1365.html` ...) 이다. 현재 최대 인덱스를 모르면 URL을 미리 생성할 수 없어서 `page_url_template` 방식은 불가.

`diag_ptt_pagination.py` 진단 결과:
- `index.html`의 "上頁" 버튼 href = `index{N-1}.html` (정적 HTML에 포함)
- 페이지당 링크 수: page 1 = 14개, page 2/3 = 20개
- over18 폼은 Crawl4AI `js_code` + `delay_before_return_html` 로 처리 완료

#### 34.3.2 구현 방식: `prev_page_link_text` 동적 pagination

`page_url_template` (정적 URL 생성) 과 별개로, `SiteConfig`에 `prev_page_link_text: str | None` 필드를 추가했다.

- 페이지 fetch 결과의 링크 목록에서 해당 텍스트가 포함된 링크를 `next_board_url` 로 추출
- `_fetch_post_urls` 가 `ListingResult.next_board_url` 반환
- `_process_board` 가 `str | None` 반환 (동적 체인)
- site loop 에서 `prev_page_link_text + max_pages > 1` 조합이면 동적 모드로 분기

PTT 설정:
```python
max_pages=3,
prev_page_link_text="上頁",
```

#### 34.3.3 smoke 결과 (성공, 2026-06-05)

| 페이지 | 링크 수 | 패턴 매칭 |
|---|---|---|
| page 1 (`index.html`) | 47개 | 14건 |
| page 2 (`index1366.html`) | 61개 | 20건 |
| page 3 (`index1365.html`) | 60개 | 20건 |

real 5/5 (sticky/short 0건). `ptt_mobile_game` 은 동일 구조이므로 같이 적용.

### 34.4 bahamut pagination smoke 이력

#### 34.4.1 1차 smoke (실패)

`page_url_template="{base}&page={page}"` 적용 시 생성된 URL: `B.php?bsn=842&page=2`

| 페이지 | 링크 수 | 패턴 매칭 |
|---|---|---|
| page 1 (`B.php?bsn=842`) | 144개 | 31건 |
| page 2 (`B.php?bsn=842&page=2`) | 147개 | **1건** |
| page 3 (`B.php?bsn=842&page=3`) | 154개 | **0건** |

원인: Cloudflare가 `bsn=842&page=2` 캐시 키로 잘못된 응답 반환.

#### 34.4.2 2차 smoke (URL 순서 수정 후)

파라미터 순서를 `B.php?page=2&bsn=842`로 맞춘 full URL 템플릿 적용 후 재smoke:

| 페이지 | 링크 수 | 패턴 매칭 |
|---|---|---|
| page 1 (`B.php?page=1&bsn=842`) | 144개 | **31건** |
| page 2 (`B.php?page=2&bsn=842`) | 147개 | **0건** |
| page 3 (`B.php?page=3&bsn=842`) | 154개 | **0건** |

URL 순서 수정으로도 page 2/3에서 0건 지속. Cloudflare 캐시 키 문제가 아니었다.

#### 34.4.3 근본 원인 분석

`diag_bahamut_pagination.py` 진단 스크립트로 확인한 실제 원인:

- `requests` 정적 HTML: page 1 = 89개, page 2 = 91개 C.php 링크 존재 (JS 렌더링 문제 아님)
- Crawl4AI/Playwright: page 2에서도 61개 C.php 링크 추출 성공
- 실제 원인: **`post_url_pattern`이 page 2+ URL 형식과 불일치**

page 2+ C.php 링크는 `bPage=N` 파라미터가 앞에 붙는다:
- page 1: `C.php?bsn=842&snA=715421&tnum=7`
- page 2+: `C.php?bPage=2&bsn=842&snA=715421&tnum=7`

기존 패턴 `C\.php\?bsn=\d+&snA=\d+`는 `C.php?bsn=...`으로 시작하는 URL만 매칭. `compiled.match()` (문자열 시작부터 매칭)이기 때문에 `bPage=2&...`가 앞에 붙으면 탈락.

추가로 page 2+에는 "마지막 댓글로" 링크도 있다:
- `C.php?bPage=2&bsn=842&last=1&snA=715421&tnum=7`

이 URL은 `bsn=842` 와 `snA=715421` 사이에 `last=1`이 끼어 있어서, 기존 `_BAHAMUT_POST_ID_RE = re.compile(r"bsn=(\d+)&snA=(\d+)")` 가 매칭 실패해 ValueError를 던진다.

#### 34.4.4 적용된 수정 (2026-06-05)

`crawler/src/sites/registry.py`:

1. `_BAHAMUT_POST_ID_RE` 분리: `_BAHAMUT_BSN_RE = re.compile(r"[?&]bsn=(\d+)")`, `_BAHAMUT_SNA_RE = re.compile(r"[?&]snA=(\d+)")`. 파라미터 순서 무관하게 추출 가능.

2. `post_url_pattern` lookahead 패턴:
   ```
   C\.php\?(?!.*[&]last=\d)(?=.*\bbsn=\d+)(?=.*\bsnA=\d+)
   ```
   - `bPage=N` prefix 있는 page 2+ URL 매칭
   - `last=1` 링크 명시 제외 (dedup 불가)

3. `max_pages=3`, `page_url_template=f"B.php?bsn={bsn}&page={{page}}"` 추가.

#### 34.4.5 3차 smoke (성공, 2026-06-05)

| 페이지 | 링크 수 | 패턴 매칭 |
|---|---|---|
| page 1 (`B.php?bsn=842`) | 144개 | 31건 |
| page 2 (`B.php?bsn=842&page=2`) | 147개 | **30건** |
| page 3 (`B.php?bsn=842&page=3`) | 154개 | **30건** |

총 15개 후보에서 5건 검증: real 2, sticky 2, short 1. 페이지당 boards OK. bahamut pagination 완료.

### 34.5 inven pagination (2026-06-05 완료)

인벤은 `?p=N` 정적 파라미터 방식.

- `requests` 기준: page 1 = 82건, page 2/3 = 13건 (고정글만, 일반글은 JS 로드)
- Crawl4AI 기준: page 1 = 82건, page 2 = 76건 (62건 고유), 3 = 76건
- `page_url_template="{base}?p={page}"`, `max_pages=3` 적용 (`inven_maple`, `inven_lineage_classic` 동일)
- smoke 결과: real 5/5, 3페이지 모두 OK

### 34.6 pagination 완료 현황

| 사이트 | 방식 | max_pages | 상태 |
|---|---|---|---|
| bahamut_* (8개) | `page_url_template` (정적) | 3 | ✅ 완료 |
| ptt, ptt_mobile_game | `prev_page_link_text="上頁"` (동적) | 3 | ✅ 완료 |
| inven_maple, inven_lineage_classic | `page_url_template="{base}?p={page}"` (정적) | 3 | ✅ 완료 |

## 35. Redis 없는 one-off dry-run inventory 방식 검증

### 35.1 질문

`CRAWL_DRY_RUN=1 python -m crawler.src.scheduler.crawl_scheduler`를 실행했을 때 Redis 연결 재시도만 반복했다.

원인:

- `crawler.src.scheduler.crawl_scheduler`의 `__main__` entrypoint는 운영용 scheduler다.
- `CrawlScheduler.run_forever()`는 APScheduler를 시작하고 Redis pub/sub trigger listener를 계속 listen한다.
- 따라서 Redis가 없는 로컬 환경에서는 dry-run 목적과 무관하게 Redis 연결 실패가 반복된다.

질문:

> Redis 없이 listing candidate inventory만 뽑는 별도 one-off script를 두는 것이 제대로 된 방식인가?

### 35.2 웹/공식 문서 확인

Crawl4AI 공식 문서는 `AsyncWebCrawler`를 async context manager로 만들고, `arun(url, config=...)`를 호출하는 one-off 또는 반복 crawl 방식을 기본 사용법으로 설명한다.

- 출처: https://docs.crawl4ai.com/api/async-webcrawler/
- 출처: https://docs.crawl4ai.com/core/quickstart/

특히 공식 문서의 핵심 구조는 다음과 같다.

- browser 전역 설정은 `BrowserConfig`
- crawl별 설정은 `CrawlerRunConfig`
- `async with AsyncWebCrawler(...)` 안에서 URL을 crawl
- context 종료 시 브라우저 리소스 정리

이는 Redis나 scheduler 없이도 listing page만 fetch하는 one-off script가 자연스러운 사용 방식이라는 뜻이다.

APScheduler 공식 문서는 scheduler가 foreground/background 형태로 계속 job을 처리하는 컴포넌트임을 설명한다.

- 출처: https://apscheduler.readthedocs.io/en/master/userguide.html
- 출처: https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/background.html

따라서 scheduler entrypoint는 장기 실행 운영 프로세스에 가깝고, “한 번 실행하고 JSONL을 만든 뒤 종료”하는 실험용 도구와는 성격이 다르다.

Redis 공식 문서는 job queue가 API와 worker를 decouple하기 위한 구조라고 설명한다.

- 출처: https://redis.io/docs/latest/develop/use-cases/job-queue/
- 출처: https://redis.io/tutorials/redis-backed-job-queue-for-background-workers/

즉 Redis는 운영 pipeline에서 trigger, queue, dedup, stats 공유에 유용하지만, listing 후보 inventory를 측정하는 read-only dry-run에는 필수 의존성이 아니다.

### 35.3 판단

별도 one-off dry-run script를 두는 것은 맞다.

이유:

1. 목적이 다르다.
   - 운영 scheduler: Redis trigger/listener, queue enqueue, dedup, progress stats
   - dry-run inventory: listing fetch, URL 후보 추출, JSONL 저장, 종료

2. 의존성이 다르다.
   - 운영: Redis 필요
   - dry-run: Redis 불필요

3. 실패 표면이 줄어든다.
   - Redis가 꺼져 있어도 후보 측정 가능
   - API/detection/dashboard 없이 crawler listing만 검증 가능

4. 실험 안전성이 높다.
   - detail fetch를 하지 않음
   - queue enqueue를 하지 않음
   - DB/S3/Redis를 오염시키지 않음

### 35.4 현재 추가한 방식

`crawler/scripts/dry_run_inventory.py`를 추가했다.

사용:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL_DRY_RUN=1 CRAWL_DRY_RUN_OUTPUT_DIR=../output \
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/dry_run_inventory.py
```

특징:

- Redis 접속 없음
- Scheduler 시작 없음
- TriggerListener 시작 없음
- `CrawlPipeline`은 재사용
- dummy Redis 객체로 unused publisher/dedup dependency만 채움
- `CRAWL_DRY_RUN=1` 분기에서 detail fetch 전에 JSONL dump 후 종료

출력:

```text
dry-run 완료: boards=N discovered=N selected=N kw_matched=N kw_unmatched=N
```

JSONL:

```text
../output/dry_run_YYYYMMDD_HHMMSS.jsonl
```

### 35.5 현재 방식의 장단점

장점:

- 기존 `_fetch_post_urls`, pagination, `ListingResult`, priority logic을 그대로 사용한다.
- 운영 crawler와 후보 추출 로직이 갈라지지 않는다.
- Redis 없이 로컬에서 바로 실행할 수 있다.
- 빠르게 검증 가능하다.

단점:

- `CrawlPipeline` 생성자 구조상 dry-run에서 사용하지 않는 `PostStorage`, `DedupChecker`, `RedisPublisher`를 dummy로 넣는다.
- `_DRY_RUN`이 module import 시점의 환경변수에 의존한다.
- 장기적으로는 listing inventory와 full pipeline이 더 명확히 분리되는 편이 낫다.

### 35.6 더 좋은 장기 구조

장기적으로는 다음 구조가 더 깨끗하다.

```text
ListingInventoryCollector
  - get_enabled_sites()
  - CrawlOptions.from_site()
  - _fetch_post_urls()
  - pagination
  - JSONL writer

CrawlPipeline
  - ListingInventoryCollector 또는 공통 listing service 사용
  - detail fetch
  - validation
  - storage
  - Redis enqueue
```

이렇게 하면:

- dry-run은 storage/publisher/dedup dummy가 필요 없다.
- 테스트도 listing 단계와 detail pipeline 단계를 분리할 수 있다.
- API나 dashboard에서 board별 stats를 추가하기 쉬워진다.

하지만 현재 단계에서는 `dry_run_inventory.py` 방식이 충분히 타당하다.

이유:

- 지금 필요한 것은 설계 완성보다 후보 증가량 실측이다.
- 운영 로직과 동일한 listing/pagination code path를 쓰는 것이 중요하다.
- dummy dependency는 dry-run 분기 전에 실제로 사용되지 않는다.

### 35.7 결론

현재 방식은 “단기 실험용으로 제대로 된 방법”이다.

다만 최종 구조로 굳히기 전에는 다음 리팩터링을 고려한다.

1. listing/pagination candidate collection을 `ListingInventoryCollector`로 분리
2. dry-run script는 collector만 사용
3. `CrawlPipeline`도 같은 collector를 재사용
4. dry-run 여부를 module import-time global이 아니라 runtime config로 전달
5. board별 stats를 JSONL/Redis 양쪽에 남김

현재 우선순위:

- 지금 만든 one-off script로 실제 inventory를 뽑는다.
- JSONL을 보고 source별 후보량/keyword matched 비율/selected=false 비율을 확인한다.
- 그 결과가 충분히 의미 있으면 collector 분리를 다음 리팩터링으로 진행한다.

## 36. dry-run inventory 실제 실행 결과

### 36.1 실행

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL_DRY_RUN=1 CRAWL_DRY_RUN_OUTPUT_DIR=../output \
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/dry_run_inventory.py
```

결과:

```text
dry-run 완료: boards=41 discovered=2135 selected=1140 kw_matched=0 kw_unmatched=2135
```

생성 파일:

```text
output/dry_run_20260607_015650.jsonl
```

JSONL line count:

```text
2135
```

즉 로그의 `discovered=2135`와 JSONL 후보 줄 수가 일치한다.

### 36.2 source별 집계

| source | boards | discovered | selected | keyword matched | unselected |
|---|---:|---:|---:|---:|---:|
| `52pojie` | 3 | 753 | 90 | 0 | 663 |
| `inven_lineage_classic` | 3 | 241 | 90 | 0 | 151 |
| `inven_maple` | 3 | 172 | 90 | 0 | 82 |
| `bahamut_lineage_classic` | 3 | 114 | 90 | 0 | 24 |
| `bahamut_aion2` | 3 | 111 | 90 | 0 | 21 |
| `bahamut_lineage_m` | 3 | 105 | 90 | 0 | 15 |
| `bahamut_bns` | 3 | 105 | 90 | 0 | 15 |
| `bahamut_lineage_w` | 3 | 100 | 90 | 0 | 10 |
| `bahamut_lineage` | 3 | 97 | 90 | 0 | 7 |
| `bahamut_tl` | 3 | 94 | 90 | 0 | 4 |
| `bahamut_aion` | 3 | 93 | 90 | 0 | 3 |
| `ptt` | 3 | 54 | 54 | 0 | 0 |
| `ptt_mobile_game` | 3 | 49 | 49 | 0 | 0 |
| `dcard_online` | 1 | 29 | 29 | 0 | 0 |
| `dcard` | 1 | 18 | 18 | 0 | 0 |

총합:

```text
discovered=2135
selected=1140
keyword_matched=0
```

### 36.3 해석

이번 dry-run은 성공이다.

확인된 것:

- Redis 없이 listing inventory 생성 가능
- pagination 적용 후 총 board page 수 41개
- 전체 후보 2,135건
- `MAX_POSTS_PER_BOARD=30` 기준 선택 후보 1,140건
- `selected=false` 후보가 995건이므로 limit 때문에 버려지는 후보도 많다.

중요한 점:

`keyword_matched=0`은 "후보가 모두 무관하다"는 의미가 아니다.

이유:

- Bahamut/Inven/PTT Lineage 같은 전용 보드는 `title_keywords=None`이라 keyword feature가 적용되지 않는다.
- mixed source인 `ptt_mobile_game`, `dcard`, `dcard_online`도 이번 실행에서는 title keyword hit가 0이었다.
- 그러나 이전 smoke에서 이 mixed source들은 `real/N=5/5` 수준으로 실제 게시글 fetch가 성공했다.

따라서 이 결과는 오히려 title keyword hard filter 제거가 필요했다는 증거다.

### 36.4 새로 보이는 병목

1. `52pojie` 후보가 매우 많다.
   - 3페이지 discovered 753건
   - selected 90건
   - unselected 663건
   - source yield와 validator noise를 따로 봐야 한다.

2. Inven/Bahamut은 pagination 효과가 크다.
   - 대부분 3페이지 × 30건 선택
   - 실제 detail fetch로 돌리면 운영 시간이 크게 늘 수 있다.

3. 선택 후보 1,140건을 전부 순차 detail fetch하면 너무 길 수 있다.
   - Dcard smoke 기준 1건 약 7~9초
   - Bahamut/Inven은 더 빠르지만 전체적으로 run time 관리 필요

4. `keyword_matched` metric이 전용 보드와 mixed 보드를 구분하지 못한다.
   - `keyword_applicable` 또는 `has_title_keywords` 필드가 필요하다.

### 36.5 다음 개선

우선순위:

1. dry-run JSONL에 `has_title_keywords` 추가
2. dry-run summary를 자동 출력
   - source별 discovered/selected/keyword matched/unselected
3. source별 `max_posts_per_board` 또는 `priority_limit` 도입 검토
   - `52pojie`는 90건을 바로 detail fetch하기보다 sample/priority가 필요
4. full pipeline 실행 전 source별 smoke 15/30으로 validator yield 확인
5. 실제 운영에서는 selected 1,140건을 모두 enqueue하지 않고 priority/scoring 단계 필요

현재 결론:

pagination과 hard-filter 제거만으로 후보량은 충분히 커졌다. 이제 병목은 "어떻게 더 많이 가져올까"가 아니라 "1,140개 후보 중 무엇을 먼저 detail fetch/detection으로 보낼까"로 바뀌었다.

## 37. 후보 1,140건 이후: priority frontier와 GitHub source 확장 조사

### 37.1 질문

현재까지 확인한 것은 다음이다.

- listing/pagination 개선으로 후보 자체는 충분히 늘었다.
- dry-run 기준 전체 후보 2,135건, 선택 후보 1,140건이다.
- 선택 후보를 전부 detail fetch하면 시간과 운영 비용이 커진다.
- title keyword만으로 거르면 은어/우회 제목/외부 링크 중심 글을 놓친다.

따라서 다음 질문은 "무엇을 더 긁을까"가 아니라 다음이다.

```text
후보를 넓게 보존하면서, 어떤 후보를 먼저 상세 크롤링할 것인가?
GitHub 같은 비게시판 source를 같은 후보 체계에 어떻게 합칠 것인가?
```

### 37.2 focused crawling / CTI crawling 조사

focused crawler 문헌의 핵심은 crawl frontier를 단순 FIFO로 보지 않고, 관련도와 품질에 따라 우선순위를 조정한다는 점이다.

확인한 참고자료:

- Focused crawler 개념: https://en.wikipedia.org/wiki/Focused_crawler
- CTI crawler architecture: https://arxiv.org/abs/2109.06932
- Dynamic CTI crawling with bandit strategy: https://arxiv.org/abs/2504.18375
- Scrapy scheduler priority queue: https://doc.scrapy.org/en/latest/topics/scheduler.html
- Scrapy AutoThrottle: https://doc.scrapy.org/en/latest/topics/autothrottle.html

우리 구조에 적용하면 다음과 같다.

```text
listing candidate 수집
-> cheap priority scoring
-> P0/P1/P2/P3 frontier
-> source별 budget 적용
-> detail fetch
-> 본문/외부 링크/다운로드/연락처 signal 추출
-> score 보정
```

중요한 점:

- title keyword는 hard filter가 아니라 priority feature다.
- low-score 후보도 반드시 sampling slot을 둔다.
- source별 yield를 계속 측정해야 한다.
- 한 source가 후보를 많이 낸다고 전부 detail fetch하면 안 된다.

### 37.3 불법 프로그램 유통 신호 조사

게임 핵/치트/모드 위장 infostealer 사례에서 반복되는 신호:

- cheat, hack, macro, bot, bypass, loader, injector, undetected, HWID bypass
- 핵, 치트, 매크로, 자동사냥, 우회
- 外掛, 輔助, 破解, 私服, 自动, 自動
- Discord, Telegram, QQ, WeChat, Kakao/OpenChat
- MediaFire, Mega, Google Drive, GitHub Releases, password-protected ZIP
- exe, dll, zip, rar, 7z, apk

확인한 참고자료:

- Fake game cheats deliver infostealer: https://www.threatlocker.com/blog/powercat-malware-campaign-fake-game-cheats-deliver-infostealer-targeting-discord-roblox-and-crypto-wallets
- Gaming-related file and infostealer infection: https://flare.io/company/press/gaming-rising-target-infostealer-malware-41-infections-gaming-related-file/
- Roblox/Discord/MediaFire 유포 사례: https://www.zscaler.com/blogs/security-research/tweaks-stealer-targets-roblox-users-through-youtube-and-discord
- Discord/Telegram malware distribution: https://candid.technology/discord-telegram-malware/

적용 판단:

- listing 단계에서는 title, URL, source, board 정도밖에 없으므로 signal이 제한적이다.
- detail 단계에서 본문/댓글/외부 링크를 얻으면 contact/download signal의 품질이 크게 좋아질 것이다.
- 따라서 1차 score는 "상세 fetch 우선순위"이며, 최종 탐지 점수가 아니다.

### 37.4 GitHub를 source로 넣을 수 있는가?

결론: 넣을 수 있고, 넣는 것이 맞다. 단, 기존 게시판 `SiteConfig`에 억지로 끼우는 것이 아니라 별도 `GitHubSourceAdapter`로 분리해야 한다.

이유:

- GitHub는 게시판 목록/상세 구조가 아니라 repository/search/readme/release/code search 구조다.
- 공식 API가 있고, 웹 UI를 Playwright로 긁는 것보다 API 사용이 정책/성능 측면에서 낫다.
- GitHub Search API는 rate limit과 1,000 result cap이 있으므로 query slicing과 backoff가 필요하다.

공식 참고자료:

- GitHub Acceptable Use Policies: https://docs.github.com/en/site-policy/acceptable-use-policies/github-acceptable-use-policies
- GitHub REST Search API: https://docs.github.com/en/rest/search/search
- GitHub REST API rate limits: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- Repository search syntax: https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories
- Code search syntax: https://docs.github.com/en/search-github/searching-on-github/searching-code
- Repository contents / README API: https://docs.github.com/en/rest/repos/contents
- Releases API: https://docs.github.com/en/rest/releases/releases

GitHub 공식 문서상 중요한 제약:

- Search API는 검색 endpoint별 rate limit이 별도로 있다.
- REST search는 각 search당 최대 1,000개 결과를 제공한다.
- code search는 인증이 필요하고, default branch 중심, 파일 크기/archived repo 등 제약이 있다.
- repository search는 name/description/topics/README 중심으로 검색할 수 있다.

### 37.5 GitHub 악용 사례 조사

GitHub가 게임 핵/치트/크랙 유통에 쓰인 사례는 이미 여러 건 확인된다.

참고자료:

- Vidar Stealer 2.0이 fake game cheats / HWID bypass repo로 유포된 사례: https://www.infosecurity-magazine.com/news/vidar-stealer-exploits-github/
- McAfee의 GitHub crack/hack/crypto tool 위장 malware 분석: https://www.mcafee.com/blogs/other-blogs/mcafee-labs/githubs-dark-side-unveiling-malware-disguised-as-cracks-hacks-and-crypto-tools/
- fake stars가 game cheats/pirated software/crypto bot 위장 malware repo 홍보에 쓰인다는 연구: https://arxiv.org/abs/2412.13459
- GitHub 계정 네트워크가 phishing repository와 악성 링크를 배포한 사례: https://blog.checkpoint.com/security/the-hidden-menace-of-phantom-attackers-on-github-by-stargazers-ghost-network/
- 악성 PoC repository 연구: https://arxiv.org/abs/2210.08374

우리 목표와 연결:

- "프로그램 내용이 뭔지"를 보려면 GitHub README/release metadata는 좋은 1차 자료다.
- "개인정보를 뺏기기 전 경로"를 보려면 README -> external link -> landing/download/contact 지점 추적이 중요하다.
- 파일 다운로드/실행은 하지 않는다. 처음에는 URL, README, release asset metadata, 외부 링크까지만 수집한다.

### 37.6 GitHub source adapter 설계 초안

```text
ForumSourceAdapter
  - Dcard / PTT / Bahamut / Inven / 52pojie
  - listing page -> post URL candidate

GitHubSourceAdapter
  - repository search
  - README fetch
  - release metadata fetch
  - limited code search

ExternalLinkSourceAdapter
  - forum/GitHub detail에서 발견한 Telegram/Discord/Drive/MediaFire/Mega 링크
  - 파일 다운로드 없이 landing metadata만 수집
```

공통 후보 형태:

```python
Candidate = {
    "source_type": "forum | github_repo | github_release | external_link",
    "source_id": "...",
    "url": "...",
    "title": "...",
    "snippet": "...",
    "published_at": "...",
    "signals": {...},
    "score": 0,
    "priority_bucket": "P0 | P1 | P2 | P3",
    "reasons": [],
}
```

초기 GitHub query 후보:

```text
game + cheat/hack/macro/bot/bypass/injector/loader
lineage/maple/roblox/valorant/cs2/minecraft + cheat/hack/macro
anti-cheat/eac/battleye/hwid + bypass
discord/telegram + loader/injector/download
```

주의:

- query가 너무 넓으면 1,000 result cap에 걸린다.
- created/pushed date, language, topic, stars range 등으로 slicing한다.
- code search는 비싸므로 repository/README/release에서 고위험으로 나온 후보에만 제한한다.

### 37.7 비용/성능 판단

현재 인프라:

- EC2 1개
- RDS 1개
- Redis는 운영 queue/dedup/stats에 사용
- Playwright/Crawl4AI 상세 fetch는 느리고 메모리 비용이 크다.

따라서 우선순위:

1. listing/API metadata 수집은 넓게 한다.
2. detail fetch는 priority budget으로 제한한다.
3. GitHub는 API metadata 중심으로 시작한다.
4. 파일 다운로드/실행은 하지 않는다.
5. P0/P1만 먼저 detail/link-follow를 적용한다.

실패 조건:

- 후보 수만 늘고 P0/P1 실질 증거가 늘지 않음
- 한 source가 대부분의 detail budget을 독점함
- title keyword matching 후보만 상세 fetch되어 sampling bias가 다시 생김
- GitHub API rate limit으로 운영 crawl이 지연됨

### 37.8 지금 코드에 먼저 반영할 범위

운영 pipeline을 바로 크게 바꾸지 않고 다음만 먼저 반영한다.

1. dry-run JSONL에 `has_title_keywords` 추가
2. cheap priority score 추가
3. `priority_bucket` / `score_reasons` 저장
4. dry-run 종료 시 source별 P0/P1/P2/P3 요약 출력
5. full detail fetch budget 변경은 다음 단계로 보류

이렇게 하면 실제 운영 queue를 더럽히지 않고 다음 질문을 검증할 수 있다.

```text
현재 2,135개 후보 중 P0/P1은 얼마나 되는가?
P2/P3 sampling을 어느 정도 잡아야 제목 편향이 줄어드는가?
52pojie처럼 후보가 많은 source는 실제로 high-risk signal을 많이 내는가?
GitHub를 붙였을 때 forum 후보와 같은 score 체계로 비교 가능한가?
```

## 38. cheap candidate scoring dry-run 구현

### 38.1 변경 내용

새 파일:

```text
crawler/src/scheduler/candidate_scoring.py
```

역할:

- listing 단계 후보를 detail fetch 전에 싸게 점수화한다.
- 제목/URL/source/board_url만 사용한다.
- 최종 탐지 점수가 아니라 detail fetch 우선순위다.
- 낮은 점수 후보를 drop하는 용도가 아니다.

출력 필드:

```text
score
priority_bucket
score_reasons
source_risk
keyword_signal
contact_signal
download_signal
game_signal
exploration_bonus
has_title_keywords
```

priority bucket:

| bucket | 의미 |
|---|---|
| `P0` | high-risk term + contact/download/source risk가 강한 후보 |
| `P1` | 여러 신호가 겹친 우선 상세 fetch 후보 |
| `P2` | 중간 위험 또는 sampling 후보 |
| `P3` | low signal. drop이 아니라 낮은 비율 sampling 대상 |

### 38.2 scoring signal

현재 cheap scorer가 보는 신호:

- source risk: `52pojie`, mixed board 등
- title keyword match
- high-risk term: hack, cheat, macro, bot, bypass, injector, loader, undetected, 핵, 치트, 매크로, 外掛, 輔助, 破解 등
- contact/sales term: Telegram, Discord, QQ, WeChat, 카톡, 오픈채팅, 문의, 판매 등
- download/file term: download, release, GitHub, MediaFire, Mega, Drive, exe, dll, zip, rar, 7z 등
- game term: Lineage, 天堂, Maple, Roblox, Valorant, CS2, Minecraft 등
- exploration bonus: title keyword가 있는 mixed board에서 title 미매칭인 후보를 sampling 후보로 표시

### 38.3 dry-run 출력 개선

`_dump_dry_run_candidates()` JSONL에 scoring 필드를 추가했다.

예시:

```json
{
  "site_id": "dcard",
  "board_url": "https://www.dcard.tw/f/game",
  "url": "https://www.dcard.tw/f/game/p/...",
  "title": "最近設定分享",
  "has_title_keywords": true,
  "keyword_matched": false,
  "selected": true,
  "score": 12,
  "priority_bucket": "P3",
  "score_reasons": ["title_unmatched_sampling_candidate"]
}
```

`crawler/scripts/dry_run_inventory.py`도 dry-run 완료 후 최신 JSONL을 읽어 source summary를 출력한다.

출력 예시:

```text
priority buckets: P0=... P1=... P2=... P3=...
source summary:
site                          total   sel   kw   P0   P1   P2   P3
52pojie                         ...   ...  ...  ...  ...  ...  ...
```

### 38.4 다음 코드 단계

아직 하지 않은 것:

- production pipeline에서 priority budget으로 detail fetch 제한
- Redis queue에 priority metadata 전달
- dashboard에 P0/P1/P2 funnel 표시
- GitHubSourceAdapter 구현
- ExternalLinkSourceAdapter 구현

다음 구현 순서:

1. dry-run scoring 결과를 실제 실행해 본다.
2. P0/P1이 너무 적거나 너무 많으면 weight를 조정한다.
3. source별 detail budget 정책을 추가한다.
4. GitHubSourceAdapter를 별도 dry-run으로 추가한다.
5. forum 후보와 GitHub 후보를 같은 Candidate schema로 합친다.

### 38.5 2026-06-07 dry-run scoring 결과와 조정

실행:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL_DRY_RUN=1 CRAWL_DRY_RUN_OUTPUT_DIR=../output \
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/dry_run_inventory.py
```

결과:

```text
dry-run 완료: boards=41 discovered=2136 selected=1140 kw_matched=0 kw_unmatched=2136
dry-run JSONL: ../output/dry_run_20260607_022242.jsonl
priority buckets: P1=7 P2=814 P3=1315
```

초기 scorer 해석:

- `P0=0`: listing 단계에서 제목/URL만 보고 "명확한 배포/연락/다운로드"까지 판단하기는 어렵다.
- `P1=7`: 대부분 52pojie의 "破解" 계열 제목 또는 Bahamut의 설치/QQ/실행 오류 글이었다.
- `P2=814`: 너무 많다. 특히 52pojie 753건 중 747건이 source risk만으로 P2가 되었다.

즉 초기 scorer는 "후보를 버리지 않기"에는 좋지만, detail fetch budget을 정하기에는 P2가 너무 넓었다.

문제 샘플:

```text
the execution arguments are not valid QQ
```

이 제목에서:

- `exe`가 `execution` 내부에서 download/file signal로 잡혔다.
- `QQ`가 이모티콘처럼 쓰였는데 contact signal로 잡혔다.

또한:

```text
【攻略】檢舉外掛的流程
```

이런 글은 외掛 단어가 있지만 실제로는 "유통"보다 "신고/규정/공식 대응"에 가깝다.

따라서 scorer를 조정했다.

조정 내용:

1. ASCII term은 substring이 아니라 token boundary로 매칭
   - `exe`가 `execution`에 매칭되지 않음
   - `bot`이 `robot`에 매칭되지 않음
2. `qq` 단독 term 제거
   - 대신 `qq号`, `qq號`, `qq群`, `qq 群`, `qq:`처럼 연락처 의도가 있는 표현만 사용
3. source risk만으로 P2 승격 금지
   - 52pojie 전체가 P2가 되는 문제 완화
4. low distribution intent penalty 추가
   - 신고/공지/규정/공식/目錄/版規/公告 류는 유통 의도를 낮게 봄
5. P0/P1은 distribution signal 조합이 있을 때만 승격

기존 JSONL에 새 scorer를 다시 적용한 결과:

```text
buckets: P2=53 P3=2083
```

source별 재계산:

| source | P2 | P3 |
|---|---:|---:|
| `52pojie` | 3 | 750 |
| `inven_lineage_classic` | 3 | 238 |
| `inven_maple` | 2 | 170 |
| `bahamut_lineage_classic` | 4 | 110 |
| `bahamut_aion2` | 12 | 100 |
| `bahamut_bns` | 9 | 96 |
| `bahamut_lineage_m` | 2 | 103 |
| `bahamut_lineage_w` | 2 | 96 |
| `bahamut_lineage` | 7 | 90 |
| `bahamut_tl` | 1 | 94 |
| `bahamut_aion` | 8 | 86 |
| `ptt` | 0 | 54 |
| `ptt_mobile_game` | 0 | 49 |
| `dcard_online` | 0 | 29 |
| `dcard` | 0 | 18 |

해석:

- 이제 P2는 "상세 fetch 후보"로 볼 수 있을 정도로 줄었다.
- P0/P1이 0인 것은 이상하지 않다. listing title만으로는 배포/연락/다운로드 조합이 거의 드러나지 않는다.
- Dcard/PTT mixed board가 모두 P3인 것도 "버린다"는 뜻이 아니다. 이들은 sampling budget으로 상세 fetch해야 한다.
- 52pojie는 source 자체가 high-risk라서 P3라도 source sampling을 따로 둬야 한다.

다음 판단:

```text
detail fetch 1차 실험 예산이 100개라면:

P2 전수: 53개
52pojie P3 sample: 10개
mixed board P3 sample: dcard/dcard_online/ptt_mobile_game 각 5개
전용 게임 보드 P3 source별 sample: 각 2~3개
```

이렇게 하면 제목 편향을 줄이면서도 EC2 1대에서 감당 가능한 detail fetch 실험이 된다.

## 39. priority 기반 detail fetch probe 구현

### 39.1 목적

dry-run scoring은 listing 단계의 제목/URL/source만 보고 우선순위를 붙인다. 하지만 이것만으로는 다음을 알 수 없다.

- P2가 실제 본문에서도 위험 신호를 많이 내는가?
- P3 샘플 안에 title로는 안 보이는 유통/연락/다운로드 신호가 있는가?
- source별 validator real 비율이 어느 정도인가?
- detail fetch 비용이 source별로 얼마나 다른가?

따라서 운영 queue/DB에 저장하지 않고, 후보 일부만 실제 detail fetch 하는 probe 스크립트를 추가했다.

### 39.2 추가 파일

```text
crawler/scripts/detail_priority_probe.py
```

역할:

1. 최신 `dry_run_*.jsonl` 읽기
2. JSONL의 기존 score를 믿지 않고 현재 `candidate_scoring.py` 기준으로 재점수화
3. P2 전수 + P3 샘플 선택
4. 실제 상세 페이지 fetch
5. 파일/이미지는 다운로드하지 않음 (`download_images=False`)
6. validator 결과 기록
7. 본문에서 위험 신호 추출
8. `detail_probe_YYYYMMDD_HHMMSS.jsonl` 저장
9. bucket/source별 요약 출력

### 39.3 샘플링 기본값

| env | 기본값 | 의미 |
|---|---:|---|
| `DETAIL_PROBE_MAX_P2` | `80` | P2 최대 fetch 수 |
| `DETAIL_PROBE_52POJIE_P3` | `10` | 52pojie P3 샘플 |
| `DETAIL_PROBE_MIXED_P3` | `5` | Dcard/PTT mixed source별 P3 샘플 |
| `DETAIL_PROBE_OTHER_P3` | `2` | 나머지 source별 P3 샘플 |
| `DETAIL_PROBE_DELAY_SECONDS` | `2` | 상세 fetch 사이 delay |
| `DETAIL_PROBE_INPUT` | unset | 특정 dry-run JSONL 직접 지정 |

현재 dry-run 파일 기준 선택 계획:

```text
input: ../output/dry_run_20260607_022242.jsonl
buckets after latest scorer: P2=48 P3=2088
chosen total: 95

P2_all=48
P3_52pojie_sample=10
P3_mixed_sample=15
P3_other_source_sample=22
```

### 39.4 실행 명령

전체 probe:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
CRAWL_DRY_RUN_OUTPUT_DIR=../output \
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/detail_priority_probe.py
```

작은 smoke probe:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
DETAIL_PROBE_MAX_P2=1 \
DETAIL_PROBE_52POJIE_P3=0 \
DETAIL_PROBE_MIXED_P3=0 \
DETAIL_PROBE_OTHER_P3=0 \
DETAIL_PROBE_DELAY_SECONDS=0 \
CRAWL_DRY_RUN_OUTPUT_DIR=../output \
CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
  ../.venv/bin/python scripts/detail_priority_probe.py
```

### 39.5 Codex sandbox 주의

Codex macOS sandbox 안에서는 Playwright/Chromium 실행이 다음 오류로 실패할 수 있다.

```text
BrowserType.launch ... kill EPERM
```

이번에도 sandbox 내부에서는 1건 probe가 fetch error로 떨어졌고, 동일 명령을 sandbox 밖에서 실행하자 정상 fetch 되었다.

따라서 실제 probe는 다음 둘 중 하나로 실행한다.

1. 사용자의 일반 터미널에서 실행
2. Codex에서 권한 승인 후 sandbox 밖 실행

### 39.6 1건 smoke probe 결과

실행:

```text
DETAIL_PROBE_MAX_P2=1
DETAIL_PROBE_52POJIE_P3=0
DETAIL_PROBE_MIXED_P3=0
DETAIL_PROBE_OTHER_P3=0
```

결과 파일:

```text
output/detail_probe_20260607_023541.jsonl
```

대상:

```text
site=52pojie
url=https://www.52pojie.cn/thread-582852-1-1.html
title=Windows破解入门
priority=P2
```

결과:

```text
ok=true
elapsed_ms=5261
body_len=14216
validator_kind=sticky
is_real_user_post=false
signals=high_risk/download/credential
```

해석:

- 상세 fetch 자체는 성공했다.
- 위험 단어와 다운로드/비밀번호 신호가 잡혔지만, validator는 `导航索引` 마커로 sticky 판정했다.
- 즉 이 후보는 실제 불법 프로그램 유통 글이라기보다 52pojie의 입문/도구 모음/안내성 글이다.

이 결과를 반영해 scorer를 다시 조정했다.

추가 조정:

- low intent term에 `入門`, `入门`, `新手`, `導航`, `导航`, `索引` 추가
- 점수는 0 아래로 내려가지 않도록 clamp

기존 JSONL 재계산 후:

```text
P2=48
P3=2088
probe target=95
```

현재 판단:

- detail probe 스크립트는 동작한다.
- P2에도 sticky/guide가 들어올 수 있으므로 validator 결과를 함께 봐야 한다.
- P2 전수 + P3 stratified sample 구조는 유지한다.
- 다음에는 전체 95건 probe를 실행하고 bucket/source별 `real`, `signal`, `fetch_error` 비율을 봐야 한다.

### 39.7 전체 95건 detail probe 결과

실행 결과 파일:

```text
output/detail_probe_20260607_023840.jsonl
```

요약:

```text
bucket   total  real signal error
P2          48    40     38     0
P3          47    36     22     2
```

source별 요약:

| source | total | real | signal | error |
|---|---:|---:|---:|---:|
| `bahamut_aion2` | 14 | 12 | 12 | 0 |
| `bahamut_bns` | 11 | 7 | 6 | 0 |
| `52pojie` | 10 | 2 | 5 | 0 |
| `bahamut_lineage` | 9 | 9 | 8 | 0 |
| `bahamut_aion` | 8 | 6 | 8 | 0 |
| `bahamut_lineage_classic` | 6 | 5 | 5 | 0 |
| `dcard` | 5 | 5 | 0 | 0 |
| `dcard_online` | 5 | 3 | 1 | 2 |
| `inven_lineage_classic` | 5 | 5 | 5 | 0 |
| `ptt_mobile_game` | 5 | 5 | 2 | 0 |
| `bahamut_lineage_m` | 4 | 4 | 3 | 0 |
| `bahamut_lineage_w` | 4 | 4 | 1 | 0 |
| `inven_maple` | 4 | 4 | 1 | 0 |
| `bahamut_tl` | 3 | 3 | 2 | 0 |
| `ptt` | 2 | 2 | 1 | 0 |

validator kind:

```text
real=76
short=9
empty=5
unknown=2
fetch_error=2
sticky=1
```

signal 종류:

```text
high_risk=35
download=23
credential=21
contact=10
```

해석:

1. P2는 꽤 좋은 우선순위다.
   - 48건 중 40건 real
   - 48건 중 38건 signal
   - fetch error 0
   - detail fetch 우선순위로 사용할 가치가 있다.

2. P3도 버리면 안 된다.
   - 47건 중 36건 real
   - 47건 중 22건 signal
   - title/cheap score가 낮아도 본문에서 신호가 나온다.
   - 따라서 P3 sampling slot은 반드시 유지해야 한다.

3. Dcard/Dcard online은 성격이 다르다.
   - `dcard`: 5/5 real, signal 0
   - `dcard_online`: 5건 중 2건 Cloudflare JS challenge
   - Dcard는 본문 fetch 성공률은 괜찮지만 listing/title 기준 위험 신호는 약하다.
   - Dcard는 "탐색 샘플"로 유지하고, signal dictionary를 Dcard 표현에 맞춰 확장해야 한다.

4. 52pojie는 high-risk지만 noise도 크다.
   - 10건 중 real 2, signal 5
   - sticky/unknown/empty가 섞인다.
   - P2/P3 모두 validator와 source-specific low-intent filtering이 필요하다.

5. Bahamut short 판정이 너무 보수적이었다.
   - short 9건 대부분이 Bahamut P2였다.
   - 예: 외掛, 계정, 다운로드, 신고/사기 관련 짧은 글
   - 50~200자 사이의 짧은 사용자 글도 탐지 목적상 의미가 있다.

### 39.8 Bahamut validator 조정

기존:

```text
_BAHAMUT_BODY_MIN_LEN = 200
```

문제:

- Bahamut은 selector가 순수 본문만 가져온다.
- 짧은 질문/제보/피해 공유 글도 50~200자 사이에 많다.
- 이번 probe에서 200자 미만 글 중 외掛/계정/다운로드 신호가 확인됐다.

변경:

```text
_BAHAMUT_BODY_MIN_LEN = 50
```

generic guard의 50자 미만 short 기준은 그대로 유지한다.

추가 테스트:

- 50자 미만은 여전히 short
- 50~200자 사이의 의미 있는 Bahamut 사용자 글은 real

판단:

- 이 변경은 수집량을 무조건 늘리는 것이 아니라, 실제 probe에서 확인된 false negative를 줄이는 조정이다.
- 특히 Bahamut의 짧은 외掛/계정/신고성 글이 downstream detection으로 넘어갈 수 있게 된다.

### 39.9 다음 단계

현재 다음 작업 후보:

1. `detail_probe_*.jsonl` 결과를 자동 분석하는 summary script 추가
   - bucket/source별 real rate
   - signal rate
   - fetch error
   - validator kind breakdown

2. production detail fetch budget 설계
   - P2 전수
   - P3 source-stratified sampling
   - Dcard/52pojie 별도 cap

3. source-specific scorer 보정
   - 52pojie low-intent/empty 후보 감소
   - Dcard 표현 signal 확장
   - Bahamut 신고/피해 글과 실제 판매/배포 글 분리

4. GitHubSourceAdapter 설계/구현
   - forum probe 결과가 확보됐으므로 다음 source adapter 실험으로 넘어갈 수 있다.

## 40. detail probe summary script 구현

### 40.1 목적

`detail_priority_probe.py` 실행 후 매번 수동으로 JSONL을 집계하지 않기 위해 summary script를 추가했다.

추가 파일:

```text
crawler/scripts/detail_probe_summary.py
```

사용:

```bash
cd /Users/jmac/Desktop/261RCOSE45700/crawler
../.venv/bin/python scripts/detail_probe_summary.py
```

특정 파일 지정:

```bash
../.venv/bin/python scripts/detail_probe_summary.py ../output/detail_probe_20260607_023840.jsonl
```

### 40.2 출력 항목

- bucket별 total/real/real rate/signal/signal rate/error
- source별 total/real/real rate/signal/signal rate/error
- sample_reason별 성과
- validator kind breakdown
- signal 종류별 document count / hit count
- latency median/p95/max
- non-real/error 샘플
- signal 샘플

### 40.3 실행 확인

대상:

```text
../output/detail_probe_20260607_023840.jsonl
```

요약:

```text
bucket summary
P2 total=48 real=40 real%=83.3% signal=38 sig%=79.2% error=0
P3 total=47 real=36 real%=76.6% signal=22 sig%=46.8% error=2

latency
count=95 median_ms=3749 p95_ms=7256 max_ms=7813
```

주의:

- 이 summary는 probe JSONL에 저장된 validator 결과를 그대로 읽는다.
- Bahamut validator를 200자 기준에서 50자 기준으로 낮춘 이후에는 기존 `detail_probe_20260607_023840.jsonl`의 `short` 9건이 자동으로 바뀌지는 않는다.
- 새 validator 효과를 반영하려면 detail probe를 다시 실행해야 한다.

### 40.4 구현 중 발견한 버그

초기 summary script에서 `real` 카운트가 중복 집계되어 real rate가 100%를 넘는 문제가 있었다.

원인:

```text
grouped[key][kind] += 1
grouped[key]["real"] += int(kind == "real")
```

`kind == "real"`일 때 같은 Counter key를 두 번 증가시켰다.

수정:

```text
grouped[key][f"kind_{kind}"] += 1
grouped[key]["real"] += int(kind == "real")
```

이후 출력:

```text
P2 real%=83.3%
P3 real%=76.6%
```

정상화됐다.

## 41. 2026-06-07 최신 문서 기준 코드 리뷰와 리팩토링

### 41.1 확인한 공식 문서

Crawl4AI v0.8.x 문서를 기준으로 현재 코드와 비교했다.

참고:

- AsyncWebCrawler: https://docs.crawl4ai.com/api/async-webcrawler/
- Browser/Crawler config: https://docs.crawl4ai.com/core/browser-crawler-config/
- Parameters reference: https://docs.crawl4ai.com/api/parameters/
- Multi-URL crawling / dispatcher: https://docs.crawl4ai.com/advanced/multi-url-crawling/
- Proxy & Security: https://docs.crawl4ai.com/advanced/proxy-security/

확인한 핵심:

1. `AsyncWebCrawler`는 보통 한 번 만들고 여러 `arun()`에 재사용하는 방식이 권장된다.
2. 여러 URL은 `arun_many()` + dispatcher가 더 효율적이다.
3. `CrawlerRunConfig`에는 `proxy_config`, `max_retries`, `fallback_fetch_function`, `session_id`, `url_matcher` 등이 있다.
4. 최신 proxy 문서는 per-request `CrawlerRunConfig.proxy_config` 사용을 권장한다.
5. `BrowserConfig`는 headless/header/user agent/browser identity 중심으로 두고, crawl별 네트워크/상호작용 옵션은 `CrawlerRunConfig`에 두는 편이 맞다.

### 41.2 바로 수정한 부분: proxy 전달 위치

기존:

```text
BrowserConfig(proxy_config=site.proxy)
```

문제:

- Crawl4AI 최신 proxy 문서는 proxy를 `CrawlerRunConfig.proxy_config`에 두는 방식을 권장한다.
- proxy는 브라우저 전체 identity라기보다 요청별 네트워크 정책으로 다뤄야 source별 적용/rotation/fallback으로 확장하기 좋다.

변경:

```text
CrawlerRunConfig(proxy_config=site.proxy)
```

수정 파일:

- `crawler/src/crawl4ai_crawler.py`
- `crawler/src/scheduler/crawl_scheduler.py`
- `crawler/scripts/smoke_each_site.py`
- `crawler/tests/unit/test_crawl4ai_crawler.py`
- `crawler/src/sites/registry.py` 주석

효과:

- listing fetch와 detail fetch 모두 최신 Crawl4AI 권장 방식에 맞춰 proxy를 run config로 전달한다.
- 나중에 `ProxyConfig.from_env`, `RoundRobinProxyStrategy`, `max_retries`로 확장하기 쉬워졌다.

### 41.3 바로 수정한 부분: CLI output 경로 안정화

문제:

- 새로 만든 probe/summary 스크립트 일부는 기본 output 경로가 현재 작업 디렉터리에 의존했다.
- 사용자가 repo root에서 실행하느냐 crawler 디렉터리에서 실행하느냐에 따라 다른 `output/`을 볼 수 있었다.

변경:

- `dry_run_inventory.py`
- `detail_priority_probe.py`
- `detail_probe_summary.py`

위 스크립트들은 env가 없으면 repo root의 `output/`을 기본으로 보도록 수정했다.

### 41.4 바로 수정한 부분: API stats endpoint 테스트 추가

추가 테스트:

- `CrawlTriggerServiceTest.getLatestPipelineStats_readsStatsJson`
- `CrawlTriggerServiceTest.getLatestPipelineStats_returnsZerosWhenMissing`
- `DetectionControllerTest.getCrawlStats_returnsLatestPipelineStats`

이유:

- `/api/crawl/stats`는 dashboard funnel이 의존하는 endpoint다.
- Redis stats JSON parsing과 empty fallback이 깨지면 UI가 조용히 빈 상태가 될 수 있다.

### 41.5 바로 정리한 부분: 죽은 코드 제거

`Crawl4AICrawler`의 `_base_run_config`는 생성만 하고 쓰지 않았다.

```text
self._base_run_config = CrawlerRunConfig(**self._base_run_kwargs)
```

삭제했다.

### 41.6 검증 결과

Crawler 관련:

```text
92 passed
py_compile 통과
```

API:

```text
./gradlew test
BUILD SUCCESSFUL
```

Dashboard:

```text
pnpm build
pnpm lint
```

둘 다 통과했다.

### 41.7 아직 남긴 큰 리팩토링 후보

이번에 바로 바꾸지 않은 이유는 동작 범위가 커서 별도 PR/실험으로 나누는 편이 안전하기 때문이다.

1. detail fetch에서 `AsyncWebCrawler` 재사용
   - 현재 `Crawl4AICrawler.fetch()`는 호출마다 `AsyncWebCrawler` context를 새로 연다.
   - Crawl4AI 문서는 crawler를 한 번 만들고 여러 `arun()`에 재사용하는 방식을 권장한다.
   - 기대 효과: 95건 probe 같은 작업의 브라우저 startup overhead 감소.
   - 리스크: site별 headers/user_agent/proxy가 다른 경우 browser config/session 경계를 잘 나눠야 한다.

2. `arun_many()` + dispatcher 도입
   - Crawl4AI 문서는 다중 URL 크롤링에 `arun_many()`와 `MemoryAdaptiveDispatcher`/`RateLimiter`를 권장한다.
   - 기대 효과: EC2 1대에서 concurrency와 memory/rate limit을 체계적으로 관리.
   - 리스크: source별 politeness, Dcard/Cloudflare, Bahamut ACS-GOTO 대응을 source별로 달리 해야 한다.

3. production priority budget 적용
   - 현재 scoring/probe는 실험 도구에 적용됐다.
   - 운영 pipeline은 아직 selected 후보를 순차 detail fetch한다.
   - 다음 단계: P2 전수 + P3 stratified sampling budget을 production crawl에 넣는다.

4. proxy strategy 확장
   - 현재는 source별 static proxy config다.
   - 최신 Crawl4AI는 `ProxyConfig.from_env`, `RoundRobinProxyStrategy`, `max_retries`를 제공한다.
   - 유료 proxy는 최후 수단이라는 원칙을 유지하되, 막힌 source 중 high-yield만 opt-in 대상이 되어야 한다.

현재 결론:

- 최신 문서 기준으로 즉시 고칠 수 있는 proxy 전달 위치와 CLI 경로 안정성은 반영했다.
- 성능 리팩토링의 핵심은 `AsyncWebCrawler` 재사용과 `arun_many()` dispatcher 도입이다.
- 다만 이건 운영 behavior가 크게 바뀌므로, 지금처럼 probe 결과를 기반으로 budget 정책을 먼저 확정한 뒤 별도 단계로 진행하는 편이 맞다.

## 42. 2026-06-07 추가 확인: 최신 Crawl4AI anti-bot/GitHub 제약과 운영 누락 버그

### 42.1 추가 조사한 공식 문서

추가로 확인한 자료:

- Crawl4AI Anti-Bot & Fallback: https://docs.crawl4ai.com/advanced/anti-bot-and-fallback/
- Crawl4AI Proxy & Security: https://docs.crawl4ai.com/advanced/proxy-security/
- Crawl4AI v0.8.5 release note: https://docs.crawl4ai.com/blog/releases/v0.8.5/
- GitHub REST Search API: https://docs.github.com/en/rest/search/search
- GitHub REST API rate limits: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api
- GitHub repository search syntax: https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories
- Fake-star/malware repository 연구: https://arxiv.org/abs/2412.13459
- YouTube crack/game-cheat malware 유통 연구: https://arxiv.org/abs/2507.16996

### 42.2 Crawl4AI anti-bot 문서 기준 검증

공식 문서상 anti-bot 관련 설정은 모두 `CrawlerRunConfig`에 둔다.

핵심:

- `proxy_config`: 단일 proxy 또는 proxy list. retry round마다 proxy 후보를 순서대로 시도한다.
- `max_retries`: anti-bot block 감지 시 retry round 수. 기본값은 0.
- `fallback_fetch_function`: retry/proxy가 모두 실패했을 때 마지막 raw HTML provider로 사용.
- `crawl_stats`: attempt 수, retry 수, 사용한 proxy, fallback 사용 여부, `resolved_by`를 남긴다.

우리 코드 반영:

- `SiteConfig.max_retries` 추가.
- `CrawlOptions.max_retries` 추가.
- listing/detail/smoke/probe fetch가 `max_retries`를 `CrawlerRunConfig`로 전달.
- `CrawlResult.crawl_stats` 추가.
- `detail_priority_probe.py`가 `crawl_stats`를 JSONL에 저장.
- Dcard/Dcard online은 실측에서 detail timeout/anti-bot 가능성이 있어 `max_retries=1`로 시작.

판단:

- 이 방향은 최신 Crawl4AI 문서와 맞다.
- 단, `max_retries`는 비용을 곱한다. worst case는 `(1 + max_retries) x proxy 후보 수`다.
- 따라서 모든 사이트에 retry를 켜면 EC2 1대 환경에서 실행 시간이 늘고, 대상 사이트에도 부담이 커진다.
- 지금처럼 문제 source에만 `max_retries=1`부터 켜고 `crawl_stats`로 실제 해결률을 보는 방식이 맞다.

다음 실험:

```text
DETAIL_PROBE_MAX_P2=80 DETAIL_PROBE_MIXED_P3=10 DETAIL_PROBE_DELAY_SECONDS=2 \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

확인할 항목:

- Dcard 계열의 `fetch_error`가 줄었는가?
- `crawl_stats.attempts > 1`인 케이스가 실제로 성공으로 전환됐는가?
- retry 때문에 median/p95 latency가 얼마나 늘었는가?

### 42.3 Crawl4AI proxy 문서 기준 검증

공식 proxy 문서 결론:

- legacy `BrowserConfig.proxy_config`는 deprecated 방향이다.
- request-level `CrawlerRunConfig.proxy_config`가 권장된다.
- proxy credentials는 코드에 하드코딩하지 않고 env로 둬야 한다.
- 여러 proxy가 필요하면 `ProxyConfig.from_env()`와 `RoundRobinProxyStrategy`를 쓸 수 있다.
- 안전 로그에서는 username/password를 절대 찍지 않아야 한다.

우리 코드 상태:

- proxy 전달 위치는 이미 `CrawlerRunConfig.proxy_config`로 이동했다.
- Bright Data CN proxy는 env 기반이고, env가 없으면 `None`이라 무료 direct crawl로 동작한다.
- 아직 `ProxyConfig.from_env()`/`RoundRobinProxyStrategy`는 쓰지 않는다.

판단:

- 현재 비용 원칙에는 static opt-in proxy가 맞다. 돈 쓰는 것은 최후 수단이다.
- rotation은 proxy pool을 유료로 확보한 뒤에 의미가 있다.
- 당장 필요한 것은 rotation 구현이 아니라 `crawl_stats` 기반으로 "어느 source가 proxy/retry 비용을 쓸 가치가 있는지" 판단하는 계측이다.

### 42.4 GitHub source 조사 보강

GitHub는 crawler 대상에 넣을 수 있지만, 게시판형 crawler와 같은 방식으로 넣으면 안 된다.

공식 제약:

- Repository search는 repo 이름/설명/topic/README 중심으로 검색할 수 있고 `in:readme`, `language:`, `topic:`, `created:`, `pushed:` 같은 qualifier를 조합할 수 있다.
- Code search는 default branch만 보고, 384KB보다 큰 파일은 검색 대상이 아니며, source code search에는 검색어가 최소 하나 필요하다.
- Code search endpoint는 인증이 필요하며 분당 제한이 빡빡하다.
- REST API는 unauthenticated 60 req/hour, authenticated 5,000 req/hour 기본 제한이 있고, search endpoint는 더 제한적이다.
- secondary rate limit은 동시성/분당 요청/CPU time 기준으로 걸릴 수 있고, 걸리면 `Retry-After` 또는 reset 시점까지 기다려야 한다.

보안 연구 근거:

- fake-star 연구는 의심 star 캠페인이 phishing/malware repository 홍보에 사용되며, 악성 repo가 짧은 기간 동안 trust signal을 부풀리는 패턴을 보인다고 보고한다.
- YouTube crack/game-cheat malware 연구는 게임 치트/무료 소프트웨어 홍보가 malware 유통 경로로 쓰인다고 보고한다. 이는 GitHub repo, release, 외부 다운로드 링크가 "프로그램 내용 파악"의 1차 단서가 될 수 있음을 뒷받침한다.

설계 결론:

- GitHub는 `SiteConfig`가 아니라 별도 `GitHubSourceAdapter`가 맞다.
- 1단계는 code search가 아니라 repository search + README + release metadata 중심으로 시작한다.
- code search는 비용과 rate limit이 크므로 P2 repo에 한해 후속 detail 단계로 제한한다.
- query는 1,000-result cap을 피하기 위해 기간/언어/topic/game keyword로 slicing한다.
- 결과는 forum 후보와 같은 candidate schema로 합치되 `source_type=github_repo|github_release|github_code`를 둔다.

초기 GitHub query 예:

```text
("lineage" OR "aion" OR "bns" OR "blade and soul") cheat in:readme archived:false
("天堂" OR "永恆" OR "劍靈") 外掛 in:readme archived:false
("ncsoft" OR "lineage") (macro OR bot OR bypass) in:readme pushed:>2025-01-01
```

### 42.5 추가로 발견한 운영 누락 버그: fit markdown만 보고 스킵

코드 재검토 중 운영 pipeline에서 detail probe와 기준이 다른 부분을 발견했다.

기존 운영 pipeline:

```text
if not result.fit_markdown.strip():
    skipped_empty += 1
```

문제:

- `CrawlResult.markdown` property는 `fit_markdown or raw_markdown`을 반환한다.
- serializer/storage는 이미 `result.markdown`을 사용한다.
- detail probe도 `fit_markdown or raw_markdown`으로 validator를 돌린다.
- 그런데 운영 pipeline만 `fit_markdown`이 비면 raw 본문이 있어도 빈 글로 스킵했다.

왜 중요하나:

- Crawl4AI의 fit/pruning 결과는 짧은 글, 링크 중심 글, 포럼 boilerplate 비율이 높은 글에서 비거나 과하게 줄 수 있다.
- 우리가 실제 probe에서 Bahamut 짧은 글도 위험 signal을 담는 사례를 봤기 때문에, raw fallback 없이 스킵하면 수집량과 recall이 줄어든다.

수정:

- 운영 pipeline도 `text = result.markdown` 기준으로 empty/validator/dedup/language/mark_seen을 수행하도록 변경했다.
- `fit_markdown`이 비어도 `raw_markdown`이 있으면 큐 enqueue까지 진행하는 integration test를 추가했다.

검증:

```text
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home .venv/bin/python -m pytest \
  crawler/tests/unit/test_crawl4ai_crawler.py \
  crawler/tests/unit/test_site_config.py \
  crawler/tests/integration/test_crawl_pipeline.py \
  crawler/tests/unit/test_candidate_scoring.py \
  crawler/tests/unit/test_content_validator.py -q

95 passed
```

### 42.6 현재까지의 정합성 판단

우리가 지금 잡은 방향은 웹 조사와 코드 실측 양쪽에서 대체로 맞다.

맞는 부분:

- 제목 키워드는 hard filter가 아니라 priority feature로 둔다.
- listing 후보는 넓게 보존하고, 상세 fetch/LLM 비용은 priority budget으로 제어한다.
- proxy는 코드만으로 해결되는 기능이 아니라 외부 네트워크 자원이며, 현재는 direct + source별 opt-in이 맞다.
- retry는 모든 사이트 기본값이 아니라 문제 source에만 제한적으로 켠다.
- GitHub는 게시판 crawler가 아니라 API metadata adapter로 분리한다.

아직 확인해야 할 부분:

- `max_retries=1`이 Dcard fetch error를 실제로 줄이는지 재실험.
- raw fallback 수정 후 Bahamut/52pojie/Dcard enqueue 수가 얼마나 늘어나는지 dry-run/detail probe 재실험.
- production pipeline에 P2/P3 budget을 넣을지, 먼저 dashboard stats만으로 운영 실측을 볼지 결정.
- `arun_many()`/dispatcher는 성능상 필요하지만 behavior 변화가 크므로 별도 실험 브랜치에서 진행.

## 43. 2026-06-07 재실험 결과: raw fallback + Dcard retry 이후

실행 파일:

```text
output/detail_probe_20260607_030817.jsonl
```

요약:

```text
rows=110

P2 total=48 real=48 real%=100.0 signal=38 signal%=79.2 error=0
P3 total=62 real=52 real%=83.9 signal=30 signal%=48.4 error=2

validator kinds:
real=100 empty=5 unknown=2 fetch_error=2 sticky=1

latency:
median_ms=3725 p95_ms=7894 max_ms=11847
```

source별 핵심:

```text
bahamut_aion2          14/14 real, 12 signal
bahamut_bns            11/11 real,  6 signal
dcard                   9/10 real,  3 signal, 1 error
dcard_online            9/10 real,  4 signal, 1 error
ptt_mobile_game        10/10 real,  4 signal
52pojie                 2/10 real,  5 signal
```

이 결과의 의미:

1. P2는 운영 detail fetch 대상으로 충분히 좋다.
   - P2 48건 중 48건이 real이고 error가 0이다.
   - signal rate도 79.2%라서 비용 대비 효과가 좋다.

2. P3는 버리면 안 되지만 전수 fetch 대상도 아니다.
   - P3 real rate는 83.9%라 나쁘지 않다.
   - signal rate는 48.4%라 P2보다 낮다.
   - 따라서 P3는 source별 stratified sampling 또는 남는 budget으로 처리하는 편이 맞다.

3. Dcard는 아직 Cloudflare 실패가 남는다.
   - dcard/dcard_online 각각 10건 중 1건 fetch error.
   - error message는 Cloudflare JS challenge.
   - `max_retries=1`만으로 완전 해결은 아니지만, 전체적으로는 90% real까지 나온다.
   - 다음 판단에는 실패 케이스의 `crawl_stats`가 필요하다.

4. 52pojie는 source risk만으로 우선순위를 높이면 안 된다.
   - 10건 중 real은 2건뿐이다.
   - 그런데 signal은 5건이라 보안/프로그램 관련 텍스트는 많다.
   - 즉 "불법 프로그램 유통 경로" source로는 가능성이 있지만 NC 게임 탐지 source로는 노이즈가 크다.
   - 운영에서는 52pojie P3 cap을 낮게 두고, GitHub/검색 seed처럼 별도 exploration bucket으로 보는 편이 맞다.

5. raw fallback 수정은 운영 반영 가치가 있다.
   - 이번 재실험에서 P2 real이 100%까지 올라갔다.
   - validator `short`가 사라지고 `empty`가 5건만 남았다.
   - fit markdown만 보던 운영 pipeline을 `result.markdown` 기준으로 바꾼 것은 recall 측면에서 맞다.

추가 계측 보강:

- 성공 result에는 `crawl_stats`가 들어오지만, 실패 result는 `CrawlerException`으로 변환되며 stats가 유실됐다.
- Dcard Cloudflare 판단을 위해 `CrawlerException.crawl_stats`를 추가했다.
- `Crawl4AICrawler.fetch()` 실패 시 Crawl4AI `result.crawl_stats`를 예외에 담는다.
- `detail_priority_probe.py` 실패 row에도 `crawl_stats`를 저장한다.

다음 결론:

- 운영 budget은 `P2 전수 + P3 source별 cap`으로 가는 것이 가장 합리적이다.
- Dcard는 proxy 구매보다 먼저 실패 `crawl_stats`를 축적한다.
- `wait_until="load"`는 selector timeout/SPA hydration/JS challenge 관찰용 보조 실험이지, HTTP 403 자체를 푸는 설정은 아니다.
- 403이 주 원인이면 retry/fallback보다 먼저 source concurrency, group concurrency, delay, 실행 순서, fingerprint 변화를 source별로 실험한다.
- 52pojie는 full crawl 대상이 아니라 낮은 cap의 exploration source로 유지한다.

## 44. 2026-06-07 운영 pipeline priority budget 반영

재실험 결과를 운영 crawler에 반영했다.

### 44.1 구현한 운영 정책

운영 상세 fetch 선택 정책:

```text
P0/P1/P2: board hard limit 안에서 우선 선택
P3: source별 cap만큼 샘플링
```

기본 cap:

```text
CRAWL_P3_52POJIE_CAP_PER_BOARD=1
CRAWL_P3_MIXED_CAP_PER_BOARD=5
CRAWL_P3_DEFAULT_CAP_PER_BOARD=1
CRAWL_PRIORITY_BUDGET_ENABLED=true
```

source 구분:

- 52pojie: real rate가 낮아 P3 cap을 낮게 유지한다.
- mixed source: `dcard`, `dcard_online`, `ptt_mobile_game`은 제목 우회 가능성이 있어 P3 cap을 중간 수준으로 둔다.
- dedicated/source default: Bahamut/Inven/PTT 전용 보드는 P3 cap을 낮게 둔다.

### 44.2 수정한 코드

`crawler/src/scheduler/crawl_scheduler.py`

- `ScoredPostCandidate` 추가.
- `_score_post_candidates()` 추가.
- `_select_detail_candidates()` 추가.
- `_process_board()`에서 listing 후보를 score한 뒤 detail fetch 대상만 선택.
- `PipelineStats`에 priority별 선택 수 추가:

```text
selected_p0
selected_p1
selected_p2
selected_p3
```

`crawler/scripts/dry_run_inventory.py`

- dry-run 완료 출력에 P0/P1/P2/P3 선택 수 표시.

API/dashboard:

- `/api/crawl/stats` 응답에 `selectedP0`, `selectedP1`, `selectedP2`, `selectedP3` 추가.
- dashboard funnel의 `선택` 항목에 `P2 n · P3 n` 표시.

### 44.3 기대 효과

이전 운영 방식:

```text
listing에서 정렬된 상위 N개를 거의 그대로 상세 fetch
```

새 운영 방식:

```text
listing 후보 보존
cheap score 계산
P0/P1/P2는 상세 fetch
P3는 source별 cap으로 탐색
```

효과:

- 제목 hard filter 문제를 피한다.
- P2의 높은 real/signal 효율을 운영에서 우선 활용한다.
- P3를 완전히 버리지 않아 은어/우회 제목 탐색을 유지한다.
- 52pojie 같은 high-noise source가 EC2 시간을 과하게 쓰는 것을 막는다.
- dashboard에서 선택량 감소가 priority budget 때문인지 확인할 수 있다.

### 44.4 검증

실행:

```text
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home .venv/bin/python -m pytest \
  crawler/tests/integration/test_crawl_pipeline.py \
  crawler/tests/unit/test_candidate_scoring.py \
  crawler/tests/unit/test_crawl4ai_crawler.py -q

.venv/bin/python -m py_compile \
  crawler/src/scheduler/crawl_scheduler.py \
  crawler/scripts/dry_run_inventory.py \
  crawler/scripts/detail_priority_probe.py \
  crawler/src/crawl4ai_crawler.py \
  shared/exceptions/base_exception.py

cd api && ./gradlew test
cd dashboard && pnpm lint
cd dashboard && pnpm build
```

결과:

```text
crawler targeted tests: 38 passed
py_compile 통과
api ./gradlew test: BUILD SUCCESSFUL
dashboard pnpm lint: 통과
dashboard pnpm build: 통과
```

### 44.5 다음 실험

이제 dry-run을 다시 실행해 운영 budget이 실제 후보량을 얼마나 줄이는지 확인한다.

```text
cd /Users/jmac/Desktop/261RCOSE45700
CRAWL_DRY_RUN=1 \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/dry_run_inventory.py
```

확인할 값:

- `discovered`: listing에서 발견한 전체 후보 수
- `selected`: 운영 budget으로 상세 fetch 대상이 된 수
- `P0/P1/P2/P3`: 각 priority 선택 수
- 52pojie selected가 과하게 크지 않은지
- Dcard/ptt_mobile_game P3가 완전히 0이 아닌지

## 45. 2026-06-07 운영 budget dry-run 결과

실행:

```text
CRAWL_DRY_RUN=1
CRAWL_DRY_RUN_OUTPUT_DIR=output
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home
.venv/bin/python crawler/scripts/dry_run_inventory.py
```

결과:

```text
boards=41
discovered=2170
selected=148
P0=0
P1=0
P2=48
P3=100
kw_matched=0
kw_unmatched=2170
```

전체 funnel:

```text
2170 discovered -> 148 selected
selection rate = 6.8%
```

source별 주요 결과:

```text
52pojie                 total=782 selected=9   P2=0  P3=782
bahamut_aion2           total=114 selected=18  P2=12 P3=102
bahamut_bns             total=104 selected=15  P2=9  P3=95
bahamut_lineage         total=97  selected=13  P2=7  P3=90
ptt_mobile_game         total=48  selected=15  P2=0  P3=48
dcard_online            total=29  selected=5   P2=0  P3=29
dcard                   total=14  selected=5   P2=0  P3=14
```

판단:

1. 운영 budget이 의도대로 작동한다.
   - 발견 후보 2,170건 중 상세 fetch 대상은 148건이다.
   - EC2 1대에서 매시간 돌릴 수 있는 수준으로 상세 fetch 수를 줄였다.

2. P2 48건이 모두 보존됐다.
   - 직전 detail probe에서 P2는 `48/48 real`, `signal 79.2%`, `error 0`이었다.
   - 따라서 P2 전수 정책은 유지한다.

3. P3는 100건 선택됐다.
   - P3는 버리지 않는다는 목표에는 맞다.
   - 다만 P3가 selected의 67.6%를 차지하므로, 비용이 부담되면 가장 먼저 줄일 대상이다.

4. 52pojie는 잘 제한됐다.
   - 후보 782건 중 9건만 선택됐다.
   - 직전 probe에서 52pojie는 `2/10 real`이었으므로 낮은 cap 유지가 맞다.

5. mixed source 탐색은 유지됐다.
   - `ptt_mobile_game=15`, `dcard=5`, `dcard_online=5`가 선택됐다.
   - 제목 키워드가 0이어도 완전히 버리지 않는 구조가 유지된다.

추정 운영 시간:

- 직전 detail probe median latency는 약 3.7초, p95는 약 7.9초였다.
- 148건을 순차 fetch하면 detail fetch만 대략 9~20분 범위로 볼 수 있다.
- listing + site/board delay까지 합치면 1시간 주기 안에는 들어올 가능성이 높다.

다음 선택지:

1. 현재 cap 유지
   - recall을 조금 더 챙기는 방향.
   - 상세 fetch 148건/회 정도면 아직 감당 가능해 보인다.

2. 비용 우선 cap
   - `CRAWL_P3_DEFAULT_CAP_PER_BOARD=1`
   - `CRAWL_P3_MIXED_CAP_PER_BOARD=3`
   - `CRAWL_P3_52POJIE_CAP_PER_BOARD=2`
   - P3를 줄여 detail fetch 수를 더 낮춘다.

현재 판단:

- 아직은 현재 cap을 유지하고 실제 운영 dry-run/detail fetch를 한 번 더 보는 편이 좋다.
- 다음 단계는 `CRAWL_DRY_RUN=0`이 아니라, production 저장/Redis 없이 selected 148건을 detail probe로 재현하는 것이다.
- 그 다음 P3 signal rate가 여전히 40~50% 수준이면 현재 cap 유지, 낮으면 P3 cap을 낮춘다.

## 46. 2026-06-07 detail probe 명령 수정: selected-only 필요

운영 dry-run 결과의 selected 후보만 상세 probe하려고 다음처럼 source별 cap을 크게 주면 안 된다.

```text
DETAIL_PROBE_52POJIE_P3=9
DETAIL_PROBE_MIXED_P3=15
DETAIL_PROBE_OTHER_P3=60
```

이 값들은 "전체 P3 총량"이 아니라 "source별 P3 cap"이다.
따라서 여러 source에 곱해져 probe 계획이 755건까지 커질 수 있다.

수정:

- `detail_priority_probe.py`에 `DETAIL_PROBE_SELECTED_ONLY=1` 추가.
- 이 옵션이 켜지면 dry-run JSONL의 `selected=true` 후보만 detail probe한다.
- URL dedupe 후 실제 probe 대상은 133건이다.
  - dry-run `selected=148`은 board별 선택 합계다.
  - 같은 URL이 여러 board/page에서 선택될 수 있으므로 detail probe에서는 중복 URL을 제거한다.

수정된 명령:

```text
cd /Users/jmac/Desktop/261RCOSE45700
DETAIL_PROBE_SELECTED_ONLY=1 \
DETAIL_PROBE_INPUT=output/dry_run_20260607_115149.jsonl \
DETAIL_PROBE_DELAY_SECONDS=1 \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

예상:

```text
unique selected candidates = 133
P2=48
P3=85
```

판단:

- 기존 755건 실행은 중단해도 된다.
- selected-only 133건 probe가 운영 budget 검증에 맞는 실험이다.

## 47. 2026-06-07 755건 P3 대량 probe 결과와 cap 조정

실수로 source별 P3 cap을 크게 설정해 755건 detail probe가 실행됐다.
원래 의도한 selected-only 실험은 아니지만, P3 전체 품질을 넓게 보는 데이터로는 유용했다.

결과:

```text
rows=755

P2 total=48  real=48  real%=100.0 signal=38  signal%=79.2 error=0
P3 total=707 real=666 real%=94.2  signal=194 signal%=27.4 error=3

latency:
median_ms=4024
p95_ms=5976
max_ms=11784
```

source별 주요 P3 signal:

```text
dcard             14 total, 10 signal, 71.4%
dcard_online      15 total,  6 signal, 40.0%, error=3
52pojie            9 total,  5 signal, 55.6%, real=2
bahamut_aion2     72 total, 32 signal, 44.4%
ptt_mobile_game   15 total,  5 signal, 33.3%
inven_maple       62 total,  6 signal,  9.7%
```

판단:

1. P2는 계속 전수 유지한다.
   - 48/48 real, signal 79.2%, error 0.

2. P3는 real rate는 높지만 signal rate가 낮다.
   - P3 전체 signal 27.4%.
   - P3를 많이 가져오면 "진짜 글"은 많지만 불법 프로그램 탐지 signal은 희석된다.

3. mixed source는 유지 가치가 있다.
   - Dcard는 signal 71.4%.
   - Dcard online은 error가 있지만 signal 40%.
   - PTT Mobile-game도 signal 33.3%.

4. default dedicated/source P3는 줄여도 된다.
   - Inven/Bahamut 일부 source는 real은 높지만 P3 signal이 낮다.
   - P2가 이미 고신호 글을 잡고 있으므로 P3 default cap은 낮추는 것이 맞다.

조정:

```text
CRAWL_P3_DEFAULT_CAP_PER_BOARD: 2 -> 1
CRAWL_P3_52POJIE_CAP_PER_BOARD: 3 -> 2
CRAWL_P3_MIXED_CAP_PER_BOARD: 5 유지
```

같은 `dry_run_20260607_115149.jsonl`에 새 cap을 재계산한 결과:

```text
selected=112
P2=48
P3=64
```

source별 새 선택량:

```text
bahamut_aion2          selected=15 p2=12 p3=3
ptt_mobile_game        selected=15 p2=0  p3=15
bahamut_bns            selected=12 p2=9  p3=3
bahamut_lineage        selected=10 p2=7  p3=3
bahamut_aion           selected=9  p2=6  p3=3
52pojie                selected=6  p2=0  p3=6
dcard                  selected=5  p2=0  p3=5
dcard_online           selected=5  p2=0  p3=5
```

효과:

- 기존 selected 148건에서 112건으로 감소.
- P2 48건은 그대로 보존.
- P3는 100건에서 64건으로 감소.
- mixed source 탐색은 유지.

현재 결론:

- 운영 기본값은 보수 cap으로 간다.
- 필요하면 env로 P3 cap을 다시 늘릴 수 있다.
- 다음 selected-only detail probe는 112건 기준으로 다시 실행하면 된다.

## 48. 2026-06-07 웹 문서 기준 코드 재검증

질문:

현재 코드가 최신 문서 기준으로 제대로 작성됐는가?

### 48.1 확인한 공식 문서

확인한 문서:

- Crawl4AI AsyncWebCrawler: https://docs.crawl4ai.com/api/async-webcrawler/
- Crawl4AI Proxy & Security: https://docs.crawl4ai.com/advanced/proxy-security/
- Crawl4AI Anti-Bot & Fallback: https://docs.crawl4ai.com/advanced/anti-bot-and-fallback/
- Crawl4AI arun_many: https://docs.crawl4ai.com/api/arun_many/
- Crawl4AI Multi-URL Crawling: https://docs.crawl4ai.com/advanced/multi-url-crawling/
- GitHub REST Search: https://docs.github.com/en/rest/search/search
- GitHub REST rate limits: https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api

### 48.2 Crawl4AI 설정 위치 검증

공식 문서 기준:

- `BrowserConfig`: browser 환경, headless, stealth, user agent 등 global browser setting.
- `CrawlerRunConfig`: per-crawl logic, caching, selector, wait, proxy, retry 등.
- proxy는 legacy `BrowserConfig.proxy_config`가 아니라 `CrawlerRunConfig.proxy_config`가 권장된다.

현재 코드:

```text
BrowserConfig:
- headless
- enable_stealth
- headers
- user_agent_mode

CrawlerRunConfig:
- cache_mode
- wait_for
- css_selector
- page_timeout
- js_code
- delay_before_return_html
- proxy_config
- max_retries
```

판단:

- 맞다.
- 이전 문서 일부에 남아 있던 `BrowserConfig.proxy_config` 표현은 최신 문서 기준으로 수정했다.

### 48.3 anti-bot / retry / crawl_stats 검증

공식 문서 기준:

- anti-bot retry 옵션은 `CrawlerRunConfig`에 둔다.
- `proxy_config`, `max_retries`, `fallback_fetch_function`이 핵심이다.
- 실패/성공 결과에는 `crawl_stats`가 포함된다.
- worst-case attempt는 `(1 + max_retries) x len(proxy_config)`다.
- `wait_until="load"`는 SPA 렌더링 지연이나 JS challenge 관찰에는 도움이 될 수 있지만, 서버가 이미 HTTP 403을 반환한 경우에는 본질적 해결책이 아니다.

현재 코드:

- `SiteConfig.max_retries` -> `CrawlOptions.max_retries` -> `CrawlerRunConfig(max_retries=...)`로 전달.
- `CrawlResult.crawl_stats` 저장.
- 실패 시 `CrawlerException.crawl_stats`로 보존.
- `detail_priority_probe.py` 실패 row에도 `crawl_stats` 저장.

판단:

- 맞다.
- Dcard Cloudflare 실패 분석을 위해 `crawl_stats`를 남기는 방향도 문서와 맞다.
- 아직 `fallback_fetch_function`은 구현하지 않았다. 비용/외부 서비스 의존이 생기므로 지금 단계에서는 보류가 맞다.

### 48.4 multi-URL / dispatcher 검증

공식 문서 기준:

- 여러 URL을 크롤링할 때는 `arun_many()`와 dispatcher가 더 효율적이다.
- `MemoryAdaptiveDispatcher`, `RateLimiter`는 concurrency, memory, rate limit을 관리한다.
- `arun()` loop는 단순하지만 많은 URL에서는 느릴 수 있다.

현재 코드:

- listing/detail fetch 모두 아직 순차 `arun()` 중심이다.
- 대신 priority budget으로 detail fetch 수를 줄였다.

판단:

- 기능적으로 틀린 코드는 아니다.
- 다만 성능 최적화 관점에서는 다음 리팩토링 후보가 맞다.
- EC2 1대 환경에서는 무작정 concurrency를 올리기보다, 현재처럼 먼저 후보 수를 줄이고 이후 `arun_many()`를 concurrency 2~3부터 실험하는 순서가 안전하다.

### 48.5 priority budget 검증

웹 문서가 직접 "P2/P3" 같은 도메인 정책을 제공하지는 않는다.
하지만 Crawl4AI Multi-URL 문서와 일반 crawler scheduling 관점에서, 많은 후보를 전부 상세 fetch하지 않고 priority를 둬서 제한하는 구조는 타당하다.

현재 코드:

```text
P0/P1/P2: board hard limit 안에서 우선 선택
P3: source별 cap
```

기본 cap:

```text
52pojie P3: 2 / board
mixed source P3: 5 / board
default P3: 1 / board
MAX_POSTS_PER_BOARD: 30
```

판단:

- 현재 실험 데이터 기준으로 맞다.
- 단, 문서/대화에서 말한 "P2 전수"는 정확히는 `MAX_POSTS_PER_BOARD` 안전 limit 안에서 우선 선택이다.
- 현재 dry-run에서는 P2가 48건이고 board별 P2가 limit을 넘지 않으므로 실질적으로 모두 보존된다.
- 나중에 P2가 board당 30건을 넘는 source가 생기면 `MAX_POSTS_PER_BOARD`를 올리거나 P2 별도 hard limit을 둬야 한다.

### 48.6 detail probe selected-only 검증

문제:

- 기존 `DETAIL_PROBE_OTHER_P3=60`은 전체 cap이 아니라 source별 cap이라 755건 probe가 됐다.

수정:

- `DETAIL_PROBE_SELECTED_ONLY=1` 추가.
- dry-run JSONL의 `selected=true` 후보만 probe한다.

판단:

- 맞다.
- 운영 budget 검증에는 source별 cap 재지정보다 selected-only가 더 정확하다.

### 48.7 GitHub adapter 관련 검증

GitHub 공식 문서 기준:

- Search API는 query당 최대 1,000 results.
- Search endpoint rate limit은 일반 REST보다 제한적이다.
- 인증 요청은 검색 endpoint 대부분 30 req/min, code search는 인증 필요 및 더 낮은 제한.
- REST API authenticated primary limit은 일반적으로 5,000 req/hour.
- secondary rate limit은 concurrent request, endpoint/minute, CPU time 등으로 걸릴 수 있다.

판단:

- GitHub를 게시판 crawler에 붙이지 않고 별도 adapter로 설계한 판단은 맞다.
- repository search + README + release metadata부터 시작하고, code search는 제한적으로 쓰는 판단도 맞다.

### 48.8 최종 판단

현재 코드 방향은 최신 문서 기준으로 대체로 맞다.

맞는 부분:

- proxy/retry를 `CrawlerRunConfig`로 이동.
- `crawl_stats` 보존.
- raw markdown fallback.
- hard title filter 제거.
- priority budget 도입.
- selected-only probe 옵션 추가.

남은 개선:

- `AsyncWebCrawler` 재사용.
- `arun_many()` + `MemoryAdaptiveDispatcher`/`RateLimiter` 실험.
- Dcard에 `wait_until="load"`를 source별로 실험하되, 목적은 403 해결이 아니라 timeout/렌더링/JS challenge 구분이다.
- P2가 board hard limit을 넘는 경우를 위한 별도 safety policy.

## 49. 2026-06-07 보수 cap 적용 후 dry-run 결과

보수 cap 적용 후 dry-run을 다시 실행했다.

실행 결과:

```text
boards=41
discovered=2173
selected=112
P0=0
P1=0
P2=48
P3=64
kw_matched=0
kw_unmatched=2173
```

source별 주요 결과:

```text
52pojie                 total=782 selected=6  P2=0  P3=782
bahamut_aion2           total=114 selected=15 P2=12 P3=102
bahamut_bns             total=105 selected=12 P2=9  P3=96
bahamut_lineage         total=99  selected=10 P2=7  P3=92
ptt_mobile_game         total=48  selected=15 P2=0  P3=48
dcard_online            total=29  selected=5  P2=0  P3=29
dcard                   total=16  selected=5  P2=0  P3=16
```

판단:

- 보수 cap이 의도대로 적용됐다.
- P2 48건은 유지됐다.
- P3는 100건에서 64건 수준으로 줄었다.
- 52pojie는 9건에서 6건으로 줄었다.
- mixed source는 여전히 탐색 후보를 유지한다.

다음 실행:

```text
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl
DETAIL_PROBE_DELAY_SECONDS=1
CRAWL_DRY_RUN_OUTPUT_DIR=output
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

예상:

- dry-run selected 합계는 112건.
- URL 중복 제거 후 detail probe 대상은 이보다 같거나 작다.

## 50. 2026-06-07 selected-only 103건 detail probe 결과

보수 cap dry-run 파일:

```text
output/dry_run_20260607_133835.jsonl
```

selected-only detail probe 결과:

```text
rows=103

P2 total=48 real=48 real%=100.0 signal=38 signal%=79.2 error=0
P3 total=55 real=52 real%=94.5  signal=30 signal%=54.5 error=0

selected_budget total=103 real=100 real%=97.1 signal=68 signal%=66.0 error=0

latency:
median_ms=3700
p95_ms=7445
max_ms=12329
```

source별 주요 결과:

```text
bahamut_aion2          15/15 real, 12 signal
ptt_mobile_game        15/15 real,  5 signal
bahamut_bns            12/12 real,  8 signal
bahamut_lineage        10/10 real,  9 signal
dcard                   5/5  real,  4 signal
dcard_online            5/5  real,  2 signal
52pojie                 0/2  real,  2 signal
```

판단:

1. 보수 cap은 성공이다.
   - 103건 중 100건 real.
   - error 0.
   - signal 66%.

2. P2는 계속 유지한다.
   - 48/48 real.
   - signal 79.2%.

3. P3도 현재 selected 범위에서는 가치가 있다.
   - P3 signal 54.5%.
   - 대량 P3 probe의 27.4%보다 훨씬 좋다.
   - cap으로 선별했을 때 P3 품질이 올라간다.

4. Dcard는 이번 selected-only에서 성공했다.
   - dcard/dcard_online 모두 5/5 real.
   - error 0.
   - Dcard 한 건은 anti-bot retry 후 성공했다.

5. 52pojie는 더 낮춘다.
   - 2건 모두 signal은 있었지만 real은 0건.
   - 운영 기본 cap을 2에서 1로 더 낮춘다.
   - 완전히 끄지는 않는다. exploration source로 최소 샘플은 유지한다.

조정:

```text
CRAWL_P3_52POJIE_CAP_PER_BOARD: 2 -> 1
```

현재 최종 기본 cap:

```text
CRAWL_P3_52POJIE_CAP_PER_BOARD=1
CRAWL_P3_MIXED_CAP_PER_BOARD=5
CRAWL_P3_DEFAULT_CAP_PER_BOARD=1
```

현재 결론:

- 이 cap 조합은 운영 테스트로 넘겨도 된다.
- 다음 단계는 `CRAWL_DRY_RUN=0` 실제 pipeline smoke다.
- 단, Redis/queue까지 연결되므로 로컬 Redis 또는 운영 환경에서 실행해야 한다.

## 51. 성능 리팩토링 1차: 상세 fetch bounded concurrency

문제:

- selected-only detail probe 기준 median 3.7s, p95 7.4s 수준이었다.
- 상세 페이지를 100건 이상 순차 fetch하면 1시간 단위로 늘어난다.
- 단순히 전체 `_process_post()`를 병렬화하면 본문 dedup과 queue enqueue 순서가 깨질 수 있다.
  - 같은 본문 2개가 동시에 `is_duplicate=False`를 통과할 수 있다.
  - 그러면 동일 글이 중복 enqueue될 위험이 있다.

반영한 구조:

1. URL dedup 선검사
   - 이미 본 URL은 fetch 전에 skip.
   - `attempted`도 증가시키지 않는다.

2. 상세 fetch만 병렬화
   - `CRAWL_DETAIL_FETCH_CONCURRENCY` 기본값 3.
   - `CRAWL_DETAIL_FETCH_STAGGER_SECONDS` 기본값 0.25초.
   - EC2 1대 환경과 anti-bot 실패 가능성을 고려해 보수적으로 시작한다.

3. 후처리는 순차 유지
   - empty/sticky/blocked validator
   - 본문 dedup
   - storage save
   - Redis enqueue
   - dedup mark_seen

즉, 느린 네트워크/브라우저 fetch 구간만 겹치고, 데이터 정합성에 민감한 단계는 기존 순서를 유지한다.

환경변수:

```text
CRAWL_DETAIL_FETCH_CONCURRENCY=3
CRAWL_DETAIL_FETCH_STAGGER_SECONDS=0.25
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_DELAY_SECONDS=2
```

로컬 실험 추천값:

```text
# 가장 보수적. 기존 순차 동작과 거의 동일.
CRAWL_DETAIL_FETCH_CONCURRENCY=1

# 현재 기본. EC2 1대에서 먼저 볼 값.
CRAWL_DETAIL_FETCH_CONCURRENCY=3

# 성능 확인용. anti-bot/error/메모리 증가 여부를 반드시 같이 봐야 함.
CRAWL_DETAIL_FETCH_CONCURRENCY=5
```

검증:

```text
26 passed
92 passed
177 passed
180 passed
```

추가한 테스트:

- 상세 fetch가 설정한 concurrency 이상으로 동시에 돌지 않는지 확인.
- fetch는 병렬이어도 동일 본문 dedup이 순차 적용되어 중복 enqueue가 막히는지 확인.

detail probe도 같은 방향으로 수정:

- `detail_priority_probe.py`에 bounded worker concurrency를 추가했다.
- `DETAIL_PROBE_CONCURRENCY` 기본값은 `CRAWL_DETAIL_FETCH_CONCURRENCY` 또는 3.
- `DETAIL_PROBE_DELAY_SECONDS`는 worker별 다음 요청 전 휴식으로 적용한다.
- 따라서 기존처럼 100건 이상을 완전 순차로 기다리지 않아도 된다.

남은 성능 개선:

1. source별 concurrency
   - Dcard/52pojie처럼 anti-bot 영향이 큰 소스는 1~2.
   - Bahamut/Inven/PTT처럼 안정적인 소스는 3~5.
   - 지금은 전역 환경변수 하나로 시작한다.

2. 실제 네트워크 benchmark
   - Redis 없이 `detail_priority_probe.py` selected-only로 concurrency 1/3/5를 비교한다.
   - 운영 pipeline 전체 smoke는 Redis/queue가 필요하다.

## 52. 성능 리팩토링 2차: Crawl4AI arun_many/dispatcher 적용

추가 웹 조사:

- Crawl4AI 공식 `AsyncWebCrawler` 문서는 `arun_many(urls, config=...)`가 여러 URL 동시 크롤링을 처리한다고 설명한다.
- Crawl4AI 공식 `arun_many()` 문서는 dispatcher를 통해 concurrency를 제어하고, stream 모드로 완료되는 결과부터 처리할 수 있다고 설명한다.
- Crawl4AI 공식 multi-URL 문서는 기본 반복 `arun()`보다 `arun_many()`가 효율적이고, `MemoryAdaptiveDispatcher`와 `RateLimiter`로 메모리/속도 제어를 붙이는 방식을 권장한다.
- Crawl4AI 공식 parameter 문서는 `mean_delay`, `max_range`가 `arun_many()` 호출 간 random delay에 쓰이고, proxy는 `CrawlerRunConfig.proxy_config`에 넣는 구조가 맞다고 설명한다.

로컬 설치 버전 확인:

```text
AsyncWebCrawler.arun_many(
  urls: List[str],
  config: CrawlerRunConfig | List[CrawlerRunConfig] | None = None,
  dispatcher: BaseDispatcher | None = None,
  **kwargs
)

MemoryAdaptiveDispatcher(
  memory_threshold_percent=90.0,
  max_session_permit=20,
  rate_limiter=None,
  ...
)

RateLimiter(
  base_delay=(1.0, 3.0),
  max_delay=60.0,
  max_retries=3,
  ...
)
```

반영:

1. `Crawl4AICrawler.fetch_many()` 추가.
   - 같은 site/board 옵션을 공유하는 URL batch를 한 번의 `AsyncWebCrawler` context에서 처리한다.
   - 내부적으로 `AsyncWebCrawler.arun_many()`를 사용한다.
   - `MemoryAdaptiveDispatcher(max_session_permit=concurrency)`를 붙였다.
   - `RateLimiter(base_delay=...)`를 붙였다.

2. pipeline 상세 fetch 경로 변경.
   - 실제 `Crawl4AICrawler`처럼 `fetch_many()`가 있으면 batch 경로를 사용한다.
   - mock/구형 래퍼처럼 `fetch_many()`가 없으면 기존 bounded `fetch()` fallback을 사용한다.
   - URL dedup은 fetch 전 선검사.
   - 본문 dedup/storage/queue enqueue는 여전히 순차 처리.

3. per-url error 보존.
   - batch 중 일부 URL이 실패해도 전체 batch를 버리지 않는다.
   - 실패 URL은 `PostFetchOutcome.error`로 전달되어 기존 `stats.failed` 경로를 탄다.

probe에 바로 `arun_many()`를 붙이지 않은 이유:

- `detail_priority_probe.py`의 selected 후보는 여러 site가 섞인다.
- site별 cookies/proxy/wait/page_timeout이 다르기 때문에 하나의 `CrawlerRunConfig`로 묶으면 설정이 섞일 수 있다.
- 따라서 probe는 현재 worker concurrency를 유지한다.
- 다음 개선은 site별로 group을 나눈 뒤 group 내부에서 `fetch_many()`를 쓰는 방식이다.

추가 테스트:

- `fetch_many()`가 `arun_many()`와 dispatcher를 호출하는지 확인.
- batch 내 실패 결과가 per-url error로 남는지 확인.
- pipeline이 `fetch_many()`를 사용할 수 있을 때 실제 batch 경로를 타는지 확인.
- batch fetch 이후에도 본문 dedup이 순차 적용되어 중복 enqueue가 막히는지 확인.

검증:

```text
crawler/tests: 180 passed
git diff --check: passed
```

## 53. 성능 리팩토링 추가 감사: 항목별 조사와 판단

이번에 추가로 본 공식 문서:

- Crawl4AI `arun_many()`
  - `stream=True`를 켜면 결과를 완료되는 즉시 처리할 수 있다.
  - dispatcher는 concurrency/rate limit/memory throttling을 담당한다.
- Crawl4AI multi-URL crawling
  - 기본 `arun()` 반복보다 `arun_many()`가 효율적이다.
  - `MemoryAdaptiveDispatcher`는 제한된 리소스에서 유리하다.
  - `SemaphoreDispatcher`는 단순 고정 concurrency가 필요할 때 적합하다.
- Crawl4AI session management
  - `session_id`는 같은 tab/page 상태를 재사용하는 sequential workflow에 유리하다.
  - parallel workload에는 적합하지 않다고 문서가 설명한다.
- Crawl4AI cache modes
  - 최신 구조는 `CacheMode` enum을 쓴다.
  - `CacheMode.BYPASS`는 매번 새로 가져오는 모드다.

항목별 판단:

| 항목 | 조사 결과 | 우리 판단 | 반영 |
| --- | --- | --- | --- |
| `arun_many()` | 공식 권장. 다중 URL concurrency에 적합 | 상세 fetch batch에 적합 | 반영 |
| `MemoryAdaptiveDispatcher` | 메모리 기반 throttling | EC2 1대 환경에 적합 | 반영 |
| `RateLimiter` | 요청 pacing/backoff | anti-bot/error 증가 억제에 필요 | 반영 |
| `stream=True` | 완료된 결과부터 처리 가능 | batch 결과 대기 시간 감소 | 반영 |
| probe site별 batch | URL별 site 옵션이 다름 | site별 그룹으로 묶으면 안전 | 반영 |
| HTTP-only crawler | 브라우저보다 빠름 | JS/anti-bot/SPA 사이트 본문 누락 위험 | 보류 |
| session reuse | sequential multi-step에 유리 | parallel detail fetch와 맞지 않음 | 보류 |
| cache read | 재방문 속도 향상 | 유통 모니터링 최신성 저하 가능 | 보류 |
| source별 concurrency | 사이트별 차단/안정성 차이 반영 가능 | 다음 실측 후 적용 | 후보 |

추가 반영:

1. `fetch_many()` 기본 streaming
   - `CrawlerRunConfig(stream=True)`를 batch fetch 기본값으로 사용한다.
   - `arun_many()`가 async generator를 반환하면 async iteration으로 수집한다.
   - list/container를 반환해도 처리 가능하게 fallback을 둔다.

2. 결과 URL 매핑 보강
   - streaming에서는 완료 순서가 입력 순서와 다를 수 있다.
   - `result.url`이 원 URL과 맞으면 URL로 매핑한다.
   - URL이 없거나 redirect로 매칭되지 않으면 남은 결과를 순서대로 fallback한다.

3. `detail_priority_probe.py` site별 batch
   - 여러 site 후보를 하나의 `CrawlerRunConfig`로 섞지 않는다.
   - site별로 group을 만들고 group 내부에서 `fetch_many()`를 사용한다.
   - `DETAIL_PROBE_BATCH_BY_SITE=false`로 기존 worker 방식 fallback 가능.

환경변수:

```text
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_DELAY_SECONDS=2
```

현재 추천 실험:

```text
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
```

비교 실험:

```text
# 순차 baseline
DETAIL_PROBE_CONCURRENCY=1

# 기본 추천
DETAIL_PROBE_CONCURRENCY=3

# 공격적 실험. error/anti-bot/메모리 증가를 반드시 같이 봐야 함.
DETAIL_PROBE_CONCURRENCY=5
```

검증:

```text
39 passed
```

## 54. 2026-06-07 site별 batch probe 결과와 source별 concurrency 조정

실험:

```text
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
```

요약:

```text
P2 total=48 real=48 signal=38 error=0
P3 total=55 real=44 signal=25 error=8
```

source별 핵심:

```text
bahamut_aion2             15 total / 15 real / 0 error
ptt_mobile_game           15 total / 15 real / 0 error
bahamut_bns               12 total / 12 real / 0 error
bahamut_lineage           10 total / 10 real / 0 error
inven_lineage_classic      4 total /  4 real / 0 error
inven_maple                3 total /  3 real / 0 error
dcard                      5 total /  1 real / 4 error
dcard_online               5 total /  1 real / 4 error
```

판단:

1. Bahamut/PTT/Inven 계열은 `concurrency=3` batch가 안정적이다.
   - 대부분 0 error.
   - fetch 시간도 site batch로 줄어든다.

2. Dcard 계열은 `concurrency=3` batch가 손실을 만든다.
   - Dcard 5건 중 4건 blocked.
   - Dcard online 5건 중 4건 blocked.
   - 이전 selected-only 순차/낮은 동시성 실험에서는 Dcard가 5/5 real이었던 점과 대비된다.

3. source별 concurrency가 필요하다는 가설이 확인됐다.
   - 전역 concurrency 하나로는 안정 source와 anti-bot source를 같이 최적화할 수 없다.

반영:

```text
CRAWL_DETAIL_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
```

동작:

- production pipeline
  - `dcard`, `dcard_online`, `52pojie`는 상세 fetch를 순차 처리한다.
  - 그 외 source는 기본 `CRAWL_DETAIL_FETCH_CONCURRENCY=3` batch를 유지한다.

- detail probe
  - `DETAIL_PROBE_BATCH_BY_SITE=true` 상태에서도 Dcard 계열은 batch `fetch_many()`를 타지 않는다.
  - `_probe_one()` 순차 경로로 간다.

추가 환경변수:

```text
# 운영/detail pipeline source별 상세 fetch concurrency
CRAWL_DETAIL_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1

# probe에서만 source별 값을 덮어쓰고 싶을 때
DETAIL_PROBE_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
```

다음 실험:

```text
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
```

기대:

- Bahamut/PTT/Inven은 batch 성능 유지.
- Dcard/Dcard online은 error가 8건에서 크게 줄어야 한다.

검증:

```text
25 passed
```

## 55. source별 concurrency 재실험 결과: 품질 회복 확인

재실험:

```text
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_DELAY_SECONDS=2
```

출력 파일:

```text
output/detail_probe_20260607_142222.jsonl
```

요약:

```text
rows=103

P2 total=48 real=48 real%=100.0 signal=38 signal%=79.2 error=0
P3 total=55 real=52 real%=94.5  signal=30 signal%=54.5 error=0

selected_budget total=103 real=100 real%=97.1 signal=68 signal%=66.0 error=0
```

source별 핵심:

```text
bahamut_aion2          15/15 real, 12 signal, 0 error
ptt_mobile_game        15/15 real,  5 signal, 0 error
bahamut_bns            12/12 real,  8 signal, 0 error
bahamut_lineage        10/10 real,  9 signal, 0 error
dcard                   5/5  real,  4 signal, 0 error
dcard_online            5/5  real,  2 signal, 0 error
52pojie                 0/2  real,  2 signal, 0 error
```

검증된 점:

1. source별 concurrency 조정은 맞았다.
   - 직전 실험에서 Dcard/Dcard online은 각 5건 중 4건이 blocked였다.
   - 이번에는 둘 다 5/5 real, 0 error로 회복했다.

2. 안정 source의 batch 성능은 유지됐다.
   - Bahamut/PTT/Inven 계열은 대부분 100% real, 0 error.

3. 전체 품질은 conservative cap 실험 수준으로 회복됐다.
   - 103건 중 100건 real.
   - error 0.
   - signal 66%.

4. latency는 증가했다.
   - median 19.8s.
   - p95 34.0s.
   - Dcard/52pojie를 순차 처리하고 site별 batch를 순서대로 실행하기 때문이다.
   - 하지만 anti-bot 손실을 줄이는 것이 우선이라 현재 교환은 합리적이다.

현재 최종 추천값:

```text
CRAWL_DETAIL_FETCH_CONCURRENCY=3
CRAWL_DETAIL_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1

DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
```

다음 성능 후보:

- site group 자체를 일부 병렬로 돌릴지 검토한다.
- 단, Dcard group은 계속 독립 순차로 유지해야 한다.
- Bahamut 계열끼리만 group-level concurrency 2 정도를 실험할 수 있다.

## 56. probe site group 병렬화 실험 모드 추가

목표:

- source 내부 concurrency는 이미 조정했다.
- 하지만 probe는 site group을 순서대로 실행하기 때문에 wall-clock 시간이 남아 있다.
- 안정 source group만 일부 병렬로 돌리고, Dcard/52pojie는 계속 순차로 유지한다.

반영:

```text
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1
```

기본값은 1이다.

- 기본값에서는 기존과 동일하게 site group을 순서대로 돈다.
- 실험할 때만 2 이상으로 올린다.
- Dcard/Dcard online/52pojie는 group-level 병렬 대상에서도 제외한다.

실험 명령:

```text
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=2
```

예상:

- Bahamut/Inven/PTT group 일부가 동시에 돈다.
- Dcard/Dcard online/52pojie는 계속 순차 처리된다.
- wall-clock 시간은 줄 수 있지만, 전체 브라우저 세션 수가 늘기 때문에 Mac/EC2 메모리와 anti-bot error를 같이 봐야 한다.

중단 기준:

- Dcard/Dcard online error가 다시 증가하면 group 병렬화를 끈다.
- Bahamut/PTT에서 error가 생기면 group concurrency를 1로 되돌린다.
- Mac/EC2 메모리 압박이 보이면 group concurrency를 1로 되돌린다.

검증:

```text
6 passed
```

## 57. site group concurrency=2 실험 결과: 보류

실험:

```text
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=2
DETAIL_PROBE_DELAY_SECONDS=2
```

출력 파일:

```text
output/detail_probe_20260607_143040.jsonl
```

요약:

```text
rows=103

P2 total=48 real=48 real%=100.0 signal=38 signal%=79.2 error=0
P3 total=55 real=50 real%=90.9  signal=29 signal%=52.7 error=2

selected_budget total=103 real=98 real%=95.1 signal=67 signal%=65.0 error=2
```

source별 핵심:

```text
dcard         5/5 real, 4 signal, 0 error
dcard_online 3/5 real, 1 signal, 2 error
```

비교:

```text
group_concurrency=1:
selected_budget 103 total / 100 real / 68 signal / 0 error

group_concurrency=2:
selected_budget 103 total /  98 real / 67 signal / 2 error
```

판단:

1. group concurrency 2는 wall-clock을 줄일 수는 있다.
2. 하지만 Dcard online에서 다시 anti-bot error가 발생했다.
   - HTTP 403 HTML.
   - Cloudflare JS challenge.
3. Dcard online group 자체는 concurrency 1이었지만, 앞선 안정 source group들이 병렬로 많이 돈 직후라 IP/브라우저 fingerprint 누적 영향 가능성이 있다.
4. 현재 목표는 속도보다 탐지 누락 최소화다.

결론:

- `DETAIL_PROBE_SITE_GROUP_CONCURRENCY=2`는 보류한다.
- 기본/추천값은 계속 1이다.
- 실험 플래그로는 남겨두되, 운영 판단에는 쓰지 않는다.

현재 추천:

```text
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
```

다음에 정말 더 줄이고 싶다면:

- Dcard/Dcard online을 먼저 또는 별도 프로세스로 먼저 처리하고,
- 그 뒤 안정 source group만 병렬 처리하는 2-phase 실행을 실험한다.
- 현재 구현처럼 안정 group 전체를 먼저 병렬 처리하고 Dcard를 마지막에 두는 방식은 Dcard online에 불리할 수 있다.

후속 수정:

```text
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true
```

- 기본값을 true로 추가했다.
- Dcard/Dcard online/52pojie를 먼저 순차 처리한다.
- 이후 Bahamut/PTT/Inven 같은 안정 source만 group-level concurrency 대상이 된다.

다음 재실험:

```text
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=2
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true
```

성공 기준:

- Dcard/Dcard online error 0.
- 전체 error 0.
- wall-clock이 group_concurrency=1보다 줄어야 한다.

## 58. Cloudflare 차단 여부 추가 조사와 로그 매칭

웹 조사:

- Cloudflare JavaScript Detections는 HTML page view 응답에 JS snippet을 주입하고, 브라우저가 이를 실행하면 `cf_clearance` 쿠키에 결과를 저장한다.
- Cloudflare 문서는 Bot Management/Managed Challenge가 client-side JavaScript signals, network-side signals, ML, fingerprint 등을 조합한다고 설명한다.
- Cloudflare rate limiting 문서는 같은 IP/source에서 짧은 시간에 많은 요청이 반복되면 제한 또는 challenge가 발생할 수 있다고 설명한다.
- Cloudflare WAF/rate-limit 문서는 403 응답과 Managed Challenge가 rate limiting/custom WAF rule 판단에 사용될 수 있음을 설명한다.

우리 로그와 매칭:

```text
fetch error reasons
cloudflare_or_waf_403_html  1
cloudflare_js_challenge     1

fetch error reasons by site
dcard_online cloudflare_or_waf_403_html=1 cloudflare_js_challenge=1
```

판단:

1. `dcard_online` 실패는 Cloudflare/anti-bot 계열이 맞다.
   - 로그에 `Cloudflare JS challenge`가 직접 등장한다.
   - 다른 실패는 `HTTP 403 with HTML content`로, Cloudflare/WAF challenge HTML일 가능성이 높다.

2. 단순 detail URL 문제는 아니다.
   - 같은 후보군을 `group_concurrency=1`로 돌렸을 때는 dcard/dcard_online 모두 5/5 real, error 0이었다.
   - `group_concurrency=2`에서만 dcard_online 2건이 실패했다.

3. Dcard group 자체를 순차 처리해도, 직전/동시 전체 traffic pattern이 영향을 줄 수 있다.
   - Cloudflare는 요청 빈도, client-side JS 결과, browser/network fingerprint, ML score 등을 조합한다.
   - 따라서 Dcard만 순차라고 충분하지 않을 수 있다.

코드 보강:

- `detail_probe_summary.py`에 fetch error reason breakdown을 추가했다.
- 이제 Cloudflare JS challenge / 403 HTML / timeout 등을 요약에서 분리해서 볼 수 있다.

현재 추천:

```text
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
```

group concurrency를 다시 실험하려면:

```text
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=2
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true
```

단, 성공 기준은 엄격하게 둔다.

- dcard/dcard_online error 0.
- 전체 fetch_error 0.
- Cloudflare JS challenge 0.
- HTTP 403 HTML 0.

윤리/운영 원칙:

- Cloudflare challenge를 억지로 우회하는 방향은 운영 리스크와 법적/정책 리스크가 크다.
- 현재는 우회보다 politeness 조정, source별 concurrency, delay, 실패 통계 축적, 공개 접근 가능한 페이지만 대상으로 하는 방향이 맞다.

## 59. Crawl4AI anti-bot 옵션 추가 조사와 적용 범위

추가 조사 출처:

- Crawl4AI Anti-Bot & Fallback: https://docs.crawl4ai.com/advanced/anti-bot-and-fallback/
- Crawl4AI Identity Based Crawling: https://docs.crawl4ai.com/advanced/identity-based-crawling/
- Crawl4AI Undetected Browser: https://docs.crawl4ai.com/advanced/undetected-browser/
- Crawl4AI Browser/Crawler Config: https://docs.crawl4ai.com/core/browser-crawler-config/
- Crawl4AI Proxy & Security: https://docs.crawl4ai.com/advanced/proxy-security/
- Cloudflare Browser Run `/crawl`: https://developers.cloudflare.com/browser-run/quick-actions/crawl-endpoint/

공식 문서 기준으로 Crawl4AI가 제공하는 관련 옵션은 세 단계로 나뉜다.

1. 기본/저비용 단계
   - `BrowserConfig(enable_stealth=True)`
   - `CrawlerRunConfig(magic=True)`
   - `CrawlerRunConfig(simulate_user=True)`
   - `CrawlerRunConfig(override_navigator=True)`
   - `CrawlerRunConfig(wait_until=...)`
   - `CrawlerRunConfig(max_retries=...)`
   - `CrawlerRunConfig(proxy_config=...)`

2. 상태 보존 단계
   - Managed Browser
   - persistent browser profile
   - `session_id`
   - 쿠키/localStorage 기반 상태 재사용

3. 고강도 단계
   - `UndetectedAdapter`
   - stealth + undetected browser 조합
   - proxy rotation

현재 우리 코드 상태:

- 이미 기본 browser는 `enable_stealth=True`.
- detail/listing run config는 `magic=True`.
- proxy는 최신 문서에 맞춰 `CrawlerRunConfig.proxy_config`로 전달한다.
- `max_retries`는 site별 설정에서 crawler까지 전달된다.
- `fetch_many()`는 `arun_many()` + dispatcher/rate limiter를 사용한다.
- Dcard 계열은 source concurrency 1, group concurrency 기본 1을 유지한다.

이번 추가 반영:

- `SiteConfig.override_navigator` 필드를 추가했다.
- `CrawlOptions`와 `Crawl4AICrawler.fetch()/fetch_many()`까지 `override_navigator`를 전달한다.
- Dcard/Dcard online에서만 아래 env로 실험적으로 켤 수 있게 했다.

```text
CRAWL_DCARD_WAIT_UNTIL_LOAD=1
CRAWL_DCARD_SIMULATE_USER=1
CRAWL_DCARD_OVERRIDE_NAVIGATOR=1
```

기본값으로 바로 켜지 않은 이유:

- 최신 baseline은 이미 `group_concurrency=1`에서 dcard/dcard_online error 0이었다.
- 추가 fingerprint 조작은 일부 site에서 오히려 challenge score를 악화시킬 수 있다.
- `wait_until="load"`는 selector timeout/SPA hydration 안정성에는 도움이 될 수 있지만, HTTP 403에는 직접 효과가 없고 latency를 늘릴 수 있다.
- `simulate_user`/`override_navigator`는 약한 anti-bot에는 도움 가능성이 있지만, Cloudflare challenge를 항상 해결하는 보장책은 아니다.

Managed Browser/persistent profile을 아직 기본 설계에 넣지 않은 이유:

- 로컬 Mac 실험에는 유용할 수 있다.
- 하지만 운영 EC2에서는 profile state, 쿠키, 로그인 상태, 개인정보/세션 관리 리스크가 생긴다.
- 반복 실행 간 상태 오염으로 재현성이 떨어진다.
- profile 디렉터리 보안, 백업 제외, 권한 관리가 필요하다.

UndetectedAdapter를 아직 기본 설계에 넣지 않은 이유:

- Crawl4AI 문서상 Cloudflare/DataDome 같은 정교한 탐지에는 더 강한 옵션이다.
- 대신 성능 영향이 있고, 유지보수/탐지 회피 성격이 강해 운영 리스크가 크다.
- 우리 목적은 공개 접근 가능한 유통 경로 탐지이므로, 우선 politeness와 수집 구조 개선을 먼저 검증하는 편이 맞다.

proxy rotation을 최후 수단으로 두는 이유:

- Crawl4AI 문서는 `ProxyConfig.from_env()`와 `RoundRobinProxyStrategy`를 제공한다.
- 하지만 현재 비용 조건은 EC2 1개 + RDS 1개다.
- 유료 proxy는 비용이 지속 발생하고, 품질 낮은 proxy는 오히려 Cloudflare score를 악화시킬 수 있다.
- Cloudflare Browser Run 문서도 자사 `/crawl` endpoint가 CAPTCHA/Turnstile/Bot Management/WAF를 우회하지 않는다고 명시한다.

다음 실험은 한 번에 모두 켜지 말고 분리한다.

공통 명령 골격:

```bash
cd /Users/jmac/Desktop/261RCOSE45700 && \
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl \
DETAIL_PROBE_SELECTED_ONLY=1 \
DETAIL_PROBE_BATCH_BY_SITE=true \
DETAIL_PROBE_CONCURRENCY=3 \
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1 \
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

실험 A: baseline

- Dcard 관련 env를 아무것도 켜지 않는다.
- `output/detail_probe_20260607_142222.jsonl`과 같은 수준으로 error 0이 나오는지 확인한다.

실험 B: fingerprint 보조 옵션

```bash
CRAWL_DCARD_SIMULATE_USER=1 \
CRAWL_DCARD_OVERRIDE_NAVIGATOR=1 \
...
```

- Cloudflare JS challenge가 줄어드는지 본다.
- HTTP 403이 줄어드는 보장은 없다.

실험 C: load wait만 단독 확인

```bash
CRAWL_DCARD_WAIT_UNTIL_LOAD=1 \
...
```

- selector timeout/본문 empty/SPA hydration 문제가 줄어드는지 본다.
- HTTP 403 대응 실험으로 해석하면 안 된다.

실험 D: 전부 켠 조합

```bash
CRAWL_DCARD_WAIT_UNTIL_LOAD=1 \
CRAWL_DCARD_SIMULATE_USER=1 \
CRAWL_DCARD_OVERRIDE_NAVIGATOR=1 \
...
```

- A/B/C보다 좋아질 때만 의미 있다.
- 좋아지지 않으면 각 옵션을 기본값으로 채택하지 않는다.

비교 기준:

- baseline: `output/detail_probe_20260607_142222.jsonl`
- 성공 기준:
  - dcard/dcard_online fetch error 0
  - Cloudflare JS challenge 0
  - HTTP 403 HTML 0
  - median/p95 latency가 baseline보다 크게 나빠지지 않을 것

판단:

- 지금 당장 더 좋은 기본값은 `Dcard는 느리게, 안정 source는 batch`.
- Crawl4AI의 추가 anti-bot 옵션은 "상시 기본값"이 아니라 "Dcard 전용 실험 스위치"로 두는 것이 맞다.
- 실험 결과가 좋으면 Dcard 계열에만 제한적으로 기본화하고, 결과가 나쁘면 env 없이 기존 baseline으로 돌아간다.

## 60. Dcard fingerprint 옵션 실험 결과

실험:

```text
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true
CRAWL_DCARD_SIMULATE_USER=1
CRAWL_DCARD_OVERRIDE_NAVIGATOR=1
```

출력 파일:

```text
output/detail_probe_20260608_012048.jsonl
```

baseline:

```text
output/detail_probe_20260607_142222.jsonl
```

비교:

```text
baseline:
rows=103 real=100 signal=68 error=0
dcard        real=5/5 error=0
dcard_online real=5/5 error=0
latency median=19847ms p95=34017ms

simulate_user + override_navigator:
rows=103 real=99 signal=68 error=1
dcard        real=5/5 error=0
dcard_online real=4/5 error=1
latency median=17172ms p95=35897ms
fetch_error=cloudflare_js_challenge 1
```

로그상 특이점:

- Dcard game 1건은 Cloudflare JS challenge가 발생했지만 retry 1회 후 성공했다.
- Dcard online 1건은 retry 후에도 `Blocked by anti-bot protection: Cloudflare JS challenge`로 실패했다.
- 403 HTML은 없었고, 실패는 Cloudflare JS challenge 1건이다.

판단:

- `simulate_user + override_navigator` 조합은 현재 baseline보다 나쁘다.
- median latency는 줄었지만 p95가 조금 늘었고, 더 중요한 error 0 조건을 깨뜨렸다.
- 따라서 이 조합은 기본값으로 채택하지 않는다.
- Dcard 계열은 env 없이 기존 보수 설정을 유지한다.

다음 실험 우선순위:

1. Dcard 관련 env 없이 baseline을 한 번 더 반복한다.
   - 목표: error 0 재현성 확인.

2. `CRAWL_DCARD_WAIT_UNTIL_LOAD=1` 단독 실험은 후순위다.
   - 목적: 403 해결이 아니라 timeout/empty/hydration 구분.
   - 현재 실패가 JS challenge였으므로 큰 기대값은 낮다.

3. 더 해볼 가치가 있는 것은 option 조작보다 실행 간격이다.
   - Dcard/Dcard online 사이 delay 확대.
   - Dcard online 첫 요청 전 cool-down.
   - Cloudflare JS challenge 발생 시 즉시 1회 retry보다 더 긴 backoff 후 retry.

현재 결론:

- Crawl4AI fingerprint 옵션은 "있다".
- 하지만 우리 실측에서는 Dcard 안정성을 개선하지 못했고, 오히려 dcard_online error를 만들었다.
- 지금 기본 전략은 `Dcard는 느리게, fingerprint 조작 없이, challenge 발생 시 더 긴 backoff`가 더 맞다.

코드 반영:

- 운영 pipeline `_fetch_post()`에 Cloudflare JS challenge 전용 외부 backoff retry를 추가했다.
- probe `_probe_one()`에도 같은 실험 스위치를 추가했다.
- 기본값은 retry 0회라 기존 동작을 바꾸지 않는다.

실험 env:

```text
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=1
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS=15
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SOURCES=dcard,dcard_online
```

probe에서는 같은 값을 `DETAIL_PROBE_*`로 override할 수 있다.

```text
DETAIL_PROBE_CLOUDFLARE_BACKOFF_RETRIES=1
DETAIL_PROBE_CLOUDFLARE_BACKOFF_SECONDS=15
DETAIL_PROBE_CLOUDFLARE_BACKOFF_SOURCES=dcard,dcard_online
```

다음 권장 실험:

```bash
cd /Users/jmac/Desktop/261RCOSE45700 && \
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl \
DETAIL_PROBE_SELECTED_ONLY=1 \
DETAIL_PROBE_BATCH_BY_SITE=true \
DETAIL_PROBE_CONCURRENCY=3 \
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1 \
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true \
DETAIL_PROBE_CLOUDFLARE_BACKOFF_RETRIES=1 \
DETAIL_PROBE_CLOUDFLARE_BACKOFF_SECONDS=15 \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

성공 기준:

- dcard/dcard_online error 0.
- Cloudflare JS challenge 최종 실패 0.
- retry 때문에 latency는 늘어날 수 있으므로, 최종 error 0을 더 우선한다.

## 61. Cloudflare 실패 원인 가설 웹 조사 검증

질문:

- 정말 `simulate_user + override_navigator` 같은 fingerprint 옵션 문제가 아니라, 요청 패턴/챌린지 상태/세션 처리 문제가 더 큰 원인인가?

조사 출처:

- Cloudflare JavaScript Detections: https://developers.cloudflare.com/cloudflare-challenges/challenge-types/javascript-detections/
- Cloudflare How Challenges Work: https://developers.cloudflare.com/cloudflare-challenges/concepts/how-challenges-work/
- Cloudflare Rate Limiting Rules: https://developers.cloudflare.com/waf/rate-limiting-rules/
- Cloudflare Rate Limiting Parameters: https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/
- Cloudflare Bot Management: https://www.cloudflare.com/application-services/products/bot-management/
- Crawl4AI Anti-Bot & Fallback: https://docs.crawl4ai.com/advanced/anti-bot-and-fallback/
- Crawl4AI Session Management: https://docs.crawl4ai.com/advanced/session-management/
- Crawl4AI Identity Based Crawling: https://docs.crawl4ai.com/advanced/identity-based-crawling/
- Crawl4AI Undetected Browser: https://docs.crawl4ai.com/advanced/undetected-browser/

확인한 사실:

1. Cloudflare JavaScript Detections는 HTML 응답에 challenge script를 주입하고, 브라우저 실행 결과를 `cf_clearance` 쿠키에 저장한다.
   - 즉 한 요청 단위의 `wait_until`만으로 해결되는 문제가 아니다.
   - 첫 HTML request, script 실행, cookie 발급/검증, 이후 WAF/custom rule 평가가 연결된다.

2. Cloudflare 문서는 JavaScript Detection 결과를 바로 block하지 않고, WAF rule이 `js_detection.passed` 값을 보고 challenge/block할 수 있다고 설명한다.
   - 우리 로그의 `Cloudflare JS challenge`는 단순 렌더링 지연보다 Cloudflare 쪽 판정/상태 문제에 가깝다.

3. Cloudflare Rate Limiting은 요청 수/기간/특성에 따라 challenge/block을 걸 수 있다.
   - rule이 trigger되면 일정 시간 mitigation이 적용될 수 있고, challenge를 통과한 뒤 counter가 reset되는 식의 동작도 있다.
   - 그래서 짧은 간격의 반복 요청이나 site group 병렬 실행이 challenge 확률을 올렸다는 우리 실측과 맞다.

4. Crawl4AI Anti-Bot 문서는 anti-bot 실패를 `403/429`, challenge page, CAPTCHA, WAF block 등으로 분리해서 본다.
   - `wait_until`보다 `max_retries`, fallback, proxy strategy, stealth/magic, session/identity 계열을 별도로 다룬다.

5. Crawl4AI Session Management는 `session_id`를 이용해 같은 browser tab/page context를 순차 요청에서 재사용할 수 있다고 설명한다.
   - Cloudflare JS Detection이 cookie/session 상태를 쓰는 구조라면, 매 요청마다 fresh context처럼 움직이는 것보다 session reuse가 더 자연스러운 다음 실험 후보가 된다.
   - 단, Crawl4AI 문서는 session이 sequential workflow용이고 parallel operation에는 맞지 않는다고 한다.

6. Crawl4AI Identity Based Crawling은 managed browser/persistent profile이 cookies/localStorage/session data를 보존한다고 설명한다.
   - 이건 Cloudflare challenge 안정화에는 유리할 수 있지만, 운영 EC2에서는 profile 보안/상태 오염/재현성 리스크가 커서 기본값으로 넣기 어렵다.

7. Crawl4AI Undetected Browser 문서는 Cloudflare/DataDome 같은 sophisticated bot detection에는 undetected browser가 더 적합할 수 있다고 설명한다.
   - 하지만 성능 비용이 있고, Crawl4AI 문서도 progressive enhancement를 권장한다.
   - 우리 현 단계에서는 기본 적용보다 Dcard 전용 opt-in 실험 후보로 보는 편이 맞다.

우리 실측과의 대응:

```text
baseline:
dcard_online 5/5 real, error 0

simulate_user + override_navigator:
dcard_online 4/5 real, Cloudflare JS challenge 1

group_concurrency=2:
dcard_online 3/5 real, Cloudflare/403 계열 error 2
```

해석:

- `simulate_user + override_navigator`가 항상 나쁘다는 뜻은 아니다.
- 하지만 우리 환경/대상/현재 Crawl4AI 설정에서는 안정성을 개선하지 못했다.
- 반대로 group concurrency 증가나 fingerprint 조작 후 Dcard online error가 증가했다.
- 따라서 현재 문제를 "wait_until 부족"이나 "fingerprint 옵션 미적용"으로 보는 것은 근거가 약하다.
- 더 설득력 있는 원인은 Cloudflare challenge/session/rate-pattern 민감성이다.

반대 가능성:

1. 샘플 수가 작다.
   - Dcard/Dcard online 각각 5건이라 통계적으로 확정은 아니다.
   - 반복 실험이 필요하다.

2. Cloudflare 정책은 시간대/IP/이전 요청 이력에 따라 달라질 수 있다.
   - 같은 설정도 어느 날은 통과하고 어느 날은 실패할 수 있다.

3. `simulate_user + override_navigator`가 나쁜 것이 아니라, 조합/순서/세션 재사용 부재가 문제일 수 있다.
   - session reuse와 같이 쓰면 결과가 달라질 수 있다.

4. 실제로는 특정 URL만 challenge를 더 잘 유발했을 수 있다.
   - 실패 URL 단위 재시도와 URL별 이력 추적이 필요하다.

판단:

- "문제는 backoff 부재였다"라고 단정하면 안 된다.
- 더 정확한 표현은 "우리 실측과 공식 문서상, Cloudflare JS challenge는 즉시 retry/fingerprint 옵션보다 요청 간격, 세션 상태, challenge 후 backoff에 더 민감할 가능성이 높다"이다.
- 그래서 다음 실험은 fingerprint 조작이 아니라 `challenge final failure -> longer backoff -> retry`가 맞다.

다음 검증 순서:

1. baseline 반복
   - Dcard env 없음.
   - 목표: error 0 재현.

2. backoff retry만 실험
   - `DETAIL_PROBE_CLOUDFLARE_BACKOFF_RETRIES=1`
   - `DETAIL_PROBE_CLOUDFLARE_BACKOFF_SECONDS=15`
   - 목표: Cloudflare JS challenge 최종 실패 0.

3. backoff seconds 비교
   - 15초, 30초, 60초를 비교.
   - 성공률과 latency trade-off 확인.

4. session reuse 후보 검토
   - Dcard/Dcard online 순차 처리에서만 `session_id` 실험.
   - parallel/batch에는 적용하지 않는다.

5. managed browser/persistent profile은 최후 실험
   - 로컬 Mac에서만 별도 profile로 실험.
   - 운영 기본값으로는 넣지 않는다.

## 62. Backoff-only probe 결과

실험:

```text
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true
DETAIL_PROBE_CLOUDFLARE_BACKOFF_RETRIES=1
DETAIL_PROBE_CLOUDFLARE_BACKOFF_SECONDS=15
```

출력 파일:

```text
output/detail_probe_20260608_013315.jsonl
```

비교:

```text
baseline:
rows=103 real=100 signal=68 error=0
dcard        5/5 real, error=0
dcard_online 5/5 real, error=0
latency median=19847ms p95=34017ms

fingerprint 옵션:
rows=103 real=99 signal=68 error=1
dcard        5/5 real, error=0
dcard_online 4/5 real, error=1
fetch_error=cloudflare_js_challenge 1
latency median=17172ms p95=35897ms

backoff-only:
rows=103 real=100 signal=68 error=0
dcard        5/5 real, error=0
dcard_online 5/5 real, error=0
latency median=20661ms p95=36175ms
fetch_error=none
```

중요 해석:

- 이번 backoff-only 실행에서는 Dcard/Dcard online에서 Cloudflare JS challenge가 발생하지 않았다.
- 따라서 "15초 backoff가 challenge를 해결했다"라고 결론내리면 안 된다.
- 더 정확한 결론은 "fingerprint 옵션을 끄고 보수 설정을 유지한 실행이 다시 안정적으로 재현됐다"이다.

판단:

- `simulate_user + override_navigator`는 현재 기본값으로 채택하지 않는다.
- `DETAIL_PROBE_CLOUDFLARE_BACKOFF_RETRIES=1`은 안전망으로는 의미가 있지만, 이번 실행에서 실제로 작동한 증거는 없다.
- backoff env는 기본값 0회로 유지하고, Cloudflare 실패가 반복되는 실험/운영 상황에서만 켠다.
- 운영 기본 전략은 여전히 다음과 같다.
  - Dcard/Dcard online concurrency 1.
  - sensitive source first.
  - fingerprint 옵션 off.
  - `wait_until=load` off.
  - Cloudflare JS challenge가 반복 관측될 때만 backoff retry opt-in.

다음 검증:

- 같은 backoff-only 명령을 1회 더 반복해 error 0이 재현되는지 본다.
- 이후 backoff env 없이 baseline도 1회 더 반복한다.
- 두 실행 모두 error 0이면, backoff는 기본값으로 켜지 않고 비상 스위치로만 둔다.

## 63. Baseline 재실험 결과: Dcard challenge 재발

실험:

```text
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true
```

출력 파일:

```text
output/detail_probe_20260608_022830.jsonl
```

요약:

```text
rows=103
real=99
signal=67
error=1

dcard        5 total / 4 real / 1 error
dcard_online 5 total / 5 real / 0 error

fetch_error=cloudflare_js_challenge 1
```

비교:

```text
20260607_142222 baseline:
dcard        5/5 real, error 0
dcard_online 5/5 real, error 0

20260608_013315 backoff-only:
dcard        5/5 real, error 0
dcard_online 5/5 real, error 0

20260608_022830 baseline repeat:
dcard        4/5 real, error 1
dcard_online 5/5 real, error 0
```

판단:

- baseline도 완전 안정이라고 볼 수 없다.
- Cloudflare JS challenge는 dcard_online뿐 아니라 dcard game에서도 재발한다.
- fingerprint 옵션이 유일한 원인은 아니다.
- challenge 발생이 시간대/IP 상태/이전 요청 이력/Cloudflare 내부 score에 따라 흔들리는 것으로 보는 편이 맞다.

전략 수정:

- `simulate_user`, `override_navigator`, `wait_until=load`는 계속 기본값 off.
- 하지만 Cloudflare JS challenge 전용 backoff retry는 "비상 스위치"가 아니라 운영 안정화 후보로 승격한다.
- 다만 default-on으로 확정하기 전에 1회 더 backoff-only 반복이 필요하다.

다음 명령:

```bash
cd /Users/jmac/Desktop/261RCOSE45700 && \
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl \
DETAIL_PROBE_SELECTED_ONLY=1 \
DETAIL_PROBE_BATCH_BY_SITE=true \
DETAIL_PROBE_CONCURRENCY=3 \
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1 \
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true \
DETAIL_PROBE_CLOUDFLARE_BACKOFF_RETRIES=1 \
DETAIL_PROBE_CLOUDFLARE_BACKOFF_SECONDS=15 \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

성공 기준:

- dcard error 0.
- dcard_online error 0.
- fetch error reasons none.

이 실험도 error 0이면:

- 운영에서 `CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=1`
- `CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS=15`
- `CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SOURCES=dcard,dcard_online`

을 기본 env 후보로 둔다.

## 64. Cloudflare/Crawl4AI 추가 웹 조사: backoff가 맞는가

질문:

- baseline에서 Cloudflare JS challenge가 간헐적으로 발생한다.
- 이때 backoff retry를 운영 안정화 후보로 보는 것이 맞는가?
- 아니면 `wait_until`, fingerprint 조작, session reuse, persistent browser가 더 우선인가?

추가 조사 출처:

- Cloudflare JavaScript Detections: https://developers.cloudflare.com/bots/reference/javascript-detections/
- Cloudflare Bot Detection Engines: https://developers.cloudflare.com/bots/concepts/bot-detection-engines/
- Cloudflare Rate Limiting Rules: https://developers.cloudflare.com/waf/rate-limiting-rules/
- Cloudflare Rate Limiting Parameters: https://developers.cloudflare.com/waf/rate-limiting-rules/parameters/
- Cloudflare Rate Limiting Best Practices: https://developers.cloudflare.com/waf/rate-limiting-rules/best-practices/
- Crawl4AI Anti-Bot & Fallback: https://docs.crawl4ai.com/advanced/anti-bot-and-fallback/
- Crawl4AI Session Management: https://docs.crawl4ai.com/advanced/session-management/
- Crawl4AI Browser/Crawler Parameters: https://docs.crawl4ai.com/api/parameters/
- Crawl4AI Identity Based Crawling: https://docs.crawl4ai.com/advanced/identity-based-crawling/
- Scrapy AutoThrottle: https://doc.scrapy.org/en/latest/topics/autothrottle.html
- MDN 429 Too Many Requests: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/429

확인한 사실:

1. Cloudflare JavaScript Detections는 HTML page view에 JS snippet을 주입하고, 실행 결과를 `cf_clearance` cookie에 저장한다.
   - 결과는 `js_detection.passed` 같은 값으로 WAF/custom rule 판단에 쓰일 수 있다.
   - 따라서 단순히 `wait_until="load"`만 길게 주는 문제로 보기 어렵다.

2. Cloudflare Bot Detection Engines는 header, session characteristics, browser signals 등을 입력으로 쓴다.
   - Cloudflare는 `__cf_bm` cookie도 사용해 bot score를 smoothing하고 false positive를 줄인다고 설명한다.
   - 즉 "한 URL fetch 실패"가 아니라 browser/session/IP/request pattern의 누적 판단일 수 있다.

3. Cloudflare Rate Limiting은 threshold/period/mitigation timeout 구조를 가진다.
   - rate limit rule은 일정 기간 action을 적용할 수 있다.
   - challenge action에서는 통과 후 counter가 reset될 수 있고, 다시 threshold에 걸리면 challenge가 재발할 수 있다.
   - 이는 우리 로그처럼 같은 설정에서도 어떤 회차는 통과하고 어떤 회차는 challenge가 뜨는 현상과 맞다.

4. Crawl4AI Anti-Bot & Fallback 문서는 Cloudflare/Akamai/DataDome/Imperva 같은 anti-bot에서 403, CAPTCHA, empty page가 발생할 수 있다고 설명한다.
   - 관련 옵션은 `CrawlerRunConfig.proxy_config`, `max_retries`, `fallback_fetch_function`이다.
   - 즉 Crawl4AI도 anti-bot block을 normal fetch failure와 별도로 다루며 retry/fallback layer를 둔다.

5. Crawl4AI Session Management는 `session_id`로 같은 browser tab/page object를 순차 요청에서 재사용할 수 있다고 설명한다.
   - 문서상 sequential workflow용이며 parallel operation에는 적합하지 않다.
   - Dcard/Dcard online은 concurrency 1이므로 session reuse 실험 후보가 될 수 있다.

6. Crawl4AI Browser/Crawler Parameters와 Identity Based Crawling 문서는 persistent context/user_data_dir가 cookies/session을 run 간 보존한다고 설명한다.
   - Cloudflare cookie/session 안정화에는 이론적으로 유리하다.
   - 하지만 운영 EC2에서는 profile state 보안, 개인정보/쿠키 저장, 상태 오염, 재현성 문제가 있다.

7. Scrapy AutoThrottle는 site에 부담을 덜 주기 위해 delay/concurrency를 동적으로 조절하며, non-200 response latency가 delay를 줄이는 데 쓰이지 않도록 한다.
   - 이는 "실패가 나왔을 때 더 빠르게 몰아치지 않고 보수적으로 늦춘다"는 우리 방향과 맞다.

8. MDN 429 문서는 `Retry-After` header가 있을 수 있다고 설명한다.
   - Dcard 실패는 429가 아니라 Cloudflare JS challenge이므로 그대로 적용할 수는 없다.
   - 그러나 rate-limit/temporary mitigation 계열에서는 retry 간격을 두는 것이 표준적인 클라이언트 대응이다.

판단:

- `wait_until="load"`는 핵심 대응이 아니다.
  - Cloudflare JS challenge는 page load만의 문제가 아니라 cookie/session/WAF 판단과 연결된다.

- `simulate_user + override_navigator`도 현 시점 우선순위가 낮다.
  - 우리 실측에서 error를 줄이지 못했고 dcard_online error를 만들었다.

- backoff retry는 "문제를 해결하는 우회책"이 아니라 "challenge/temporary mitigation에 대한 보수적 재시도 정책"이다.
  - 웹 조사와 실측을 합치면 저비용 1차 운영 안정화 후보로 타당하다.
  - 단, backoff가 실제로 challenge를 회복시키는지 확인하려면 challenge 발생 회차에서 backoff가 작동한 로그가 필요하다.

- session reuse는 backoff 다음 후보가 맞다.
  - Cloudflare 문서상 cookie/session signal이 중요하고, Crawl4AI도 sequential session reuse를 제공한다.
  - Dcard는 serial path라 기술적으로 맞다.
  - 다만 구현/실험은 Dcard 전용 opt-in으로 제한해야 한다.

- persistent profile/managed browser는 아직 이르다.
  - 성공률을 높일 가능성은 있지만 상태 보존 리스크와 운영 복잡도가 크다.
  - 로컬 Mac 전용 실험 후보로만 둔다.

실행 순서 결론:

1. 운영 기본 유지
   - Dcard/Dcard online concurrency 1.
   - sensitive first.
   - fingerprint 옵션 off.
   - `wait_until=load` off.

2. 운영 안정화 1차 후보
   - Cloudflare JS challenge 전용 backoff retry.
   - `CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=1`
   - `CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS=15`
   - `CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SOURCES=dcard,dcard_online`

3. 운영 안정화 2차 후보
   - Dcard/Dcard online 전용 `session_id` reuse.
   - sequential fetch에만 적용.
   - batch/parallel에는 적용하지 않는다.

4. 최후 후보
   - persistent browser profile.
   - managed browser.
   - UndetectedAdapter.
   - proxy.

반대 의견/주의:

- Cloudflare challenge는 내부 score/정책/시간대/IP에 따라 변한다.
- 샘플 수가 작기 때문에 한두 번 error 0이어도 완전한 안정성을 보장하지 않는다.
- backoff가 효과를 입증하려면 "challenge 발생 -> backoff sleep -> retry success" 로그가 필요하다.
- session reuse는 cookie/session 안정화에는 좋지만, 상태 오염과 재현성 저하를 만들 수 있다.

## 65. Cloudflare cookie/session 근거와 Dcard session reuse 후보

추가 질문:

- Cloudflare JS challenge가 간헐적으로 발생한다면, backoff 다음으로 `session_id` reuse를 실험하는 것이 근거 있는 순서인가?
- persistent profile까지 바로 가야 하는가?

추가 조사 출처:

- Cloudflare Cookies: https://developers.cloudflare.com/fundamentals/reference/policies-compliances/cloudflare-cookies
- Cloudflare Clearance: https://developers.cloudflare.com/turnstile/get-started/pre-clearance/
- Cloudflare Rate Limiting Best Practices: https://developers.cloudflare.com/waf/rate-limiting-rules/best-practices/
- Cloudflare Interstitial Challenge Pages: https://developers.cloudflare.com/cloudflare-challenges/challenge-types/challenge-pages/
- Cloudflare JavaScript Detections: https://developers.cloudflare.com/bots/reference/javascript-detections/
- Playwright Browser Contexts: https://playwright.dev/docs/browser-contexts
- Playwright BrowserContext API: https://playwright.dev/docs/api/class-browsercontext
- Crawl4AI Session Management: https://docs.crawl4ai.com/advanced/session-management/
- Crawl4AI Browser/Crawler Parameters: https://docs.crawl4ai.com/api/parameters/

Cloudflare cookie/session 관련 핵심:

1. `cf_clearance`
   - Cloudflare는 challenge를 통과한 visitor에게 `cf_clearance` cookie를 발급한다.
   - 이 cookie는 visitor/device에 묶이며, 다른 machine에서 쉽게 재사용되지 않도록 설계되어 있다.
   - Cloudflare 문서는 challenge level에 따라 `cf_clearance`가 Managed/Non-Interactive/Interactive Challenge를 우회할 수 있다고 설명한다.
   - JavaScript Detection 결과도 `cf_clearance`에 저장된다.

2. `__cf_bm`
   - Cloudflare Bot Management/Bot Fight Mode는 `__cf_bm` cookie를 사용할 수 있다.
   - 이 cookie에는 Cloudflare proprietary bot score 계산 관련 정보가 들어가며, Anomaly Detection이 켜진 경우 session identifier도 포함될 수 있다.
   - 즉 cookie/session 상태가 매번 초기화되면 bot score smoothing이나 session continuity에 불리할 수 있다.

3. Sequence/rate limiting
   - Cloudflare는 sequence rules에서 request 순서와 request 사이 시간을 cookie로 추적할 수 있다고 설명한다.
   - Rate limiting best practices는 `cf_clearance` cookie 값 기준 rate limiting 예시도 제시한다.
   - 따라서 "같은 IP에서 몇 초 간격으로 순차 요청"뿐 아니라 "같은 clearance/session에서 얼마나 많이 요청했는지"도 판단 조건이 될 수 있다.

Playwright/Crawl4AI 상태 관리 관련 핵심:

1. Playwright default browser context는 isolated clean-slate environment다.
   - 각 context는 cookies/localStorage/sessionStorage를 분리한다.
   - 이는 테스트 재현성에는 좋지만, Cloudflare가 session continuity를 기대하는 경우에는 매 요청이 낯선 visitor처럼 보일 수 있다.

2. Playwright BrowserContext는 cookies/localStorage/IndexedDB storage state를 보관/복원할 수 있다.
   - 이것은 session persistence의 기술적 근거다.
   - 다만 저장된 state를 재사용하면 상태 오염과 보안 리스크가 생긴다.

3. Crawl4AI `session_id`
   - Crawl4AI는 `session_id`로 같은 browser tab/page object를 순차 crawl에서 재사용할 수 있다고 설명한다.
   - 문서상 parallel operation에는 적합하지 않고 sequential workflow에 맞다.
   - Dcard/Dcard online은 현재 concurrency 1이므로 조건이 맞는다.

4. Crawl4AI persistent context
   - `use_persistent_context=True`, `user_data_dir`는 cookies/session을 run 간 보존한다.
   - 그러나 이것은 disk profile을 남기므로 운영 EC2에서는 보안/재현성/상태 오염 리스크가 크다.

새 판단:

- backoff는 "temporary challenge/mitigation에 대한 저비용 완충"이다.
- `session_id` reuse는 "같은 실행 안에서 Dcard detail 연속 fetch의 session continuity를 높이는 실험"이다.
- persistent profile은 "실행 간 cookie/session까지 보존하는 강한 실험"이다.

따라서 순서는 다음이 맞다.

1. backoff retry
   - 구현 완료.
   - default-on 여부는 추가 실험으로 판단.

2. Dcard/Dcard online 전용 `session_id` reuse
   - 같은 실행 안에서만 session 유지.
   - disk profile 저장 없음.
   - Dcard serial path에만 적용.
   - batch/fetch_many에는 적용하지 않음.

3. persistent profile/user_data_dir
   - 로컬 Mac 전용 실험.
   - 운영 기본값 보류.

4. UndetectedAdapter/proxy
   - 최후 단계.

session_id 실험 설계:

```text
CRAWL_DCARD_SESSION_REUSE=1
CRAWL_DCARD_SESSION_ID_PREFIX=dcard-detail
```

동작 아이디어:

- `dcard` detail fetch는 `session_id="dcard-detail-dcard"`.
- `dcard_online` detail fetch는 `session_id="dcard-detail-dcard-online"`.
- 같은 source 내부에서 5개 detail URL을 같은 Crawl4AI session으로 순차 fetch한다.
- source가 끝나면 session을 kill할 수 있으면 kill한다.

주의:

- Dcard와 Dcard online을 같은 session으로 묶을지는 별도 판단이 필요하다.
  - 같은 도메인이라 cookie continuity에는 유리할 수 있다.
  - 하지만 board/topic 이동 패턴이 더 부자연스럽게 보일 수도 있다.
  - 1차 실험은 source별 별도 session이 더 안전하다.

- session_id를 쓰면 한 실패가 다음 요청에 영향을 줄 수 있다.
  - 예: challenge 실패 cookie/state가 남아 다음 URL도 불리해질 수 있다.
  - 따라서 session reuse 실험은 실패 시 session reset 옵션과 함께 설계해야 한다.

권장 다음 코드 실험:

1. `CrawlOptions.session_id`는 아직 넣지 않는다.
2. 먼저 `Crawl4AICrawler.fetch()`에 optional `session_id` 전달만 추가한다.
3. `detail_priority_probe.py`에서만 Dcard session reuse 실험 스위치를 붙인다.
4. probe 결과가 좋으면 운영 pipeline에 제한적으로 이식한다.

성공 기준:

- baseline repeat에서 발생한 dcard Cloudflare JS challenge가 없어져야 한다.
- dcard/dcard_online error 0.
- latency가 backoff-only보다 크게 나빠지지 않을 것.

실패 기준:

- Cloudflare JS challenge가 source 첫 요청 이후 연쇄적으로 늘어난다.
- Dcard body empty/unknown이 증가한다.
- session state 때문에 재현성이 떨어진다.

구현 결과:

- `Crawl4AICrawler.fetch()`가 optional `session_id`를 받아 `CrawlerRunConfig.session_id`로 전달한다.
- `detail_priority_probe.py`에 Dcard session reuse opt-in을 추가했다.
- 기본값은 off다.
- `fetch_many()`에는 적용하지 않았다. Crawl4AI 문서상 session reuse는 sequential workflow용이기 때문이다.

추가 env:

```text
CRAWL_DCARD_SESSION_REUSE=1
CRAWL_DCARD_SESSION_ID_PREFIX=dcard-detail
CRAWL_DCARD_SESSION_SOURCES=dcard,dcard_online
```

다음 probe 명령:

```bash
cd /Users/jmac/Desktop/261RCOSE45700 && \
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl \
DETAIL_PROBE_SELECTED_ONLY=1 \
DETAIL_PROBE_BATCH_BY_SITE=true \
DETAIL_PROBE_CONCURRENCY=3 \
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1 \
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true \
CRAWL_DCARD_SESSION_REUSE=1 \
CRAWL_DCARD_SESSION_ID_PREFIX=dcard-detail \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

비교 대상:

- `output/detail_probe_20260608_022830.jsonl`: baseline repeat, dcard Cloudflare JS challenge 1.
- `output/detail_probe_20260608_013315.jsonl`: backoff-only, error 0.

판단 기준:

- dcard error 0.
- dcard_online error 0.
- fetch error reasons none.
- Dcard/Dcard online body empty/unknown 증가 없음.

검증:

```text
27 passed
190 passed
```

## 66. Dcard session reuse probe 결과

실험:

```text
DETAIL_PROBE_INPUT=output/dry_run_20260607_133835.jsonl
DETAIL_PROBE_SELECTED_ONLY=1
DETAIL_PROBE_BATCH_BY_SITE=true
DETAIL_PROBE_CONCURRENCY=3
DETAIL_PROBE_SITE_GROUP_CONCURRENCY=1
DETAIL_PROBE_SENSITIVE_GROUPS_FIRST=true
CRAWL_DCARD_SESSION_REUSE=1
CRAWL_DCARD_SESSION_ID_PREFIX=dcard-detail
```

출력 파일:

```text
output/detail_probe_20260608_024321.jsonl
```

요약:

```text
rows=103
real=99
signal=67
error=1

dcard        5 total / 5 real / 0 error
dcard_online 5 total / 4 real / 1 error

fetch_error=cloudflare_js_challenge 1
```

비교:

```text
baseline repeat (20260608_022830):
dcard        4/5 real, error 1
dcard_online 5/5 real, error 0

backoff-only (20260608_013315):
dcard        5/5 real, error 0
dcard_online 5/5 real, error 0

session reuse only (20260608_024321):
dcard        5/5 real, error 0
dcard_online 4/5 real, error 1
```

판단:

- session reuse 단독은 채택하지 않는다.
- Cloudflare JS challenge가 dcard에서 dcard_online으로 이동했을 뿐, error 0을 만들지 못했다.
- session continuity가 이론적으로 그럴듯하더라도, 현재 실측에서는 안정화 효과가 확인되지 않았다.
- session reuse 코드는 probe 전용 opt-in 실험 스위치로 남겨둔다.
- 운영 pipeline에는 아직 이식하지 않는다.

현재 최선 후보:

```text
1. Dcard/Dcard online concurrency 1
2. sensitive source first
3. fingerprint 옵션 off
4. wait_until=load off
5. Cloudflare JS challenge 전용 backoff retry
```

운영 env 후보:

```text
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=1
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS=15
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SOURCES=dcard,dcard_online
```

다음 선택지:

1. backoff-only를 한 번 더 반복해 error 0 재현성을 확인한다.
2. 또는 backoff + session reuse 조합을 실험한다.

하지만 우선순위는 1번이다.

- session reuse 단독이 실패했기 때문에 조합 실험의 기대값은 낮다.
- backoff-only는 이미 error 0을 낸 유일한 후보이다.

## 67. Anti-bot 추가 조사: Cloudflare를 넘어선 판단 프레임

질문:

- 우리가 보고 있는 `Cloudflare JS challenge`를 anti-bot 전체 맥락에서 어떻게 이해해야 하는가?
- 단순 retry/backoff 외에 더 봐야 할 구조는 무엇인가?

추가 조사 출처:

- Cloudflare Bot Detection Engines: https://developers.cloudflare.com/bots/concepts/bot-detection-engines/
- Cloudflare How Challenges Work: https://developers.cloudflare.com/cloudflare-challenges/concepts/how-challenges-work/
- Cloudflare Supported Browsers: https://developers.cloudflare.com/cloudflare-challenges/reference/supported-browsers/
- Cloudflare JavaScript Detections: https://developers.cloudflare.com/bots/reference/javascript-detections/
- Cloudflare Cookies: https://developers.cloudflare.com/fundamentals/reference/policies-compliances/cloudflare-cookies
- Cloudflare Challenge Solve Rate: https://developers.cloudflare.com/fundamentals/security/cloudflare-challenges/challenge-solve-rate
- Crawl4AI Anti-Bot & Fallback: https://docs.crawl4ai.com/advanced/anti-bot-and-fallback/
- Crawl4AI Complete SDK Reference: https://docs.crawl4ai.com/complete-sdk-reference/
- Crawl4AI Undetected Browser: https://docs.crawl4ai.com/advanced/undetected-browser/
- Crawl4AI Session Management: https://docs.crawl4ai.com/advanced/session-management/
- DataDome docs: https://docs.datadome.co/docs/
- DataDome CDN integration: https://docs.datadome.co/docs/cdn-integration
- FP-Inconsistent paper: https://arxiv.org/abs/2406.07647

anti-bot 시스템의 주요 신호:

1. Network/request 신호
   - IP reputation.
   - ASN/datacenter 여부.
   - request rate.
   - burst pattern.
   - header 조합.
   - HTTP/TLS fingerprint.

2. Browser/client 신호
   - JavaScript 실행 가능 여부.
   - Web APIs.
   - Canvas/WebGL.
   - navigator 속성.
   - browser version/UA 일관성.
   - headless automation 흔적.

3. Session/cookie 신호
   - `cf_clearance`.
   - `__cf_bm`.
   - challenge 통과 이력.
   - bot score smoothing.
   - sequence cookie.
   - 같은 visitor/session에서의 요청 순서와 간격.

4. Behavioral 신호
   - request sequence.
   - page view 흐름.
   - challenge solve behavior.
   - 비정상적으로 빠른 반복 접근.
   - 동일한 URL 패턴 반복.

5. ML/anomaly 신호
   - Cloudflare는 ML/heuristics/behavioral analysis/JS signals를 조합한다고 설명한다.
   - DataDome 같은 anti-bot도 CDN 뒤에서 client IP/header/JS tag/API 등을 종합한다.

우리 실험과 맞는 부분:

- `simulate_user + override_navigator`가 실패를 없애지 못했다.
  - 이는 단일 browser fingerprint 패치만으로는 부족하다는 anti-bot 문서/연구와 맞다.

- `session_id` reuse 단독도 실패를 없애지 못했다.
  - session continuity가 유리할 가능성은 있지만, challenge 실패 state가 남거나 request sequence가 더 민감해질 수도 있다.

- `group_concurrency=2`에서 Dcard online error가 늘었다.
  - rate/sequence/request pattern 쪽 신호가 중요하다는 문서와 맞다.

- `backoff-only`가 현재까지 유일한 error 0 실험이다.
  - backoff가 Cloudflare를 우회했다기보다, challenge/temporary mitigation에 덜 공격적으로 대응한 결과로 해석하는 것이 맞다.

중요한 반대 근거:

- Cloudflare challenge solve rate 문서는 challenge success/failure가 실제 browser의 subsequent request/validated solution과 연결된다고 설명한다.
- 따라서 단순히 "15초 기다리면 해결"이 아니다.
- backoff는 실패 직후 재시도 압력을 낮추는 정책일 뿐, challenge solve 자체를 보장하지 않는다.

- Crawl4AI Undetected Browser 문서는 Cloudflare/DataDome 같은 sophisticated bot detection에는 더 깊은 browser patch가 필요할 수 있다고 설명한다.
- 그러나 이것은 비용/성능/운영 리스크가 크고, 탐지 회피 성격이 강해서 최후 단계로 두는 것이 맞다.

- FP-Inconsistent 연구는 fingerprint를 조작하는 evasive bot들이 여러 fingerprint 속성의 공간/시간 일관성을 유지하기 어렵다고 설명한다.
- 즉 어설픈 `override_navigator`류 조작은 오히려 fingerprint inconsistency를 만들 수 있다.
- 우리 실험에서 `simulate_user + override_navigator`가 개선되지 않은 것과 방향이 맞다.

현재 판단 프레임:

1. "우회"가 아니라 "부담 줄이기/공개 접근 안정화"로 접근한다.
   - rate를 낮춘다.
   - source별 concurrency를 제한한다.
   - challenge가 나오면 즉시 반복하지 않는다.
   - 실패 유형을 정확히 기록한다.

2. 단일 옵션으로 해결하려 하지 않는다.
   - `wait_until=load` 단독: 탈락.
   - `simulate_user + override_navigator` 단독: 탈락.
   - `session_id` 단독: 탈락.
   - backoff-only: 현재 유일한 성공 후보.

3. 단계적 escalation만 허용한다.
   - Level 0: baseline serial crawl.
   - Level 1: Cloudflare JS challenge 전용 backoff.
   - Level 2: backoff seconds 조정.
   - Level 3: backoff + session reuse 조합 실험.
   - Level 4: persistent profile local-only.
   - Level 5: UndetectedAdapter/proxy/managed browser. 최후 후보.

4. 운영 기본 후보는 아직 Level 1까지만이다.

```text
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=1
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS=15
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SOURCES=dcard,dcard_online
```

추가로 조사/실험할 만한 것:

1. Cloudflare challenge 발생 URL의 공통점
   - board_game URL에서 더 잘 발생하는가?
   - 오래된 글/짧은 title/특정 board가 더 민감한가?

2. Dcard/Dcard online 사이 cooldown
   - dcard 5건 직후 dcard_online이 바로 시작된다.
   - source group 사이 30~60초 cooldown이 challenge를 줄이는지 확인할 가치가 있다.

3. challenge 발생 후 source-level cooldown
   - 한 URL에서 challenge가 나오면 같은 source의 다음 URL 전에 30~60초 쉬는 정책.
   - backoff retry와 비슷하지만 "다음 URL 보호"에 초점이 있다.

4. session reset 정책
   - session reuse가 실패 state를 전파할 수 있으므로, challenge 발생 시 session kill/reset이 필요할 수 있다.

5. `crawl_stats` 분석 강화
   - resolved_by.
   - attempts.
   - blocked reason.
   - status code.
   - retry round.

다음 코드 후보:

- 운영 pipeline에 바로 session reuse를 넣지 않는다.
- 대신 다음으로 가장 현실적인 개선은 source-level cooldown이다.

```text
CRAWL_DETAIL_SOURCE_COOLDOWN_SOURCES=dcard,dcard_online
CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS=30
```

또는 challenge 이후에만 적용:

```text
CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS=30
```

이유:

- anti-bot 문서들이 공통적으로 rate/sequence/session/request pattern을 중요하게 본다.
- backoff-only가 현재 유일한 성공 후보였다.
- source-level cooldown은 비용이 거의 없고, proxy/persistent profile보다 운영 리스크가 낮다.

## 68. Anti-bot 추가 조사 2: JS challenge를 단일 오류로 보면 안 되는 이유

날짜: 2026-06-08

질문:

- 우리가 보는 `Cloudflare JS challenge`는 정확히 무엇인가?
- 이 문제가 `wait_until=load`, `override_navigator`, session reuse 같은 단일 옵션으로 해결될 수 있는가?
- 지금 비용 구조(EC2 1개, RDS 1개)에서 가장 먼저 해야 할 anti-bot 대응은 무엇인가?

참고 자료:

- Cloudflare Bot Detection Engines: https://developers.cloudflare.com/bots/concepts/bot-detection-engines/
- Cloudflare JavaScript Detections: https://developers.cloudflare.com/cloudflare-challenges/challenge-types/javascript-detections/
- Cloudflare Cookies: https://developers.cloudflare.com/fundamentals/reference/policies-compliances/cloudflare-cookies
- Cloudflare Challenge Solve Rate: https://developers.cloudflare.com/fundamentals/security/cloudflare-challenges/challenge-solve-rate
- Crawl4AI Anti-Bot & Fallback: https://docs.crawl4ai.com/advanced/anti-bot-and-fallback/
- Crawl4AI Complete SDK Reference: https://docs.crawl4ai.com/complete-sdk-reference/
- Crawl4AI Session Management: https://docs.crawl4ai.com/advanced/session-management/
- Crawl4AI Undetected Browser: https://docs.crawl4ai.com/advanced/undetected-browser/
- DataDome AI Threats Detection: https://docs.datadome.co/docs/ai-detection
- FP-Inconsistent paper: https://arxiv.org/abs/2406.07647

조사 내용:

1. Cloudflare bot detection은 여러 엔진을 조합한다.
   - 공식 문서는 heuristics, JavaScript detections, machine learning, anomaly detection 등을 설명한다.
   - ML 입력에는 headers, session characteristics, browser signals가 포함된다.
   - 따라서 `Cloudflare JS challenge`는 "JS가 늦게 로드됨" 하나만 뜻하지 않는다.
   - request pattern, browser signal, session cookie, IP 평판이 함께 영향을 줄 수 있다.

2. Cloudflare JavaScript Detections는 `cf_clearance` 결과와 WAF rule enforcement로 이어질 수 있다.
   - JS detection 결과는 cookie에 저장된다.
   - WAF rule이 그 결과를 보고 challenge/block을 걸 수 있다.
   - 즉 `wait_until=load`는 렌더링 완료 대기에는 의미가 있지만, 이미 challenge/block 판단이 난 상태를 근본적으로 해결하지 못한다.

3. Cloudflare는 `__cf_bm` cookie로 bot score를 안정화하고 false positive를 줄인다고 설명한다.
   - 이것은 session continuity가 의미 있을 수 있다는 근거다.
   - 하지만 우리 실험에서 session reuse 단독은 error 0을 만들지 못했다.
   - 따라서 session reuse는 단독 기본값이 아니라 backoff/cooldown 이후의 조합 실험 후보가 맞다.

4. Crawl4AI 문서도 anti-bot 사이트에서 403, CAPTCHA, empty page가 발생할 수 있고, layered fallback이 필요하다고 설명한다.
   - Crawl4AI에는 session management, user simulation, undetected browser 같은 옵션이 있다.
   - 그러나 Cloudflare/DataDome급 보호는 단순 옵션 하나로 안정화된다고 보기 어렵다.
   - 우리 코드가 blocking reason을 분류하고 source별 정책을 다르게 두는 방향은 문서와 맞다.

5. DataDome 문서도 headless browser, forged fingerprint, inconsistent browser fingerprint, data center IP reputation, residential proxy, free proxy 등을 탐지 항목으로 설명한다.
   - 이는 anti-bot 문제가 "프록시만 쓰면 해결"도 아니고 "브라우저 지문만 바꾸면 해결"도 아니라는 근거다.
   - 특히 품질 낮은 proxy나 어설픈 fingerprint 조작은 오히려 위험 신호가 될 수 있다.

6. FP-Inconsistent 연구는 evasive bot들이 fingerprint를 조작하면서도 속성 간 일관성을 유지하기 어렵다고 설명한다.
   - 우리 실험에서 `simulate_user + override_navigator`가 개선되지 않은 것은 이 방향과 맞다.
   - 어설픈 browser signal 조작은 기본값으로 두면 안 된다.

우리 실측과 맞춰 본 판단:

- concurrency를 올렸을 때 Dcard 계열 Cloudflare/403 오류가 늘었다.
- `simulate_user + override_navigator`는 개선되지 않았다.
- session reuse 단독도 개선되지 않았다.
- backoff-only는 한 번 error 0 결과를 만들었다.
- baseline repeat에서는 다시 challenge가 생겼다.

따라서 현재 가장 그럴듯한 원인은 다음 조합이다.

```text
Dcard 계열은 Cloudflare가 적용되어 있고,
짧은 시간 안의 반복 상세 접근/세션 상태/브라우저 신호/IP 상태가 합쳐져
간헐적인 JS challenge를 만든다.
```

지금 코드 방향 평가:

좋은 방향:

- detail fetch를 무작정 병렬화하지 않고 source별로 묶는다.
- Dcard/52pojie 같은 민감 source를 별도로 낮은 concurrency로 둔다.
- Cloudflare JS challenge를 별도 error reason으로 분리한다.
- challenge 전용 backoff retry를 opt-in으로 둔다.
- `wait_until=load`, fingerprint option, session reuse를 기본값이 아니라 실험 플래그로 둔다.

아직 부족한 부분:

- challenge가 발생한 source의 다음 URL까지 쉬게 하는 source-level cooldown이 없다.
- backoff retry가 "해당 URL" 중심이고, source 전체 요청 패턴 완화까지는 못 한다.
- session reuse 실패 시 session reset/kill 정책이 없다.
- crawl_stats에 challenge 발생 전후의 source order, attempt, elapsed, cooldown 적용 여부가 더 명확히 남으면 좋다.

현 시점 추천 순서:

1. 기본값은 계속 보수적으로 둔다.
   - proxy 없음.
   - undetected browser 없음.
   - fingerprint 조작 없음.
   - session reuse 기본 off.

2. 운영/실험 후보 1순위는 backoff다.

```text
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=1
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS=15
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SOURCES=dcard,dcard_online
```

3. 다음 코드 후보는 source-level cooldown이다.

```text
CRAWL_DETAIL_SOURCE_COOLDOWN_SOURCES=dcard,dcard_online
CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS=30
```

4. challenge 이후에만 쉬는 정책도 후보로 둔다.

```text
CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS=30
```

5. 그 다음에만 session reuse 조합을 실험한다.

```text
CRAWL_DCARD_SESSION_REUSE=1
CRAWL_DCARD_SESSION_ID_PREFIX=dcard-detail
```

6. persistent profile, UndetectedAdapter, 유료 proxy는 마지막 단계다.
   - 비용이 늘어난다.
   - 운영 상태가 오염될 수 있다.
   - 보안상 profile/cookie 관리 부담이 생긴다.
   - 탐지 회피 성격이 강해지고 유지보수가 어려워진다.

결론:

- `Cloudflare JS challenge`는 단순 load/wait 문제가 아니다.
- 현재 코드에서 `wait_until=load`를 켜는 것보다, source별 요청 압력을 낮추는 것이 더 근거 있다.
- 지금까지의 실측과 공식 문서 기준으로는 `backoff + source-level cooldown`이 가장 비용이 낮고 보안적으로 안전한 다음 단계다.
- proxy나 undetected browser는 "안 되면 마지막에 쓰는 비용 큰 옵션"이지, 지금 바로 기본 설계에 넣을 옵션은 아니다.

## 69. Anti-bot 조사 기반 코드 반영: source/challenge cooldown

날짜: 2026-06-08

반영 이유:

- Dcard 계열 Cloudflare JS challenge는 단순 렌더링 대기가 아니라 source별 요청 패턴/세션/브라우저 신호가 합쳐진 결과일 가능성이 높다.
- backoff retry는 해당 URL 재시도에는 도움이 되지만, challenge가 발생한 source의 다음 URL을 보호하지는 못한다.
- proxy, persistent profile, undetected browser는 비용/보안/유지보수 리스크가 크므로 아직 기본 설계로 넣지 않는다.

반영한 코드:

- `crawler/scripts/detail_priority_probe.py`
  - 상세 probe의 순차 site batch 경로에 source-level cooldown을 추가했다.
  - Cloudflare JS challenge 최종 실패 row 이후에는 challenge cooldown을 적용할 수 있게 했다.
  - probe plan 출력에 `source_cooldown`, `challenge_cooldown` 값을 표시한다.

- `crawler/src/scheduler/crawl_scheduler.py`
  - 운영 상세 fetch의 순차 경로에 source-level cooldown을 추가했다.
  - Dcard처럼 `detail_fetch_concurrency_for_site(site_id) == 1`인 source에 자연스럽게 적용된다.
  - Cloudflare JS challenge 최종 실패 이후 다음 URL 전에 더 긴 cooldown을 적용할 수 있게 했다.

새 환경변수:

```text
CRAWL_DETAIL_SOURCE_COOLDOWN_SOURCES=dcard,dcard_online
CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS=30
CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS=30
```

probe 전용 override:

```text
DETAIL_PROBE_SOURCE_COOLDOWN_SOURCES=dcard,dcard_online
DETAIL_PROBE_SOURCE_COOLDOWN_SECONDS=30
DETAIL_PROBE_CHALLENGE_COOLDOWN_SECONDS=30
```

기본값:

- `CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS=0`
- `CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS=0`
- 즉 기본 동작은 기존과 같다.

실험 추천 명령:

```bash
cd /Users/jmac/Desktop/261RCOSE45700 && \
DETAIL_PROBE_INPUT=output/dry_run_YYYYMMDD_HHMMSS.jsonl \
DETAIL_PROBE_MAX_P2=80 \
DETAIL_PROBE_52POJIE_P3=9 \
DETAIL_PROBE_MIXED_P3=15 \
DETAIL_PROBE_OTHER_P3=60 \
DETAIL_PROBE_DELAY_SECONDS=2 \
DETAIL_PROBE_SOURCE_COOLDOWN_SOURCES=dcard,dcard_online \
DETAIL_PROBE_SOURCE_COOLDOWN_SECONDS=30 \
DETAIL_PROBE_CHALLENGE_COOLDOWN_SECONDS=30 \
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=1 \
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS=15 \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

주의:

- cooldown은 수집 속도를 늦춘다.
- 대신 Cloudflare/anti-bot challenge를 줄일 가능성이 있고, 비용은 거의 없다.
- 이 실험도 error 0을 보장하는 우회책이 아니라 공개 접근 안정화 정책이다.

## 70. 운영 판단 변경: anti-bot 안정화보다 빠른 배치 우선

날짜: 2026-06-08

상황:

- Dcard 계열 Cloudflare JS challenge는 cooldown/backoff를 붙여도 안정적으로 해결되지 않았다.
- 755건 규모 detail probe에서 `concurrency=3`, sensitive group first, cooldown 조합은 시간이 너무 오래 걸린다.
- 현재 목표는 anti-bot 해결 자체가 아니라, 전체 후보를 빠르게 처리하고 실패 source는 실패로 기록하는 것이다.

판단:

- Dcard Cloudflare 문제는 더 붙잡지 않는다.
- proxy/undetected/persistent profile도 지금 단계에서는 쓰지 않는다.
- 막히는 source는 실패로 남기고, 나머지 source를 빠르게 batch 처리한다.
- cooldown/backoff는 실험용 opt-in으로만 유지한다.

코드 반영:

- `crawler/scripts/detail_priority_probe.py`에 `DETAIL_PROBE_FAST_MODE=1`을 추가했다.
- fast mode 기본값:
  - `DETAIL_PROBE_BATCH_BY_SITE`: false
  - `DETAIL_PROBE_CONCURRENCY`: 3
  - `DETAIL_PROBE_DELAY_SECONDS`: 2
- 의미:
  - site별 batch/순차 보호보다 예전 전역 worker 방식에 가깝게 돌린다.
  - 전체 wall-clock/latency를 우선한다.
  - Dcard/Dcard online Cloudflare 실패는 1~3건 수준이면 감수하고 summary에서 분리한다.
  - cooldown/backoff/session reuse는 켜지 않는다.

빠른 probe 명령:

```bash
cd /Users/jmac/Desktop/261RCOSE45700 && \
DETAIL_PROBE_FAST_MODE=1 \
DETAIL_PROBE_INPUT=output/dry_run_YYYYMMDD_HHMMSS.jsonl \
DETAIL_PROBE_MAX_P2=80 \
DETAIL_PROBE_52POJIE_P3=9 \
DETAIL_PROBE_MIXED_P3=15 \
DETAIL_PROBE_OTHER_P3=60 \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

명시적으로 꺼야 하는 것:

```text
DETAIL_PROBE_SOURCE_COOLDOWN_SECONDS
DETAIL_PROBE_CHALLENGE_COOLDOWN_SECONDS
DETAIL_PROBE_CLOUDFLARE_BACKOFF_RETRIES
DETAIL_PROBE_CLOUDFLARE_BACKOFF_SECONDS
CRAWL_DCARD_SESSION_REUSE
```

결론:

- Dcard anti-bot 안정화는 후순위로 미룬다.
- 현재는 fast mode의 예전 전역 worker 방식으로 전체 처리량과 latency를 먼저 회복한다.
- 실패 source는 summary에서 `fetch_error`로 분리해서 보고, dashboard/후처리에서 "접근 실패"로 다루는 쪽이 맞다.

비교 기준으로 삼을 과거 결과:

```text
output/detail_probe_20260607_030817.jsonl
rows=110
latency median_ms=3725 p95_ms=7894
dcard 1 error, dcard_online 1 error

output/detail_probe_20260607_120823.jsonl
rows=755
latency median_ms=4024 p95_ms=5976
dcard_online 3 error
```

따라서 목표는 "Dcard error 0"이 아니라 "전체는 빠르게 끝나고, Cloudflare 실패가 Dcard 계열 소수로 제한되는 상태"다.

## 71. 로컬 Mac과 EC2 실행 profile 분리

날짜: 2026-06-08

문제:

- 로컬 Mac에서는 `DETAIL_PROBE_CONCURRENCY=10`도 버틸 수 있다.
- 하지만 EC2 1대에서는 같은 값을 쓰면 CPU credit, memory, Chromium process 수 때문에 느려지거나 실패가 늘 수 있다.
- 특히 T 계열 EC2는 burstable CPU credit 구조라서 짧게는 빠르지만 오래 돌리면 CPU가 throttling될 수 있다.

참고 자료:

- AWS EC2 burstable CPU credits: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html
- AWS EC2 instance type specifications: https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-type-specifications.html
- AWS EC2 general purpose instances: https://docs.aws.amazon.com/ec2/latest/instancetypes/gp.html
- Crawl4AI multi-URL crawling: https://docs.crawl4ai.com/advanced/multi-url-crawling/

현재 코드 구조상 중요한 점:

1. `DETAIL_PROBE_FAST_MODE=1`
   - `DETAIL_PROBE_BATCH_BY_SITE=false`로 전역 worker queue를 탄다.
   - 각 worker가 `_probe_one()`을 호출한다.
   - `_probe_one()`은 `Crawl4AICrawler.fetch()`를 쓰고, 현재 `fetch()`는 호출마다 `AsyncWebCrawler` context를 연다.
   - 따라서 concurrency 10은 실제로 headless browser 작업을 최대 10개 가까이 동시에 밀 수 있다.

2. 운영 pipeline의 batch 경로
   - source별 fetch_targets가 있고 `fetch_many()`를 탈 수 있으면 Crawl4AI `arun_many()` + `MemoryAdaptiveDispatcher`를 쓴다.
   - dispatcher는 `memory_threshold_percent=85.0`, `max_session_permit=concurrency`로 설정되어 있다.
   - EC2 운영에서는 전역 worker 방식보다 이 경로가 더 안전하다.

3. Dcard/52pojie
   - 운영 기본값은 `CRAWL_DETAIL_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1`이다.
   - 이는 유지한다.
   - Dcard를 빠르게 만들려고 concurrency를 올리지 않는다.

권장 profile:

### Local fast profile

목적:

- Mac 로컬에서 빠르게 전체 후보 품질을 훑는다.
- Dcard/Dcard online Cloudflare 실패 1~3건은 감수한다.

```bash
cd /Users/jmac/Desktop/261RCOSE45700 && \
DETAIL_PROBE_FAST_MODE=1 \
DETAIL_PROBE_CONCURRENCY=10 \
DETAIL_PROBE_INPUT=output/dry_run_YYYYMMDD_HHMMSS.jsonl \
DETAIL_PROBE_MAX_P2=80 \
DETAIL_PROBE_52POJIE_P3=9 \
DETAIL_PROBE_MIXED_P3=15 \
DETAIL_PROBE_OTHER_P3=60 \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

성공 기준:

- median 3~5초대.
- p95 6~10초대.
- fetch_error가 Dcard/Dcard online 소수에 집중.
- Bahamut/PTT/Inven error가 늘지 않을 것.

### EC2 small profile

목적:

- EC2 1대에서 CPU/memory를 과하게 쓰지 않으면서 로컬 fast와 비슷한 처리 방향을 유지한다.
- 긴 실행에서 CPU credit 고갈과 Chromium memory pressure를 피한다.

```bash
cd /Users/jmac/Desktop/261RCOSE45700 && \
DETAIL_PROBE_FAST_MODE=1 \
DETAIL_PROBE_CONCURRENCY=4 \
DETAIL_PROBE_INPUT=output/dry_run_YYYYMMDD_HHMMSS.jsonl \
DETAIL_PROBE_MAX_P2=80 \
DETAIL_PROBE_52POJIE_P3=9 \
DETAIL_PROBE_MIXED_P3=15 \
DETAIL_PROBE_OTHER_P3=60 \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

EC2가 `t3.small`, `t4g.small`, `t3.medium`, `t4g.medium` 수준이면 먼저 4부터 시작한다.

### EC2 tiny/safe profile

목적:

- 메모리 1~2GiB 또는 CPU credit이 불안정한 환경에서 크롤러가 죽지 않게 한다.

```bash
cd /Users/jmac/Desktop/261RCOSE45700 && \
DETAIL_PROBE_FAST_MODE=1 \
DETAIL_PROBE_CONCURRENCY=2 \
DETAIL_PROBE_INPUT=output/dry_run_YYYYMMDD_HHMMSS.jsonl \
DETAIL_PROBE_MAX_P2=80 \
DETAIL_PROBE_52POJIE_P3=9 \
DETAIL_PROBE_MIXED_P3=15 \
DETAIL_PROBE_OTHER_P3=60 \
CRAWL_DRY_RUN_OUTPUT_DIR=output \
CRAWL4_AI_BASE_DIRECTORY=output/_crawl4ai_home \
.venv/bin/python crawler/scripts/detail_priority_probe.py
```

운영 pipeline 권장값:

```text
CRAWL_DETAIL_FETCH_CONCURRENCY=3
CRAWL_DETAIL_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
CRAWL_DETAIL_FETCH_STAGGER_SECONDS=0.25
CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS=0
CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS=0
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=0
```

EC2에서 더 빠르게 하고 싶을 때의 순서:

1. 먼저 후보 수를 줄인다.
   - `CRAWL_P3_DEFAULT_CAP_PER_BOARD`
   - `CRAWL_P3_MIXED_CAP_PER_BOARD`
   - `CRAWL_P3_52POJIE_CAP_PER_BOARD`
   - concurrency보다 후보 수 조절이 비용 절감 효과가 크다.

2. 안정 source만 concurrency를 올린다.
   - Dcard/Dcard online/52pojie는 1 유지.
   - Bahamut/PTT/Inven은 3~4까지 가능.

```text
CRAWL_DETAIL_FETCH_CONCURRENCY=4
CRAWL_DETAIL_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
```

3. EC2 metrics를 본다.
   - CPU utilization.
   - CPU credit balance/surplus credit.
   - memory 사용량.
   - Chromium process 수.
   - crawl latency p50/p95.
   - fetch_error site 분포.

4. 다음 조건이면 concurrency를 낮춘다.
   - p95가 급격히 증가한다.
   - timeout이 Dcard 외 source에서도 생긴다.
   - CPU credit이 계속 줄어든다.
   - 메모리 사용률이 80~85% 이상으로 유지된다.

결론:

- 로컬 Mac: `DETAIL_PROBE_CONCURRENCY=10` 가능.
- EC2 small: 먼저 `4`.
- EC2 tiny: `2`.
- 운영 기본: `CRAWL_DETAIL_FETCH_CONCURRENCY=3`.
- 가장 중요한 최적화는 concurrency를 무작정 올리는 것이 아니라, P3 budget과 source별 concurrency를 같이 조절하는 것이다.

## 72. Local fast profile 재실험 결과: concurrency 10

날짜: 2026-06-08

실행 성격:

- `DETAIL_PROBE_FAST_MODE=1`
- `DETAIL_PROBE_CONCURRENCY=10`
- `DETAIL_PROBE_BATCH_BY_SITE=false`
- cooldown/backoff/session reuse 없음
- 총 755건 detail probe

출력 파일:

```text
output/detail_probe_20260608_031537.jsonl
```

요약:

```text
rows=755

P2 total=48  real=48  real%=100.0 signal=38  signal%=79.2 error=0
P3 total=707 real=667 real%=94.3  signal=194 signal%=27.4 error=3

validator kinds:
real=715 sticky=23 short=6 unknown=4 empty=4 fetch_error=3

latency:
median_ms=4891 p95_ms=7693 max_ms=10231
```

source별 핵심:

```text
bahamut_aion2          72 total, 71 real, 32 signal, 0 error
bahamut_bns            69 total, 68 real, 23 signal, 0 error
bahamut_lineage        67 total, 64 real, 23 signal, 0 error
inven_maple            62 total, 62 real,  6 signal, 0 error
ptt                    54 total, 53 real, 19 signal, 0 error
dcard_online           15 total, 14 real,  8 signal, 1 error
dcard                  14 total, 11 real,  8 signal, 1 error
52pojie                 9 total,  1 real,  5 signal, 1 error
```

fetch error:

```text
cloudflare_js_challenge = 2
anti_bot_blocked        = 1

dcard        cloudflare_js_challenge=1
dcard_online cloudflare_js_challenge=1
52pojie      anti_bot_blocked=1 (HTTP 429 Too Many Requests)
```

과거 755건 결과와 비교:

```text
20260607_120823:
median_ms=4024 p95_ms=5976 max_ms=11784
fetch_error=3, 모두 dcard_online Cloudflare

20260608_031537:
median_ms=4891 p95_ms=7693 max_ms=10231
fetch_error=3, dcard/dcard_online/52pojie 각각 1
```

판단:

1. Local fast profile은 성공이다.
   - 755건 전체에서 fetch error가 3건뿐이다.
   - P2는 48/48 real, error 0이다.
   - 안정 source(Bahamut/PTT/Inven)는 error 0을 유지했다.

2. 실패는 우리가 감수하기로 한 source에 제한됐다.
   - Dcard/Dcard online Cloudflare JS challenge 각각 1건.
   - 52pojie HTTP 429 1건.
   - Bahamut/PTT/Inven 쪽으로 실패가 번지지 않았다.

3. latency는 예전 755건보다 조금 느려졌지만 허용 범위다.
   - median 4.0초대에서 4.9초로 증가.
   - p95 6.0초대에서 7.7초로 증가.
   - max는 10.2초로 오히려 낮아졌다.

4. 52pojie는 계속 별도 취급해야 한다.
   - 9건 중 real 1건.
   - signal은 5건이라 보안 텍스트는 많지만 게시글 real 검증 품질은 낮다.
   - 429도 발생했으므로 P3 cap은 낮게 유지한다.

확정 profile:

### Local fast

```text
DETAIL_PROBE_FAST_MODE=1
DETAIL_PROBE_CONCURRENCY=10
DETAIL_PROBE_BATCH_BY_SITE=false
```

목표:

- 대량 후보 품질 확인.
- Dcard/52pojie 소수 error 감수.
- Bahamut/PTT/Inven error가 0에 가까운지 확인.

### EC2 small start

```text
DETAIL_PROBE_FAST_MODE=1
DETAIL_PROBE_CONCURRENCY=4
DETAIL_PROBE_BATCH_BY_SITE=false
```

목표:

- local fast와 같은 실행 구조를 유지하되 headless browser 동시 실행 수를 낮춘다.
- EC2에서 CPU credit/memory pressure를 줄인다.

### 운영 pipeline

```text
CRAWL_DETAIL_FETCH_CONCURRENCY=3
CRAWL_DETAIL_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
CRAWL_DETAIL_FETCH_STAGGER_SECONDS=0.25
```

운영에서는 probe처럼 전역 worker 10개를 쓰지 않는다.
운영은 source별 batch와 `fetch_many()`/dispatcher 경로를 우선한다.

최종 결론:

- 로컬 검증은 `concurrency=10` fast profile로 간다.
- EC2 검증은 같은 fast profile이지만 `concurrency=4`부터 시작한다.
- 운영은 `CRAWL_DETAIL_FETCH_CONCURRENCY=3`과 source override를 유지한다.
- Dcard/52pojie 실패를 완전히 없애려 하지 않고, 실패 reason을 기록해 후처리에서 제외/재시도 대상으로 다룬다.

## 73. 운영 설정값 전체 재검토: 비용/성능/수집량 기준

날짜: 2026-06-08

질문:

- 운영에서 우리가 실제로 조정할 수 있는 설정값은 무엇인가?
- EC2 1대 + RDS 1대 조건에서 어떤 값을 기본으로 두는 것이 좋은가?
- 더 빠르게 하려면 어떤 순서로 값을 바꿔야 하는가?

참고 자료:

- Crawl4AI Browser/Crawler Config: https://docs.crawl4ai.com/core/browser-crawler-config/
- Crawl4AI Multi-URL Crawling: https://docs.crawl4ai.com/advanced/multi-url-crawling/
- Crawl4AI CLI config examples: https://docs.crawl4ai.com/core/cli/
- AWS EC2 burstable CPU credits: https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/burstable-credits-baseline-concepts.html
- AWS EC2 instance specifications: https://docs.aws.amazon.com/ec2/latest/instancetypes/ec2-instance-type-specifications.html
- AWS RDS pricing: https://aws.amazon.com/rds/pricing/
- AWS S3 pricing: https://aws.amazon.com/s3/pricing/
- AWS S3 storage classes: https://docs.aws.amazon.com/AmazonS3/latest/userguide/storage-class-intro.html

공식 문서에서 확인한 근거:

1. Crawl4AI `CrawlerRunConfig`
   - `wait_for`는 CSS/JS 조건 대기용이다.
   - `scan_full_page`, `scroll_delay`, `wait_until`, `page_timeout`, `delay_before_return_html`은 page interaction/latency에 직접 영향을 준다.
   - `max_retries`, `proxy_config`, `fallback_fetch_function`은 anti-bot/retry layer다.

2. Crawl4AI multi-URL
   - `RateLimiter`는 요청 간 random delay, max backoff, retry, 429/503 같은 rate-limit code 대응을 제공한다.
   - `MemoryAdaptiveDispatcher`는 동시 session 수와 memory threshold를 함께 다루는 구조다.
   - EC2 1대 운영에서는 단순 worker 10개보다 `fetch_many()` + dispatcher 경로가 더 안전하다.

3. AWS EC2
   - T 계열은 burstable CPU credit 구조라서 짧은 burst와 장시간 sustained load의 성능이 다르다.
   - headless browser concurrency를 로컬 Mac 기준으로 잡으면 EC2에서 CPU credit 또는 memory pressure가 생길 수 있다.

4. RDS/S3
   - RDS 비용은 DB instance hour, storage, backup, I/O 등이 핵심이다.
   - S3도 storage뿐 아니라 PUT/COPY/lifecycle transition/request 비용이 있다.
   - 작은 raw artifact를 무한히 많이 S3에 만들면 request/object overhead가 커질 수 있다.
   - raw body/image 장기 보관은 RDS보다 S3/local archive가 낫지만, retention과 object 수를 같이 관리해야 한다.

운영 설정값 분류:

### A. 수집량 budget

| env | 현재/기본 | 운영 권장 | 이유 |
|---|---:|---:|---|
| `MAX_POSTS_PER_BOARD` | `30` | `30` 유지 | listing 후보 폭 확보. 단 P3 budget으로 detail 수를 제어 |
| `CRAWL_PRIORITY_BUDGET_ENABLED` | `true` | `true` | 제목 hard filter 대신 priority budget 유지 |
| `CRAWL_P3_DEFAULT_CAP_PER_BOARD` | `1` | `1` | 일반 source P3 전수 fetch 방지 |
| `CRAWL_P3_MIXED_CAP_PER_BOARD` | `5` | `5` | Dcard/PTT mixed source exploration 보존 |
| `CRAWL_P3_52POJIE_CAP_PER_BOARD` | `1` | `1` | 52pojie는 signal은 있으나 real 품질 낮고 429 발생 |

운영 판단:

- 수집량을 늘리고 싶을 때는 `MAX_POSTS_PER_BOARD`보다 P3 cap을 먼저 조절한다.
- 52pojie cap은 올리지 않는다.
- mixed source에서 recall이 부족하면 `CRAWL_P3_MIXED_CAP_PER_BOARD=7` 정도만 실험한다.

### B. detail fetch concurrency

| env | 현재/기본 | 운영 권장 | 이유 |
|---|---:|---:|---|
| `CRAWL_DETAIL_FETCH_CONCURRENCY` | `3` | `3` 시작, EC2 여유 있으면 `4` | EC2 1대 + headless browser 기준 보수값 |
| `CRAWL_DETAIL_SOURCE_CONCURRENCY` | `dcard=1,dcard_online=1,52pojie=1` | 유지 | 민감 source는 serial |
| `CRAWL_DETAIL_FETCH_STAGGER_SECONDS` | `0.25` | `0.25` 유지 | batch 시작 시 한꺼번에 몰리는 것을 완화 |

운영 판단:

- EC2에서 먼저 쓸 값:

```text
CRAWL_DETAIL_FETCH_CONCURRENCY=3
CRAWL_DETAIL_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
CRAWL_DETAIL_FETCH_STAGGER_SECONDS=0.25
```

- EC2가 충분하면 다음만 1단계 올린다.

```text
CRAWL_DETAIL_FETCH_CONCURRENCY=4
```

- Dcard/Dcard online/52pojie는 계속 1로 둔다.

### C. anti-bot/retry/cooldown

| env | 현재/기본 | 운영 권장 | 이유 |
|---|---:|---:|---|
| `CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES` | `0` | `0` | Dcard 완전 회복보다 빠른 batch 우선 |
| `CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS` | `0` | `0` | latency 증가 방지 |
| `CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS` | `0` | `0` | cooldown은 효과 대비 너무 느림 |
| `CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS` | `0` | `0` | 실패는 기록하고 넘김 |
| `CRAWL_DCARD_SESSION_REUSE` | off | off | session reuse 단독 효과 없음 |
| `CRAWL_DCARD_WAIT_UNTIL_LOAD` | off | off | 403/Cloudflare 해결책 아님 |
| `CRAWL_DCARD_SIMULATE_USER` | off | off | 개선 근거 부족 |
| `CRAWL_DCARD_OVERRIDE_NAVIGATOR` | off | off | fingerprint inconsistency 리스크 |

운영 판단:

- Dcard/52pojie 실패 1~3건은 정상 운영 noise로 본다.
- retry/cooldown을 켜는 순간 latency가 늘고 EC2 자원을 묶는다.
- Cloudflare/429 실패는 별도 reason으로 저장해 후처리에서 제외하거나 별도 재시도 queue로 분리한다.

### D. listing/site pacing

| env | 현재/기본 | 운영 권장 | 이유 |
|---|---:|---:|---|
| `INTER_SITE_DELAY_SECONDS` | `15` | `10~15` | site 전환 시 부하 완화 |
| `INTER_BOARD_DELAY_SECONDS` | `3` | `2~3` | board 간 pacing |
| `CRAWL_INTERVAL_MINUTES` | `60` | `60` 유지 | EC2/RDS/LLM 비용 방어 |

운영 판단:

- 주기를 먼저 줄이지 않는다.
- 실행 시간이 60분에 가까워지면 주기를 줄이는 대신 P3 cap/detail concurrency를 조정한다.
- 빠른 탐지가 필요할 때만 특정 source 수동 trigger 또는 priority source 별도 job을 검토한다.

### E. Crawl4AI per-site 옵션

| 설정 | 운영 권장 | 이유 |
|---|---|---|
| `page_timeout` | site별로 유지, 너무 크게 올리지 않음 | timeout이 길면 EC2 worker가 묶임 |
| `wait_for` | 꼭 필요한 site만 | 잘못 걸면 45~60초 timeout |
| `wait_until` | 기본 off/`domcontentloaded` 계열 우선 | `networkidle/load`는 latency 증가 가능 |
| `delay_before_return_html` | Dcard/SPA 등 필요한 site만 | 전체 적용 금지 |
| `scan_full_page` | 필요한 site만 | scroll은 latency/CPU 증가 |
| `proxy` | 기본 off | 비용/보안/법무 리스크 |
| `download_images` | detail probe/운영 기본 text 우선 | 이미지 저장은 S3/RDS/네트워크 비용 증가 |

운영 판단:

- 이미 접근 가능한 Inven/PTT/Bahamut은 proxy/fingerprint 옵션을 추가하지 않는다.
- Dcard는 실패를 줄이려고 무거운 옵션을 켜지 않는다.
- image/OCR은 LLM 후보가 확정된 뒤 2차 단계로 분리한다.

### F. 저장/비용

| 설정 | 운영 권장 |
|---|---|
| `ENABLE_S3_UPLOAD` | 초기 운영은 `false` 또는 text-only |
| `S3_BUCKET_NAME` | S3 활성 시 필수 |
| RDS raw body 저장 | 장기적으로 metadata/summary 중심으로 축소 |
| 이미지 저장 | 기본 off, 필요 시 selected/high-risk만 |
| retention | local raw/log는 짧게, S3 archive는 lifecycle 적용 |

운영 판단:

- RDS는 dashboard query와 detection summary 중심으로 둔다.
- raw text/image를 RDS에 오래 쌓지 않는다.
- S3를 쓰더라도 작은 object 대량 생성과 lifecycle transition 비용을 고려한다.

권장 운영 profile:

```text
MAX_POSTS_PER_BOARD=30
CRAWL_PRIORITY_BUDGET_ENABLED=true
CRAWL_P3_DEFAULT_CAP_PER_BOARD=1
CRAWL_P3_MIXED_CAP_PER_BOARD=5
CRAWL_P3_52POJIE_CAP_PER_BOARD=1

CRAWL_DETAIL_FETCH_CONCURRENCY=3
CRAWL_DETAIL_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
CRAWL_DETAIL_FETCH_STAGGER_SECONDS=0.25

CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=0
CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS=0
CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS=0

INTER_SITE_DELAY_SECONDS=15
INTER_BOARD_DELAY_SECONDS=3
CRAWL_INTERVAL_MINUTES=60

ENABLE_S3_UPLOAD=false
```

EC2에서 더 빠르게 하는 순서:

1. `CRAWL_DETAIL_FETCH_CONCURRENCY=4`로 1단계만 올린다.
2. Dcard/52pojie source override는 유지한다.
3. p95 latency, timeout, CPU credit, memory를 본다.
4. 안정적이면 `CRAWL_P3_MIXED_CAP_PER_BOARD=7`을 실험한다.
5. 그래도 부족하면 source 추가/검색 API/GitHub adapter를 늘린다.

절대 먼저 하지 말 것:

- Dcard/52pojie concurrency 올리기.
- cooldown/backoff 기본 on.
- wait_until/load 전역 적용.
- scan_full_page 전역 적용.
- proxy 전역 적용.
- 이미지/OCR 전수 저장.

최종 판단:

- 운영은 로컬 probe처럼 worker 10이 아니라 `fetch_many()`/dispatcher 중심의 source별 batch가 맞다.
- 현재 가장 좋은 운영 기본값은 concurrency 3, 민감 source 1, P3 cap 유지다.
- 수집량 확대는 concurrency보다 source 확장과 P3 budget 조절로 한다.
