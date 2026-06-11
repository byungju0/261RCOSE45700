# 0001. 시크릿 관리 전략 — Docker secrets + EC2 SSH 수동 작성 채택

> 결정일: 2026-05-12
> 상태: Accepted
> 태그: #infra #security #deployment #high

## Context (배경)

Story 5-2 (GitHub Actions 완전 통합 CI/CD 파이프라인) 구현 중 4개 컨테이너(crawler / detection / api / dashboard)가 사용할 시크릿을 어떻게 EC2에 안전하게 전달할지 결정 필요.

**시크릿 2종**: `OPENAI_API_KEY`, `DB_PASSWORD`

**제약 조건**:

1. **학생 IAM 봉인** (`<student-iam-user>`): IAM Role 생성 차단, IAM Access Key 발급 차단, SSM Session Manager / EC2 Instance Connect 권한 차단 → **AWS Secrets Manager / SSM Parameter Store API 호출에 필요한 자격증명 통로가 구조적으로 0개**
2. **외부 SaaS 가입 회피 정책** ([memory feedback_no_external_services](../../../.claude/projects/-Users-jmac-Desktop-261RCOSE45700/memory/feedback_no_external_services.md)): Cloudflare Tunnel, Tailscale, Doppler, 1Password Connect, Infisical Cloud 등 신규 SaaS 가입 X
3. **단일 EC2 t3.xlarge** (Ubuntu 24.04 + Docker compose 5 컨테이너 합반)
4. **단일 `.pem` 키** (관리자 접속 + GHA 자동 배포 공용)
5. **2명 팀, 졸업 데모 D-day 안정성 최우선** (Story 5-4 E2E 데모 + 발표 D-day)
6. **시크릿 회전 주기 > 프로젝트 수명** (OpenAI API key와 DB password는 SSH로 수동 회전)

산업 표준은 외부 시크릿 매니저(AWS Secrets Manager / HashiCorp Vault) 사용이지만, 학생 IAM 제약으로 봉인되어 있고 외부 SaaS는 회피 정책으로 차단되어 있어 가용 옵션이 제한됨.

## Decision (결정)

**옵션 A 채택 — Docker `secrets:` 키워드 + EC2 EBS 디스크 `/opt/app/secrets/` 파일 + SSH 수동 작성 + Quality Gate 3종 보강**.

핵심 메커니즘:
- 시크릿 파일: EC2의 `/opt/app/secrets/openai_api_key`, `/opt/app/secrets/db_password`, `/opt/app/secrets/redis_password` (파일 chmod 0444, owner root:root; 상위 디렉터리 chmod 700, owner root:root) — `docs/deployment.md` §2.6 절차로 SSH 1회 작성
- `.env` 파일: EC2의 `/opt/app/.env` (chmod 600, root:root) — 비-시크릿 환경변수
- Docker 노출: `infra/compose.prod.yml`의 `secrets:` 키워드로 컨테이너 내부 `/run/secrets/<name>` read-only mount
- ENV 변환: `infra/docker-secret-shim.sh`가 `/run/secrets/<name>` → 대문자 ENV 변환 (앱 코드는 `os.environ["OPENAI_API_KEY"]`, `os.environ["DB_PASSWORD"]` 그대로 사용)
- 검증·안전 가드 (이미 `deploy.yml`에 구현됨):
  1. **IMAGE_TAG fail loud**: hex-only + length 7~40 검증, 위반 시 `exit 1` ([deploy.yml:206-215](../../.github/workflows/deploy.yml#L206-L215))
  2. **Cold-start 가드**: 이전 SHA marker (`/opt/app/IMAGE_TAG`) 없으면 `:latest`로 무한 롤백 거부 + `exit 4` ([deploy.yml:311-313](../../.github/workflows/deploy.yml#L311-L313))
  3. **Container healthcheck 폴링**: Dockerfile `HEALTHCHECK` 기반 + 180s deadline 동안 6개 서비스 healthy 확인, 실패 시 자동 롤백 + 롤백 후 재검증 ([deploy.yml:273-349](../../.github/workflows/deploy.yml#L273-L349))
- **Pre-deploy assertion(시크릿 파일 존재/길이 사전 검증)은 추가하지 않음**: container healthcheck가 startup 시점에 동등하게 catch (시크릿 누락 → 컨테이너 startup 실패 → healthcheck unhealthy → 자동 롤백)하므로 cosmetic 개선으로 판정 (2026-05-12 결정).

## Alternatives (검토한 대안)

| 대안 | 장점 | 단점 | 결과 |
|------|------|------|------|
| **A. Docker secrets + EC2 SSH 수동** | Compose `environment:`/`env_file:`에 시크릿을 직접 두지 않아 `docker inspect`와 GHA workspace 노출을 피함, 학생 IAM·외부 SaaS 회피 정책 모두 호환 | shim이 앱 호환을 위해 시크릿을 프로세스 ENV로 변환하므로 컨테이너 내부 `/proc/<pid>/environ`에는 남음. 시크릿 회전 시 EC2 SSH 필요, Source of Truth = EC2 디스크 (인스턴스 분실 시 복구 0%), audit = `auth.log`만 | **채택** |
| B. SOPS + age (CNCF Sandbox) | Git이 Source of Truth, audit trail = git history, 산업 표준 | age private key 자체를 EC2에 평문 저장 → 동일 위험 회귀, `sops`+`age` 바이너리 설치 + `.sops.yaml` + CI decrypt step 추가, 2명 팀 학습 곡선, 키 분실 시 시크릿 영구 복구 불가 | 기각 — 운영 부담 > 보안 이득, *4명 agent 만장일치 기각* |
| C. GHA Secrets → SSH Push | GitHub Secrets(libsodium sealed box, AES-256) 신뢰 경계, 회전 = GH UI + workflow_dispatch | 시크릿이 GHA workspace 경유 → 폭발 반경 ↑ (repo 권한자 + Actions runner 접근자), SSH heredoc escape 버그(`$`, `` ` ``, `"`, `\`) 매 배포 노출, deploy.yml +5 LOC + GH Secrets 4개 추가, 12-factor 위반("config는 환경에 속한다") | 기각 — Amelia "끝점 같으면 경로 늘릴 이유 없음" + Quinn "CI/CD에 시크릿 책임 떠넘기는 안티패턴" |
| D. `.env` 단일 파일 + `env_file:` | 12-factor 정렬, 운영 단순성(단일 파일), LOC -50 | 현재 작성된 `compose.prod.yml` `secrets:` 블록 + `docker-secret-shim.sh` 폐기 = 작동 자산 되돌림, `env_file:`은 컨테이너 내부 `env`/`docker inspect`에 시크릿 평문 노출 → 보안 격리 -1단계, D-day 회귀 risk | 기각 — OpenAI key 노출 시 과금 폭탄 + 보안 격리 후퇴 |

**의사결정 프로세스**: 4 BMad agent (Winston/Amelia/Murat/Dr. Quinn) 3 라운드 토론. 4명 모두 입장 변경 경험(ironic shift). Round 3 최종 합의: Amelia + Quinn 옵션 A 권고. Winston/Murat의 옵션 D 우위 주장은 Amelia의 "Config ≠ Secret + env var `/proc` 노출 + GHA workspace 경유 + 작동 코드 되돌림" 반박을 결정적으로 무력화하지 못함.

## Consequences (결과·영향)

### Positive

- **코드 변경 0 LOC**: `infra/compose.prod.yml` (197 LOC) + `infra/docker-secret-shim.sh` 이미 작성된 자산 유지 → 회귀 risk 최저
- **보안 격리 +1**: Docker `secrets:` read-only mount + shim 사용으로 compose 파일·`docker inspect`·GHA workspace에 시크릿 평문이 남지 않음. 단, 앱 호환을 위해 shim이 ENV로 변환하므로 컨테이너 내부 프로세스 환경에는 노출됨.
- **GHA에 시크릿 도달 0**: 시크릿이 GitHub workspace에 절대 안 닿음 → GH 조직 권한 노출 시에도 시크릿 영향 0 (폭발 반경 최소)
- **12-factor 호환**: 시크릿이 EC2 환경에 속함, 코드 저장소(git)와 완전 분리
- **회전 시 컨테이너 재기동만 필요**: shim이 시작 시점에 secret 파일을 ENV로 변환하므로 파일 교체 후 컨테이너 재기동으로 반영
- **6 layer defense-in-depth**: 상위 디렉터리 권한(700 root:root) + 파일 권한(0444 root:root) + Docker secrets read-only mount + git 격리(.gitignore) + Network 격리(fail2ban) + Audit(auth.log)
- **검증 자동화로 testability 8/10**: IMAGE_TAG 검증 + cold-start 가드 + container healthcheck 폴링 + 자동 롤백 후 재검증이 deploy.yml에 구현되어 있어 옵션 C에 필적하는 검증 자동화 달성. Pre-deploy assertion 미추가도 healthcheck가 동일 fail-fast를 보장.

### Negative

- **시크릿 회전 시 EC2 SSH 수동 작업 필요** (`docs/deployment.md` §3 절차): 회전 주기 >> 프로젝트 수명이므로 실 부담 ≈ 0
- **Source of Truth = EC2 디스크**: 인스턴스 분실 시 시크릿 복구 불가 → 1Password 등 안전한 보관소에 별도 백업 권장
- **Audit log = `auth.log`만**: GitHub audit log / CloudTrail 시크릿 변경 추적 없음 (학생 프로젝트 컴플라이언스 수준에서 수용)
- **자동 회전 없음**: AWS Secrets Manager의 자동 회전 기능 사용 불가

### Risks

- **EC2 노드 compromise 시 모든 시크릿 노출**: fail2ban + ed25519 키 + .pem 1Password 백업으로 진입점 좁힘 (defense-in-depth Layer 5)
- **`.pem` 분실 시 EC2 키페어 재발급 불가**: 학생 IAM 권한 없음 → EC2 launch 시점에 `~/.ssh/authorized_keys`에 백업 공개키 미리 등록 권장 ([deployment.md §2.1](../deployment.md))
- **결정이 깨지는 조건**:
  - 학생 IAM 제약 해제 (졸업 후 개인 계정 이전) → AWS Secrets Manager / SSM Parameter Store 마이그레이션 검토
  - 팀 규모 4명 이상 확대 → SOPS+age 또는 Infisical/OpenBao 검토
  - 시크릿 회전 빈도 분기 1회 이상 → 자동화 가치 재평가

## 결정하지 않은 것

- **AWS Secrets Manager 마이그레이션 계획** (졸업 후 개인 계정 이전 시점 결정)
- **`.env.example`을 git에 commit할지 여부** (deferred, Story 5-2 외 별도 작업)
- **시크릿 회전 알람**: 현재 회전 주기 = "필요 시" 수동, 정기 회전 정책 미수립
- **두 번째 admin SSH 공개키 등록**: Dr. Quinn 제안 (단일 `.pem` over-constraint 해소) — 별도 보강 작업으로 deferred

## 관련 자료

### 공식 문서
- [Manage secrets securely in Docker Compose — Docker Docs](https://docs.docker.com/compose/how-tos/use-secrets/)
- [Manage sensitive data with Docker secrets — Docker Docs](https://docs.docker.com/engine/swarm/secrets/)
- [SEC02-BP03 Store and use secrets securely — AWS Well-Architected Framework](https://docs.aws.amazon.com/wellarchitected/latest/framework/sec_identities_secrets.html)
- [The Twelve-Factor App — III. Config](https://12factor.net/config)

### 벤치마크·리서치
- [SOPS Mozilla → CNCF Sandbox (2023)](https://github.com/getsops/sops)
- [AWS Secrets Manager vs Systems Manager Parameter Store — TutorialsDojo](https://tutorialsdojo.com/aws-secrets-manager-vs-systems-manager-parameter-store/)
- [Top 5 Secrets Management Tools 2026](https://guptadeepak.com/top-5-secrets-management-tools-hashicorp-vault-aws-doppler-infisical-and-azure-key-vault-compared/)

### 의사결정 프로세스
- 4 BMad agent (Winston/Amelia/Murat/Dr. Quinn) 3 라운드 cross-talk 토론
- Round 1: 분기 (A=Amelia, C=Winston/Murat, D=Quinn) — SOPS B 만장일치 기각
- Round 2: Ironic shift (4명 모두 입장 변경) — 2:2 동률
- Round 3: Murat의 quality gate orthogonality 정정 후 Amelia A 회귀 → A+Quinn vs D+Winston/Murat, A 채택

### 관련 파일
- `infra/compose.prod.yml` (`secrets:` 블록, 197 LOC)
- `infra/docker-secret-shim.sh` (`/run/secrets/` → ENV 변환)
- `.github/workflows/deploy.yml` (deploy job — IMAGE_TAG 검증 L206-215, cold-start 가드 L311-313, container healthcheck 폴링 L273-309, 자동 롤백 + 재검증 L311-349)
- `docs/deployment.md` §2.6 (시크릿 + .env ClickOps 절차), §3 (회전 절차), §6 (보안 트레이드오프)
- `_bmad-output/implementation-artifacts/5-2-github-actions-완전-통합-ci-cd-파이프라인.md` (Story 5-2 spec)

### 관련 제약 (memory)
- [project_aws_student_account_constraints.md](../../../.claude/projects/-Users-jmac-Desktop-261RCOSE45700/memory/project_aws_student_account_constraints.md)
- [feedback_no_external_services.md](../../../.claude/projects/-Users-jmac-Desktop-261RCOSE45700/memory/feedback_no_external_services.md)
