# environments/prod — 학생 계정 미사용

> **2026-05-04 PIVOT — 학생 계정에서는 본 prod 환경을 사용하지 않습니다.**

학생 계정 1개로 dev/prod 분리 의미가 없어 dev 환경 1개만 운영합니다. 본 prod 디렉토리는:

1. **portfolio 자료**로 코드 보존 — 졸업 후 실 production 계정 확보 시 그대로 활용
2. 본래 design(custom VPC + Multi-AZ 검토 + CloudTrail/KMS CMK/Budgets) 일부는 PIVOT으로 학생 계정 dev 환경에서 비활성됨. 복원하려면 git history 참조

## 절대 apply 금지

본 prod의 `terraform.tfvars` 작성 + `terraform apply`는 학생 계정에서 의미 없음. CI 워크플로우(`terraform.yml`)도 prod apply 잡을 비활성하거나 무시해야 함 — Story 5.3 PIVOT으로 prod 잡 트리거 시 학생 계정에 dev 환경과 동일한 자원이 prod 이름으로 한 벌 더 생성될 뿐.

## 복구 (졸업 후 실 계정)

1. PIVOT 이전 commit으로 환경 코드 복원: `git log infra/terraform/environments/prod/main.tf`
2. `modules/networking/`, `modules/security-baseline/`도 함께 PIVOT 이전으로 복원
3. 새 AWS 계정 + IAM credentials로 bootstrap 1회 apply 후 환경 init/apply
