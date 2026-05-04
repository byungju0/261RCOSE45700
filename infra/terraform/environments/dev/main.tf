locals {
  env = "dev"

  common_tags = {
    Project     = "tracker"
    Environment = local.env
    ManagedBy   = "terraform"
    Repository  = var.github_repository
    Account     = "student-account"
  }
}

##
# 1) Networking — Default VPC lookup (학생 계정 PIVOT, custom VPC 미생성)
##
module "networking" {
  source = "../../modules/networking"

  region = var.region
  tags   = local.common_tags
}

##
# 2) Security Groups (4종) — Default VPC 안에 생성
##
module "security_groups" {
  source = "../../modules/security-groups"

  name_prefix = var.name_prefix
  vpc_id      = module.networking.vpc_id

  tags = local.common_tags
}

##
# 3) Secrets Manager placeholder (KMS는 AWS-managed default 사용)
##
module "secrets" {
  source = "../../modules/secrets"

  name_prefix             = "tracker/${local.env}"
  recovery_window_in_days = 7

  tags = local.common_tags
}

##
# 4) S3 archive (SSE-S3, KMS X)
##
module "s3_archive" {
  source = "../../modules/s3-archive"

  bucket_name_prefix = "tracker-archive"
  env                = local.env
  crawler_role_arn   = module.iam.crawler_role_arn

  # Access logging은 CloudTrail 버킷 미생성으로 비활성
  access_log_bucket_id = ""

  tags = local.common_tags
}

##
# 5) IAM (EC2 Roles + GitHub OIDC + GHA Terraform Role)
##
module "iam" {
  source = "../../modules/iam"

  name_prefix           = var.name_prefix
  archive_bucket_arn    = module.s3_archive.bucket_arn
  detection_secret_arns = module.secrets.detection_secret_arns
  api_secret_arns       = module.secrets.api_secret_arns
  tfstate_bucket_name   = var.tfstate_bucket_name

  create_oidc_provider = true

  github_actions_sub_patterns = [
    "repo:${var.github_repository}:ref:refs/heads/main",
    "repo:${var.github_repository}:pull_request",
  ]

  tags = local.common_tags
}

##
# 6) RDS — db.t3.micro, publicly_accessible=true(학생 계정 강제),
#    Default VPC subnet group, parameter group rds.force_ssl=1
##
module "rds" {
  source = "../../modules/rds"

  identifier               = var.name_prefix
  engine_version           = "16.13"
  major_engine_version     = "16"
  parameter_group_family   = "postgres16"
  instance_class           = "db.t3.micro" # 학생 계정 4종 한정 — db.t4g.micro arm64 미가용
  allocated_storage        = 20
  db_name                  = "tracker"
  username                 = "tracker_admin"
  admin_password_secret_id = module.secrets.rds_admin_password_secret_id

  db_subnet_group_name = "default" # Default VPC

  backup_retention_period = 7
  deletion_protection     = false # dev
  skip_final_snapshot     = true  # dev

  security_group_id = module.security_groups.rds_sg_id

  tags = local.common_tags
}

##
# 7) EC2 ×3 (모두 t3.medium x86_64, Default VPC subnet 배치)
##
module "ec2_crawler" {
  source = "../../modules/ec2-service"

  service_name         = "${var.name_prefix}-crawler"
  instance_type        = "t3.medium" # 학생 계정 최대 사양
  subnet_id            = module.networking.first_subnet_id
  security_group_id    = module.security_groups.crawler_sg_id
  iam_instance_profile = module.iam.crawler_instance_profile_name
  root_volume_size_gb  = 30

  tags = local.common_tags
}

module "ec2_detection" {
  source = "../../modules/ec2-service"

  service_name         = "${var.name_prefix}-detection"
  instance_type        = "t3.medium"
  subnet_id            = module.networking.first_subnet_id
  security_group_id    = module.security_groups.detection_sg_id
  iam_instance_profile = module.iam.detection_instance_profile_name
  root_volume_size_gb  = 30

  tags = local.common_tags
}

module "ec2_api" {
  source = "../../modules/ec2-service"

  service_name         = "${var.name_prefix}-api"
  instance_type        = "t3.medium"
  subnet_id            = module.networking.second_subnet_id
  security_group_id    = module.security_groups.api_sg_id
  iam_instance_profile = module.iam.api_instance_profile_name
  root_volume_size_gb  = 30

  tags = local.common_tags
}

# NOTE: security-baseline 모듈은 학생 계정 PIVOT으로 비활성됨 (호출 X).
# CloudTrail/KMS CMK/Budgets는 학교 계정 default 정책 또는 콘솔 1회 설정에 의존.
