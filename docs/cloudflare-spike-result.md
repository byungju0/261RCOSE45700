# Cloudflare 우회 가능성 검증 — 스파이크 결과 (Story 2.1)

- **스파이크 일자**: 2026-04-27
- **타임박스**: 2 영업일(16시간) — 본 측정은 1회 세션 내 완료
- **결정**: ✅ **Playwright + `playwright-stealth` 채택** (`crawler/src/browser/stealth_browser.py`)
- **Story 2.2 AC 변경 필요 여부**: 변경 없음. epics.md SPIKE 2.1 AC1 시나리오대로 진행.

---

## 1. 검증 환경

| 항목 | 값 |
|---|---|
| Python | 3.x (`crawler/.venv`) |
| Playwright | `1.58.0` (architecture.md L112 핀 유지) |
| playwright-stealth | `2.0.3` |
| 브라우저 | Chromium Headless Shell `145.0.7632.6` (본 스파이크에서 처음 설치) |
| OS | macOS Darwin 25.3.0 (arm64) |
| 모드 | `headless=True` (1차 측정) + `headless=False` (코드 리뷰 후 추가 측정, 2026-04-27) |
| User-Agent | `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ... Chrome/124.0.0.0 ...` |
| Locale | `ko-KR` |

**`headless=False` 추가 측정 (2026-04-27, 코드 리뷰 후속)**: 코드 리뷰에서 Anti-Pattern #10 절차 미준수가 지적되어 macOS GUI 환경에서 headed 모드 재측정 수행. 결과는 §3 표에 함께 기록됨. headed 모드는 일반적으로 headless보다 탐지 회피가 쉬운 환경이므로, 이번 케이스(tailstar.net이 CF Bot Protection 비활성)에서는 두 모드 모두 통과가 예상되었고 실측에서 그대로 확인됨.

### 사전 점검 (Task 1)

- ✅ `import playwright, playwright_stealth` 정상
- ✅ `crawler/.venv/bin/playwright install chromium` — Story 1.1 시점 누락분 본 스파이크에서 설치 완료
- ✅ `curl -I https://tailstar.net` → `HTTP/2 200`, `server: cloudflare`, `cf-ray: 9f2e291af9b608e6-LAX` (Cloudflare 프록시 확인)

---

## 2. 시도 사이트

| 순위 | 사이트 | 시도 여부 | 이유 |
|---|---|---|---|
| 1 | **`tailstar.net`** | ✅ 시도 | PRD 지정 1순위 + Cloudflare 프록시 확인 |
| 2 | (예비) PRD 한국 게임 커뮤니티 | ❌ 미시도 | 1순위가 통과하여 후순위 불요 |

**1순위 통과 → 후순위 미시도가 정상 종료 경로.**

---

## 3. Phase A 결과 — Playwright + stealth

**스크립트**: `crawler/spikes/cf_stealth_probe.py`
**측정 횟수**: 3회 (≥3 AC 충족, 시도 간 2초 간격)

| Attempt | 분류 | HTTP | Elapsed | Title | 콘텐츠 셀렉터 | Notes |
|---|---|---|---|---|---|---|
| 1 | **Pass** | 200 | 3,452 ms | 테일스타 - 재밌는 인터넷 놀이터 | matched (`title`/`canonical`/`Generator=XpressEngine`) | challenge/block 마커 없음 |
| 2 | **Pass** | 200 | 1,609 ms | (동일) | matched | (동일) |
| 3 | **Pass** | 200 | 1,870 ms | (동일) | matched | (동일) |

**합계 (headless=True): 3 Pass / 0 CF Challenge / 0 Block / 0 Timeout**

### Phase A 추가 측정 — `headless=False` (2026-04-27, 코드 리뷰 후속)

| Attempt | 분류 | HTTP | Elapsed | Title | 콘텐츠 셀렉터 | Notes |
|---|---|---|---|---|---|---|
| 1 | **Pass** | 200 | 5,868 ms | 테일스타 - 재밌는 인터넷 놀이터 | matched | challenge/block 마커 없음 |
| 2 | **Pass** | 200 | 3,312 ms | (동일) | matched | (동일) |
| 3 | **Pass** | 200 | 3,948 ms | (동일) | matched | (동일) |

**합계 (headless=False): 3 Pass / 0 CF Challenge / 0 Block / 0 Timeout / 0 Error**

headless=False는 headed 모드 특성상 평균 응답 시간이 약 2배 증가(headless 대비)하나, 통과 여부에는 영향 없음. 두 모드 모두 통과했으므로 stealth 채택 결정 유지.

### 통과 판정 기준 충족

- HTTP 200 ✅
- `<title>테일스타 - 재밌는 인터넷 놀이터</title>` — 실제 게시판 메인 타이틀 ✅
- `<meta name="Generator" content="XpressEngine">` — 실제 콘텐츠 마크업 ✅
- `Just a moment…`, `cf-challenge`, `cdn-cgi/challenge-platform`, `cf-mitigated` 마커 부재 ✅

### 관찰 — `tailstar.net`의 Cloudflare 프로파일

응답 헤더에 `server: cloudflare`, `cf-ray`, `cf-cache-status: DYNAMIC`이 있으나 **JS 챌린지/Turnstile/IP 체크가 활성화되어 있지 않음**. 즉 본 사이트는 Cloudflare를 CDN/DDoS 완충재로만 사용하고 봇 보호 모드는 비활성. 단순 `curl -A "<browser-UA>"`로도 전체 HTML이 정상 응답되는 수준의 보호.

이 관찰은 PRD에 명시된 다른 한국 게임 커뮤니티 사이트들(Cloudflare Bot Fight Mode 활성 가능)에는 일반화되지 않을 수 있음. **사이트별 재측정은 Story 2.2 ~ 2.6에서 사이트 어댑터 작성 시 개별 수행** 필요.

### AC1 (실제 CF JS 챌린지 우회 검증) — Story 2.6/2.7 이관

**코드 리뷰 후속 결정 (2026-04-27)**: 본 스파이크가 채택한 1순위 사이트 `tailstar.net`은 측정 시점 기준 Cloudflare Bot Protection이 비활성화된 상태였음. 따라서 본 스파이크는 엄밀히 말하면 *"stealth가 약한 CF 보호 사이트에서 동작함"*을 검증한 것이고, *"강한 CF JS 챌린지를 실제로 통과함"*은 검증하지 못함.

**왜 본 스파이크에서 보강 측정을 하지 않는가**:
- PRD에 명시된 한국 게임 커뮤니티 사이트는 `tailstar.net` 1개뿐 — 후순위 후보가 PRD에 없음
- 본 스토리 정의(line 25)가 PTT/tieba 등을 명시적으로 스파이크 범위 외로 규정 (Story 2.6/2.7)
- PRD에 없는 임의 한국 커뮤니티(fmkorea, 루리웹, 인벤 등) 시도는 스코프 침범 + IP 차단 누적 위험

**Story 2.6/2.7로의 이관 사항**:
1. PTT 어댑터 작성 시 `StealthBrowser.fetch_html()`이 실제 CF 챌린지 사이트에서 동작하는지 라이브 검증
2. tieba.baidu.com / 52pojie.cn / bbs.nga.cn은 GFW 차단 + CF 챌린지 복합 환경 — Story 2.7 진행 시 별도 측정
3. 만약 강한 CF 보호 사이트에서 stealth가 실패하면 본 결정 문서 §7 "에스케이프 해치"의 후퇴 경로(Camoufox / FlareSolverr 재시도 / 매니지드 서비스)로 전환

본 스파이크의 stealth 채택 결정은 *MVP 1순위 사이트(tailstar.net)에서 정상 동작*이라는 측정 결과에 한해 유효하며, Story 2.6/2.7 라이브 검증 결과에 따라 재평가될 수 있음.

---

## 4. Phase B 결과 — FlareSolverr

**시도하지 않음.** 근거:
- epics.md SPIKE 2.1 AC3: "사용할 구현체가 결정되며" = 단일 구현체 채택
- 본 스토리 Anti-Pattern #2: Phase A 통과 시 Phase B 추가 도입은 운영 컨테이너/장애 지점만 늘림
- 2026-Q1 기준 FlareSolverr는 CAPTCHA 솔버 비기능 + Cloudflare 업데이트 후 자주 망가지는 상태(ZenRows/iproyal 보고서). 약점이 큰 도구를 통과 사례 없이 채택하면 운영 위험.

향후 PRD의 다른 사이트(Cloudflare 강한 보호 활성화 케이스)에서 stealth가 실패하면 그때 Phase B를 별도 스파이크로 재기동.

---

## 5. 의사결정

### 채택: `crawler/src/browser/stealth_browser.py`

- **클래스**: `StealthBrowser`
- **시그니처**: `async def fetch_html(self, url: str, *, correlation_id: str) -> str`
- **의존성**: `playwright.async_api.async_playwright`, `playwright_stealth.Stealth`
- **실패 처리**: `BrowserError(CrawlerException)` raise — `None` 반환 금지 (architecture.md P10)
- **챌린지 감지**: 응답 HTML에서 `Just a moment…`, `cf-challenge`, `cdn-cgi/challenge-platform`, `cf-mitigated` 마커 또는 block 마커가 발견되면 즉시 raise (Cross-Cutting Concern #5: silent failure 방지)

### 미채택: `flaresolverr.py`

- 본 스토리에서는 작성하지 않음(epics.md AC3, Anti-Pattern #2)
- `crawler/src/browser/flaresolverr.py` stub도 만들지 않음 (epics.md AC3 명시: "다른 후보의 빈 stub은 만들지 않는다")

### Story 2.2와의 연결

`StealthBrowser`는 ProxyProvider를 인자로 받지 않는 단순 형태로 구현. Story 2.2에서 ProxyProvider 인터페이스가 정의되면 그 시점에 생성자를 확장 (DI 친화적 위치만 확보).

---

## 6. Story 2.2 AC 변경 제안

**제안 없음 — 현행 epics.md SPIKE 2.1 / Story 2.2 AC 그대로 진행 가능.**

이유:
- 본 스파이크가 stealth 채택을 확정 → Story 2.2 AC1 "ProxyProvider 인터페이스 + 기본 stealth 구현" 시나리오와 정합
- FlareSolverr 스택으로 전환되었다면 Story 2.2 AC를 "FlareSolverr 클라이언트 + ProxyProvider 어댑터"로 재작성해야 했지만, 그 분기는 발생하지 않음
- `tailstar.net` 외 사이트(Cloudflare Bot Fight Mode 활성 케이스)에 대한 stealth 검증은 Story 2.6/2.7 시점에 수행 — 현 시점에 AC 선제 변경 불필요

---

## 7. 에스케이프 해치 (이 결정이 깨질 때 어떻게 후퇴할 것인가)

| 트리거 | 후퇴 경로 |
|---|---|
| Story 2.6/2.7에서 PRD 다른 사이트가 강한 Cloudflare 보호로 stealth 실패 | (a) **Camoufox** 또는 **Patchright** — 하드닝된 Firefox/Chrome 빌드, stealth보다 탐지 회피 강력. (b) **FlareSolverr 재시도** — 본 스파이크 시점에는 미채택이지만 사이트별로 부분 채택 가능. (c) 해당 사이트를 **MVP 범위에서 제외**하고 Growth 단계로 보류 |
| `playwright==1.58.0` + stealth 2.0.3 조합이 향후 Cloudflare 업데이트로 무력화 | architecture.md L112 핀을 갱신하는 별도 PR (영향 범위: crawler 전체). 본 스파이크에서는 핀 변경하지 않음. |
| MVP 운영 단계에서 IP 차단 누적 | **ProxyBroker** (PRD 명시) → Camoufox와 조합. Story 2.2 ProxyProvider 추상화가 이 확장을 흡수해야 함. |
| 모든 stealth/Camoufox/FlareSolverr 실패 | Growth 단계 매니지드 서비스 도입(ZenRows / Bright Data). 비용 발생. PRD의 "MVP는 차단 사이트 제외" 정책으로 회귀 가능. |

---

## 8. 타임박스 초과 시 미완료 시도

**해당 없음** — 본 스파이크는 1세션 내에 측정·결정·구현·테스트까지 완료. 16시간 타임박스 대비 충분한 여유 마진.

---

## 9. 임시 스파이크 스크립트 처리

- `crawler/spikes/cf_stealth_probe.py` — **보존** (재측정 가능성 + 향후 사이트별 검증 시 재사용)
- `crawler/spikes/README.md` — 사용법 1줄 명시 (Task 8.1)
- `.gitignore` 제외 처리 없이 커밋

---

## 10. References

- [Story 2.1 파일](../_bmad-output/implementation-artifacts/2-1-cloudflare-우회-가능성-검증.md)
- [Epic 2 SPIKE 2.1 AC](../_bmad-output/planning-artifacts/epics.md)
- [Architecture: P10 예외 처리 / Cross-Cutting #5 Silent Failure](../_bmad-output/planning-artifacts/architecture.md)
- 외부: [BrowserStack — Bypass Cloudflare with Playwright (2026)](https://www.browserstack.com/guide/playwright-cloudflare)
- 외부: [ZenRows — FlareSolverr 2026 Status](https://www.zenrows.com/blog/flaresolverr)
