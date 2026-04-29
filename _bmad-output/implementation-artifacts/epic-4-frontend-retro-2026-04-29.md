# Epic 4 (Frontend Portion) Retrospective

**Date:** 2026-04-29
**Epic:** Epic 4 — 탐지 결과 조회 및 통계 대시보드 (프론트엔드 부분 한정)
**Scope:** 본 회고는 인프라·프론트 담당이 직접 작업한 5개 프론트 스토리만 다룬다. 백엔드 4-1 / 4-2 / 4-3 (다른 팀원 영역, 현재 backlog) 은 회고 범위 외.
**Type:** Partial retrospective — 프론트 5개 스토리 모두 done, 백엔드 3개는 backlog
**Facilitator:** Amelia (Developer)

---

## 1. Epic Summary

### Stories Reviewed (Done)

| Story | 설명 | Status |
|---|---|---|
| 4-4 | React 대시보드 메인 화면 + 라우팅 골격 (MSW 모킹) | done |
| 4-4-1 | Tailwind v4 + shadcn 디자인 시스템 인프라 도입 | done (UX Spec 기반, lightweight) |
| 4-4-2 | Custom 컴포넌트 5종 + Dashboard C-Light 재구성 | done (UX Spec 기반, lightweight) |
| 4-5 | 탐지 목록·상세 화면 + 키보드 단축키 + 수동 크롤링 트리거 | done (UX Spec 기반, lightweight) |
| 4-6 | 통계 화면 + 주간/월간 추이 | done (UX Spec 기반, lightweight) |

### Stories Out of Scope (백엔드 담당 영역)

- 4-1 Spring REST API 기반 구조 — backlog
- 4-2 탐지 상세 조회/수동 크롤링 트리거 엔드포인트 — backlog
- 4-3 통계 엔드포인트 — backlog

### Delivery Metrics

- 본인 담당 스토리 완료: 5/5 (100%)
- 코드 리뷰 패치: 24건 (Critical 2 / High 6 / Medium 11 / Low 5) — 디자인 시스템 v10 overhaul 단계
- 보안 이슈: 0건 (Blind Hunter / Edge Case Hunter / Security 3-layer 리뷰 통과)
- Deferred 항목: 6건 carryover (deferred-work.md)
- Production 번들 검증: dist 에 MSW 0건 ✅
- PR: #9 (디자인 시스템 v10 overhaul) merged

---

## 2. What Went Well

### A. MSW v2 백엔드 의존성 분리 전략

- Story 4-4 에서 `import.meta.env.DEV` 분기 + 동적 import + `onUnhandledRequest: 'bypass'` 설정 정착
- Production 번들 격리 검증: `grep -l "msw" dist/assets/*.js` → 0건
- 4-5 / 4-6 에서 동일 패턴으로 handlers 배열만 확장 (detections / detail / crawl / stats period)
- **결과: 백엔드 4-1~4-3 backlog 상태에서도 프론트 5개 스토리 모두 막힘 없이 done. 본인 작업을 독립적으로 진척시키는 핵심 결정.**

### B. 공통 인프라 재사용 설계

- 4-4 에서 깐 `api/client.ts` (axios + ProblemDetailError + X-Correlation-ID), `types/api.ts`, `components/common/{ErrorBoundary, LoadingSpinner, RefreshIndicator}` 가 4-5 / 4-6 에서 추가 작업 없이 그대로 활용
- 인터페이스 변경 0회 — 4-4 단계에서 충분히 안정적인 추상화 도달

### C. 디자인 시스템 채택 (shadcn + Tailwind v4 + 토큰)

- shadcn(radix-nova) 11종 + Custom 11종 (C1~C11) 체계 정착
- 토큰 시스템 v10 (라이트/다크 + WCAG AA 2-tier + N1 severity) 까지 통합
- 3-layer 리뷰 0 보안 이슈 통과

### D. 키보드 단축키 시스템

- Story 4-5 GlobalShortcutProvider — j/k/enter/o/c/esc/g+t/g+d/g+l/g+s
- 데스크톱 우선 UX (PRD L233) 결정과 부합
- 한 번에 정착, 후속 회귀 없음

---

## 3. Challenges / Pain Points

### E. Recharts v3 + TypeScript 타입 시스템 불일치 (Story 4-4)

- BarChart `<T extends object>` generic 시도 → Recharts v3 `TypedDataKey<T, any>` 와 nominal 불일치
- 4번 build 실패 후 결국 `{name, value}[]` 단일 인터페이스로 통일 (PieChart 와 동일)
- **교훈:** 외부 라이브러리 v3 docs 사전 확인 필요. 라이브러리 타입과 내부 타입을 강제로 맞추려 시간 낭비.

### F. 디자인 시스템 v10 overhaul 후행 발생

- 4-4-1 (Tailwind/shadcn) → 4-4-2 (C-Light) → 4-5 / 4-6 본구현 → **이후** 토큰 v10 + 3-column (Sidebar/Topbar/RightRail) + Hero + N1 severity + 24건 패치
- 결과: 이미 만든 페이지를 두 번 손댐 (7+ 커밋, 24 패치)
- Deferred 6건 중 4건 (correlation pill mock, REVIEWED_FRACTION mock, Today 롤오버, Freshness 회귀) 이 overhaul 단계에서 발생
- **교훈:** UX Spec lock 시점이 모호했음. 다음 프론트 작업 시 디자인 시스템 결정을 본구현 시작 전에 동결하는 게 효율적.

### G. Deferred mock 데이터 누적

- Hero correlation pill (unique·중복 산술 fabricated)
- REVIEWED_FRACTION 0.25 고정 mock
- Today timestamp 자정 롤오버 (렌더 시점 1회 계산)
- RecentAlertList "High confidence" 헤딩 미스매치
- FreshnessIndicator / NewDetectionsBadge 제거 회귀
- 3-column 레이아웃 모바일 breakpoint 부재
- **교훈:** mock 데이터 추가 시 deferred-work.md 자동 등록 워크플로우가 동작했지만, 백엔드 의존 vs 즉시 처리 가능 분류가 작업 시점에 안 됐음.

### H. Lightweight Story 파일 부재로 인한 추적성 저하

- 4-4-1 / 4-4-2 / 4-5 / 4-6 정식 Story 파일 없이 UX Design Spec 이 spec 역할 수행
- **장점:** 작성 부담 감소, 빠른 진행
- **단점:** 본 회고에서 "어디가 아팠는지" 직접 기록을 끌어올 수 없음 (sprint-status 주석에만 의존)
- **교훈:** lightweight 진행 자체는 유지하되, 작업 종료 시 1~2줄짜리 "Story Notes" (struggle / decision / debt) 항목을 sprint-status 주석 외에 별도 파일에 누적하는 가벼운 보완 고려.

---

## 4. Action Items

### Immediate (본인 도메인, 백엔드 무관 — 즉시 처리 가능)

- [ ] **AI-1: Today timestamp 자정 롤오버 수정** — `dataUpdatedAt` 기반 ticking state 로 교체
  - 위치: `dashboard/src/pages/Dashboard/index.tsx:31`
  - 성공 기준: 60s 폴링 사이 자정이 넘어도 표시 갱신

- [ ] **AI-2: 3-column 레이아웃 desktop-only 명시** — `< lg` breakpoint 동작 정의 (드로어화 또는 명시적 주석)
  - 위치: `dashboard/src/layouts/RootLayout.tsx:20`
  - 결정: PRD L233 (1280px+) 에 따라 명시적 주석으로 desktop-only 선언이 우선. 모바일 대응은 Growth 단계로 명시.

### Deferred (백엔드 4-1~4-3 합류 후 처리)

- [ ] **AI-3: Hero correlation pill 재구현** — 백엔드 grouping 필드 추가 후 fabricated 산술 제거
- [ ] **AI-4: REVIEWED_FRACTION 실데이터 swap** — Stats API 에 reviewed count 필드 추가 시 즉시 교체
- [ ] **AI-5: RecentAlertList 헤딩 결정** — 백엔드 `minConfidence` 필터 지원 후 "Recent" 변경 vs query 추가 결정
- [ ] **AI-6: FreshnessIndicator / NewDetectionsBadge 복원 결정** — Hero 시스템 상태 줄에 dataUpdatedAt 연결 vs 영구 제거. 제품 결정 필요.

### Process (다음 프론트 작업에 적용)

- [ ] **AI-7: 외부 라이브러리 v 메이저 사용 시 타입 호환성 사전 검증** — 본구현 시작 전 `package.json` 타입 정의 + 공식 docs 1회 확인 단계 추가
- [ ] **AI-8: 디자인 시스템 변경은 본구현 시작 전 lock** — 토큰 / 컴포넌트 / 레이아웃 결정 변경이 본구현 후 발생하면 별도 overhaul 사이클로 명시 분리 (이번처럼 회귀 비용 발생)
- [ ] **AI-9: Lightweight 스토리 진행 시 종료 노트 1~2줄 누적** — struggle / decision / debt 한 줄씩만 별도 파일에 적재, 회고 추적성 보완

---

## 5. Critical Path (다음 작업 진입 전)

본인 담당 영역에서 차단 요소는 **없음**. 백엔드 4-1~4-3 합류는 다른 팀원 영역으로 본 회고 범위 외.

다음 본인 도메인 작업 후보:
1. **Epic 1 잔여**: 1-1 / 1-5 review → done 정합성 확인 (sprint-status 업데이트)
2. **프론트 안정화**: AI-1, AI-2 즉시 처리 가능 항목
3. **Epic 5 인프라**: 5-0 배포 토폴로지 spike 부터 시작 가능 (백엔드 합류 시점과 무관하게 진행 가능)
4. **프론트 E2E 자동화** (선택): 백엔드 합류 시점 안전망

---

## 6. Readiness Assessment

| 항목 | 상태 | 비고 |
|---|---|---|
| Testing & Quality | ✅ 통과 | 3-layer 리뷰 0 보안 이슈 통과. NFR4 5분 반영 검증은 Story 5.1 백엔드 합류 후로 deferred (sprint-status 명시) |
| Deployment | ⏳ N/A | AWS 프로비저닝은 Epic 5 (5-3) 영역 |
| Stakeholder Acceptance | ⏳ Pending | 백엔드 합류 후 통합 검증에서 결정 |
| Technical Health | ✅ 안정 | 코드 리뷰 24건 패치 완료 + simplify refactor 사이클 완료 (refactor 커밋 6130bc0, f61be37, 35cdd5e) |
| Unresolved Blockers | ⚠️ Deferred 6건 | 4건 백엔드 의존 / 2건 즉시 처리 가능 (AI-1, AI-2) |

---

## 7. Significant Discoveries

본 epic 에서 다음 epic 의 계획을 근본적으로 바꾸는 발견은 없음. 디자인 시스템 v10 은 후속 프론트 작업 (백엔드 통합 시) 그대로 활용 가능.

다만 **프로세스 차원**에서 다음 권장:
- 다음 디자인 시스템 변경 사이클이 또 발생하면, 이번처럼 본구현 후 overhaul 이 아니라 별도 디자인 시스템 스토리로 분리 (회귀 비용 가시화)

---

## 8. Key Takeaways (3 Sentences)

1. **MSW 모킹 + 공통 인프라 재사용 전략은 성공적이었다** — 백엔드 backlog 상태에서도 프론트 5개 스토리 모두 done.
2. **디자인 시스템 v10 overhaul 이 본구현 후 발생한 게 가장 큰 비효율이었다** — 다음엔 본구현 전 디자인 시스템 lock.
3. **Deferred 6건 중 2건 (AI-1, AI-2) 은 백엔드와 무관하게 즉시 처리 가능** — 다음 작업 진입 전 정리.

---

## Appendix: Key Commits

| Commit | Story | 설명 |
|---|---|---|
| `e8a9762` | 4-4 | React 메인 대시보드 + MSW 모킹 + 라우팅 골격 |
| `8312084` | 4-4-1 | 디자인 시스템 인프라 도입 (Tailwind/shadcn) |
| `39c43c4` | 4-4-2 | Custom 컴포넌트 5종 + C-Light 재구성 |
| `023c535` | 4-5 데이터 | shadcn 6종 + MSW handler 확장 |
| `1995b0b` | 4-5 화면 | 탐지 목록/상세 + 키보드 단축키 + 수동 크롤링 |
| `6b2c1a2` | 4-6 | 통계 화면 + 주간/월간 추이 |
| `963d492` | overhaul | 토큰 시스템 v10 이식 + 다크 테마 |
| `d122486` | overhaul | 3-column 레이아웃 |
| `9d35b9d` | overhaul | N1 severity 배지 |
| `8aa0e47` | overhaul | Hero + Recent · High confidence |
| `1d8dc24` | overhaul | 24건 일괄 패치 (Critical 2 / High 6 / Medium 11 / Low 5) |
| `f61be37`, `6130bc0` | refactor | simplify 정리 사이클 |
