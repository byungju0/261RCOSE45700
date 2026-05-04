terraform {
  required_version = ">= 1.14, < 2.0"

  # State backend — bootstrap에서 만든 tracker-tfstate-dev S3 버킷
  # Terraform 1.10+ S3 native locking (use_lockfile) — 별도 DynamoDB 테이블 불필요.
  backend "s3" {
    bucket       = "tracker-tfstate-dev"
    key          = "tracker/dev/terraform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}
