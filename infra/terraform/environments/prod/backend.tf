terraform {
  required_version = ">= 1.14, < 2.0"

  backend "s3" {
    bucket       = "tracker-tfstate-prod"
    key          = "tracker/prod/terraform.tfstate"
    region       = "ap-northeast-2"
    encrypt      = true
    use_lockfile = true
  }
}
