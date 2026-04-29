# Story 4.4: React 대시보드 메인 화면 및 라우팅 구조

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

프론트엔드 개발자로서,
React Router v7 기반 4개 라우트와 메인 대시보드 화면이 백엔드 API 완성 전에도 독립적으로 동작 가능하도록 MSW 모킹 위에 구현되기를 원한다,
그래서 담당자가 오늘 탐지 현황을 한눈에 파악하고 각 화면으로 이동할 수 있으며, Story 4.5·4.6이 동일한 라우터·API 클라이언트·공통 컴포넌트 위에서 바로 작업을 시작할 수 있다.

## Acceptance Criteria

1. **Given** 브라우저에서 `/`에 접속할 때, **When** 메인 대시보드가 로드되면, **Then** 오늘 총 탐지 수와 전일 대비 증감 수치가 표시된다. (FR23, UX-DR1)
2. 탐지 유형별 파이 차트가 Recharts `PieChart`로 표시되며, 카테고리는 `매크로_판매`, `핵_배포`, `계정_거래`, `리세마라`, `기타` 5종이다. (FR24, UX-DR1)
3. 사이트별 바 차트가 Recharts `BarChart`로 표시된다. (FR25, UX-DR1)
4. 오늘 탐지 0건일 때 "오늘 탐지된 게시글이 없습니다" Empty State 메시지가 차트 영역 대신 표시된다.
5. 마지막 업데이트 시각이 대시보드 우측 상단에 "N분 전 업데이트" 형식(`date-fns/formatDistanceToNow` + `ko` locale)으로 표시된다.
6. React Router v7 `createBrowserRouter`로 `/` (대시보드), `/detections` (목록 placeholder), `/detections/:id` (상세 placeholder), `/stats` (통계 placeholder) 4개 라우트가 동작한다. (UX-DR6)
7. **Given** 메인 대시보드에서, **When** 60초가 경과하면, **Then** TanStack Query `useQuery({ refetchInterval: 60_000 })`로 통계가 자동 갱신된다. **And** 갱신 중에는 전체 스피너 대신 헤더 우측 상단의 진행 인디케이터(`isFetching && !isLoading`)만 표시된다.
8. `ErrorBoundary` 공통 컴포넌트가 라우트 최상위(`<Outlet />` 부모)에 적용되어 자식 라우트에서 발생한 렌더 에러를 복구 UI로 보여준다. (UX-DR5)
9. `LoadingSpinner` 공통 컴포넌트가 초기 로딩 시(`isLoading`) 표시된다. (UX-DR5)
10. API 클라이언트(`src/api/client.ts`)가 axios 인스턴스를 노출하며, 모든 요청에 `X-Correlation-ID` 헤더를 자동 부착하고(`crypto.randomUUID()`), 응답이 ProblemDetail(RFC 9457) 에러일 때 `ProblemDetailError` 클래스로 변환하여 throw한다. (P9, UX-DR5)
11. MSW v2가 개발 모드(`import.meta.env.DEV === true`)에서만 활성화되며, `GET /stats` 요청에 architecture P1(camelCase) + P5(ISO 8601 UTC) 계약을 따르는 mock 응답을 반환한다. 프로덕션 빌드(`npm run build`)에는 MSW 워커가 포함되지 않는다.
12. `npm run build` 가 0 에러로 성공하고, `npm run dev` 후 Chrome에서 `/`, `/detections`, `/detections/:id`, `/stats` 4개 URL 접속 시 화이트스크린 없이 각자 placeholder 또는 Dashboard 컴포넌트가 렌더된다.
13. 대시보드 초기 로드 시간이 Chrome 데스크톱(1280px 이상)에서 ≤ 3초이다. 측정은 DevTools Network 탭의 `DOMContentLoaded` 기준으로 수동 검증한다. (NFR2)

## Tasks / Subtasks

- [x] **Task 1: 의존성 설치 및 MSW 추가** (AC: #11)
  - [x] 1.1 `cd dashboard && npm install` — 263 packages installed
  - [x] 1.2 `npm install --save-dev msw` — msw@^2.13.6 (devDependency)
  - [x] 1.3 `npx msw init public/ --save` — `public/mockServiceWorker.js` 생성 + `package.json` workerDirectory 추가
  - [x] 1.4 `npm run build` 1회 실행해 기존 보일러플레이트 빌드 가능 사전 검증 — 성공 (193KB)

- [x] **Task 2: TypeScript 타입 정의 (`src/types/api.ts`)** (AC: #1, #2, #3, #10)
  - [x] 2.1 `DetectionType` 유니온 타입 5종
  - [x] 2.2 `Detection` 인터페이스 (id, isIllegal, type, confidence, reason, rawText, translatedText, postUrl, siteName, language, detectedAt)
  - [x] 2.3 `StatsResponse` 인터페이스 + 분포 엔트리 타입 4종 (TypeDistributionEntry, SiteDistributionEntry, LangDistributionEntry, TrendEntry)
  - [x] 2.4 `ProblemDetail` 인터페이스 (RFC 9457)
  - [x] 2.5 `DetectionListResponse` 페이지네이션 골격

- [x] **Task 3: API 클라이언트 (`src/api/client.ts`)** (AC: #10, P9, P1)
  - [x] 3.1 axios 인스턴스 + baseURL `import.meta.env.VITE_API_BASE_URL ?? '/api'` + timeout 10s
  - [x] 3.2 요청 인터셉터: `crypto.randomUUID()`로 X-Correlation-ID 자동 부착
  - [x] 3.3 응답 인터셉터: ProblemDetail 형식 검증 후 ProblemDetailError로 변환
  - [x] 3.4 `ProblemDetailError extends Error` — problem/errorCode/status 필드 + instanceof 체크 가능
  - [x] 3.5 `.env.example` 신규 생성 — VITE_API_BASE_URL=http://localhost:8080

- [x] **Task 4: MSW 핸들러 셋업 (`src/mocks/`)** (AC: #11)
  - [x] 4.1 `handlers.ts` — `http.get(\`${baseUrl}/stats\`, ...)` 1개
  - [x] 4.2 mock 데이터: todayCount=12, delta=3, 5개 type, 5개 site, 3개 lang
  - [x] 4.3 `browser.ts` — `setupWorker(...handlers)` export
  - [x] 4.4 `main.tsx`에서 `import.meta.env.DEV` 분기 + 동적 import + await worker.start
  - [x] 4.5 `onUnhandledRequest: 'bypass'` 설정

- [x] **Task 5: 라우터 설정 (`src/router.tsx`)** (AC: #6, UX-DR6)
  - [x] 5.1 `createBrowserRouter` Data Router API
  - [x] 5.2 부모 `/` + errorElement, 자식 4개 (index, detections, detections/:id, stats)
  - [x] 5.3 `RootLayout` — 헤더(Tracker 로고 + NavLink 3개 + RefreshIndicator) + Outlet
  - [x] 5.4 placeholder 페이지 3종 (DetectionList, DetectionDetail, Stats) — "Story 4.5/4.6에서 구현됩니다"

- [x] **Task 6: 공통 컴포넌트 (`src/components/common/`)** (AC: #8, #9, UX-DR5)
  - [x] 6.1 `ErrorBoundary.tsx` — `useRouteError` + `ProblemDetailError` 분기 + `isRouteErrorResponse` 처리 + 새로고침 버튼
  - [x] 6.2 `LoadingSpinner.tsx` — SVG 스피너 + size sm/md/lg + label prop
  - [x] 6.3 `RefreshIndicator.tsx` — RootLayout이 `useIsFetching` 훅으로 isFetching 판단 후 prop 전달

- [x] **Task 7: 차트 래퍼 컴포넌트 (`src/components/charts/`)** (AC: #2, #3)
  - [x] 7.1 `PieChart.tsx` — Recharts PieChart + Pie + Cell + Legend + Tooltip + ResponsiveContainer
  - [x] 7.2 `BarChart.tsx` — Recharts BarChart + Bar + XAxis + YAxis + Tooltip + CartesianGrid. `{name, value}` 통일 인터페이스
  - [x] 7.3 LineChart는 미구현 (Story 4.6 범위)
  - [x] 7.4 `colors.ts` — TYPE_COLORS 5종 + CHART_PALETTE 7색

- [x] **Task 8: API 데이터 훅 (`src/api/stats.ts`)** (AC: #1, #7)
  - [x] 8.1 `useStatsQuery` — refetchInterval 60_000, staleTime 30_000
  - [x] 8.2 fetchStats 함수 — apiClient.get<StatsResponse>
  - [x] 8.3 TanStack Query v5 객체 시그니처 준수 (data/isLoading/isFetching/error/dataUpdatedAt 노출)

- [x] **Task 9: 메인 대시보드 페이지 (`src/pages/Dashboard/`)** (AC: #1, #2, #3, #4, #5)
  - [x] 9.1 `index.tsx` — useStatsQuery + isLoading 시 LoadingSpinner + error throw (errorElement에서 처리)
  - [x] 9.2 `TodayCount.tsx` — count 큰 숫자 + delta 부호 색상 (양수 빨강 / 음수 회색)
  - [x] 9.3 `TypeDistribution.tsx` — PieChart 래핑 + Empty State
  - [x] 9.4 `SiteDistribution.tsx` — BarChart 래핑 (data.map으로 {name,value} 변환) + Empty State
  - [x] 9.5 `LastUpdated.tsx` — formatDistanceToNow + ko locale + 30초 강제 리렌더로 라벨 갱신
  - [x] 9.6 CSS Grid 2열 (`repeat(2, minmax(0, 1fr))`)

- [x] **Task 10: 진입점 통합 (`src/main.tsx`, `src/App.tsx`)** (AC: #6, #7, #8)
  - [x] 10.1 `main.tsx` — enableMocking → createRoot → StrictMode → QueryClientProvider → RouterProvider
  - [x] 10.2 `App.tsx` 삭제 (RootLayout이 대체)
  - [x] 10.3 `App.css` 삭제, `src/assets/` 삭제 (hero.png, react.svg, vite.svg), `index.css` 폰트/리셋만 유지
  - [x] 10.4 `public/icons.svg` 삭제 (보일러플레이트 잔여물)

- [x] **Task 11: 검증** (AC: #11, #12, #13)
  - [x] 11.1 `npm run build` 성공 — 0 에러 (chunk size 경고만, 차단 사유 아님)
  - [x] 11.2 `npm run dev` 부팅 — `VITE v8.0.10 ready in 90 ms`, `http://localhost:5173/`
  - [x] 11.3 4개 URL 200 응답 확인 — `/`, `/detections`, `/detections/1`, `/stats` (curl 검증)
  - [x] 11.4 DevTools Network 검증은 브라우저 수동 확인 필요 — MSW 핸들러 코드/X-Correlation-ID 인터셉터 코드 검증 완료
  - [x] 11.5 60초 폴링 검증은 브라우저 수동 확인 필요 — refetchInterval: 60_000 코드 검증 완료
  - [x] 11.6 `grep -l "msw" dist/assets/*.js` → 0건. `grep -c "setupWorker\|mockServiceWorker"` → 0. **MSW 프로덕션 번들 미포함 확정**
  - [x] 11.7 `npm run lint` — 0 errors (mockServiceWorker.js 자동생성 파일에 1 warning, dev 코드는 클린)

## Dev Notes

### 본 스토리 범위 (Scope Boundary — 가장 중요)

| 이번 스토리에서 한다 | 이번 스토리에서 **하지 않는다** |
|---|---|
| `/` 메인 대시보드 완성 (탐지 수, 파이 차트, 바 차트) | `/detections` 목록 화면 본체 → Story 4.5 |
| 4개 라우트 등록 + RootLayout + ErrorBoundary | `/detections/:id` 상세 화면 본체 → Story 4.5 |
| `api/client.ts` axios + ProblemDetail 변환 | `/stats` 통계 화면 본체 (LineChart 포함) → Story 4.6 |
| `api/stats.ts` useStatsQuery 훅 | `api/detections.ts` 목록·상세 fetcher → Story 4.5 |
| `types/api.ts` Detection·Stats·ProblemDetail 타입 골격 | DetectionListResponse 상세 + 필터 파라미터 타입 → Story 4.5 |
| `components/charts/PieChart.tsx`, `BarChart.tsx` | `LineChart.tsx` → Story 4.6 |
| `components/common/ErrorBoundary.tsx`, `LoadingSpinner.tsx`, `RefreshIndicator.tsx` | 토스트 알림 컴포넌트 → Story 4.5 (수동 크롤링 트리거 결과 표시) |
| MSW v2 `GET /stats` 핸들러 1개 | `GET /detections`, `GET /detections/{id}`, `POST /crawl/trigger` mock → Story 4.5 |
| 보일러플레이트 카운터 데모 제거 (App.tsx, App.css, assets/) | 실제 백엔드 연동 → Story 4.1·4.3 dev 완료 후 통합 |
| 1280px 데스크톱 레이아웃 | 모바일 반응형 → Growth 단계 (PRD L233) |
| 60초 폴링 + 진행 인디케이터 | 5분 이내 반영 E2E 검증 → Story 4.5 (`tests/performance/test_pipeline_latency.py`) |

### Project Context

- 본 스토리는 Epic 4의 첫 번째 프론트엔드 스토리. Epic 4 백엔드 스토리(4.1·4.2·4.3)는 backlog 상태이지만, **MSW v2로 모킹하여 백엔드 의존성 없이 독립 진행**한다. Story 4.1·4.3 완성 후 `import.meta.env.VITE_API_BASE_URL` 환경변수만 변경하면 실제 백엔드로 전환된다.
- Story 1.1에서 `dashboard/`는 `npm create vite@latest -- --template react-ts`로 스캐폴딩됨. 현재 `App.tsx`는 Vite 기본 카운터 데모이며, **본 스토리에서 완전 제거**한다.
- Story 1.1에서 `dashboard/package.json`에 다음 의존성이 이미 선언되어 있음 (npm install만 필요):
  - `react@19.2.5`, `react-dom@19.2.5`, `react-router-dom@7.14.2`
  - `@tanstack/react-query@5.100.5`, `axios@1.15.2`
  - `recharts@3.8.1`, `@radix-ui/react-select@2.2.6`, `date-fns@4.1.0`
  - dev: `vite@8.0.10`, `typescript@~6.0.2`, `@vitejs/plugin-react@6.0.1`, `eslint@10.2.1`
- **Story 1.3(docker-compose) 미완료 상태에서도 본 스토리는 진행 가능**. 백엔드 API 서버 없이도 MSW가 모든 요청을 가로채 mock 응답을 반환한다.
- `shared/` Python 모듈은 본 스토리와 무관 (Python 전용. 프론트엔드는 TypeScript로 자체 타입 정의).

### Technical Stack Decisions

| 항목 | 결정 | 근거 |
|---|---|---|
| 모킹 라이브러리 | **MSW v2** | Service Worker 레벨 가로채기 — 컴포넌트 코드는 실제 axios 호출 그대로 작성. Story 4.1·4.3 완성 시 worker 비활성화만으로 실 백엔드 전환. fetch/axios/SWR 무관하게 동작. msw v1 → v2는 `rest` → `http` namespace로 변경됨 — **반드시 v2 API 사용** |
| 모킹 활성화 조건 | `import.meta.env.DEV` | Vite의 ESM 환경에서 `process.env.NODE_ENV`는 컴파일 시 치환되지만 import.meta.env가 표준. 프로덕션 빌드 시 dead-code elimination으로 MSW import도 제거됨 |
| 라우팅 패턴 | `createBrowserRouter` (Data Router API) | React Router v7 권장. `errorElement`로 ErrorBoundary 통합, loader/action 추후 활용 가능. `<BrowserRouter>` JSX 패턴은 v7에서 legacy로 분류 |
| ErrorBoundary 구현 | 라우터 `errorElement` + `useRouteError()` | React 19에서도 기존 클래스형 ErrorBoundary 동작하지만, React Router v7과 통합 시 `errorElement`가 라우트별 에러 격리에 더 적합. 둘 다 쓰지 않고 라우터 패턴 단일화 |
| Correlation ID 생성 | `crypto.randomUUID()` | 브라우저 표준 (Chrome/Edge 최신 2버전 — PRD L231). uuid 패키지 추가 의존성 불필요 |
| 갱신 폴링 | TanStack Query `refetchInterval: 60_000` | architecture L211 결정사항. WebSocket/SSE는 1시간 크롤링 주기에 과도. **변경 금지** |
| 차트 라이브러리 | Recharts | architecture L154, L211 결정. d3 직접 사용/Chart.js 대안 도입 금지 |
| 상태 관리 | TanStack Query (서버 상태만) | architecture L213. Zustand/Redux/Jotai 추가 금지. UI state는 useState로 충분 |
| 페이지네이션 | offset 기반 placeholder | architecture L172. 본 스토리는 타입 골격만, 구현은 4.5 |

### File Structure Requirements (필수 생성/수정)

```
dashboard/
├── public/
│   └── mockServiceWorker.js              ← 신규 (npx msw init 생성)
├── src/
│   ├── main.tsx                          ← 수정 (MSW + QueryClient + Router)
│   ├── App.tsx                           ← 삭제 또는 RootLayout으로 재정의
│   ├── App.css                           ← 삭제 (보일러플레이트)
│   ├── index.css                         ← 유지 (폰트/리셋만)
│   ├── assets/                           ← 삭제 (react.svg, vite.svg, hero.png)
│   ├── router.tsx                        ← 신규
│   ├── api/
│   │   ├── client.ts                     ← 신규
│   │   └── stats.ts                      ← 신규
│   ├── types/
│   │   └── api.ts                        ← 신규
│   ├── mocks/
│   │   ├── browser.ts                    ← 신규
│   │   └── handlers.ts                   ← 신규
│   ├── components/
│   │   ├── common/
│   │   │   ├── ErrorBoundary.tsx         ← 신규
│   │   │   ├── LoadingSpinner.tsx        ← 신규
│   │   │   └── RefreshIndicator.tsx      ← 신규
│   │   └── charts/
│   │       ├── PieChart.tsx              ← 신규
│   │       ├── BarChart.tsx              ← 신규
│   │       └── colors.ts                 ← 신규
│   ├── pages/
│   │   ├── Dashboard/
│   │   │   ├── index.tsx                 ← 신규
│   │   │   ├── TodayCount.tsx            ← 신규
│   │   │   ├── TypeDistribution.tsx      ← 신규
│   │   │   ├── SiteDistribution.tsx      ← 신규
│   │   │   └── LastUpdated.tsx           ← 신규
│   │   ├── DetectionList/
│   │   │   └── index.tsx                 ← 신규 (placeholder, 4.5에서 본구현)
│   │   ├── DetectionDetail/
│   │   │   └── index.tsx                 ← 신규 (placeholder, 4.5에서 본구현)
│   │   └── Stats/
│   │       └── index.tsx                 ← 신규 (placeholder, 4.6에서 본구현)
│   └── layouts/
│       └── RootLayout.tsx                ← 신규 (헤더 + Outlet)
├── package.json                          ← 수정 (msw devDep 추가)
├── .env.example                          ← 신규 (VITE_API_BASE_URL)
└── vite.config.ts                        ← 변경 불필요 (1.1 스캐폴딩 그대로)
```

### Architecture Compliance Notes

- **P1 JSON camelCase** ([architecture.md:250-266](_bmad-output/planning-artifacts/architecture.md#L250-L266)): MSW mock 응답 + TypeScript 인터페이스 모두 camelCase. snake_case 사용 시 백엔드 통합 시점에 즉시 깨짐. **mock에서도 절대 snake_case 금지.**
- **P4 에러 코드 UPPER_SNAKE_CASE** ([architecture.md:294-306](_bmad-output/planning-artifacts/architecture.md#L294-L306)): `ProblemDetail.errorCode` 필드값 — `DETECTION_NOT_FOUND`, `INVALID_FILTER_PARAM` 등 UPPER_SNAKE_CASE. 본 스토리에서는 `STATS_FETCH_FAILED` 정도만 mock 에러 시나리오에서 사용 가능
- **P5 ISO 8601 UTC** ([architecture.md:310-321](_bmad-output/planning-artifacts/architecture.md#L310-L321)): `detectedAt`, `trend[].date` 등 모든 시간은 `"2026-04-27T14:30:00Z"` 형식. Unix timestamp 절대 금지. React 표시 시 `new Date(detectedAt).toLocaleString('ko-KR')`
- **P9 ProblemDetail 전파** ([architecture.md:375-383](_bmad-output/planning-artifacts/architecture.md#L375-L383)): 에러 분기는 HTTP status code가 아닌 `error.errorCode`로 — Task 3.4 `ProblemDetailError` 클래스가 이 패턴을 강제
- **X-Correlation-ID 헤더** ([architecture.md:204](_bmad-output/planning-artifacts/architecture.md#L204)): 프론트엔드가 새 요청마다 UUID 생성하여 헤더 부착. 백엔드는 이를 응답 헤더로 echo + 로그에 기록 → Crawler/Detection/API 3개 EC2 로그 추적의 마지막 고리
- **TanStack Query 60초 폴링** ([architecture.md:211](_bmad-output/planning-artifacts/architecture.md#L211)): 결정사항. WebSocket·SSE 도입 금지
- **Frontend FR 매핑** ([architecture.md:700-701](_bmad-output/planning-artifacts/architecture.md#L700-L701)): 본 스토리 = `dashboard/src/pages/Dashboard/` 신설. FR23·FR24·FR25 커버
- **데스크톱 1280px+ 우선** ([prd.md:233](_bmad-output/planning-artifacts/prd.md#L233)): 모바일 반응형 미고려. 미디어 쿼리 작성 시간 낭비

### Latest Tech Information (검증 완료 — 2026-04-27)

**MSW v2 (msw@latest)** — Mock Service Worker
- Browser integration docs: https://mswjs.io/docs/integrations/browser/
- v1 → v2 변경: `rest.get()` → `http.get()`, `req.url.searchParams` → `request.url`(URL 객체), `res(ctx.json())` → `HttpResponse.json()`. **v1 예제 검색 결과 무시할 것**
- 설치: `npm install --save-dev msw`
- 워커 초기화: `npx msw init public/ --save` — `package.json`에 `msw.workerDirectory: "public"` 자동 추가
- Vite 통합: `import.meta.env.DEV` 체크 (Vite docs 표준), `process.env.NODE_ENV` 사용 시 ESM 환경에서 동작 불안정
- 비동기 시작: `await worker.start({ onUnhandledRequest: 'bypass' })` 후 `createRoot(...).render()` — race condition 방지
- 프로덕션 제외 보장: `msw`를 devDependency로 설치 + DEV 분기 import → tree-shaking으로 번들 미포함

**TanStack Query v5** — `@tanstack/react-query@5.100.5`
- v4 → v5 주요 변경: 콜백 시그니처가 객체 형태로 통일됨. `useQuery(key, fn, options)` (v4) → `useQuery({ queryKey, queryFn, ...options })` (v5). **v4 패턴 사용 금지**
- `isLoading` (초기 로딩) vs `isFetching` (재요청 포함). AC #7의 진행 인디케이터는 `isFetching && !isLoading` 조합

**React Router v7** — `react-router-dom@7.14.2`
- v6 → v7: `<BrowserRouter>` 패턴은 legacy. `createBrowserRouter` + `<RouterProvider>`가 표준
- `errorElement`로 라우트별 에러 격리. `useRouteError()` 훅으로 에러 객체 접근
- 4개 라우트 nested: 부모 `path: '/'` + 자식 4개 (index 대시보드 포함)

**Recharts v3** — `recharts@3.8.1`
- ResponsiveContainer 필수: 모든 차트는 `<ResponsiveContainer width="100%" height={300}>` 래핑

### Anti-Patterns to Avoid (이번 스토리 특화)

1. ❌ **`<BrowserRouter>` JSX 패턴 사용** — React Router v7에서는 `createBrowserRouter` Data Router가 표준. errorElement·loader 활용 위해 강제
2. ❌ **MSW v1 `rest.get()` API** — v2에서 제거됨. `import { http, HttpResponse } from 'msw'` 사용
3. ❌ **`process.env.NODE_ENV` Vite에서 사용** — `import.meta.env.DEV` 표준
4. ❌ **MSW를 dependencies에 추가** — devDependencies. 프로덕션 번들 미포함 보장
5. ❌ **TanStack Query v4 시그니처** — `useQuery(key, fn)` 금지. `useQuery({ queryKey, queryFn })` 객체 형태만
6. ❌ **API 응답에 snake_case** — mock에서도 camelCase 강제. P1 위반 시 백엔드 통합 즉시 깨짐
7. ❌ **Unix timestamp 사용** — ISO 8601 UTC 문자열만 (`"2026-04-27T14:30:00Z"`)
8. ❌ **HTTP status code만으로 에러 분기** — `error.errorCode` 또는 `instanceof ProblemDetailError`로 분기 (P9)
9. ❌ **Zustand/Redux/Jotai 도입** — TanStack Query + useState로 충분
10. ❌ **WebSocket·SSE 도입** — 60초 폴링 결정사항 (architecture L211)
11. ❌ **클래스형 ErrorBoundary 별도 작성** — 라우터 errorElement + useRouteError 패턴으로 단일화
12. ❌ **모바일 반응형 미디어 쿼리 작성** — 1280px+ 데스크톱 우선 (PRD L233). Growth 단계까지 미고려
13. ❌ **react.svg, vite.svg, hero.png, App.css 카운터 데모 잔여 유지** — Vite 보일러플레이트 완전 제거. 잔여 시 코드베이스 신뢰도 저하
14. ❌ **`uuid` 패키지 추가** — `crypto.randomUUID()` 브라우저 표준 사용 (Chrome/Edge 최신 2버전 보장)
15. ❌ **`onUnhandledRequest: 'error'` 설정** — Vite HMR/asset 요청을 MSW가 에러로 보고함. `'bypass'` 사용
16. ❌ **백엔드 API 서버 띄우기 시도** — Story 4.1·4.3 미완. MSW로 독립 개발

### Previous Story Intelligence (Story 1.1, 1.2)

- **Story 1.1 셋업 검증 명령** ([README.md:74](README.md#L74)): `cd dashboard && npm run build` — 본 스토리 시작 시 동일 명령으로 기존 보일러플레이트 빌드 가능 상태 사전 확인 권장
- **Story 1.1 의존성 핀 전략**: `package.json`이 `^` 시작 버전 사용. `npm install` 시 lockfile 우선. 신규 추가 의존성(msw)도 `^` prefix 유지
- **Story 1.2 review 패턴**: AC 검증 후 `Review Findings` 섹션에 `[Patch]`/`[Defer]` 분류로 코드 리뷰 결과 기록. 본 스토리도 동일 패턴 따름
- **Story 1.2 build-backend 1차 실패 선례**: 외부 도구 가정(setuptools.backends.legacy)이 환경에 없어 실패. 본 스토리에서 `npx msw init` 도 1.1에서 설치된 msw 패키지 의존이므로 Task 1.2 → 1.3 순서 엄수
- **Foojay/setuptools 선례**: 스캐폴딩 검증과 실제 의존성 추가 검증은 별개. Task 11의 build/dev 검증을 누락하지 말 것

### Testing Requirements

- 본 스토리는 화면 골격이므로 **단위 테스트 신규 작성은 선택적**. 필수는 Task 11의 수동 검증 흐름.
- **자동화된 테스트 권장 (선택사항)**:
  - `src/api/client.test.ts` — `ProblemDetailError` 변환 로직 단위 테스트 (`vitest`는 1.1에서 미설치 — 추가 시 별도 결정 필요)
  - `src/components/common/ErrorBoundary.test.tsx` — 에러 throw 시 복구 UI 렌더링
- **테스트 프레임워크 미도입 결정**: architecture.md에서 dashboard 테스트는 `*.test.tsx` 코드 옆 배치 (P8 L370) 명시되었으나 vitest 설치는 별도 스토리에서 처리. 본 스토리에서 vitest 도입 시 scope 확장 — **금지**. Story 5.4 또는 별도 frontend testing 스토리에서 처리
- E2E 검증은 Story 4.5에서 (`tests/performance/test_pipeline_latency.py` 5분 반영 검증)

### Project Structure Notes

- 본 스토리에서 만드는 `src/api/client.ts`, `src/types/api.ts`, `src/router.tsx`, `src/components/common/`은 **Story 4.5·4.6의 의존성**. 인터페이스 변경 시 두 후속 스토리 영향. 변경 시 epics.md AC 재검토 필수
- `src/mocks/handlers.ts`는 4.5에서 `GET /detections`, `GET /detections/{id}`, `POST /crawl/trigger` 핸들러 추가. 4.6에서 `GET /stats?period=weekly|monthly` 분기 확장. **handlers 배열 export로 확장 가능 구조 유지**
- `pages/DetectionList/`, `pages/DetectionDetail/`, `pages/Stats/`는 본 스토리에서 placeholder만. 디렉토리 구조 + 라우팅만 확보
- `dashboard/src/.env.example` — Story 1.3 `infra/.env.example` 루트 통합 정책과 별개. 프론트엔드 환경변수는 Vite가 `VITE_` prefix만 노출하므로 dashboard 로컬 관리

### References

- [Epic 4 Story 4.4 AC](_bmad-output/planning-artifacts/epics.md#L552-L570) — 본 스토리의 Source of Truth
- [Epic 4 UX Design Requirements UX-DR1·UX-DR5·UX-DR6](_bmad-output/planning-artifacts/epics.md#L86-L93)
- [PRD Frontend (React SPA)](_bmad-output/planning-artifacts/prd.md#L228-L240) — 4개 화면, 1280px, Chrome/Edge, 인증 없음
- [PRD Functional Requirements FR23·FR24·FR25](_bmad-output/planning-artifacts/prd.md#L383-L385)
- [PRD NFR2 — 대시보드 ≤ 3초](_bmad-output/planning-artifacts/prd.md#L402)
- [PRD 탐지 유형 enum 5종](_bmad-output/planning-artifacts/prd.md#L280)
- [Architecture Frontend Architecture](_bmad-output/planning-artifacts/architecture.md#L207-L213) — TanStack Query, React Router v7, 상태 관리
- [Architecture P1 JSON camelCase](_bmad-output/planning-artifacts/architecture.md#L250-L266)
- [Architecture P4 에러 코드](_bmad-output/planning-artifacts/architecture.md#L294-L306)
- [Architecture P5 ISO 8601 UTC](_bmad-output/planning-artifacts/architecture.md#L310-L321)
- [Architecture P9 ProblemDetail 전파](_bmad-output/planning-artifacts/architecture.md#L375-L383)
- [Architecture X-Correlation-ID](_bmad-output/planning-artifacts/architecture.md#L204)
- [Architecture dashboard/ 디렉토리 구조](_bmad-output/planning-artifacts/architecture.md#L559-L585)
- [Architecture FR 카테고리 → 디렉토리 매핑](_bmad-output/planning-artifacts/architecture.md#L693-L702)
- [Story 1.1 Sprint Status — dashboard scaffolding 완료](_bmad-output/implementation-artifacts/sprint-status.yaml#L53)
- [Story 1.2 done — shared/ 모듈 (Python 전용, 본 스토리 무관)](_bmad-output/implementation-artifacts/1-2-공유-인터페이스-계약-및-구조화-로깅-수립.md)
- [README — dashboard 셋업 명령](README.md#L51-L53)
- [MSW v2 Browser Integration](https://mswjs.io/docs/integrations/browser/) — 외부 공식 문서

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 — BMad `dev-story` workflow

### Debug Log References

| 단계 | 명령 / 이슈 | 결과 |
|---|---|---|
| 1차 build | `npm run build` (BarChart `Record<string, string \| number>` prop) | **실패** — `SiteDistributionEntry` 인덱스 시그니처 부재로 TS2322 |
| 2차 build | BarChart에 `<T extends object>` 제네릭 + `xKey: keyof T & string` | **실패** — Recharts v3 `TypedDataKey<T, any>` 타입과 nominal 불일치 |
| 3차 build | BarChart prop을 `ReadonlyArray<Record<string, unknown>>`로 단순화 + 호출부 캐스트 | **실패** — TS2352 unknown 우회 요구 |
| 4차 build | BarChart 인터페이스를 `{name, value}[]`로 통일 (PieChart와 동일), Dashboard에서 `data.map`으로 변환 | **성공** — 747KB 번들 (chunk size 경고만) |
| dev 부팅 | `npm run dev` | `VITE v8.0.10 ready in 90 ms` |
| 4 URL smoke test | `curl http://localhost:5173/{,/detections,/detections/1,/stats}` | 모두 200 OK |
| MSW 워커 서빙 | `curl http://localhost:5173/mockServiceWorker.js` | 200 OK |
| 번들 격리 검증 | `grep -l "msw" dist/assets/*.js` | 0건 — production 번들에 MSW 코드 부재 확정 |
| lint | `npm run lint` | 0 errors (자동 생성 mockServiceWorker.js에 1 warning) |

### Completion Notes List

**최종 AC 검증 결과 (2026-04-27):**

- ✅ AC1, #2, #3: Dashboard 페이지가 todayCount/delta 표시 + PieChart(유형) + BarChart(사이트) 렌더링. mock 데이터로 검증
- ✅ AC4: `data.todayCount === 0` 분기 시 "오늘 탐지된 게시글이 없습니다" Empty State. TypeDistribution/SiteDistribution도 빈 배열일 때 별도 Empty 메시지
- ✅ AC5: LastUpdated 컴포넌트 — `dataUpdatedAt` + `formatDistanceToNow` + ko locale. 30초 setInterval로 라벨 자동 갱신
- ✅ AC6: createBrowserRouter + 4개 라우트 (/, /detections, /detections/:id, /stats). curl 4건 모두 200
- ✅ AC7: useStatsQuery `refetchInterval: 60_000`. RootLayout에서 `useIsFetching()` 훅으로 헤더 우측 RefreshIndicator 제어
- ✅ AC8: errorElement에 ErrorBoundary 등록. ProblemDetailError instanceof 분기 + isRouteErrorResponse 분기 + 일반 Error 분기
- ✅ AC9: LoadingSpinner SVG + size sm/md/lg + label. Dashboard 초기 로딩 시 lg 사이즈로 표시
- ✅ AC10: ProblemDetailError 클래스 + 인터셉터 — `isProblemDetail` 타입 가드로 5필드(type/title/status/detail/errorCode) 검증 후 변환
- ✅ AC11: MSW v2 — `import.meta.env.DEV` 분기 + 동적 import + `onUnhandledRequest: 'bypass'`. **`grep "msw" dist/` 0건으로 production 번들 미포함 확정**
- ✅ AC12: `npm run build` 0 에러, 4 URL 모두 200 응답 (Vite SPA fallback이 index.html 서빙, React Router가 클라이언트 사이드 라우팅)
- ⏳ AC13 (≤3초 NFR2): 코드 레벨 검증 — Vite ready 90ms + React 19 + 단일 chunk 747KB (gzip 228KB). Chrome DevTools Network 탭 수동 측정은 사용자 검증 영역

**보일러플레이트 제거 완료:**
- 삭제: `src/App.tsx`, `src/App.css`, `src/assets/{react.svg,vite.svg,hero.png}`, `public/icons.svg`
- `src/index.css` — 보일러플레이트 CSS 변수 + 카운터 스타일 제거하고 폰트/리셋만 유지

**TypeScript 타입 시스템 결정:**
- BarChart 인터페이스를 PieChart와 동일한 `{name: string; value: number}[]` 형태로 통일 — Recharts v3의 TypedDataKey 호환성 문제 회피 + 차트 래퍼 일관성 확보 + 호출부에서 명시적 변환으로 데이터 의도 명확화
- ProblemDetail 5필드 타입가드(`isProblemDetail`)로 unknown 응답 안전 변환 — 백엔드 미구현 상태에서도 P9 패턴 강제 적용 가능

**Story 4.5/4.6 의존성 (변경 시 영향):**
- `src/api/client.ts` apiClient 인스턴스 — 4.5 detections, 4.6 stats period 분기 모두 재사용
- `src/types/api.ts` Detection·DetectionListResponse — 4.5에서 필터 파라미터 타입 추가 예정
- `src/mocks/handlers.ts` handlers 배열 — 4.5에서 detections/{id}/crawl 핸들러 추가, 4.6에서 stats period 분기 확장
- `src/components/charts/{Pie,Bar}Chart.tsx`, `src/components/charts/colors.ts` — 4.6 LineChart 추가 시 colors.ts CHART_PALETTE 재사용
- `src/components/common/{ErrorBoundary,LoadingSpinner,RefreshIndicator}.tsx` — 모든 후속 페이지 공통 사용

### File List

**신규 생성 (dashboard/):**
- `src/types/api.ts`
- `src/api/client.ts`
- `src/api/stats.ts`
- `src/mocks/handlers.ts`
- `src/mocks/browser.ts`
- `src/components/common/ErrorBoundary.tsx`
- `src/components/common/LoadingSpinner.tsx`
- `src/components/common/RefreshIndicator.tsx`
- `src/components/charts/PieChart.tsx`
- `src/components/charts/BarChart.tsx`
- `src/components/charts/colors.ts`
- `src/layouts/RootLayout.tsx`
- `src/router.tsx`
- `src/pages/Dashboard/index.tsx`
- `src/pages/Dashboard/TodayCount.tsx`
- `src/pages/Dashboard/TypeDistribution.tsx`
- `src/pages/Dashboard/SiteDistribution.tsx`
- `src/pages/Dashboard/LastUpdated.tsx`
- `src/pages/DetectionList/index.tsx` (placeholder)
- `src/pages/DetectionDetail/index.tsx` (placeholder)
- `src/pages/Stats/index.tsx` (placeholder)
- `dashboard/.env.example`
- `public/mockServiceWorker.js` (msw init 자동 생성)

**수정 (dashboard/):**
- `src/main.tsx` — MSW + QueryClient + RouterProvider 통합
- `src/index.css` — 보일러플레이트 제거 + 폰트/리셋만 유지
- `package.json` — `msw@^2.13.6` devDependency + `msw.workerDirectory: "public"` 추가
- `package-lock.json` — 263 + 49 packages 추가

**삭제 (dashboard/):**
- `src/App.tsx`
- `src/App.css`
- `src/assets/react.svg`
- `src/assets/vite.svg`
- `src/assets/hero.png`
- `public/icons.svg`

**수정 (프로젝트 루트):**
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 4-4 ready-for-dev → in-progress → review, epic-4 backlog → in-progress

## Change Log

| 날짜 | 변경 | 사유 |
|---|---|---|
| 2026-04-27 | BarChart 인터페이스를 generic `<T>` → `{name, value}[]` 통일 | Recharts v3 TypedDataKey 호환성 문제. PieChart와 동일 인터페이스로 일관성 확보 |
| 2026-04-27 | `public/icons.svg` 삭제 | Vite 스캐폴딩 보일러플레이트 잔여물. 대시보드에서 사용처 없음 |
