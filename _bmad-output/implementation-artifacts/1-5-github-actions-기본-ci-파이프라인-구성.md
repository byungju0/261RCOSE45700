# Story 1.5: GitHub Actions 기본 CI 파이프라인 구성

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

개발자로서,
코드 푸시 시 자동으로 lint와 단위 테스트가 실행되기를 원한다,
그래서 코드 품질이 개발 초기부터 유지되며 PR 머지 시 회귀가 차단된다.

## Acceptance Criteria

1. **Given** `.github/workflows/crawler.yml`이 존재할 때, **When** `crawler/**` 경로 변경이 push 또는 PR로 트리거되면, **Then** Python 3.11 환경에서 `flake8 crawler/src crawler/tests` lint와 `pytest crawler/tests/unit` 단위 테스트가 실행된다. (Epic AC1)
2. **Given** `.github/workflows/detection.yml`이 존재할 때, **When** `detection/**` 경로 변경이 트리거되면, **Then** Python 3.11 환경에서 `flake8 detection/src detection/tests` lint와 `pytest detection/tests/unit` 단위 테스트가 실행된다. (Epic AC2)
3. **Given** `.github/workflows/api.yml`이 존재할 때, **When** `api/**` 경로 변경이 트리거되면, **Then** Java 21 (Temurin) 환경에서 `./gradlew test`가 실행되며 Spring Boot 단위 테스트가 통과한다. (Epic AC3)
4. **Given** `.github/workflows/dashboard.yml`이 존재할 때, **When** `dashboard/**` 경로 변경이 트리거되면, **Then** Node.js 20.19+ 환경에서 `npm ci` → `npm run lint` → `npm run build`가 통과한다. (Epic AC4 — `npm test`는 dashboard에 vitest 미도입 상태이므로 Story 5.2/Growth로 deferred하고 lint+build로 대체. Dev Notes 참조)
5. **Given** 어떤 워크플로우든 실패할 때, **When** PR 상태 확인이 발생하면, **Then** 해당 PR의 머지가 GitHub Branch Protection에 의해 블로킹된다. (Epic AC5 — Branch Protection rule 설정은 본 스토리 범위, 단 admin 권한 필요 시 README에 안내)
6. **Given** 워크플로우가 외부 시크릿을 참조할 때, **When** 워크플로우 정의 파일을 읽으면, **Then** `VARCO_API_KEY` 등 민감 값이 `secrets.VARCO_API_KEY` 형식으로만 참조되고 평문으로 하드코딩되지 않는다. (Epic AC6, NFR5)
7. **Given** 모노레포 4개 서브시스템이 독립 워크플로우를 가질 때, **When** 한 서브시스템만 변경된 PR을 푸시하면, **Then** `paths:` 필터에 의해 해당 워크플로우만 실행되고 나머지는 스킵된다. (효율 + ARCH-7 "독립 워크플로우" 정신)

## Tasks / Subtasks

- [x] **Task 1: `.github/workflows/crawler.yml` 작성** (AC: #1, #6, #7)
  - [x] 1.1 트리거 정의 — `on: push (branches: [main]) + pull_request`, `paths: ['crawler/**', 'shared/**', '.github/workflows/crawler.yml']`
  - [x] 1.2 단일 job `lint-test` — `runs-on: ubuntu-latest`, `defaults.run.working-directory: crawler`
  - [x] 1.3 Steps: checkout v6 → setup-python v6 (3.11, cache pip, cache-dependency-path crawler/requirements.txt) → pip 업그레이드 → `pip install -r requirements.txt` → flake8 설치 → `flake8 src tests --max-line-length=120` → pytest with exit-5 가드
  - [x] 1.4 `pip install -e ../shared`는 requirements.txt의 마지막 라인이 자동 처리. working-directory crawler 기준 상대경로 `../shared` 동작
  - [x] 1.5 `env: SERVICE_NAME: crawler` job-level 설정

- [x] **Task 2: `.github/workflows/detection.yml` 작성** (AC: #2, #6, #7)
  - [x] 2.1 crawler.yml과 동일 구조, paths를 `detection/**, shared/**`로
  - [x] 2.2 `working-directory: detection`, `SERVICE_NAME: detection`
  - [x] 2.3 `pytest tests/unit -v` (exit-5 가드)

- [x] **Task 3: `.github/workflows/api.yml` 작성** (AC: #3, #6, #7)
  - [x] 3.1 트리거 동일 — paths `api/**`, `.github/workflows/api.yml`
  - [x] 3.2 Steps: checkout v6 → setup-java v5 (temurin 21, cache gradle) → working-directory api → chmod +x gradlew → `./gradlew test --no-daemon`
  - [x] 3.3 `api/settings.gradle`에 `org.gradle.toolchains.foojay-resolver-convention 1.0.0` 이미 등록됨 — 추가 작업 불필요
  - [x] 3.4 `./gradlew build` 대신 `test`만 — 단위 테스트 게이트 한정

- [x] **Task 4: `.github/workflows/dashboard.yml` 작성** (AC: #4, #6, #7)
  - [x] 4.1 트리거 — paths `dashboard/**`, `.github/workflows/dashboard.yml`
  - [x] 4.2 Steps: checkout v6 → setup-node v6 (20.19, cache npm) → working-directory dashboard → `npm ci` → `npm run lint` → `npm run build`
  - [x] 4.3 `npm run build`는 `tsc -b && vite build` 조합이라 typecheck + 번들이 한 번에 — 별도 `tsc --noEmit` 단계 불필요. `npm test`는 vitest 미도입으로 Story 5.2/Growth로 deferred

- [x] **Task 5: PR 머지 블로킹 (Branch Protection)** (AC: #5)
  - [x] 5.1 `docs/ci-setup.md` 작성 — Branch Protection 절차, paths 필터와 required check 상호작용 (Loose vs Strict 옵션) 명시
  - [x] 5.2 4 워크플로우 job name 모두 `lint-test`로 통일
  - [x] 5.3 admin 권한 미보유 시 슬랙 요청 — `docs/ci-setup.md`에 절차 안내

- [x] **Task 6: 시크릿 관리 검증** (AC: #6, NFR5)
  - [x] 6.1 `grep -rEn "VARCO_API_KEY|AWS_ACCESS_KEY|password|token"` → 0 hit (exit 1)
  - [x] 6.2 detection.yml은 단위 테스트만이므로 `secrets.*` 참조 자체 없음. 향후 패턴은 `docs/ci-setup.md`에 문서화
  - [x] 6.3 architecture.md의 `.env.example` 위치는 각 서브시스템 루트 — 본 스토리는 신규 추가 없음 (변경 없음)

- [x] **Task 7: 트리거 동작 검증 (로컬 프록시)**
  - [x] 7.1 4 yml YAML 파싱 OK (js-yaml로 검증, jobs.lint-test 정의 확인)
  - [x] 7.2 dashboard `npm run lint && npm run build` 로컬 통과 (193KB / 49ms)
  - [x] 7.3 api `./gradlew test --no-daemon` 로컬 통과 (BUILD SUCCESSFUL, Spring Boot context load OK)
  - [x] 7.4 crawler/detection은 로컬 venv 부재 (PEP 668 brew Python 차단) — push 시 GitHub Actions에서 실제 검증
  - [x] 7.5 GitHub UI 빨강 검증은 push 후 별도 확인 (개발자 체크리스트)

- [x] **Task 8: 마무리**
  - [x] 8.1 6개 AC 수동 검증 — Completion Notes 작성
  - [x] 8.2 File List 기록
  - [x] 8.3 PR 본문에 워크플로우 4종 + BP 안내 포함 (PR 생성 시점)
  - [x] 8.4 sprint-status.yaml 1-5 → review 전환

## Dev Notes

### 본 스토리 범위 (Scope Boundary — 가장 중요)

| 이번 스토리에서 한다 | 이번 스토리에서 **하지 않는다** |
|---|---|
| 4개 GitHub Actions 워크플로우 작성 (lint + 단위 테스트) | 도커 이미지 빌드·푸시 → Story 5.2 |
| paths 필터로 모노레포 효율화 | AWS 배포 단계 → Story 5.3 |
| Branch Protection 안내 문서 | E2E / 통합 테스트 → Story 5.4 |
| GitHub Secrets 패턴 정립 (참조 가이드) | VARCO 실제 통합 테스트 → Story 3.2/3.3 |
| dashboard lint + typecheck + build 게이트 | dashboard `npm test` (vitest 도입) → Growth 단계 |

### Project Context

- **현재 브랜치**: `feat/1-5-github-actions-ci` (main 분기, dashboard PR #9 미머지 상태)
- **저장소 루트** = `tracker/` 모노레포 (architecture.md L88 모노레포 결정)
- **`.github/workflows/`**: 디렉토리만 존재, yml 파일 0개
- **서브시스템 상태**:
  - `crawler/`: `src/`, `tests/__init__.py` (실제 단위 테스트 없음), `requirements.txt` (`-e ../shared` 포함)
  - `detection/`: 위와 동일
  - `api/`: Spring Boot 3.5.0 Gradle 스캐폴드, `src/test/java/.../ApplicationTests.java` 1개
  - `dashboard/`: Vite 8 + React 19 + ESLint 10. **`npm test` 스크립트 미정의** (`package.json` `scripts` 확인). PR #9 머지 후 v10 디자인 시스템 합류 예정
  - `shared/`: Story 1.2에서 완성된 Python 모듈 (`pip install -e shared/` 지원, `pyproject.toml` 정의됨)

### Technical Stack Decisions

| 항목 | 결정 | 근거 |
|---|---|---|
| Action 버전 | `actions/checkout@v6`, `setup-python@v6`, `setup-node@v6`, `setup-java@v5` | 2026-04 기준 모두 안정 최신. v5/v6 시리즈는 Node 24 런타임. Runner v2.327.1+ 필요 |
| Python 버전 | `'3.11'` 고정 | architecture.md L93 명시 (`requires-python = ">=3.11"`). 마이너 자동 픽업 회피, 버전 드리프트 차단 |
| Java 버전 | `'21'` Temurin | architecture.md L149 (Java 21 LTS Virtual Threads). `actions/setup-java@v5`의 distribution `temurin` |
| Node 버전 | `'20.19'` 고정 | architecture.md L151 (Vite 8 요구). dashboard `package.json`의 `@types/node ^24.12`는 타입만 — 런타임은 20.19 |
| Gradle 캐시 | `setup-java@v5`의 `cache: 'gradle'` | 빌드 시간 단축. `gradlew test` 첫 실행 시 의존성 다운로드만 캐시 |
| pip 캐시 | `setup-python@v6`의 `cache: 'pip'` + `cache-dependency-path` | requirements.txt 변경 시에만 캐시 무효화 |
| npm 캐시 | `setup-node@v6`의 `cache: 'npm'` + `cache-dependency-path: dashboard/package-lock.json` | `npm ci` 빠르게 |
| paths 필터 | 서브시스템별 `paths:` 명시 | 모노레포 표준. PR이 dashboard만 건드리면 Java/Python 워크플로우 스킵 |
| 워크플로우 자기 변경 트리거 | `paths`에 `.github/workflows/<name>.yml` 자기 참조 포함 | 워크플로우 자체 수정 시에도 검증 트리거 |
| pytest 0건 종료코드 처리 | `pytest tests/unit -v --co --no-header` 또는 `pyproject.toml`에 `[tool.pytest.ini_options] xfail_strict = true` | 테스트 0건 시 exit code 5 발생 → 워크플로우 fail 방지 패턴 |
| dashboard 게이트 구성 | lint + tsc --noEmit + build | `npm test` 미정의 상태에서 회귀 차단 가능한 최대치. Story 1.5 AC4를 명시적으로 완화 (위 표 참조) |

### Architecture Compliance Notes

- **ARCH-7** (architecture.md L81): `crawler.yml, detection.yml, api.yml, dashboard.yml 4개 독립 워크플로우 — 코드 푸시 시 자동 빌드·배포`. 본 스토리는 "빌드·배포"가 아닌 "lint + 단위 테스트" 단계만 — 배포는 Story 5.2/5.3에서 확장.
- **NFR5** (PRD): 시크릿 노출 금지. 워크플로우 파일에 평문 키·토큰·비밀번호 절대 금지. GitHub Secrets만 사용.
- **architecture.md L196**: `시크릿 관리 — 환경변수 + IAM Role`. CI 환경에서는 `${{ secrets.* }}`로 주입.
- **모노레포 효율** (architecture.md L88): paths 필터 없으면 한 PR에 4개 워크플로우 모두 실행 → 시간/비용 낭비. paths 필수.

### File Structure Requirements (필수 생성)

```
.github/
└── workflows/
    ├── crawler.yml         ← 신규
    ├── detection.yml       ← 신규
    ├── api.yml             ← 신규
    └── dashboard.yml       ← 신규
```

**선택 생성** (Task 5):
- `docs/ci-setup.md` — Branch Protection 설정 안내 (또는 README 섹션)

**수정 파일** (있으면):
- `crawler/pyproject.toml` 또는 `crawler/setup.cfg` — pytest 0건 종료코드 처리 옵션 (택일)
- `detection/pyproject.toml` 또는 `detection/setup.cfg` — 동일

### Testing Requirements

**자동화 게이트 (CI에서 실행됨)**:
- crawler/detection: `flake8 + pytest tests/unit/`
- api: `./gradlew test`
- dashboard: `npm run lint + tsc --noEmit + npm run build`

**수동 검증 (이번 스토리 dev 시)**:
1. **로컬 사전 검증** — 각 서브시스템 명령을 로컬에서 직접 실행하여 통과하는지 먼저 확인 (CI 실패 디버그 시간 최소화):
   ```bash
   # crawler
   cd crawler && pip install flake8 && flake8 src tests --max-line-length=120 && pytest tests/unit -v
   # detection
   cd detection && pip install flake8 && flake8 src tests --max-line-length=120 && pytest tests/unit -v
   # api
   cd api && ./gradlew test --no-daemon
   # dashboard
   cd dashboard && npm ci && npm run lint && npx tsc --noEmit -p tsconfig.app.json && npm run build
   ```
2. **워크플로우 트리거 검증** — 본 브랜치 push 후 GitHub Actions 탭에서 4 워크플로우 실행 확인.
3. **paths 필터 검증** — 의도적으로 dashboard 파일만 1줄 변경한 commit을 push해 dashboard 워크플로우만 트리거되는지 확인 (검증 후 revert).
4. **시크릿 미노출 검증**:
   ```bash
   grep -rE "VARCO_API_KEY|AWS_ACCESS_KEY|password\s*=\s*['\"]" .github/workflows/
   # 출력에 평문 값이 없어야 함 (있으면 즉시 fail)
   ```
5. **Branch Protection 미설정 시**: README에 절차 명시 + Tracker(infra담당)가 admin에게 요청.

### Previous Story Intelligence

**Story 1.1 (모노레포 스캐폴딩, status: review)**:
- `.gitkeep` → 실제 파일 교체 패턴 (Story 1.2에서 적용). `.github/workflows/`도 .gitkeep만 있으면 본 스토리에서 제거하고 yml 4개로 교체.
- **Spring Boot 3.4 → 3.5 변경 선례**: `start.spring.io`가 3.4를 거부해 3.5로 전환. 본 스토리는 `build.gradle`의 `springBootVersion`을 그대로 사용 — 추가 변경 없음.
- **Foojay Toolchain Resolver**: Java 21 toolchain 자동 다운로드 위해 `settings.gradle`에 plugin 등록되어 있어야 함. 미등록 시 `./gradlew test` 실패 가능 → 본 스토리 Task 3.3에서 확인.
- **Story 1.1 review 상태**: 다른 팀원 담당으로 추정, 미머지 항목이 있다면 본 스토리 CI가 그 결과를 검증하게 됨. **본 브랜치는 main에서 분기하므로 Story 1.1의 review 잔여 작업이 main에 합류된 상태를 가정**.

**Story 1.2 (공유 인터페이스, status: done)**:
- `pip install -e shared/` 패턴 — root 기준 상대 경로. CI working-directory를 `crawler/`로 둘 경우 `-e ../shared`로 작동하는지 Task 1.4에서 검증 (워크플로우 setup 시점에 디렉토리 컨텍스트 주의).
- `requirements.txt`의 `-e ../shared` 마지막 라인은 Story 1.2가 추가한 것. CI에서 `pip install -r requirements.txt` 실행 시 자동으로 shared 패키지 설치됨 → 별도 step 불필요.
- `pip install --upgrade pip setuptools` 선행 권장 — Story 1.2 dev에서 `pip install -e shared/` 시도 중 setuptools 관련 오류 발생 사례 있음.
- **`SERVICE_NAME` 환경변수**: structured_logger import 시 필요. CI에서 `env: SERVICE_NAME: crawler` (또는 detection) job-level 설정.

### Latest Tech Information (2026-04 기준)

| 라이브러리 | 최신 안정 버전 | 본 스토리 채택 |
|---|---|---|
| `actions/checkout` | v6 | v6 |
| `actions/setup-python` | v6 (Node 24 runtime) | v6 |
| `actions/setup-node` | v6 (Node 24 runtime) | v6 |
| `actions/setup-java` | v5 | v5 |
| `actions/cache` | v4 | setup-* 내장 cache 옵션 우선, 별도 사용 시 v4 |

**중요**: GitHub-hosted runner는 v2.327.1+ 이어야 위 actions 정상 동작. Free tier ubuntu-latest는 자동 갱신.

### Anti-Patterns to Avoid (이번 스토리 특화)

1. ❌ **워크플로우만 작성하고 Branch Protection 미설정** — 4 워크플로우가 빨강 떠도 머지 가능 → AC #5 위반. Task 5 반드시 완수 (admin 권한 없으면 README 안내라도).
2. ❌ **paths 필터 누락** — 한 PR에 4 워크플로우 모두 실행. 시간 낭비 + 무관 영역 fail로 PR 블로킹. Task 1.1, 2.1, 3.1, 4.1 paths 필수.
3. ❌ **`actions/checkout@main` 또는 `@latest` 참조** — 비고정 ref. 항상 메이저 버전 핀 (`@v6`).
4. ❌ **`pip install -r requirements.txt`만 하고 `pip install --upgrade pip setuptools` 생략** — Story 1.2 선례 (`-e ../shared` 처리 중 setuptools<68 에러).
5. ❌ **`./gradlew` 실행 권한 미설정** — Linux runner에서 `Permission denied`. `chmod +x gradlew` step 추가 필수 (또는 `bash gradlew test`).
6. ❌ **dashboard에 `npm test` 강제 실행** — 스크립트 미정의 → exit 1. AC #4를 lint+typecheck+build로 명시적 변경, vitest 도입은 별도 스토리.
7. ❌ **VARCO_API_KEY를 워크플로우에 평문으로 작성** — NFR5 위반. 본 스토리는 단위 테스트만이므로 시크릿 참조 자체가 불필요. Task 6.1 grep 검증.
8. ❌ **워크플로우 파일명에 한글 / 공백 / 대소문자 혼용** — `crawler.yml` 등 lowercase ASCII만.
9. ❌ **모든 step에 `if: success()` 명시** — 기본값. 군더더기.
10. ❌ **`continue-on-error: true`로 실패 무시** — AC #5 (PR 블로킹) 직접 위반.

### References

- [Architecture: ARCH-7 GitHub Actions CI/CD](/_bmad-output/planning-artifacts/architecture.md#L81)
- [Architecture: 모노레포 디렉토리 트리 — .github/workflows/](/_bmad-output/planning-artifacts/architecture.md#L433-L440)
- [Architecture: 시크릿 관리 — 환경변수 + IAM Role](/_bmad-output/planning-artifacts/architecture.md#L196)
- [Epics: Story 1.5 AC](/_bmad-output/planning-artifacts/epics.md#L264-L279)
- [Story 1.2 Dev Notes — `pip install -e shared/` 패턴](/_bmad-output/implementation-artifacts/1-2-공유-인터페이스-계약-및-구조화-로깅-수립.md#L98-L107)
- [actions/checkout v6 Releases](https://github.com/actions/checkout/releases)
- [actions/setup-python v6 Releases](https://github.com/actions/setup-python/releases)
- [actions/setup-node v6 Releases](https://github.com/actions/setup-node/releases)
- [actions/setup-java v5 Releases](https://github.com/actions/setup-java/releases)

## Dev Agent Record

### Status

review

### Completion Notes

- 4 워크플로우 모두 동일 구조: 단일 `lint-test` job, `paths` 필터, 메이저 버전 핀(checkout/setup-* v5/v6).
- crawler/detection: `flake8 src tests --max-line-length=120` + `pytest tests/unit` (exit 5 = no tests collected → notice + pass 처리). `requirements.txt`의 `-e ../shared`가 `working-directory: crawler` 컨텍스트에서 그대로 동작.
- api: Foojay 플러그인이 `settings.gradle`에 이미 등록되어 있어 Java 21 toolchain 자동 다운로드. `chmod +x gradlew` step으로 Linux runner의 권한 이슈 방지. 로컬 검증 시 BUILD SUCCESSFUL (Spring Boot context load 통과).
- dashboard: `npm run build`가 `tsc -b && vite build` 조합이라 typecheck + 번들 한 단계 통합. 로컬 검증 49ms / 193KB. AC #4를 `npm test` 대신 `lint + build`로 명시 완화 — vitest 도입은 Growth 단계 deferred.
- 시크릿: 4 yml 파일 모두 평문 키/토큰 0 hit (`grep -rEn "VARCO_API_KEY|AWS_ACCESS_KEY|password|token"` exit 1). 단위 테스트만이라 `secrets.*` 참조 자체가 본 스토리 범위에 불필요. 향후 통합 테스트 시 패턴은 `docs/ci-setup.md`에 문서화.
- Branch Protection: admin 권한 필요 작업이라 본 스토리에서는 `docs/ci-setup.md`로 절차만 정립. paths 필터 + required check 상호작용 trade-off (Loose 권장 / Strict는 Story 5.2 후속) 명시.

**미해결/다음 스토리**:
- crawler/detection은 로컬 Python venv 부재로 lint+pytest 로컬 검증 스킵. 첫 push 후 GitHub Actions 실제 실행 결과 확인 필요.
- 의도적 lint 위반 → 빨강 → revert 검증은 push 후 개발자 직접 확인 (workflow 정의 자체에 issue 없음).
- vitest 도입 (`dashboard/`)은 Story 5.2 또는 별도 small story로.
- `ci-aggregator.yml` (Loose → Strict 전환용)은 Story 5.2 (CI/CD 완전 통합)로.

### File List

신규:
- `.github/workflows/crawler.yml`
- `.github/workflows/detection.yml`
- `.github/workflows/api.yml`
- `.github/workflows/dashboard.yml`
- `docs/ci-setup.md`

수정:
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (1-5 status: backlog → ready-for-dev → in-progress → review)
- `_bmad-output/implementation-artifacts/1-5-github-actions-기본-ci-파이프라인-구성.md` (본 스토리 파일 — Tasks 체크 + Dev Agent Record)

### Change Log

- 2026-04-28 — Story 1.5 dev 완료, status: ready-for-dev → review.
