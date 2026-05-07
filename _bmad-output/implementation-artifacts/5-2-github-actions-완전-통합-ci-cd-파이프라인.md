# Story 5.2: GitHub Actions 완전 통합 CI/CD 파이프라인 (PIVOT — SSH `.pem` 자동 배포)

Status: in-progress

> **2026-05-06 PIVOT — OIDC + IAM Role 자동 배포 봉인 → SSH `.pem` GH Secret 직결 채택.**
>
> 학생 IAM 사용자 `<student-iam-user>`에서 (1) IAM Role 신규 생성 차단 (2) IAMFullAccess 등 권한 정책 attach 화이트리스트 외 차단 (`AmazonAPIGatewayPushToCloudWatchLogs` / `AWSCloud9SSMInstanceProfile` / `AWSLambdaBasicExecutionRole` 3개만 허용 — 모두 service role용) (3) AWS Access Key 발급 차단으로 **GHA→AWS 자동 배포 통로(OIDC / Access Key / CodeDeploy) 모두 봉인** 확인. EC2 접근 통로도 SSM Session Manager / EC2 Instance Connect 모두 권한 차단되어 **SSH `.pem` 키만 가능**.
>
> 외부 SaaS(Cloudflare Tunnel / Tailscale) 가입 회피 결정으로 22번 인바운드는 `0.0.0.0/0` + defense-in-depth(ed25519 + fail2ban + host fingerprint verification)로 안전화. 단일 `.pem` 사용 — 관리자 접속용 + GHA 자동 배포용 분리 안 함 (사용자 결정으로 단순함 우선, 이전 권장 14 AC에서 GHA 전용 deploy 키 + deploy 전용 SSH 사용자 분리 2개 항목 제거 → 12 AC).
>
> **신 사양 흐름:**
> ```
> [PR 머지 → main]
>   → GHA: lint/test 4개 서브시스템 aggregator
>   → GHA: BuildKit cache mode=max로 Docker 이미지 빌드 → GHCR push (GITHUB_TOKEN)
>   → GHA: appleboy/ssh-action으로 EC2 SSH (.pem GH Secret) → docker pull → docker compose up -d
>   → GHA: healthcheck → 실패 시 이전 SHA로 자동 롤백 → exit 1
> ```

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

개발자로서,
main 브랜치 머지가 4개 서브시스템(crawler / detection / api / dashboard)의 빌드 · 테스트 · GHCR 이미지 푸시 · EC2 SSH 배포까지 자동화되기를 원한다,
그래서 PR 머지만으로 학생 계정 EC2 인스턴스에 최신 버전이 배포되고 헬스체크 실패 시 자동 롤백된다.

## Acceptance Criteria

1. **Given** main 브랜치에 PR이 머지될 때 **When** GitHub Actions가 트리거되면 **Then** lint/typecheck + 단위 테스트 + 통합 테스트가 4개 서브시스템(crawler / detection / api / dashboard) 모두 실행되고, 1건이라도 실패하면 배포 단계가 차단된다 (Story 1.5의 path-filtered workflow 4종 + aggregator로 strict required check 구성 — `docs/ci-setup.md`에서 deferred됐던 항목 본 스토리에서 해결)

2. **And** Docker 이미지가 BuildKit `cache-from/cache-to type=registry,ref=ghcr.io/<owner>/<repo>/<service>:cache,mode=max`로 빌드되어 빌드 시간이 단축된다 (멀티스테이지 모든 레이어 캐싱). inline cache는 min 모드만 가능하므로 **사용 금지**

3. **And** 이미지가 `ghcr.io/<owner>/<repo>/<service>:<git-sha>`로 푸시되며 인증은 `${{ secrets.GITHUB_TOKEN }}` + workflow `permissions: { packages: write, contents: read }`로 처리된다 (**PAT 사용 금지** — fine-grained PAT는 GHCR 미지원, classic PAT는 키 회전 부담). main 머지 시 `:latest` 태그도 같이 push

4. **And** main 머지 후 `deploy` job이 `appleboy/ssh-action@v1.2.4`로 EC2에 SSH 접속하여 `docker pull` + `docker compose up -d <service>` + healthcheck를 실행한다. 4개 서비스(crawler / detection / api / dashboard)에 매핑된 EC2 인스턴스(또는 단일 EC2 다중 service)에 각각 배포

5. **And** SSH 인증에 4개 GH Secret을 사용한다: `EC2_SSH_KEY`(이미 보유한 `.pem` 파일 내용 통째 — `-----BEGIN ... PRIVATE KEY-----` 부터 `-----END ... PRIVATE KEY-----`까지), `EC2_HOST`(EC2 public IP), `EC2_USER`(`ec2-user` 또는 `ubuntu`), `EC2_HOST_FINGERPRINT`(`ssh-keyscan -t ed25519 <ip>` 결과). `appleboy/ssh-action`의 `fingerprint:` 옵션으로 host fingerprint verification 적용 → MITM 공격 차단

6. **And** healthcheck(`curl -fsS http://localhost:<port>/health` 또는 `docker inspect --format '{{.State.Health.Status}}'`)가 30초 내 통과하지 못하면 **자동 롤백** — 이전 SHA 태그(`docker inspect --format '{{.Config.Image}}' <service>` 로 배포 전 캡처)로 다시 `docker pull` + `docker compose up -d <service>` 실행. 워크플로는 `exit 1`로 종료하여 GHA UI에 fail 표시

7. **And** workflow에 `concurrency: { group: deploy-prod, cancel-in-progress: false }`가 설정되어 main 머지가 연속적으로 일어나도 배포 워크플로가 **순차 처리** — state 일관성 보호 (CI 워크플로의 `cancel-in-progress: true`와 의도적으로 다름)

8. **And** main branch protection이 활성화된다: (a) PR 필수 + 최소 1명 리뷰 (b) direct push 금지 (c) auto-merge 비활성 (d) Story 1.5의 4개 path-filtered workflow + aggregator + 본 스토리의 `deploy.yml`이 모두 통과 시에만 머지 가능 — Repo Settings → Branches → `main` 룰

9. **And** GitHub Environment "production"이 생성되어 모든 EC2 관련 secret 4개(`EC2_SSH_KEY`, `EC2_HOST`, `EC2_USER`, `EC2_HOST_FINGERPRINT`)가 그 environment scope에 등록된다 (Repository scope 대비 격리 강함). `deploy` job은 `environment: production`으로 묶여 실행되며, 필요 시 Required reviewers를 등록하여 추가 사람 게이트를 걸 수 있다 (옵션 — 평소 비활성, 주요 릴리스 시점에 활성화)

10. **And** EC2 OS hardening: `fail2ban` 설치 + `/etc/fail2ban/jail.local`의 `[sshd]` 섹션에 `enabled=true, maxretry=3, findtime=600, bantime=86400` (3 fail / 10분 / 24h ban) 설정. SSH brute-force 99% 차단 (defense-in-depth — `0.0.0.0/0` 22번 노출 트레이드오프 보강)

11. **And** `appleboy/ssh-action`의 `script:` 안 모든 명령은 **절대 경로** 사용 (`/usr/bin/docker`, `/usr/local/bin/docker compose`, `/usr/bin/curl` 등) — 인터랙티브 vs 비인터랙티브 셸 PATH 차이로 "command not found" 발생 회피 (appleboy/ssh-action [Issue #297](https://github.com/appleboy/ssh-action/issues/297) 등 다수 보고). 또한 `script_stop: true` 옵션으로 한 줄 실패 시 즉시 중단

12. **And** 시크릿 관리: docker compose `secrets:` 키워드로 EC2의 `/run/secrets/<name>` 파일 마운트. 시크릿 파일은 EC2의 `/opt/app/secrets/` 디렉토리(chmod 700, owner root)에 chmod 600 파일로 저장. `.gitignore`에 `*.env` + `secrets/` 등록. **환경변수 직접 주입 금지** — Docker daemon 접근 권한자에게 노출되므로

## Tasks / Subtasks

> **선행 조건:** Story 5.3 ClickOps PIVOT 완료(EC2 t3.medium ×3 또는 단일 EC2 + RDS db.t3.micro + S3 + Default VPC). 본 스토리는 그 위에 자동 배포 파이프라인을 얹는다.
>
> **외부 의존성 결정:** Cloudflare Tunnel / Tailscale 등 외부 SaaS 가입 회피 결정 (memory `feedback_no_external_services.md`) — 22번 인바운드는 `0.0.0.0/0` + fail2ban + ed25519 + host fingerprint verification으로 안전화.
>
> **키 관리 결정:** 단일 `.pem` 사용 — 관리자 접속용 + GHA 자동 배포용 분리 안 함. 분리 시 보안 폭발 반경 축소 효과 있으나 학생 프로젝트 규모에서 키 관리 부담 ↑ vs 보안 이득 trade-off에서 단순함 선택. `.pem` 분실 시 EC2 키페어 재발급 권한 없음 → 1Password 등 안전한 곳에 백업 필수.

- [ ] **Task 1. EC2 SSH 셋업** (AC: #4, #5, #10) — 콘솔 ClickOps + EC2 SSH 작업
  - [ ] EC2 launch 검증 (이미 launch된 경우 생략) — Amazon Linux 2023 또는 Ubuntu 22.04
  - [ ] `.pem` 키 백업 (1Password 또는 안전한 보관소) + 노트북 1Password에 별도 사본 — 분실 시 재발급 권한 없음 명시
  - [ ] 노트북에서 SSH 접속 검증: `ssh -i <key>.pem ec2-user@<ip>`
  - [ ] EC2에 `fail2ban` 설치 (`sudo dnf install fail2ban` 또는 `sudo apt install fail2ban`)
  - [ ] `/etc/fail2ban/jail.local` 설정: `[sshd]` 섹션에 `enabled=true, maxretry=3, findtime=600, bantime=86400`
  - [ ] `sudo systemctl enable --now fail2ban` 활성
  - [ ] EC2 host fingerprint 추출: 노트북에서 `ssh-keyscan -t ed25519 <ec2-ip> | awk '{print $3}'` 결과를 GH Secret으로 사용

- [ ] **Task 2. GitHub Environment "production" + Secrets 등록** (AC: #5, #9) — GH 콘솔 ClickOps
  - [ ] Repo Settings → Environments → New environment "production" 생성
  - [ ] Environment secrets에 4개 등록:
    - [ ] `EC2_SSH_KEY` — `.pem` 파일 내용 통째 (`-----BEGIN ... -----END ...`)
    - [ ] `EC2_HOST` — EC2 public IP 또는 도메인
    - [ ] `EC2_USER` — `ec2-user` (Amazon Linux) 또는 `ubuntu` (Ubuntu)
    - [ ] `EC2_HOST_FINGERPRINT` — Task 1에서 추출한 fingerprint
  - [ ] (옵션) Required reviewers 1명 등록 — 평소 비활성, 주요 릴리스 시점에만 활성화

- [ ] **Task 3. Branch protection 설정** (AC: #8) — GH 콘솔 ClickOps
  - [ ] Repo Settings → Branches → Add rule (또는 기존 `main` 룰 편집)
  - [ ] Branch name pattern: `main`
  - [ ] 활성화: ☑ Require a pull request before merging (1 approval) / ☑ Require status checks to pass / ☑ Do not allow bypassing
  - [ ] Required status checks에 등록: `crawler-lint-test`, `detection-lint-test`, `api-lint-test`, `dashboard-lint-test`, `aggregator`, `deploy-prod` (workflow가 작성된 후)
  - [ ] Allow auto-merge: **OFF**

- [x] **Task 4. `.github/workflows/deploy.yml` 신규 작성** (AC: #1, #2, #3, #4, #6, #7, #11)
  - [x] trigger: `on: { push: { branches: [main] }, workflow_dispatch: {} }` (workflow_dispatch는 비상 백업)
  - [x] `permissions: { packages: write, contents: read }`
  - [x] `concurrency: { group: deploy-prod, cancel-in-progress: false }`
  - [x] jobs:
    - [x] `lint-test` — Story 1.5의 4개 path-filtered workflow를 `workflow_call:` 추가로 reusable로 만들고 aggregator + deploy.yml 모두에서 호출 (ci.yml 신규 + deploy.yml에서 동일 reusable 4종 호출)
    - [x] `build-push` — `docker/setup-buildx-action@v3` + `docker/login-action@v3`(GHCR) + `docker/build-push-action@v6`(`cache-from/to type=registry,...:cache,mode=max`) × 4개 서비스 (matrix)
    - [x] `deploy` — `environment: production` + `needs: [build-push]`(lint-test도 deploy.yml에 직접 호출되어 build-push의 needs로 들어감) + `appleboy/ssh-action@v1.2.4`로 SSH → 절대 경로 명령(`/usr/bin/docker`/`/usr/bin/date`/`/usr/bin/sleep`/`/usr/bin/cat`/`/usr/bin/echo`) → `docker pull` / `docker compose up -d` / 30s healthcheck 폴링 / 실패 시 이전 SHA로 자동 롤백
  - [x] `script_stop: true` + `fingerprint: ${{ secrets.EC2_HOST_FINGERPRINT }}` 옵션 적용

- [~] **Task 5. EC2 docker compose + healthcheck 정의** (AC: #6, #12) — 코드 템플릿 + EC2 SSH 작업 분리
  - [x] `infra/compose.prod.yml` 작성 — 4개 서비스(crawler / detection / api / dashboard) + redis 정의 (deploy.yml의 scp-action으로 EC2 `/opt/app/compose.prod.yml`에 매 배포마다 업로드)
  - [x] 각 서비스에 `healthcheck:` 블록 정의 — Dockerfile `HEALTHCHECK` (crawler/detection: pgrep 프로세스 검사, api: `/actuator/health` curl, dashboard: `/healthz` wget) + redis는 compose 레벨 `redis-cli ping`
  - [x] `secrets:` 키워드로 `/run/secrets/<name>` 마운트 정의 + `infra/docker-secret-shim.sh` 추가 (4개 Dockerfile ENTRYPOINT chain에 삽입 — `/run/secrets/*` → 대문자 env 변환 후 exec CMD). AC #12 "환경변수 직접 주입 금지" 준수
  - [ ] **[USER]** `/opt/app/secrets/` 디렉토리 생성 (chmod 700, owner root) — EC2 SSH ClickOps. 절차는 `docs/deployment.md` §2.4 참조
  - [ ] **[USER]** 시크릿 파일들 (`varco_api_key`, `db_password` 등) 수동 등록 — 각 파일 chmod 600
  - [x] `.gitignore`에 `*.env`(line 67) + `secrets/` (신규 추가) + `*.pem`(line 72) + `*.key`(line 73) + `id_rsa*` (lines 76~79) 모두 등록 확인

- [~] **Task 6. dependabot 제거 commit** (AC: #8 — auto-merge OFF + 의도치 않은 자동 배포 회피)
  - [x] `.github/dependabot.yml` 이미 working tree에서 제거됨 (Story 5-3 ClickOps PIVOT 시점 작업)
  - [ ] **[USER]** commit message 예시: `chore(ci): dependabot 제거 — main 머지 자동 배포 흐름과 충돌 회피` (사용자 git workflow 본인 컨트롤 정책)
  - [ ] **[USER]** (선택) Repo Settings → Code security and analysis → "Dependabot security updates": **OFF** (보안 PR 자동 생성 X) / "Dependabot alerts": **ON** (알림만 받기) — GH 콘솔 ClickOps

- [ ] **[USER] Task 7. 첫 배포 검증** (AC: #1~#12 통합) — Tasks 1~3 완료 + 첫 머지 후 검증
  - [ ] feature/* 브랜치에서 dummy 변경 + PR → main 머지
  - [ ] GHA workflow 실행 확인: ci/aggregator → deploy/lint-test 4종 → deploy/build-push 4종 → deploy/deploy 순차 통과
  - [ ] EC2에서 `/usr/bin/docker compose -f /opt/app/compose.prod.yml ps` + `... logs <service>`로 새 SHA 컨테이너 정상 실행 확인
  - [ ] 4개 서비스 모두 healthcheck 통과 확인

- [ ] **[USER] Task 8. 자동 롤백 검증** (AC: #6) — 의도적 헬스체크 실패 시뮬레이션
  - [ ] 헬스체크 endpoint를 의도적으로 깨뜨리는 변경 (예: api `/actuator/health` 비활성 또는 dashboard nginx `/healthz` 제거)
  - [ ] PR → main 머지 → 워크플로 실행 관찰
  - [ ] 워크플로가 healthcheck 실패 감지 → 이전 SHA로 자동 롤백 → exit 1로 fail 표시 확인
  - [ ] EC2 `docker ps`에서 이전 버전 컨테이너 복원 확인 (다운타임 측정)

- [x] **Task 9. 운영 절차 문서화** (산출물 AC 외)
  - [x] `docs/deployment.md` 작성:
    - [x] 자동 배포 흐름 다이어그램 (§1)
    - [x] `.pem` 분실 시 복구 절차 (§2.1 — EC2 launch 시 추가 SSH 키를 authorized_keys에 미리 등록 권장)
    - [x] 비상 수동 트리거 (workflow_dispatch — `rollback_to` 입력) 사용법 (§5)
    - [x] 시크릿 추가/회전 절차 (§3)
    - [x] 보안그룹 22번 노출 트레이드오프 + defense-in-depth 4 layer 설명 (§6.1)
  - [x] `docs/ci-setup.md` 갱신 — Story 1.5 deferred strict gate 항목이 `ci.yml` aggregator + 4개 reusable workflow_call 패턴으로 본 스토리에서 해결됐음을 명시

## Dev Notes

### Architectural Constraints

- **자동 배포 통로 봉인** (memory `project_aws_student_account_constraints.md`): OIDC + IAM Role + Access Key + CodeDeploy + EC2 instance profile 모두 영구 봉인 → SSH가 유일한 통로
- **EC2 접근 통로 = SSH `.pem`만**: SSM Session Manager / EC2 Instance Connect 권한 차단 확인 (2026-05-06)
- **외부 SaaS 회피** (memory `feedback_no_external_services.md`): Cloudflare Tunnel / Tailscale 가입 X, AWS + GitHub native 솔루션만
- **단일 `.pem`**: 분리 안 함 (사용자 결정으로 단순함 우선)
- **Region**: `us-east-1` (학생 계정 제약)

### 기술 스택 결정

- **`appleboy/ssh-action@v1.2.4`** — 활성 메인테인 + Trivy 보안 스캔 + ED25519 지원
- **BuildKit registry cache `mode=max`** — 멀티스테이지 모든 레이어 캐싱, inline cache(min만 가능) 대비 최적
- **`fail2ban` 3 fail/10분/24h ban** — 검색에서 일관 권장 수치
- **GHCR + `GITHUB_TOKEN`** — GitHub 공식 권장 (PAT 비추), workflow `permissions: packages: write` 필수

### 보안 트레이드오프 — 22번 0.0.0.0/0 정당화

- **학생 계정 제약**: AWS 자격증명 봉인 → GHA에서 SG 룰 동적 변경 자동화 불가
- **GHA 러너 IP는 동적**: 화이트리스트 운영 어려움 (매주 갱신 워크플로도 AWS API 봉인으로 불가)
- **Defense-in-depth 4 layer 적용**: ed25519 + password 비활성 + 비표준 포트(선택) + fail2ban 3/10분/24h → brute-force 99% 차단
- **트레이드오프 명시**: 교과서적 best practice는 IP 화이트리스트지만 학생 계정 제약으로 단순함 + defense-in-depth 채택

### Source tree components to touch

- **신규**: `.github/workflows/deploy.yml`, `/opt/app/compose.yml`(EC2), `/opt/app/secrets/*`(EC2), `docs/deployment.md`
- **수정**: `docs/ci-setup.md` (Story 1.5 deferred 항목 정리), `.gitignore` (secrets / *.pem)
- **삭제**: `.github/dependabot.yml` (이미 working tree에서 제거)

### Testing standards summary

- 본 스토리는 **인프라 자동화 스토리** — 단위 테스트 X, integration test = Task 7/8 (실 배포 + 자동 롤백 시뮬레이션)
- 검증 산출물: GHA workflow 실행 로그(success / fail 케이스 모두 확보)

### Project Structure Notes

- `infra/` 디렉토리는 5-3 ClickOps PIVOT 후 docker-compose.yml + .env.example만 유지
- 본 스토리에서 `/opt/app/compose.yml`은 EC2 내부 경로 (git X) — `infra/docker-compose.yml`을 prod용으로 변형하여 EC2에 SCP로 한 번 올림 또는 `appleboy/scp-action`으로 첫 배포 시 자동 푸시
- EC2 ↔ GH Secret 연결고리: `.pem` 단일 키로 모든 자동 배포 + 관리자 접속

### References

- [Source: _bmad-output/planning-artifacts/architecture.md#Infrastructure-Deployment](../planning-artifacts/architecture.md) — 5-3 ClickOps PIVOT + 5-2 SSH `.pem` 결정 박스
- [Source: _bmad-output/planning-artifacts/epics.md#Story-5.2](../planning-artifacts/epics.md) — Story 5.2 PIVOT 박스 (OIDC 봉인 → SSH `.pem`)
- [Source: docs/ci-setup.md](../../docs/ci-setup.md) — Story 1.5 deferred strict gate (본 스토리에서 해결)
- [Source: 메모리 `project_aws_student_account_constraints.md`] — 자동 배포 통로 봉인 + EC2 접근 통로 SSH only 검증
- [Source: 메모리 `feedback_no_external_services.md`] — 외부 SaaS 가입 회피 결정
- [Web research 2026-05-06] — GHCR 인증 (GITHUB_TOKEN), BuildKit cache mode=max, appleboy/ssh-action 알려진 함정(인터랙티브 셸 이슈 #297), fail2ban 권장 수치, GHA concurrency cancel-in-progress 차이 (CI: true / Deploy: false)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (BMad dev-story workflow, 2026-05-07 세션)

### Debug Log References

- YAML 파싱: PyYAML 6 venv로 ci.yml / deploy.yml / 4개 reusable / compose.prod.yml 모두 parse OK
- Docker compose validation: `IMAGE_TAG=test REGISTRY_PATH=ghcr.io/test/test docker compose -f infra/compose.prod.yml config` (env_file/secrets path를 /tmp 디렉토리로 sed 치환 후) PASS
- 로컬 `docker buildx build --check`은 Docker Daemon 미가동으로 실행 불가 — 실 빌드/검증은 GHA 러너에서 수행 (Task 7/8 사용자 검증 시점)

### Completion Notes List

**완료한 코드 산출물 (Tasks 4 / 5 코드 측면 / 9):**

1. `.github/workflows/ci.yml` (신규, 50 lines) — PR + push:main에서 path filter 없이 항상 실행되는 strict aggregator. 4개 reusable workflow를 `uses:`로 호출 + 마지막 `aggregator` 잡이 `if: always()` + `toJSON(needs)` 검사로 4종 결과 합산. `ci / aggregator` 단일 required check 후보. `concurrency: { group: ci-${{ github.ref }}, cancel-in-progress: true }`로 stale PR 실행 자동 취소.

2. `.github/workflows/deploy.yml` (신규, 205 lines) — 12 AC 거의 전부를 한 워크플로에 통합. `concurrency: { group: deploy-prod, cancel-in-progress: false }` (AC #7), `permissions: { packages: write, contents: read }` (AC #3), 4개 reusable lint-test 호출 (AC #1) → matrix build-push 4종 (BuildKit `cache-from/to type=registry,...:cache,mode=max` — AC #2, GHCR `:sha` + `:latest` 태깅 — AC #3) → deploy 잡 (`environment: production` — AC #9, `appleboy/scp-action@v1.0.0` + `appleboy/ssh-action@v1.2.4` — AC #4/#11, `fingerprint:` host 검증 + `script_stop: true`로 Issue #297 회피, 30초 healthcheck 폴링 → 실패 시 `/opt/app/IMAGE_TAG` 파일에서 이전 SHA 읽어 재배포 — AC #6). `workflow_dispatch.inputs.rollback_to`로 수동 롤백 지원.

3. 기존 4개 워크플로(`crawler.yml` / `detection.yml` / `api.yml` / `dashboard.yml`)에 `workflow_call:` 트리거 추가 — 기존 path-filter trigger와 공존. ci.yml + deploy.yml 양쪽에서 reusable로 호출 가능.

4. **Dockerfile 4종 신규** (스토리 스펙 외 신규 의존성, 사용자 사전 동의 — `함께 작성 (Recommended)`):
   - `crawler/Dockerfile` — `python:3.11-slim` + `playwright install --with-deps chromium` + tini + secret-shim. CMD `python -m crawler.src.scheduler.crawl_scheduler`. HEALTHCHECK = pgrep 스케줄러 프로세스.
   - `detection/Dockerfile` — `python:3.11-slim` + tini + secret-shim. CMD `python -m detection.src.main`. HEALTHCHECK = pgrep main 프로세스.
   - `api/Dockerfile` — multi-stage `eclipse-temurin:21-jdk-noble` builder(`./gradlew bootJar -x test`) → `21-jre-noble` runtime + tini + secret-shim. HEALTHCHECK = `/actuator/health` curl. EXPOSE 8080.
   - `dashboard/Dockerfile` — multi-stage `node:20.19-alpine` builder(`npm ci && npm run build`) → `nginx:1.27-alpine` runtime. nginx config에 SPA fallback + `/healthz` 200 응답. HEALTHCHECK = `/healthz` wget. EXPOSE 80.
   - 각 서비스 `.dockerignore`로 캐시·테스트·로컬 IDE 산출물 빌드 컨텍스트 제외.

5. `infra/compose.prod.yml` (신규, 123 lines) — 단일 EC2 `docker compose` 사양. 5개 서비스(redis + crawler/detection/api/dashboard). `${REGISTRY_PATH}/<service>:${IMAGE_TAG:-latest}` 이미지 참조 → deploy.yml에서 env로 주입. AC #12 준수: `secrets:` 블록으로 `/opt/app/secrets/{varco_api_key,db_password}` → `/run/secrets/<name>` 마운트, env_file는 비-시크릿 설정만(`/opt/app/.env`). redis 헬스체크 + crawler/detection의 `depends_on: { redis: { condition: service_healthy } }` 의존성 명시.

6. `infra/docker-secret-shim.sh` (신규, executable) — `/run/secrets/<name>` 파일을 대문자 env로 export 후 exec CMD. 4개 Dockerfile ENTRYPOINT chain의 두 번째 단계로 삽입(`tini → secret-shim → CMD`). AC #12 "환경변수 직접 주입 금지"를 코드 변경 0건으로 충족(앱 코드는 기존대로 `os.environ["VARCO_API_KEY"]`를 그대로 읽음).

7. `.gitignore` 갱신 — 기존 `*.env` / `*.pem` / `*.key` / `id_rsa*` / `id_ed25519*` / `*credentials*.json`이 이미 등록됨 확인. 신규로 `secrets/` 패턴 추가 (Task 5 AC #12 마지막 subtask).

8. `docs/deployment.md` (신규, 197 lines) — 자동 배포 흐름 다이어그램 / EC2 + GH Environment ClickOps 절차 / 시크릿 회전 / 자동 롤백 동작 / `workflow_dispatch` rollback_to 사용법 / 22번 0.0.0.0/0 트레이드오프 + defense-in-depth 4 layer / 단일 EC2 4GB RAM 트레이드오프 / 트러블슈팅 표.

9. `docs/ci-setup.md` 갱신 — Story 1.5 시점 deferred 항목이 ci.yml aggregator + 4개 reusable workflow_call 조합으로 본 스토리에서 해소됐음을 §"Story 5.2 Aggregator + 배포 게이트 추가"에 정리. Branch protection 절차도 5.2 strict 사양으로 갱신 (`ci / aggregator` required + Allow auto-merge OFF).

**사용자 의존성 (별도 진행):**
- Task 1 (EC2 SSH/fail2ban/host fingerprint) — `docs/deployment.md` §2.1 절차 그대로 EC2 SSH 작업
- Task 2 (GH Environment "production" + 4 secrets) — §2.2
- Task 3 (Branch protection — `ci / aggregator` required) — §2.3
- Task 5 user 부분 (`/opt/app/secrets/` mkdir + 시크릿 파일 등록) — §2.4
- Task 6 (dependabot 제거 commit) — 사용자 git workflow 정책상 사용자 commit
- Task 7/8 (실 배포 + 자동 롤백 검증) — 첫 머지 + 의도적 healthcheck 실패 시뮬레이션

**알려진 제약/주의:**
- 첫 배포 cold-start: `/opt/app/IMAGE_TAG` 파일이 없으면 롤백 fallback 태그가 `latest`로 떨어짐 (이미 `latest`도 동일 broken 이미지). 첫 배포 시 healthcheck 동작을 별도로 검증하고, 필요 시 `workflow_dispatch + rollback_to: <known-good-sha>`로 수동 처리 — `docs/deployment.md` §4 명시.
- 단일 EC2 t3.medium 4GB에 4개 서비스 + redis 동거 — Playwright Chromium 200MB + JVM 500MB 등으로 OOM 리스크. 측정 후 분리 검토 — `docs/deployment.md` §6.3 명시.
- main push 1회당 reusable workflow 4종이 ci.yml + deploy.yml 양쪽에서 실행되어 비용 2x — 배포 안전성 우선으로 수용 (deploy.yml이 workflow_dispatch 우회 시에도 lint-test gate 보장하기 위함). `docs/ci-setup.md`에 명시.
- AC #5의 GH Secret 4종 등록·AC #8 Branch protection·AC #9 Environment "production" + Required reviewers는 모두 GitHub UI ClickOps라 코드로 자동화 불가 — 절차는 docs/deployment.md에 정확히 기술.

### File List

**신규 최종 (3차 PIVOT 반영, 단일 EC2 t3.xlarge):**
- `.github/workflows/ci.yml`
- `.github/workflows/deploy.yml` (단일 host)
- `crawler/Dockerfile`
- `crawler/.dockerignore`
- `detection/Dockerfile`
- `detection/.dockerignore`
- `api/Dockerfile`
- `api/.dockerignore`
- `dashboard/Dockerfile`
- `dashboard/.dockerignore`
- `infra/compose.prod.yml` (단일 EC2: redis + crawler + detection + api + dashboard 5컨테이너)
- `infra/docker-secret-shim.sh` (executable)
- `docs/deployment.md`

**git history에 보존되는 분리 사양 (3차 PIVOT 시 제거)**:
- `infra/compose.crawler.yml` / `infra/compose.app.yml` — 2대 분리 사양. 학생 계정 종료 후 개인 계정으로 옮기면 cross-SG ingress 자유로워져 분리 다시 가능. 코드는 git log로 복원.

**수정 (5):**
- `.github/workflows/crawler.yml` — `workflow_call:` trigger 추가
- `.github/workflows/detection.yml` — `workflow_call:` trigger 추가
- `.github/workflows/api.yml` — `workflow_call:` trigger 추가
- `.github/workflows/dashboard.yml` — `workflow_call:` trigger 추가
- `.gitignore` — `secrets/` 패턴 추가
- `docs/ci-setup.md` — Story 5.2 aggregator + 배포 게이트 정리

**삭제 (working tree에서 이미 제거 — 본 스토리 이전 작업):**
- `.github/dependabot.yml` (Task 6)

### Change Log

- 2026-05-07 (1차): Story 5.2 in-progress 진입. Tasks 4/5(코드)/6(파일 삭제 확인)/9 코드 산출물 + Dockerfile 4종(스펙 외 신규 의존성, 사용자 사전 동의) 작성. Tasks 1/2/3, Task 5 EC2 측 셋업, Task 6 commit/Dependabot 토글, Task 7/8 실 배포 검증은 사용자 ClickOps + git workflow로 별도 진행. Status는 ready-for-dev → in-progress (모든 사용자 의존 Task 완료 시 review로 이동).

- 2026-05-07 (2차, host topology PIVOT): 메모리 분석 후 단일 EC2 가정 → **2대 분리** (tracker-crawler + tracker-app)로 보강. PIVOT 박스 "단일 EC2 docker compose"는 자동 배포 통로 단순화 사유였고 메모리 분석이 아니었음 — t3.medium 4GB 5컨테이너 합반 시 워킹셋 1.7~3.3GB로 OOM-killer 위험. 변경 산출물: ① `infra/compose.prod.yml` 삭제 → `infra/compose.crawler.yml` + `infra/compose.app.yml` 분할 ② `deploy.yml` deploy 잡을 host matrix(`crawler` / `app`) + `fail-fast: false`로 변경 — 각자 독립 SCP/SSH/healthcheck/롤백 ③ GH Secrets: 단일 `EC2_HOST` / `EC2_HOST_FINGERPRINT` → `EC2_HOST_{CRAWLER,APP}` / `EC2_HOST_FINGERPRINT_{CRAWLER,APP}`로 분리(`EC2_SSH_KEY`/`EC2_USER`는 공통) ④ `docs/deployment.md` §2 ClickOps 절차를 2 EC2 + SG 2개(crawler-sg / app-sg, redis 6379 source = crawler-sg 한정) + `.env` 호스트별 분기로 재작성, §6.3에 결정 근거 명시 ⑤ AC #5의 시크릿 4종 → 6종으로 늘어남(스펙 외 보강이지만 AC 의도(host fingerprint 검증 + .pem GH Secret)는 동일하게 충족). 코드 변경 분량 약 250줄.

- 2026-05-07 (3차, host topology 재PIVOT): 사용자가 콘솔에서 `app-sg`에 redis 6379 ingress 룰 추가 시도 시 학생 IAM SCP가 차단(`explicit deny in identity-based policy: ControlOnlyOwnResources`). IP /32 우회도 동일 패턴으로 막힐 가능성 + EIP 권한 불명. 2대 분리 폐기. 사용자 추가 정보 — 학생 SCP가 허용하는 인스턴스에 **t3.xlarge도 포함**(이전 가정은 t3.medium 한도) → 단일 EC2를 t3.xlarge(16GB)로 상향해서 OOM 우려를 인스턴스 사양으로 해소하는 방향으로 회귀. 환율 1452원/USD 기준 EC2만 ~18만원/월, 전체 인프라 ~21만원/월(budget 30만원의 70%, 11주 총 ~57만원), 사용자 결정 진행. 변경 산출물: ① compose.crawler.yml + compose.app.yml 삭제 → compose.prod.yml 재작성(redis 호스트 포트 노출 제거, mem_limit/mem_reservation 16GB 환경에 맞게 완화: crawler 4GB / api 2GB / detection 1GB / dashboard 128MB, hard cap 합 ~7GB) ② deploy.yml의 host matrix → 단일 deploy 잡으로 되돌리기, healthcheck deadline 30s → 60s(5컨테이너 동시 startup이라 여유), service 리스트 redis/crawler/detection/api/dashboard 5종 ③ GH Secrets 6종 → **4종으로 회귀**(`EC2_HOST` / `EC2_HOST_FINGERPRINT` / `EC2_SSH_KEY` / `EC2_USER`) ④ docs/deployment.md §1 흐름·§2 ClickOps·§6.3 결정 근거 모두 단일 EC2 t3.xlarge로 재작성, 1차→2차→3차 PIVOT 결정 흐름 표로 정리, swap 셋업 절차 제거. 학생 계정 종료 후 개인 계정으로 옮기면 2대 분리 가능하다는 future plan은 §6.3에 명시(분리 코드는 git history에 보존).

- 2026-05-07 (4차, 운영 셋업 진행 중 추가 발견): EC2 launch + RDS launch ClickOps 진행 중 추가 학생 SCP 패턴 / GitHub plan 제약 발견 — 이를 반영한 미세 조정. ① **GitHub Environments 사용 불가** — repo가 byungju0 personal repo + gitjay3가 collaborator(write)라 Environment 관리 권한이 owner 외 부여 불가능(GitHub 구조적 제약). deploy.yml의 `deploy` 잡에서 `environment: production` 줄 제거 → **Repository secrets로 우회**. Required reviewers 같은 release 게이트 잃지만 학생 프로젝트 규모에서 수용. ② **RDS PostgreSQL 16.x 선택 불가** — 학생 SCP가 18.3-R1만 노출. PG 18.3 채택. **Flyway 10.x(Spring Boot 3.5 default) PG 18 미인증** — 첫 배포 시 V1~V4 migration 실행 모니터링 필요, 실패 시 `flywayVersion = 12.x`로 build.gradle 핀 추가(deferred-work에 등재). ③ **EC2 launch wizard 함정** — Edit 모드 SG + 서브넷/AZ 명시 조합에서 ingress 룰 추가가 deny. "기본 설정 없음(서브넷)" + simple view SG로 우회 통과. ④ **`/opt/app/` 디렉토리 권한** — `/opt/app` 자체는 ubuntu:ubuntu 755(scp-action 업로드 위치), `/opt/app/secrets` 만 root:root 700(시크릿 저장소). 본 커밋 시점 사용자 EC2(`tracker-prod`)는 D-1~D-4 셋업 완료, RDS(`tracker-prod-db`)는 launching 단계.
