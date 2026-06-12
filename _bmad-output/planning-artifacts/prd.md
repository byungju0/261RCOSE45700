---
stepsCompleted: ['step-01-init', 'step-02-discovery', 'step-02b-vision', 'step-02c-executive-summary', 'step-03-success', 'step-04-journeys', 'step-05-domain', 'step-06-innovation', 'step-07-project-type', 'step-08-scoping', 'step-09-functional', 'step-10-nonfunctional', 'step-11-polish', 'step-12-complete']
completedAt: '2026-04-24'
status: complete
inputDocuments: ['tracker_기획서.md', '_bmad-output/brainstorming/brainstorming-session-2026-04-24-1430.md']
workflowType: 'prd'
classification:
  projectType: web_app
  domain: scientific+general
  complexity: high
  projectContext: brownfield
---

# Product Requirements Document - Tracker

**Author:** Tracker
**Date:** 2026-04-24

## Executive Summary

Tracker는 NC AI 게임 보안 담당자를 위한 자동화된 불법 프로그램 유포 탐지 시스템이다. 한국·중국·대만 커뮤니티 게시판 7개 부모 사이트 + 검색엔진 8개 (총 **15개 데이터 소스**) 를 1시간 주기로 자동 크롤링하고, **OpenAI 멀티모달 LLM(GPT-4o/4.1) 파이프라인**을 통해 다국어 텍스트 및 이미지 게시글을 통합 탐지하여 React 대시보드에 목록화한다. 담당자는 대시보드에서 탐지 게시글 목록을 확인하고 원본 URL로 즉시 이동해 조치를 취한다. <!-- 2026-05-19 Epic 2 PIVOT 반영: "최대 6개" → 게시판 7 부모(인벤·PTT·Dcard·Bahamut + 52pojie·tieba·nga) + 검색 8(github/reddit/bing/duckduckgo_cn/baidu/sogou/bilibili/facebook) = 15. 자세한 우선순위 표는 Product Scope → 데이터 소스 섹션 참조. -->

**문제:** 게임 치트 경제 규모 약 85억 달러(Intorqa, 2026) 수준으로 성장하며, PC 게이머 80%가 치터를 경험한다. 기존 anti-piracy 솔루션(MUSO, Irdeto)은 영상·음악 저작권 침해에 특화되어 있고, 게임 불법 프로그램 유포 채널(한·중 커뮤니티)을 실시간으로 커버하는 솔루션은 공백 상태다. 수동 모니터링으로는 다국어 대응과 이미지 우회 탐지가 불가능하다.

**해결:** 크롤러 + 전처리 + OpenAI 멀티모달 LLM 파이프라인의 End-to-End 자동화로, 담당자가 사이트를 직접 순회하지 않고 단일 대시보드에서 불법 게시글 목록을 확인하고 처리할 수 있도록 한다. <!-- 2026-05-27 PIVOT: VARCO Translation+LLM+Vision 3단 → OpenAI 멀티모달 단일 호출 + Tier 차등. -->

### What Makes This Special

기존 솔루션과의 결정적 차이는 세 가지다:

1. **다국어 + 이미지 동시 탐지:** OpenAI 멀티모달 LLM(GPT-4o/4.1)이 텍스트·이미지·언어(한국어 / 간체 / 번체)를 통합 분석한다. 2026-05-27 PIVOT으로 VARCO Translation+LLM+Vision 3단 파이프라인을 멀티모달 LLM 호출로 교체했고, 2026-06-11 재정의로 이를 **비용 차등 다단계 에이전트**(저비용 트리아지 → 조건부 심층 분석 → 증거 통합)로 확장했다. 자세한 결정은 `sprint-change-proposal-2026-06-11.md` 참조.

2. **도메인 특화 고정확도:** 게임 불법 프로그램 게시글은 가격 명시, 텔레그램 유도, 매크로·핵 은어(外挂, 破解) 패턴이 명확하여 범용 콘텐츠 모더레이션(OpenAI Moderation API F1 0.77) 대비 높은 정확도(목표 Precision ≥ 0.85)가 현실적으로 달성 가능하다.

3. **조치 중심 워크플로우:** 탐지 결과를 "왜 불법인가" 설명 중심이 아닌 "어떤 게시글이, 어느 사이트에" 목록 중심으로 제공. 원본 URL 직접 링크로 담당자의 조치 흐름을 단절 없이 연결한다.

## Project Classification

| 항목 | 값 |
|------|-----|
| **프로젝트 유형** | Web App (React SPA 대시보드 + Java Spring REST API + Python AI 데이터 파이프라인) |
| **도메인** | 게임 보안 / AI-ML 탐지 시스템 |
| **복잡도** | High — 분산 AWS 인프라(EC2 ×3, S3, RDS, Redis), 다국어 처리, 외부 OpenAI API + Tier 차등 처리 |
| **프로젝트 컨텍스트** | Brownfield — 기획서 및 기술 결정 사항(아키텍처 옵션 A, Playwright+stealth, NodeMaven 단계별 전략) 완비 |
| **협력 기업** | NC AI (게임 보안 도메인 자문) <!-- 2026-05-27 PIVOT: VARCO API 의존 제거. LLM은 OpenAI 직접 계약. --> |
| **개발 기간** | 11주 (2026년 4월 기준) |

## Success Criteria

### User Success

- 담당자가 대시보드에서 탐지 목록 확인 → 원본 URL 클릭 → 즉시 조치의 3단계 워크플로우가 단절 없이 완성된다.
- 날짜·사이트·유형 필터를 조합하여 원하는 탐지 게시글을 30초 이내에 검색할 수 있다.
- 탐지 목록에 표시된 게시글의 85% 이상이 실제 불법 게시글이어서 담당자가 결과를 신뢰하고 조치에 활용한다.

### Business Success

- NC AI 최종 발표 시연에서 명확한 불법 게시글(가격·연락처 명시) 10건 이상을 실시간 탐지하는 데모를 성공시킨다.
- 크롤링 자동화: 1시간 주기 무중단 운영, 발표 기간 포함 24시간 이상 안정 운영을 입증한다.
- 탐지 대상 사이트: MVP 최소 2개 안정 수집 확인, 목표 4개 이상 연결 성공.

### Technical Success

- End-to-End 파이프라인(크롤링 → 전처리 → 멀티모달 LLM 분류 + Tier 라우팅 → RDS → 대시보드)이 수동 개입 없이 자동 실행된다.
- 1회 배치 처리 시간 ≤ 30분.
- 크롤링 완료 후 대시보드 반영 지연 ≤ 5분.
- DLQ 알람 정상 작동: 실패 메시지 3회 재시도 후 `posts:dlq` 격리 및 Grafana 알람 발생 확인.

### Measurable Outcomes

| 지표 | 목표값 | 측정 방법 |
|------|--------|-----------|
| **Precision (전체)** | ≥ 0.85 | 라벨셋 ≥ 300건 (Tier별 ≥ 75건) — 2026-05-27 PIVOT 갱신 |
| **Recall (T1 Critical)** | ≥ 0.85 | 핵·치트 / 사설서버 / 불법 프로그램·봇 배포 — 사업 가치 핵심 |
| **Recall (T2 High)** | ≥ 0.70 | 계정 거래 / 매크로 판매 |
| **Recall (T3 Medium)** | ≥ 0.55 | 리세마라 / 현금화 / 광고 도배 |
| **Tier별 confusion matrix** | 측정 필수 | Tier 오분류(T2→T1 / T1→T2 등)도 사업 위험 |
| **게시글당 평균 비용 (USD)** | 평균 ≤ $0.005, **p95 ≤ $0.02** | 이미지 첨부 유/무 분리 집계. **일일 비용 cap + 게시글당 예산 cap 환경변수 적용** (2026-06-11: 멀티 에이전트 escalate 게시글의 꼬리 비용을 p95로 분리 명시) |
| **F1** | (참고값) | Tier별 산출 — 단독 목표 아님 |
| **명확 케이스 정탐율** | ≥ 90% | 가격·텔레그램·매크로 명시 게시글 — 발표 시연 핵심 지표 |
| **배치 처리 시간** | ≤ 30분 | 배치 시작~종료 로그 차이 |
| **대시보드 반영 지연** | ≤ 5분 | 크롤링 완료 시각 → 대시보드 업데이트 시각 |
| **운영 안정성** | 24시간 무중단 | APScheduler 실행 로그 확인 |

## Product Scope

### 데이터 소스 (2026-05-19 PIVOT 반영)

총 **15개 데이터 소스** = 게시판형 7 부모 사이트 + 검색엔진형 8 사이트. 게시판형은 `SiteConfig` 추상화 (board → post 1-hop), 검색엔진형은 `SearchEngineConfig` 추상화 (query → SERP → 외부 링크 2-hop) 로 처리. 출력은 모두 `CrawlEvent` 동일 — 다운스트림 탐지 파이프라인 무영향.

#### 게시판형 (Stories 2-1~2-7, 코드 정착 완료 — 142 PASS)

| 우선순위 | 부모 사이트 | 지역 | 구현 실수 | 비고 |
|---|---|---|---|---|
| P0 | **Bahamut** | 대만 | 8 NC 게임 보드 (Lineage / Lineage M / Lineage W / Lineage Classic / Aion / Aion2 / BNS / TL) | 모두 순수 NC. `title_keywords` 불필요. 최우선 데이터 소스 |
| P0 | **인벤 (Lineage Classic)** | 한국 | 1 보드 | NC 직접 관련 |
| P1 | **PTT** | 대만 | 2 보드 (Lineage 순수 NC + Mobile-game 혼합) | 18세 인증 게이트 자동 통과 |
| P1 | **Dcard** | 대만 | 2 보드 (game / online — 모두 혼합) | React SPA, `title_keywords=_NC_GAME_KEYWORDS` 필터 |
| P2 | **인벤 (메이플)** | 한국 | 1 보드 | NEXON 비교군 — 운영 valid 검증용 |
| P3 | **52pojie** | 중국 | 1 보드 | Cloudflare 보호, stealth + zh-CN UA 통과. 프록시 옵션 |
| P3 (disabled) | **tieba** | 중국 | 2 보드 (游戏外挂 / 手游辅助) | **Bright Data CN PoC 실패 (2026-05-20)** — proxy 라우팅·중국 IP 발급은 정상이나 Baidu anti-bot 이 stealth Chromium까지 HTTP 403. 추가로 민감 키워드 검색은 중국 본토 휴대폰·실명 인증 계정 필수 → 대체 proxy/우회 경로 검토 전까지 `registry.enabled=False` |
| P3 (disabled) | **NGA** | 중국 | 1 보드 (fid=489) | **Bright Data CN PoC 실패 (2026-05-20)** — `ERR_TUNNEL_CONNECTION_FAILED` (NGA 가 proxy 패턴 자체 차단 추정). ngaPassportUid 쿠키 필수 + 계정 가입에 중국 본토 휴대폰·실명 인증 → 대체 proxy 검토 전까지 `registry.enabled=False` |

#### 검색엔진형 (Stories 2-8~2-12, Epic 3 완료 후 착수 — backlog)

| 우선순위 | 사이트 | 지역 | 도전 난이도 | 비고 |
|---|---|---|---|---|
| P0 (추상화 검증) | **github** | 글로벌 | 낮음 | `SearchEngineConfig` 첫 도전, 추상화 모델 검증용 |
| P1 | **reddit** | 글로벌 | 낮음 | 글로벌 NC 정보 유통 |
| P1 | **bing** | 글로벌 (중국 콘텐츠 우회) | 중간 | 중국 콘텐츠의 글로벌 유통 우회 링크 |
| P1 | **duckduckgo_cn** | 글로벌 | 낮음 | 추적 회피 검색엔진, CN 쿼리 특화 |
| P2 | **facebook** (via Bing) | 글로벌 | 높음 | Facebook 자체 검색 API 제약 → Bing `site:facebook.com` 우회 |
| P3 (proxy 선결) | **baidu** | 중국 | 높음 | 중국 1위 검색엔진, 중국 residential proxy 필수 |
| P3 (proxy 선결) | **sogou** | 중국 | 높음 | 중국 검색엔진, 중국 residential proxy 필수 |
| P3 (proxy 선결) | **bilibili** | 중국 | 높음 | 영상 메타데이터 + 설명. 중국 residential proxy 필수 |

#### 진행 트랙

1. **트랙 A (즉시 운영 가능)**: P0~P1 게시판형 (Bahamut + 인벤 + PTT + Dcard) — 외부 contract 호환 검증 완료, 142 PASS
2. **트랙 B (proxy 선결 필요)**: P3 게시판형 (tieba·NGA `registry.enabled=False` — 2026-05-20 Bright Data PoC 실패 후 대체 proxy/우회 검토, 52pojie 일부) + P3 검색엔진형 (baidu, sogou, bilibili) — **중국 residential proxy 인프라 트랙** 완료 후 활성화
3. **트랙 C (Epic 3 완료 후)**: P0~P2 검색엔진형 (github, reddit, bing, duckduckgo_cn, facebook) — `SearchEngineConfig` 추상화 신설 (Story 2-8) 부터 시작
4. **트랙 D (Known issues — 단발 fix)**: `dcard_online` `wait_for=css:article` 타임아웃, `ptt_mobile_game`·`dcard /f/game` 페이지네이션 또는 deprioritize

---

### MVP - Minimum Viable Product

크롤링 → 전처리(URL 중복·content 중복·content_validator 품질 가드·serialize) → **멀티모달 LLM 분류 + Tier 라우팅** → RDS 저장 → React 대시보드 표시까지의 End-to-End 탐지 파이프라인을 자동 실행한다. <!-- 2026-05-27 PIVOT: VARCO Translation + VARCO LLM 2단 → OpenAI 멀티모달 LLM 단일 호출. language_detector 폐기, 멀티모달 LLM이 텍스트+이미지+다국어 통합 처리. 자세한 결정은 sprint-change-proposal-2026-05-27.md 참조. --> <!-- 2026-05-19 PIVOT: 전처리 단계 갱신 (html_parser·keyword_filter 제거, content_validator + url_dedup_checker + serializer 신규). 본문 키워드 매칭은 LLM (Epic 3) 로 위임. -->

- 크롤링: Playwright + stealth, ProxyBroker(개발), APScheduler 1시간 주기
- 전처리: Crawler EC2 인라인 수행 (옵션 A)
- AI: OpenAI 멀티모달 LLM(GPT-4o + GPT-4o-mini) **비용 차등 다단계 에이전트** — 트리아지(저비용) → 조건부 이미지/링크 심층 분석 → 증거 통합 → Tier 분류 (2026-06-11 재정의; 2026-05-27 단일 호출에서 확장)
- 백엔드: Java Spring REST API + Redis MQ + RDS PostgreSQL
- 대시보드: 탐지 목록 / 상세 / 통계 화면
- 인프라: AWS EC2 ×3, S3, RDS, Redis (t3.medium 기준) <!-- 2026-04-24 PRD freeze 시점 사양. 실 deployment는 2026-05-09 3차 PIVOT으로 **단일 t3.xlarge 16GB**로 회귀 — architecture.md / 기획서 2.1.1.a 참조 -->

### Growth Features (Post-MVP)

- ~~**VARCO Vision 이미지 탐지**~~ — **MVP 편입 (2026-05-27 PIVOT)**. 멀티모달 LLM(GPT-4o)이 텍스트+이미지+다국어 통합 처리하므로 별도 Vision 단계 불필요.
- ~~**BERT 2차 필터**~~ — **보류 (2026-05-27 PIVOT)**. 멀티모달 LLM 단가 통제가 가능하면 사전 필터링 필요성 낮음. 일일 비용 cap 운영 데이터로 재검토.
- **프록시 업그레이드:** ProxyBroker → NodeMaven(중국 IP 전문, ~$50~80/월). 중국 사이트 차단율 실측 후 도입 시점 결정. <!-- 2026-05-19 PIVOT: tieba·NGA·52pojie 한국 IP HTTP 403 확인, 검색엔진 baidu·sogou·bilibili도 동일 패턴 예상. 본 트랙 활성화는 중국 residential proxy 선결 필요. -->
- **검색엔진형 데이터 소스 (Stories 2-8~2-12):** github, reddit, bing, duckduckgo_cn, facebook (글로벌) + baidu, sogou, bilibili (중국 proxy 선결) — `SearchEngineConfig` 추상화 신설 후 단계적 활성화. Epic 3 (탐지 파이프라인) 안정화 후 착수. 자세한 우선순위는 `### 데이터 소스` 섹션 표 참조.
- **수동 크롤링 트리거:** `POST /crawl/trigger` — 관리자 즉시 실행 API.
- **실시간 알림:** 신뢰도 0.95 이상 고위험 탐지 시 Slack·이메일 즉시 알림.

### Vision (Future)

- **NC 타이틀 전체 적용:** 리니지·블레이드앤소울·쓰론앤리버티 등 타이틀별 탐지 키워드·LLM 프롬프트 커스터마이징.
- **탐지 채널 확장:** 디스코드 서버, 텔레그램 채널, 레딧 등 신규 유포 채널 추가.
- **Class-RAG 자동 개선:** pgvector 기반 유사 탐지 사례 검색으로 모호 케이스 정확도 지속 개선 (재학습 불필요).

## User Journeys

### Journey 1: 보안 담당자 — 일상 모니터링 (Primary Success Path)

**페르소나:** 김민준, NC AI 게임 보안 팀 담당자. 리니지 시리즈 담당으로 매일 오전 한국·중국 불법 프로그램 커뮤니티를 직접 검색해왔다. 중국어는 구글 번역을 써도 게임 은어는 놓치기 일쑤였고, 이미지로만 올라온 판매 게시글은 아예 탐지가 불가능했다.

**Opening — 기존 고통:** 월요일 오전, 민준은 tailstar.net을 열고 수백 개 게시글 중 불법 판매 게시글을 직접 클릭해가며 확인한다. 중국 포럼은 언어 장벽에 막혀 넘어가기가 어렵다. 하루에 2~3시간이 이 작업에 소요된다.

**Rising Action — 첫 사용:** Tracker 대시보드에 접속한다. 오늘 탐지 수, 사이트별 분포 차트가 즉시 보인다. tailstar.net에서 탐지된 게시글 12건, tieba.baidu.com에서 3건. 사이트 필터를 tailstar.net으로 좁히고 "매크로 판매" 유형을 클릭한다.

**Climax — 가치 전달 순간:** 목록에서 게시글 하나를 클릭한다. 원문(한국어), 번역문(원본이 중국어인 경우), 탐지 유형, 신뢰도 0.91이 표시된다. 출처 URL을 클릭하자 tailstar.net 원본 게시글로 바로 이동한다. 민준은 신고 처리를 즉시 완료한다. 직접 검색하던 2~3시간이 15분으로 줄었다.

**Resolution — 새 현실:** 매일 아침 대시보드를 열어 탐지 목록을 확인하고 조치하는 것이 루틴이 됐다. 중국 포럼도 번역된 채로 목록에 올라와 더 이상 언어 장벽이 없다.

**→ 드러나는 요구사항:** 탐지 목록 조회(필터), 탐지 상세(원문·번역·신뢰도), 원본 URL 링크, 대시보드 통계 차트

---

### Journey 2: 보안 담당자 — 긴급 대응 (Edge Case)

**상황:** NC 신작 게임 오픈 베타 당일, 불법 매크로 판매 게시글이 급증하고 있다는 제보가 들어왔다. 다음 자동 크롤링까지 45분이 남아 있다.

**Opening:** 민준은 Tracker 대시보드를 열지만 최신 게시글이 아직 반영되지 않았다.

**Rising Action:** 관리자 메뉴에서 "즉시 크롤링" 버튼을 누른다. `POST /crawl/trigger` 요청이 발송되고 진행 상태가 표시된다.

**Climax:** 8분 후 크롤링이 완료되고 탐지 목록이 업데이트된다. 오늘 날짜 필터로 신규 게시글 23건이 확인된다. 그 중 "매크로 판매" 16건, "계정 거래" 4건.

**Resolution:** 신뢰도 0.90 이상 게시글 16건에 대해 원본 URL을 열어 순차적으로 신고 처리한다. 오픈 베타 첫날 불법 프로그램 게시글 대응을 당일 완료.

**→ 드러나는 요구사항:** 수동 크롤링 트리거 API, 크롤링 진행 상태 표시, 날짜 필터, 신뢰도 정렬

---

### Journey 3: 보안 팀장 — 주간 현황 보고 (Operations User)

**페르소나:** 이수현, 게임 보안 팀장. 주간 회의에서 불법 프로그램 현황을 경영진에게 보고해야 한다. 기존에는 담당자에게 수동으로 집계를 요청했다.

**Opening:** 매주 금요일 오전, 이수현은 Tracker 통계 화면을 연다.

**Rising Action:** 주간 탐지 추이 차트에서 월~금 탐지 수 변화를 확인한다. 사이트별 비교 차트에서 tailstar.net이 전체의 61%를 차지함을 파악한다. 유형별 분포에서 매크로 판매가 급증 추세임을 발견한다.

**Resolution:** 차트 화면을 캡처해 주간 보고서에 첨부한다. 집계 요청 없이 5분 만에 보고 자료 준비 완료.

**→ 드러나는 요구사항:** 통계 화면(주간·월간 추이 차트, 사이트별·유형별 분포)

---

### Journey Requirements Summary

| 여정 | 드러난 핵심 기능 |
|------|-----------------|
| 일상 모니터링 | 탐지 목록(필터), 탐지 상세(원문·번역·신뢰도), 원본 URL 링크, 대시보드 |
| 긴급 대응 | 수동 크롤링 트리거, 크롤링 진행 상태, 날짜 필터, 신뢰도 정렬 |
| 주간 보고 | 통계 화면(추이·사이트별·유형별 차트) |

## Domain-Specific Requirements

### 크롤링 윤리 및 법적 제약

- 대상 사이트의 `robots.txt` 및 이용약관을 사전 확인하고, 크롤링 속도를 제어하여 대상 서비스에 과도한 부하를 주지 않는다.
- 수집된 게시글 텍스트·이미지는 탐지 목적으로만 사용하며, 제3자 제공 및 외부 공개를 금지한다.

### 탐지 오류(False Positive) 관리

- 탐지 결과는 판단 보조 자료이며, 최종 조치 결정은 담당자 검토를 거친다.
- **Tier별 차등 신뢰도 임계값** 적용: T1=0.65, T2=0.75, T3=0.85, T4=0.90 또는 inactive (2026-05-27 PIVOT — 단일 0.70 임계값 폐기).
- T1 Critical false positive 시 무고한 사용자 대상 알림을 막기 위해 운영 단계에서 **사람 리뷰 큐**(human-in-the-loop)를 경유하여 발송. 구체 워크플로우는 별도 정의.

### 데이터 보관 정책 (2026-05-27 Tier 기반 갱신)

- **T1 Critical:** 원본(텍스트+이미지) 영구 보존
- **T2 High / T3 Medium / T4 Low:** 원본 90일 보존 후 archive (집계 통계만 잔류) — 2026-05-27 PIVOT post-approval: T4 "즉시 폐기" → "90일 보존". 크롤 볼륨이 낮으므로 전수 보존이 디버깅·라벨셋 확장·오탐 분석에 유리. 운영 데이터 누적 후 폐기 주기 재검토.
- **`is_illegal=false` 결과도 저장**: 합법 게시글 분류 결과를 같은 보존 기간으로 유지 (오탐 분석 + Recall 측정의 분모로 활용)
- 이미지에 사용자 캐릭터명 등 PII 포함 가능성 → OpenAI 외부 전송 정책은 **법무 확인 필요** (미해결, Risks 섹션 참조).

## Innovation & Novel Patterns

### 감지된 혁신 영역

**1. 게임 도메인 특화 다단계 AI 탐지 파이프라인**

기존 anti-piracy 솔루션(MUSO, Irdeto)은 영상·음악 저작권 침해에 특화되어 있으며, 게임 불법 프로그램 유포 탐지를 위한 특화 파이프라인은 공백 상태다. Tracker는 OpenAI 멀티모달 LLM(GPT-4o/4o-mini)에 게임 도메인 추론을 결합한 **비용 차등 다단계 에이전트**(트리아지 → 조건부 이미지/링크 심층 분석 → 증거 통합)로 다국어·텍스트·이미지·외부 링크를 통합 처리하는 게임 보안 특화 탐지 시스템을 구현한다. 게시글의 게임·맥락을 에이전트가 자가 추론하므로 사이트별 설정 없이 새 데이터 소스에 적응한다. <!-- 2026-06-11 재정의: 단일 호출 → 멀티 에이전트. 2026-05-27 PIVOT: VARCO 3단 → 멀티모달 단일 호출 -->

**2. 멀티모달 LLM을 활용한 텍스트 우회 + Tier 차등 탐지**

텍스트 탐지를 회피하기 위해 판매 정보를 이미지로만 업로드하는 전략이 게임 불법 프로그램 유포 채널에서 확산되고 있다. OpenAI 멀티모달 LLM(GPT-4o/4.1)이 이미지 속 텍스트와 본문을 단일 컨텍스트로 통합 분석하여 우회 게시글을 탐지한다. 더 나아가 Tier(T1 Critical / T2 High / T3 Medium / T4 Low) 차등 처리로 핵·사설서버 등 사업 핵심 카테고리의 Recall에 자원을 집중한다.

### 경쟁 환경 및 시장 맥락

| 구분 | 기존 솔루션 | Tracker |
|------|------------|---------|
| 대상 | 영상·음악 저작권 | 게임 불법 프로그램 유포 |
| 언어 | 주로 영어권 | 한국어 + 중국어·대만 번체 |
| 탐지 방식 | 텍스트 기반 | 텍스트 + 이미지 단일 멀티모달 LLM + Tier 차등 |
| 도메인 이해 | 범용 | 게임 은어·매크로·핵 특화 |

### 검증 접근법

- **LLM 탐지 정확도:** 라벨셋 ≥ 300건 (Tier별 ≥ 75건)으로 Tier별 Precision/Recall 측정. 멀티모달 LLM 단일 호출 결과 기준 — 2026-05-27 PIVOT으로 BERT 2차 필터는 보류.
- **멀티모달 이미지 탐지:** 이미지 첨부 게시글을 라벨셋에 포함하여 단일 LLM 호출 정탐율 측정. (VARCO Vision 별도 검증 단계 제거)
- **시연 검증:** NC AI 발표 시 명확 케이스(가격·연락처 명시) ≥ 10건 실시간 탐지 데모.

### 리스크 및 완화 (2026-05-27 갱신)

| 리스크 | 완화 전략 |
|--------|-----------|
| LLM이 게임 은어를 오판 | Tier별 차등 임계값 적용 (T1=0.65, T4=0.90). T1 false positive는 사람 리뷰 큐 경유. |
| 중국 사이트 차단율 높아 데이터 부족 | ProxyBroker → NodeMaven 단계별 전략, 대만(PTT·Dcard) GFW 회피 병행 |
| ~~VARCO Vision 이미지 탐지 미도입 시~~ | 해소 — 멀티모달 LLM(GPT-4o)이 텍스트+이미지 통합 처리로 MVP 흡수 |
| ~~BERT 추가 없이 LLM만으로 정확도 부족~~ | 보류 — 일일 비용 cap 운영 데이터로 재검토 |
| **OpenAI 단일 vendor 의존** | 수용 리스크. 비용 cap 환경변수 + 일일 모니터링이 1차 통제. 가용성 장애 시 큐 대기(Hold) 후 복구 — 데이터 유실 없음. |
| **OpenAI 비용 폭증 (이미지 토큰 단가)** | PoC 단가 측정 후 일일 비용 cap 설정. T4 inactive 처리로 호출량 감축. |
| **T1 false positive 시 무고한 사용자 알림** | 운영 단계 사람 리뷰 큐 경유. 자동 알림 직결 금지. |
| **이미지 PII OpenAI 전송 컴플라이언스** | 법무 확인 필요 — 결과에 따라 이미지 마스킹 또는 텍스트-only fallback 적용 가능. PoC 전 결정 권장. |
| **번역 품질 — OpenAI 단독 의존** | `translated_text_ko` 단일 호출 흡수로 별도 검증 단계 없음. SPIKE 3.0에서 ≥30건 중 외국어 ≥15건의 번역 품질을 운영자가 spot-check. 명백한 오역 발생 시 프롬프트 보정 또는 Story 3-3에서 별도 번역 호출 분기 옵션 검토. |

## Web App Specific Requirements

### Project-Type Overview

Tracker는 세 개의 독립 레이어로 구성된 복합 시스템이다. 각 레이어는 AWS EC2 단위로 분리되며, Redis MQ를 통해 비동기 연결된다.

| 레이어 | 기술 | 역할 |
|--------|------|------|
| 크롤링 파이프라인 | Python, Playwright+stealth, APScheduler | 수집 + 전처리 + Redis enqueue |
| AI 탐지 파이프라인 | Python, OpenAI API | Redis dequeue + 멀티모달 LLM 분류 + Tier 라우팅 + RDS 저장 |
| 서비스 레이어 | Java Spring + React SPA | REST API + 대시보드 |

### Frontend (React SPA)

- **렌더링 방식:** SPA (Single Page Application)
- **지원 브라우저:** Chrome / Edge 최신 2버전 (내부 운영 도구)
- **SEO:** 불필요 — 인증 없이 외부 노출되지 않는 내부 도구
- **반응형:** 데스크톱 1280px+ 우선 / 모바일 < 768px 지원(Tailwind `md` breakpoint 기준 햄버거 drawer + 카드 뷰 + bottom Drawer 필터). 태블릿 768~1023px은 best-effort. **2026-05-13 PIVOT** — 외부 운영자의 모바일 긴급 조치(원본 URL 점프 + 수동 크롤링 트리거) 요구로 Growth 단계 항목을 MVP로 끌어옴 (Story 4.7)
- **접근성:** 기본 수준 (내부 도구, WCAG 준수 필수 아님)
- **인증:** MVP에서 제외. 내부망(VPC 보안 그룹) + AWS 네트워크 레벨 접근 제어로 대체. 애플리케이션 인증(SSO 등)은 Growth 단계
- **핵심 화면 4종:**
  - 메인 대시보드: 오늘 탐지 수, 전일 대비, 유형별 파이 차트, 사이트별 바 차트
  - 탐지 목록: 날짜·사이트·유형·언어 필터 + 신뢰도 정렬
  - 탐지 상세: 원문·번역문·탐지 유형·신뢰도·출처 URL 링크
  - 통계: 주간·월간 추이 차트, 사이트별·언어별 분포

### Backend API (Java Spring)

- **API 스타일:** REST (JSON)
- **문서화:** Swagger(OpenAPI) 자동 생성
- **주요 엔드포인트:**

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | `/detections` | 탐지 목록 조회 (필터: date, site, type, lang, page) |
| GET | `/detections/{id}` | 탐지 상세 조회 |
| GET | `/stats` | 통계 조회 (총 탐지 수, 유형별·사이트별 분포) |
| POST | `/crawl/trigger` | 수동 크롤링 즉시 실행 |

- **모니터링:** Prometheus 메트릭 수집 + Grafana 대시보드 (API 응답 시간, 에러율, 큐 길이, DLQ 알람)
- **Redis 역할:** MQ(`posts:queue`/`posts:processing`/`posts:dlq`) + 중복 해시 SET(`posts:dedup`) + LLM rate limit 토큰 버킷(`llm:rate_limit`) + 대시보드 캐시

### 성능 목표

| 지표 | 목표값 |
|------|--------|
| API 응답 시간 (GET /detections) | ≤ 500ms (p95) |
| 대시보드 초기 로드 | ≤ 3초 |
| 1회 배치 처리 시간 | ≤ 30분 |
| 크롤링 완료 → 대시보드 반영 | ≤ 5분 |

### Infrastructure (AWS)

> ⚠️ **2026-04-24 PRD freeze 시점 사양.** 실 deployment는 2026-05-04~2026-05-09 학생 IAM SCP 제약 발견으로 다단계 PIVOT 적용 (1차: 3대 t3.medium x86_64 강제 다운그레이드, 2차: 2 EC2 분리 시도, 3차 최종: 단일 t3.xlarge 16GB 회귀). 최신 사양은 [architecture.md](architecture.md) Infrastructure & Deployment 섹션 + [tracker_기획서.md](../../tracker_기획서.md) 2.1.1.a 참조.

| 리소스 | 사양 | 역할 |
|--------|------|------|
| Crawler EC2 | t3.medium | Playwright + APScheduler + 전처리 인라인 (옵션 A) |
| Detection EC2 | t3.medium | OpenAI API 호출 전담 (2026-05-27 PIVOT — BERT 보류로 업사이징 조건 해소) |
| API EC2 | t3.medium | Spring + Redis(docker-compose) + Grafana |
| RDS | PostgreSQL (t3.micro~small) | sources / posts / post_images / detections 4개 테이블 |
| S3 | 표준 | 크롤링 원본 텍스트 + 이미지 아카이브 |
| CI/CD | GitHub Actions | 코드 푸시 시 자동 빌드·배포 |

### Implementation Considerations

- `detections.type` 허용값(enum) 사전 정의 필요: `매크로_판매`, `핵_배포`, `계정_거래`, `리세마라`, `기타`
- ProxyProvider 인터페이스 추상화 — ProxyBroker(개발) → NodeMaven(운영) 교체 시 코드 변경 최소화
- APScheduler interval을 환경변수(`CRAWL_INTERVAL_MINUTES`)로 외부화 — 재배포 없이 1시간 ↔ 15분 전환 가능

## Project Scoping & Phased Development

### MVP Strategy & Philosophy

**MVP 접근법:** Problem-solving MVP. 핵심 질문 — "크롤링 → AI 탐지 → 대시보드 파이프라인이 수동 개입 없이 자동으로 동작하고, 명확한 불법 게시글을 Precision ≥ 0.85로 탐지할 수 있는가?"

**팀 구성:** 3인 (크롤링·AI 담당 일드매 / 백엔드 최병주 / 인프라·프론트 박재성), 11주

**MVP 최소 조건:** 담당자가 대시보드에서 탐지 목록을 보고 원본 URL로 이동해 조치할 수 있으면 MVP 완성.

### MVP Feature Set (Phase 1 — 1~9주)

**지원 핵심 여정:**
- Journey 1: 일상 모니터링 (탐지 목록 확인 → URL 조치)
- Journey 2: 긴급 대응 (수동 크롤링 트리거)

**Must-Have 기능:**

| 영역 | 기능 |
|------|------|
| 크롤링 | Playwright+stealth + ProxyBroker, APScheduler 1시간 주기, 이미지 수집, S3 적재. 대상: tailstar.net(한국), PTT·Dcard(대만), tieba.baidu.com·52pojie.cn·bbs.nga.cn(중국, 연결 성공 확인 시) |
| 전처리 | HTML 파싱, 언어 감지, 중복 해시(Redis), 키워드 1차 필터 (Crawler EC2 인라인) |
| AI 탐지 | OpenAI 멀티모달 LLM 분류 + Tier 라우팅, Redis MQ(queue/processing/dlq) |
| 백엔드 | Java Spring REST API 4종 (`GET /detections`, `GET /detections/{id}`, `GET /stats`, `POST /crawl/trigger`) |
| 수동 크롤링 | `POST /crawl/trigger` — 즉시 크롤링 실행 (긴급 대응용) |
| 대시보드 | 메인 대시보드, 탐지 목록(필터), 탐지 상세, 통계 화면 |
| 인프라 | AWS EC2 ×3, S3, RDS(PostgreSQL), Redis, GitHub Actions CI/CD |
| QA | 라벨셋 ≥ 300건 (Tier별 ≥ 75건), Tier별 Precision/Recall 측정 |

### Post-MVP Features

**Phase 2 — Growth (MVP 이후, 실측 데이터 기반 결정):**
- ~~VARCO Vision 이미지 탐지~~ → **MVP 편입 (2026-05-27 PIVOT)** — OpenAI 멀티모달 LLM이 통합 처리
- ~~BERT 2차 필터~~ → **보류 (2026-05-27 PIVOT)** — 일일 비용 cap 운영 데이터로 재검토
- 프록시 업그레이드: NodeMaven (~$50~80/월, GFW 우회)
- 애플리케이션 레벨 인증 (SSO 또는 ID/PW)
- T2/T3/T4 알림 채널 확장 (MVP는 T1 즉시 알림만 구현)
- ~~모바일 반응형 대시보드~~ → **MVP로 편입 (2026-05-13 PIVOT, Story 4.7)**

**Phase 3 — Expansion:**
- NC 타이틀 전체 적용 (리니지·블소·쓰론앤리버티 키워드·프롬프트 커스터마이징)
- 탐지 채널 확장 (디스코드, 텔레그램, 레딧)
- Class-RAG 자동 개선 (pgvector 기반 유사 사례 검색)

### Risk Mitigation Strategy

**기술 리스크:**

| 리스크 | 가능성 | 완화 전략 |
|--------|--------|-----------|
| 크롤링 차단 (Cloudflare/GFW) | 높음 | FlareSolverr 병행, 대만(PTT·Dcard) GFW 우회 선행 확보, 차단 사이트 이월 |
| OpenAI API rate limit 초과 | 중간 | Redis 토큰 버킷(`llm:rate_limit`) + Tier 차등 retry + 일일 비용 cap 환경변수 |
| ~~BERT 도입 시 EC2 부족~~ | 해소 | 2026-05-27 PIVOT으로 BERT 보류 |

**리소스 리스크:**

| 리스크 | 완화 전략 |
|--------|-----------|
| 11주 일정 부족 | 멀티모달 LLM 단일 호출로 Vision/Translation 단계 통합 → 파이프라인 단순화. BERT는 보류 (2026-05-27 PIVOT). |
| 중국 사이트 탐지 데이터 부족 | 대만 사이트(GFW 없음)로 다국어 탐지 검증. 중국은 NodeMaven 도입 후 확장 |

## Functional Requirements

### 콘텐츠 수집 (Content Collection)

- **FR1:** 시스템은 지정된 커뮤니티 사이트(tailstar.net, PTT, Dcard, tieba.baidu.com, 52pojie.cn, bbs.nga.cn — 최대 6개, 연결 성공 확인 분)를 1시간 주기로 자동 크롤링할 수 있다
- **FR2:** 시스템은 bot 탐지 우회 기술을 사용하여 대상 사이트의 차단 없이 게시글을 수집할 수 있다
- **FR3:** 시스템은 Cloudflare JS 챌린지가 적용된 사이트를 우회하여 수집할 수 있다
- **FR4:** 시스템은 게시글 본문 텍스트와 첨부 이미지를 함께 수집할 수 있다
- **FR5:** 시스템은 수집한 원본 데이터(텍스트+이미지)를 아카이브 스토리지에 보관할 수 있다
- **FR6:** 담당자는 특정 사이트에 대해 즉시 크롤링을 수동으로 실행할 수 있다

### 콘텐츠 전처리 (Content Preprocessing)

- **FR7:** 시스템은 수집된 HTML에서 광고·네비게이션을 제거하고 본문·제목·이미지 URL을 추출할 수 있다
- **FR8:** 시스템은 게시글의 언어(한국어/중국어/번체)를 자동으로 감지할 수 있다
- **FR9:** 시스템은 이미 처리된 게시글을 해시 기반으로 식별하여 중복 처리를 방지할 수 있다
- **FR10:** 시스템은 불법 프로그램 관련 키워드 사전으로 관련 게시글 후보를 1차 선별할 수 있다

### AI 탐지 (AI Detection)

> **2026-05-27 PIVOT.** VARCO Translation + VARCO LLM 2단 파이프라인을 **OpenAI 멀티모달 LLM(GPT-4o/4.1) 단일 호출**로 교체. 카테고리 균등 처리 → **Tier(T1 Critical / T2 High / T3 Medium / T4 Low) 차등 처리**. 자세한 결정은 `sprint-change-proposal-2026-05-27.md` 참조.
>
> **2026-06-11 재정의.** 단일 멀티모달 호출을 **비용 차등 다단계 에이전트**(S0 정규화 → S1 트리아지 → 조건부 S2a 이미지 분석 / S2b 1-hop 링크 추적 → S3 증거 통합)로 확장. detection의 사이트 종속(게임별 프롬프트 오버레이) 제거 — 게시글 자체에서 게임·맥락 자가 추론. 자세한 결정은 `sprint-change-proposal-2026-06-11.md` 참조.

- **FR11:** 시스템은 한국어 외 게시글(중국어 간체·번체 등 외국어)의 본문을 한국어로 번역한 결과를 함께 제공할 수 있다. **2026-05-27 PIVOT 갱신** — 별도 Translation API 호출이 아니라 Story 3-3 멀티모달 LLM 호출 응답 스키마의 `translated_text_ko: str | null` 필드로 흡수 (분류·`reason_ko`·번역을 단일 호출로 동시 산출). 한국어 원문은 `translated_text_ko = null`. 이미지 속 외국어 텍스트(핵 UI 스크린샷의 중국어 라벨 등)도 한국어로 변환하여 동일 필드에 포함 가능.
- **FR12:** 시스템은 게시글의 본문 텍스트와 첨부 이미지를 통합 분석하여 불법 여부와 유형(핵·치트 / 사설서버 / 불법 프로그램·봇 배포 / 계정 거래 / 매크로 판매 / 리세마라 / 게임머니 현금화 / 광고 도배 / 기타·욕설)을 자동 분류하고, 각 분류에 **Tier(T1 Critical / T2 High / T3 Medium / T4 Low)**를 부여할 수 있다 (다중 라벨 시 최상위 Tier 적용)
- **FR12-A:** *(2026-06-11 신규)* 시스템은 분류를 **비용 차등 다단계 에이전트**로 수행할 수 있다 — 전 게시글에 저비용 트리아지(텍스트 1차 분류 + 게임 맥락 추론 + 번역)를 적용하고, 의심 게시글에 한해 이미지 분석·링크 추적·증거 통합 단계로 escalate한다. 명백한 무관 게시글(트리아지 고신뢰 `기타`)은 fast path로 종결하여 비용을 절감한다. 최종 출력 스키마(`{type, confidence, reason_ko, translated_text_ko, image_observed}`)는 단일 호출 시점과 동일하게 유지된다 (저장 계약 불변)
- **FR12-B:** *(2026-06-11 신규)* 시스템은 게시글 본문·이미지에 포함된 외부 링크를 **1-hop으로 추적**하여 배포 사이트 여부를 증거로 수집할 수 있다 — 링크 페이지의 HTML/텍스트를 1단계만 fetch해 분석하며, **파일 다운로드는 수행하지 않는다**(실행파일·압축 응답은 즉시 abort하되 "배포 파일 직링크 존재"는 증거로 기록). 디스코드·텔레그램·카카오 오픈채팅 등 메신저 초대링크는 fetch 없이 메타데이터(비공개 채널 유도)만 분석한다. 안전 가드: 사설 IP/메타데이터 엔드포인트 차단(SSRF), redirect 매 hop 재검증, 응답 바이트 상한, egress 프록시(`LINK_TRACE_PROXY`) 라우팅, 동일 URL Redis 캐시
- **FR12-C:** *(2026-06-11 신규)* 시스템의 탐지는 **데이터 소스(사이트)에 비종속적**이어야 한다. 구체적으로 두 가지를 분리한다 — **(1) 라우팅 제거:** 크롤러 `source_id` → 게임 프롬프트 파일을 고르는 매핑(`SOURCE_ID_TO_GAME` + `prompts/games/*.md`)을 분류 경로에서 제거하고, 게임·도메인 맥락은 에이전트가 게시글 본문에서 **자가 추론**한다. 새 크롤 사이트를 추가해도 detection 측 설정 변경 없이 동작한다. **(2) 도메인 지식 보존:** 사이트에 종속되지 않는 큐레이션 지식(한·중·대만권 게임 은어 사전 — 外掛/私服/代儲/蝦皮 등, 오탐 방지 규칙 — 메이플=NEXON 비교군, 52pojie=게임 무관 크랙 포럼 등)은 **단일 공용 도메인 가이드**로 모든 게시글에 항상 제공한다(게임별 파일 분기 없음). 즉 "어느 게임인가"는 추론하되, "그 게임 생태계 지식"은 잃지 않는다. (크롤러의 제목 키워드 사전 필터·사이트별 품질 검증은 비용 절감 프리필터로 유지되며, 본 요구는 detection 단계에 한정)
- **FR13:** 시스템은 각 탐지 결과에 신뢰도 점수(0~1)를 산출하고, **Tier별 차등 임계값**(T1=0.65 / T2=0.75 / T3=0.85 / T4=0.90)으로 **대시보드 노출 여부**를 결정할 수 있다. **저장 자체는 임계값과 무관하게 모든 분류 결과를 RDS에 보존** (2026-05-27 PIVOT post-approval — 크롤 볼륨이 낮으므로 디버깅·라벨셋 확장·오탐 분석을 위한 전수 저장)
- **FR14:** 시스템은 탐지 결과와 함께 불법 판단 근거 텍스트(한국어)를 생성할 수 있다
- **FR15:** 시스템은 탐지 처리 실패 시 **Tier별 차등 재시도**(T1=3회 / T2=2회 / T3=1회 / T4=0회) 후 DLQ로 이동시킬 수 있다
- **FR16:** 시스템은 외부 LLM API 호출량을 제어하여 할당량 초과를 방지하고, **일일 비용 상한(USD)을 환경변수**로 설정 가능해야 한다
- **FR16-NEW-1:** 시스템은 게시글의 첨부 이미지(핵 UI 스크린샷·사설서버 배너 등)를 LLM의 멀티모달 입력으로 통합 분석할 수 있다
- **FR16-NEW-2:** 시스템은 T1 Critical 탐지 발생 시 외부 알림 채널(채널 구체값은 운영팀 협의 후 확정)로 즉시 알림을 발송할 수 있다. T2는 일일 다이제스트, T3는 주간 리포트, T4는 통계만 집계. **(2026-06-11 재정의: 이 기능은 이미 구현되어 있음 — 백엔드 알림 아웃박스(`notification_events`/`channels`/`rules`/`deliveries`, `V7`) + `NotificationEventProcessor`(5초 폴링·발송·재시도) + 채널 6종(Discord/Slack/Teams/Google Chat/Webhook) + 룰 엔진(`minTier` 필터로 T1만 발송 가능) + 프론트 설정 UI. detection이 탐지 저장 시 `notification_events`를 적재하므로 end-to-end 작동. T1 알림은 `minTier=T1` 룰 설정만으로 충족. **미구현(deferred): 사람 리뷰 큐(human-in-the-loop) — 현재 즉시 발송 설계와 충돌하여 별도 설계 필요. T2 다이제스트·T3 주간 리포트.**)**
- **FR16-NEW-3:** 시스템은 Tier별 차등 보존 정책을 적용할 수 있다 — T1만 원본 영구 보존, **T2·T3·T4는 90일 후 archive** (2026-05-27 post-approval: T4 즉시 폐기 → 90일 보존으로 변경, 크롤 볼륨 낮음). 모든 분류 결과(`is_illegal=false` 포함)는 보존 기간 동안 RDS에 유지된다. **(2026-06-11 재정의: 90일 retention job 구현은 deferred-work 이월. 크롤 볼륨이 낮아 보존 기간 내 폐기 압력이 없으므로 본 기수에서는 전수 저장만 유지)**

### 탐지 결과 조회 (Detection Browsing)

- **FR17:** 담당자는 탐지된 게시글 목록을 조회할 수 있다
- **FR18:** 담당자는 탐지 목록을 날짜·사이트·탐지 유형·언어로 필터링할 수 있다
- **FR19:** 담당자는 탐지 목록을 신뢰도 기준으로 정렬할 수 있다
- **FR20:** 담당자는 특정 탐지 게시글의 원문·번역문·탐지 유형·신뢰도·판단 근거를 상세 조회할 수 있다
- **FR21:** 담당자는 탐지 상세 화면에서 원본 게시글 URL로 직접 이동할 수 있다
- **FR22:** 시스템은 설정된 **Tier별 신뢰도 임계값** 이상의 탐지 결과만 기본 목록에 노출한다 (대시보드 디스플레이 필터). **저장은 임계값과 무관하게 전수 보존**되며, 임계값 미만 결과는 QA 리뷰 모드(`?show_below_threshold=true` 또는 동등 파라미터)로 조회 가능 (2026-05-27 PIVOT post-approval)

### 통계 및 분석 (Statistics & Analytics)

- **FR23:** 담당자는 오늘의 총 탐지 수와 전일 대비 증감을 조회할 수 있다
- **FR24:** 담당자는 탐지 유형별 분포를 조회할 수 있다
- **FR25:** 담당자는 사이트별 탐지 건수 분포를 조회할 수 있다
- **FR26:** 담당자는 주간·월간 탐지 추이 차트를 조회할 수 있다
- **FR27:** 담당자는 언어별 탐지 분포를 조회할 수 있다

### 시스템 운영 (System Operations)

- **FR28:** 시스템은 크롤링 파이프라인을 지정된 시간 간격으로 자동 실행하며, 간격을 재배포 없이 변경할 수 있다
- **FR29:** 시스템은 크롤링 및 탐지 파이프라인의 실행 상태를 모니터링할 수 있다
- **FR30:** 시스템은 처리 실패한 메시지를 격리하고 운영자에게 알람을 발송할 수 있다
- **FR31:** QA 담당자는 수동 라벨링 테스트셋으로 탐지 정확도(Precision/Recall)를 측정할 수 있다
- **FR32:** 시스템은 크롤링 완료 후 5분 이내에 탐지 결과를 대시보드에 반영할 수 있다

## Non-Functional Requirements

### Performance

- **NFR1:** `GET /detections` API 응답 시간 ≤ 500ms (p95 기준, RDS 인덱스 정상 상태)
- **NFR2:** 대시보드 초기 로드 시간 ≤ 3초 (Chrome 데스크톱, 사내망 기준)
- **NFR3:** 1회 배치(크롤링 → 전처리 → LLM 탐지 → RDS 저장) 완료 시간 ≤ 30분
- **NFR4:** 크롤링 완료 후 대시보드 탐지 결과 반영 지연 ≤ 5분

### Security

- **NFR5:** OpenAI API 키·AWS 자격증명은 환경 변수로 관리하며 코드 저장소에 노출 금지
- **NFR6:** AWS 자격증명은 EC2 IAM Role 기반으로 관리하며 Access Key 하드코딩 금지
- **NFR7:** RDS 및 Redis는 VPC 내부망에서만 접근 가능하도록 보안 그룹 구성
- **NFR8:** S3 버킷은 퍼블릭 접근을 차단하고 VPC 내 EC2만 접근 허용
- **NFR9:** 수집된 게시글 데이터는 탐지 목적으로만 사용하며 외부 공개 금지

### Reliability

- **NFR10:** 크롤링 파이프라인은 24시간 무중단 자동 실행을 유지한다 (APScheduler 프로세스 재시작 시 다음 주기에 자동 복구)
- **NFR11:** OpenAI API 호출 실패 시 **Tier별 차등 자동 재시도**(T1=3회 / T2=2회 / T3=1회 / T4=0회) 후 DLQ로 격리한다 (2026-05-27 PIVOT — 단일 3회 정책 폐기)
- **NFR12:** DLQ 메시지 누적 시 Grafana 알람이 발생하여 운영자가 5분 이내에 인지할 수 있다
- **NFR13:** EC2 단일 인스턴스 재시작 후 데이터 유실 없이 파이프라인이 재개된다 (S3 원본 아카이브 + Redis AOF 활용)

### Integration

- **NFR14:** OpenAI API rate limit 초과 또는 일일 비용 cap 도달 시 Redis 토큰 버킷(`llm:rate_limit`)으로 자동 대기하며 수동 개입 없이 처리를 재개한다
- **NFR15:** 프록시 프로바이더(ProxyBroker → NodeMaven) 교체 시 `ProxyProvider` 인터페이스 구현체 변경만으로 완료되며 크롤러 핵심 로직 수정이 불필요하다
- **NFR16:** Redis 큐 연산(`BRPOPLPUSH`)은 원자적으로 실행되어 Worker 크래시 시 메시지 유실이 발생하지 않는다
- **NFR17:** 크롤링 스케줄 간격(`CRAWL_INTERVAL_MINUTES`)은 환경 변수 변경만으로 적용되며 재배포가 불필요하다
