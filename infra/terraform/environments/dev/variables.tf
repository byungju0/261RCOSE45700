variable "region" {
  description = <<-EOT
    AWS region. Default: ap-northeast-2(Seoul).
    학생 계정 SCP `RestrictRegionVirginia`가 us-east-1만 차단. 나머지 16개 region 허용.
    architecture decision은 ap-northeast-2 — 변경 시 비용/지연 영향 평가 필요.
  EOT
  type        = string
  default     = "ap-northeast-2"

  validation {
    # 학교 허용 region 16개 (us-east-1 차단)
    condition = contains(
      [
        "us-east-2", "us-west-1", "us-west-2",
        "ap-south-1", "ap-northeast-1", "ap-northeast-2", "ap-northeast-3",
        "ap-southeast-1", "ap-southeast-2",
        "ca-central-1",
        "eu-central-1", "eu-west-1", "eu-west-2", "eu-west-3", "eu-north-1",
        "sa-east-1",
      ],
      var.region,
    )
    error_message = "학생 계정 제약: region이 학교 허용 화이트리스트에 없음. us-east-1(버지니아) 차단 + 나머지 16개 region만 허용 (RestrictRegionVirginia 정책)."
  }
}

variable "name_prefix" {
  description = "리소스 prefix."
  type        = string
  default     = "tracker-dev"
}

variable "vpc_cidr" {
  description = "VPC CIDR."
  type        = string
  default     = "10.20.0.0/16"
}

variable "availability_zones" {
  description = "AZs."
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]
}

variable "public_subnet_cidrs" {
  description = "Public subnet CIDRs (EC2 3종)."
  type        = list(string)
  default     = ["10.20.1.0/24", "10.20.2.0/24"]
}

variable "private_subnet_cidrs" {
  description = "Private subnet CIDRs (RDS multi-AZ subnet group 요건)."
  type        = list(string)
  default     = ["10.20.11.0/24", "10.20.12.0/24"]
}

variable "budget_alert_emails" {
  description = <<-EOT
    AWS Budgets 알림 수신 이메일.
    Public repo PII 보호를 위해 default 미정의 — 실제 값은:
      - 로컬: terraform.tfvars (.gitignore)
      - CI:   GitHub Actions Variables → TF_VAR_BUDGET_ALERT_EMAILS 환경변수
  EOT
  type        = list(string)
}

variable "github_repository" {
  description = "GitHub OIDC trust 매칭에 사용할 repo (owner/name)."
  type        = string
  default     = "byungju0/261RCOSE45700"
}

variable "tfstate_bucket_name" {
  description = "Bootstrap이 만든 tfstate 버킷 이름 (GitHub Actions Role 권한 한정용)."
  type        = string
  default     = "tracker-tfstate-dev"
}
