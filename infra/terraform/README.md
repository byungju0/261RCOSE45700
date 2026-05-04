# Terraform — AWS 인프라 (학생 계정 PIVOT 사양)

Tracker 시스템의 AWS 인프라(EC2 / RDS / S3 / IAM / Secrets)를 IaC로 관리한다.

> **⚠️ 2026-05-04 PIVOT — 학생 계정 SCP 제약 적용**
>
> 본래 production-grade 결정(custom VPC + Graviton arm64 + CloudTrail/KMS CMK/Budgets/Multi-AZ 검토)을 학생 계정 SCP에 맞춰 다운그레이드:
> - **EC2**: r6g/t4g(arm64) → **t3.medium x86_64 ×3**
> - **VPC**: custom VPC → **Default VPC data source lookup**
> - **RDS**: `publicly_accessible=false` + private subnet → **`true` 강제 + SG 1차 방어 + `rds.force_ssl=1`**
> - **CloudTrail / KMS CMK / Budgets / Flow Logs**: 학생 계정 권한 부족 가정으로 코드 제외 (학교 default 정책 의존)
> - **S3 SSE**: KMS → **SSE-S3(AES256)**
> - **prod 환경**: 미사용 (학생 계정 1개로 dev 1개만 운영)
>
> Production 복구 (졸업 후 실 계정 확보 시): git history에서 PIVOT 이전 commit 복원.

**Console 수동 생성(ClickOps) 금지** — 모든 가능한 리소스는 PR 리뷰를 거친 코드 → apply가 단일 진실의 원천.

## 디렉토리 구조

```
infra/terraform/
├── bootstrap/                      # 1회성 — state 백엔드 S3 버킷 생성
├── modules/
│   ├── networking/                 # VPC + subnets + S3 endpoint + Flow Logs
│   ├── security-groups/            # crawler / detection / api / rds 4종
│   ├── iam/                        # EC2 Instance Roles + GitHub OIDC + GHA Role
│   ├── ec2-service/                # crawler/detection/api 공통 EC2 패턴
│   ├── rds/                        # PostgreSQL 16.13 db.t4g.micro Single-AZ
│   ├── s3-archive/                 # 원본 HTML 아카이브 버킷
│   ├── security-baseline/          # EBS encryption + CloudTrail + Budgets
│   └── secrets/                    # Secrets Manager placeholder 3종
└── environments/
    ├── dev/                        # main 머지 시 자동 apply
    └── prod/                       # GitHub Environments 보호 규칙 + 수동 승인
```

## 사전 결정 (학생 계정 PIVOT 적용)

| 항목 | 값 | 본래(PIVOT 이전) |
|---|---|---|
| Terraform | `>= 1.14, < 2.0` | 동일 |
| AWS provider | `~> 6.0` | 동일 |
| Region | `ap-northeast-2` (Seoul) | 동일 |
| AWS 계정 | **학생 계정** (학교 관리, SCP 제약) | 일반 계정 가정 |
| State backend | S3 + native locking, **SSE-S3(AES256)** | SSE-KMS → 학생 계정 SCP로 폴백 |
| 환경 분리 | dev 활성, **prod 미사용** | dev + prod 양쪽 |
| 모듈 사용 | `terraform-aws-modules/{security-group,ec2-instance,rds}/aws` 우선, **VPC는 default data source** | `vpc/aws` 모듈도 사용 |
| GitHub Actions ↔ AWS | OIDC + IAM Role | 동일 |
| EC2 접근 | SSM Session Manager 단독 | 동일 |
| EC2 사양 | **crawler/detection/api 모두 t3.medium x86_64** (학생 계정 4종 한정) | r6g.large / t4g.medium / t4g.large arm64 |
| RDS | PostgreSQL 16.13, **db.t3.micro, publicly_accessible=true(강제), default subnet group, force_ssl=1** | db.t4g.micro, publicly_accessible=false, custom subnet group |
| CloudTrail / KMS CMK / Budgets / Flow Logs | **모두 미생성** (학생 계정 권한 부족 가정) | 모두 코드로 정의 |
| 월 예산 | **학교 사전 설정 budget 활용** | 30만원 자체 Budget |

## `.terraform.lock.hcl` commit 정책 (best practice)

`.terraform.lock.hcl`은 provider 버전(예: `hashicorp/aws v6.43.0`)을 hash까지 박아두는 lock 파일. **반드시 git commit**해서 모든 환경에서 동일 provider 버전 사용 보장 (HashiCorp 공식 권장).

**bootstrap apply 또는 환경 init 후 절차:**

```bash
# CloudShell에서 init 직후
cd infra/terraform/bootstrap   # 또는 environments/dev
terraform init                  # → .terraform.lock.hcl 생성

# 로컬로 다운로드 (CloudShell 우상단 Actions → Download file)
# → repo 같은 위치에 두고 commit
git add infra/terraform/bootstrap/.terraform.lock.hcl
git commit -m "chore(infra): commit terraform.lock.hcl (provider version pin)"
```

각 디렉토리(bootstrap + environments/{dev,prod} + modules/*)별로 1회 생성 + commit. 이후 provider 마이너 업데이트 시 `terraform init -upgrade`로 lock 갱신 + commit.

**왜 필요한가** — 본 PR에서 겪은 v6→v7 메이저 호환성 사고를 lock으로 부분 방지. lock 없으면 매 init 시 가장 최신 provider를 받아 의도치 않은 breaking change 노출.

## 학생 계정 정보 (확정)

| 항목 | 값 |
|---|---|
| AWS Account ID | `<AWS_ACCOUNT_ID>` |
| IAM 사용자 ARN | `arn:aws:iam::<AWS_ACCOUNT_ID>:user/<IAM_USER>` |
| IAM 그룹 | `<IAM_GROUP>` |
| Region | `ap-northeast-2` (Seoul) |

## 학생 계정 정책 요약

- **루트 계정**: 학교 관리자만 보유 — 학생은 IAM 사용자로만 로그인
- **`<mfa-required-scp>`**: MFA 인증 없이는 모든 AWS API 호출 차단
- **`<own-resource-only-policy>`**: 자기가 만든 자원만 제어 가능
- **`<region-restrict-policy>`**: `us-east-1`(버지니아 북부) 1개만 차단. **나머지 16개 region 허용** (Terraform validation 화이트리스트):
  - 미국: `us-east-2` `us-west-1` `us-west-2`
  - 아시아 태평양: `ap-south-1` `ap-northeast-1` **`ap-northeast-2`(서울 — 기본)** `ap-northeast-3` `ap-southeast-1` `ap-southeast-2`
  - 캐나다/유럽/남미: `ca-central-1` `eu-central-1` `eu-west-1` `eu-west-2` `eu-west-3` `eu-north-1` `sa-east-1`
- **권한 그룹**: `<iam-advanced-policy>` + `<iam-basic-policy>` + `<power-user-policy>` + `<instance-type-allow-policy>` + `<t3-extra-allow-policy>` (정책 본문 조회 불가)
- **EC2 인스턴스 타입**: **t3.{nano, micro, small, medium} 4종**만 launch 가능 (콘솔 확인 2026-05-04)
- **IAM Access Key 발급**: ❌ **차단** — `iam:ListAccessKeys`도 권한 거부 확인 (2026-05-04)

## Terraform 사용 — AWS CloudShell이 **유일한 옵션** ⭐

학교가 IAM Access Key 발급을 차단했으므로 로컬 머신에서 `aws configure` 사용 불가. **AWS CloudShell**만 가능:

```bash
# 1. AWS 콘솔에 MFA로 로그인 (계정 ID: <AWS_ACCOUNT_ID>, 사용자: <IAM_USER>)
# 2. 우상단 CloudShell 아이콘 클릭 (Seoul region 선택 후 진입)
# 3. CloudShell에서 — credentials 자동 주입됨, 별도 토큰 불필요

sudo yum install -y unzip git
curl -O https://releases.hashicorp.com/terraform/1.15.1/terraform_1.15.1_linux_amd64.zip
unzip terraform_1.15.1_linux_amd64.zip
sudo mv terraform /usr/local/bin/

git clone https://github.com/byungju0/261RCOSE45700.git
cd 261RCOSE45700/infra/terraform/bootstrap

# bootstrap (1회)
terraform init
terraform apply -var "env=dev"
# → tracker-tfstate-dev 버킷 생성

# 환경 apply
cd ../environments/dev
cp terraform.tfvars.example terraform.tfvars
# → terraform.tfvars 편집(budget_alert_emails 등). tfvars는 .gitignore
terraform init
terraform apply
```

⚠️ **CloudShell home 디렉토리 1GB 제한 + 일정 기간 미사용 시 자동 wipe**. bootstrap apply 후 `terraform.tfstate` 즉시 로컬 다운로드(CloudShell 우상단 Actions → Download file) + 안전한 곳(1Password 등) 백업 필수.

## prod 환경 미사용

prod는 학생 계정에서 미사용. `terraform apply -var "env=prod"` 실행 금지.

## CI 게이트 — 정적 가드만 (plan/apply 자동화 없음)

`.github/workflows/terraform.yml` — `static-checks` 단일 잡:

| 트리거 | 잡 | 내용 |
|---|---|---|
| `pull_request` (paths: `infra/terraform/**`) | static-checks | fmt + validate + TFLint + Checkov |
| `push` to `main` (paths: `infra/terraform/**`) | static-checks | 동일 |

학생 계정 SCP(`<mfa-required-scp>` + IAM Access Key 발급 차단) 운영 결정으로 **CI에서는 plan/apply를 자동 실행하지 않음**. 실 plan/apply는 사용자가 AWS CloudShell에서 위 절차로 수동 실행.

`static-checks` 잡 4단계:
1. `terraform fmt -check -recursive infra/terraform`
2. 모듈/환경 디렉토리별 `terraform validate`
3. `tflint --config=.tflint.hcl` (AWS plugin 0.47.0, `aws_instance_invalid_type` 등)
4. `checkov --config-file .checkov.yml` (skip 룰 9종 모두 architecture.md 또는 학생 계정 PIVOT 인용 사유 명시)

→ AWS API 호출 / credentials / OIDC 모두 불필요. workflow `permissions: contents: read` (read-only). 비용 0.

## 사전 요구 (1회 ops)

| 항목 | 절차 |
|---|---|
| Bootstrap apply | CloudShell에서 1회 (위 "Terraform 사용 — AWS CloudShell" 섹션) |
| Secrets Manager 시크릿 1회 주입 | 아래 |
| GitHub Repository 보안 가드 점검 | 아래 "GitHub 측 점검 항목" 표 |

### Secrets Manager 1회 주입

```bash
aws secretsmanager put-secret-value \
  --secret-id tracker/dev/varco-api-key \
  --secret-string "$(read -s -p 'VARCO API key: ' k && echo "$k")"

aws secretsmanager put-secret-value \
  --secret-id tracker/dev/proxy-credentials \
  --secret-string '{"username":"...","password":"...","endpoint":"..."}'
```

`tracker/dev/rds-admin-password`는 `random_password`가 자동 주입한다.

## drift 점검

월 1회 또는 ad-hoc:

```bash
cd infra/terraform/environments/dev
terraform plan -refresh-only
```

drift 발견 시:
- Console에서 변경된 항목을 코드에 반영(`terraform import`가 필요한 경우 해당 자원만)
- 또는 코드 정의대로 `terraform apply` (Console 변경을 되돌림)

## pre-commit (로컬)

```bash
pip install pre-commit checkov
brew install tflint terraform-docs
pre-commit install
pre-commit run --all-files
```

훅이 잡는 가드:
- `terraform_fmt` — 포맷 강제
- `terraform_validate` — 문법 검증
- `terraform_tflint` — AWS 룰셋 (`.tflint.hcl`)
- `terraform_checkov` — 보안 스캔 (`.checkov.yml`)
- `terraform_docs` — 모듈 README의 `<!-- BEGIN_TF_DOCS -->`~`<!-- END_TF_DOCS -->` 자동 갱신
- `detect-aws-credentials` / `detect-private-key` — 시크릿 누설 차단

## Public repository 보안 가드

본 repo는 **public**이다. 다음 가드가 코드/CI 양쪽에 박혀 있으며, ops 단계에서 GitHub 측 설정을 1회 점검하면 표준적인 public Terraform repo 보안 수준이 확보된다.

### 코드/CI에 이미 박혀 있는 것

| 가드 | 어디 |
|---|---|
| 시크릿 값 코드 0건 (Secrets Manager placeholder만) | `modules/secrets/` |
| tfstate · tfvars · `.terraform/` git 제외 | `.gitignore` |
| AWS 장기 Access Key 미사용 (OIDC + IAM Role) | `modules/iam/` + `terraform.yml` |
| `pre-commit` 시크릿 누설 가드 (`detect-aws-credentials`, `detect-private-key`) | `.pre-commit-config.yaml` |
| 정적 보안 스캔 (Checkov + TFLint) PR 게이트 | `terraform.yml` static-checks 잡 |
| RDS password `random_password` + `ignore_changes` (state 평문 노출 최소화) | `modules/rds/` |
| S3 버킷 4종 퍼블릭 차단 + TLS-only deny | 모든 S3 모듈 |
| **CI plan/apply 잡 미존재** — fork PR이 OIDC 토큰을 받아 우리 AWS로 assume 시도할 통로 자체 없음 (정적 가드만 실행) | `terraform.yml` static-checks 단일 잡 |
| **`pull_request_target` 절대 사용 금지** (pwn-request 패턴 회피) | 본 repo 워크플로우 4종 모두 `pull_request` 사용 |
| **PII(이메일) 코드 default 미박힘** (실제 값은 `terraform.tfvars` `.gitignore` 또는 CloudShell 환경변수) | `environments/{dev,prod}/variables.tf` |
| **CODEOWNERS** — `infra/`/`.github/`/`dashboard/` 변경 PR에 `@gitjay3` 자동 review 요청 | `.github/CODEOWNERS` |
| **Dependabot** — terraform-aws-modules / GitHub Actions / dashboard npm 의존성 매주 자동 PR | `.github/dependabot.yml` |
| **Workflow `permissions:` 최소 권한** — workflow default `contents: read`, 잡별로 필요 권한만 추가 | `terraform.yml` 각 잡 `permissions:` 블록 |

### GitHub 측 점검 (Settings → ...)

| 항목 | 2026 기본 상태 | 점검 경로 | 액션 |
|---|---|---|---|
| **Secret scanning** | public repo 자동 활성 | Settings → Code security → Secret scanning | "Enabled" 표시 확인 |
| **Push protection** | public repo 자동 활성 | Settings → Code security → Secret scanning → Push protection | "Enabled" 표시 확인 |
| **First-time contributor 승인 게이트** | 기본 활성 | Settings → Actions → General → "Fork pull request workflows from outside collaborators" | "Require approval for first-time contributors" 라디오가 선택되어 있는지 확인 |
| **Repository Ruleset (main)** | 미설정 | Settings → **Rules → Rulesets** → New ruleset → Branch ruleset | Target `main` 지정 후 ✅ Restrict deletions / ✅ Require linear history / ✅ Require pull request before merging (1 reviewer) / ✅ **Require review from Code Owners** (CODEOWNERS 활용) / ✅ Require status checks to pass (`Static checks (fmt / validate / TFLint / Checkov)` 등록) / ✅ Block force pushes — branch protection rule보다 권장 (다중 ruleset 동시 적용 가능, 2026 표준) |
| **Dependabot security updates** | 기본 활성 | Settings → Code security → Dependabot | "Dependabot security updates" + "Dependabot version updates" 두 토글 모두 Enabled (version updates는 `.github/dependabot.yml`로 동작) |

### 사고 시 대응

- **AWS Key/Token 누설 (push protection을 누가 bypass)** — 즉시 IAM 콘솔에서 키/Role 비활성화 → CloudTrail로 사용 이력 조회 → 영향 범위에 따라 리소스 회수.
- **타인 fork PR로 의심 trigger 흔적** — `terraform.yml`은 정적 가드만 실행 (AWS credentials / OIDC 미사용)이라 fork PR이 우리 AWS 자원을 만질 통로 자체 없음. Actions 로그에서 contributor 신원만 확인.
- **drift 발견** — Console에서 누가 ClickOps 했는지 CloudTrail 추적 + `terraform plan -refresh-only`로 차이 진단 → 코드 반영 또는 apply로 정정.

## 주의 — 안티패턴

- **ClickOps 금지** — Console에서 만든 리소스는 영원히 drift.
- **DynamoDB lock 테이블 만들지 말 것** — 1.10+ S3 native locking으로 대체.
- **tfstate에 평문 시크릿 금지** — Secrets Manager placeholder만 정의, 값 주입은 Console / ops 스크립트.
- **`terraform apply -auto-approve`를 로컬에서 직접 실행 금지** — dev는 main 머지가, prod는 환경 보호 규칙이 게이트.
- **Resource: "*" 와일드카드 금지** — Checkov `CKV_AWS_111`. EC2 Instance Role은 모두 ARN 한정.
- **AMI x86_64 금지** — Graviton 인스턴스에 부팅 시 즉시 실패. `data "aws_ami"` 필터에 `architecture = "arm64"` 필수.
- **모듈 v3 핀 금지 (RDS)** — `terraform-aws-modules/rds/aws` v7 사용.

## 참고

- [architecture.md Infrastructure & Deployment](../../_bmad-output/planning-artifacts/architecture.md#L221-L256) — 22개 결정
- [PR #18 (commit bd172d9)](https://github.com/byungju0/261RCOSE45700/commit/bd172d9) — Terraform IaC 정책 + AWS 사이징
- [DATA_POLICY.md](../DATA_POLICY.md) — 수집 데이터 사용·공개 정책
