# dashboard

Tracker 운영자 대시보드 — React 19 SPA. 탐지 결과 조회, 기간별 분석, 알림 연동, 수동 크롤링 트리거를 5분 SLA 안에 마무리하는 데 봉사한다.

루트 [README](../README.md)와 [`_bmad-output/planning-artifacts/ux-design-specification.md`](../_bmad-output/planning-artifacts/ux-design-specification.md)가 제품/UX 맥락을 담당한다. 본 README는 dashboard 디렉토리에 들어온 개발자가 바로 작업할 수 있는 실행 정보와 코드 구조를 정리한다.

## 기능

- Dashboard: 오늘의 탐지 현황과 기간별 탐지 섹션을 분리한다.
- 기간별 분석: 최근 7일/30일 기준으로 Quick filters, Hotspots, 탐지 추이를 함께 갱신한다.
- DetectionList: 사이트, 유형, 언어, 지정 날짜, 최근 7일/30일 필터를 URL query로 유지한다.
- DetectionDetail: 원문·번역·분류 근거·원본 URL을 확인한다.
- Notifications: 알림 채널, 규칙, 전송 이력을 관리한다.
- Manual crawl: 상단 버튼과 단축키로 수동 크롤링을 트리거하고 진행 상태를 확인한다.

## 스택

| 영역 | 선택 |
|---|---|
| 런타임/빌드 | Node.js 22 LTS, Vite 8, React 19, TypeScript 6 |
| 패키지 매니저 | pnpm 11.1.1 (`packageManager` 필드 + corepack 자동 활성, Node 16.9+ 필요) |
| 라우팅 | React Router v7 (코드 스플릿 `lazy()` + route-level chunk) |
| 서버 상태 | TanStack Query v5 (`useQuery({ refetchInterval: 60_000 })`) |
| 디자인 시스템 | Tailwind v4 + shadcn/ui (style: new-york) + Radix Primitives |
| 차트 | Recharts (`--chart-1`~`--chart-5` CSS 변수 주입) |
| 폼·검증 | URL query 기반 탐지 필터 + 알림 채널/규칙 생성 폼 |
| 알림 | Sonner (toast) |
| 아이콘 | lucide-react |
| 테마 | `data-theme` 커스텀 관리 (Topbar.tsx `useState` + localStorage + `document.documentElement.setAttribute`). FOUC 가드는 `index.html` 인라인 스크립트. `next-themes` 패키지 설치됨이나 ThemeProvider는 미사용. |
| 모바일 | vaul drawer + `useIsMobile()` (Tailwind `md` 768px breakpoint) |
| 단위 테스트 | Vitest(jsdom) + Testing Library + `@testing-library/jest-dom` |
| Mock API | MSW v2 (`public/mockServiceWorker.js`, dev에서 항상 활성 / prod는 `VITE_USE_MOCK=true` 빌드만 활성) |
| 데모 빌드 | `VITE_USE_MOCK=true pnpm build` — prod 번들에 MSW worker 보존, frontend-only 데모용 (`infra/compose.demo.yml`) |
| E2E | Playwright 1.60 (chromium 데스크톱 + Pixel 7 모바일) |

## 명령

```bash
# 패키지 매니저는 pnpm. Node 16.9+의 corepack으로 자동 활성됨 (`corepack enable` 한 번).
pnpm install
pnpm dev             # Vite dev server (MSW 활성 — VITE_API_BASE_URL 미설정 시)
pnpm build           # tsc -b && vite build
pnpm preview         # 빌드 산출물 미리보기
pnpm lint            # eslint (@eslint-react + react-hooks + react-refresh)

pnpm test            # Vitest run (CI 모드)
pnpm test:watch      # Vitest watch
pnpm test:coverage   # Vitest + v8 coverage

pnpm exec playwright install --with-deps  # 최초 1회
pnpm e2e             # 데스크톱 + 모바일 spec 모두 실행
```

## 환경 변수

| 키 | 기본 | 설명 |
|---|---|---|
| `VITE_API_BASE_URL` | 미설정 | 실 API 엔드포인트. 미설정 시 axios baseURL이 `/api`로 떨어지고, dev에선 MSW worker가 가로채 mock 응답 반환. 로컬 백엔드 통합 시 `http://localhost:8080/api`. 프로덕션은 Caddy reverse-proxy 경로 `/api` |
| `VITE_USE_MOCK` | `false` | `true`로 빌드 시 prod 번들에도 MSW worker 포함 — frontend-only 데모용. `vite.config.ts`의 `removeDevMswWorker`가 이 플래그를 보고 `dist/mockServiceWorker.js` 보존 여부를 결정한다 |

## 디렉토리 구조

```
src/
├── api/            # axios 클라이언트 + TanStack Query hooks (useDetectionsQuery, useStatsSuspenseQuery 등)
├── components/
│   ├── ui/         # shadcn primitives (button, card, dialog, drawer, select, table, tabs, sonner, skeleton, kbd)
│   ├── charts/     # Recharts 래퍼 (BarChart, LineChart, PieChart, colors)
│   └── tracker/    # 도메인 컴포넌트 (DetectionRow, DetectionCard, BilingualPanel, ManualCrawlButton, ConfidenceBadge, TypeIcon, ChartCard, EmptyState, ShortcutsCheatsheet, RecentAlertList, labels)
├── layouts/        # RootLayout / Sidebar(햄버거 drawer) / Topbar / PageContainer / RightRail
├── pages/          # Dashboard / DetectionList / DetectionDetail / Notifications / Stats (route-level lazy)
├── lib/            # detectionFilter / filterOptions / severity / statsView / time / shortcuts / sources / useDetectionFilter / useIsMobile / utils / crawlProgress
├── mocks/          # MSW v2 handlers + dev fixtures
├── main.tsx        # createRoot + QueryClientProvider + GlobalShortcutProvider + RouterProvider
└── index.css       # Tailwind v4 entry + CSS variable tokens (light/dark)
```

## 키보드 단축키 (데스크톱)

- `j` / `k` — 목록 행 다음/이전
- `enter` — 상세 진입, `esc` — 목록 복귀
- `o` — 출처 URL 새 탭, `c` — 링크 복사
- `g + d` — 대시보드, `g + l` — 탐지 목록, `g + n` — 알림 연동, `g + t` — 수동 트리거
- `/` — 검색 focus, `?` — 단축키 cheatsheet

모바일 < md 에서는 단축키 비활성, 햄버거 menu drawer + 카드 탭으로 대체.

## 백엔드 통합 메모

- API 응답은 camelCase (Jackson). Spring `ProblemDetail` (RFC 9457) 기반 에러를 `ErrorBoundary` 에서 사용자 메시지로 변환.
- `X-Correlation-ID` 응답 헤더는 axios interceptor 가 sessionStorage 에 캐시 → 사용자가 신고 시 콘솔에서 식별 가능.
- 60초 폴링은 `useQuery({ refetchInterval: 60_000 })` 기본값. 대시보드 / 목록 모두 동일.
- `/stats?period=weekly|monthly`는 기간별 분포와 추이를 같은 기준으로 반환한다.
- `/detections`는 `date` 또는 `range=7d|30d` 기간 필터를 지원한다. `date`가 있으면 `range`보다 우선한다.

## 모바일 지원 메모

- 진입 트리거: `useIsMobile()` (`window.matchMedia('(max-width: 767px)')`).
- 사이드바: lg 이상 고정 / `< lg`에서 햄버거 버튼 → vaul drawer 슬라이드.
- DetectionList: `< md`에서 `<table>` 숨김, `DetectionCard` 그리드로 교체. 행 클릭 = 상세 진입.
- FilterBar: `< md`에서 bottom Drawer 로 전체 필터 패널 표시.
- E2E: `e2e/mobile.mobile.spec.ts` — Pixel 7 viewport 3 시나리오.
- PWA(`vite-plugin-pwa`)는 frontend-only 데모 경로와 충돌해 제거됐다. 모바일 디자인·컴포넌트는 그대로 유효하다.
