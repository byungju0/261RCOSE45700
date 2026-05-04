variable "region" {
  description = "AWS region. PIVOT으로 prod 미사용이지만 default는 ap-northeast-2 유지."
  type        = string
  default     = "ap-northeast-2"

  validation {
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
    error_message = "학생 계정 제약: us-east-1 차단 (RestrictRegionVirginia 정책)."
  }
}

variable "name_prefix" {
  type    = string
  default = "tracker-prod"
}

variable "vpc_cidr" {
  type    = string
  default = "10.30.0.0/16"
}

variable "availability_zones" {
  type    = list(string)
  default = ["ap-northeast-2a", "ap-northeast-2c"]
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.30.1.0/24", "10.30.2.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.30.11.0/24", "10.30.12.0/24"]
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
  type    = string
  default = "byungju0/261RCOSE45700"
}

variable "tfstate_bucket_name" {
  type    = string
  default = "tracker-tfstate-prod"
}

variable "existing_oidc_provider_arn" {
  description = <<-EOT
    dev 환경에서 만든 GitHub OIDC provider의 ARN.
    dev `terraform output oidc_provider_arn` 값을 여기 주입.
  EOT
  type        = string
}
