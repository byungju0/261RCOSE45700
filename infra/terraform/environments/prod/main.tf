# ════════════════════════════════════════════════════════════════════════════
# 학생 계정 PIVOT — 본 prod 환경은 사용하지 않습니다.
# 코드는 졸업 후 실 production 계정 확보 시 portfolio 자료로 보존.
# 자세한 내용: README.md
#
# WARNING — apply 시도 시 학생 계정에 dev와 별개 자원 한 벌이 더 생성될 뿐
# 의미 없는 비용 발생. CI 워크플로우의 apply-prod 잡도 비활성화됨.
# ════════════════════════════════════════════════════════════════════════════

locals {
  env = "prod"

  common_tags = {
    Project     = "tracker"
    Environment = local.env
    ManagedBy   = "terraform"
    Repository  = var.github_repository
  }
}

module "networking" {
  source = "../../modules/networking"

  name                 = var.name_prefix
  region               = var.region
  vpc_cidr             = var.vpc_cidr
  availability_zones   = var.availability_zones
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  nat_strategy         = "none"

  tags = local.common_tags
}

module "security_groups" {
  source = "../../modules/security-groups"

  name_prefix = var.name_prefix
  vpc_id      = module.networking.vpc_id

  tags = local.common_tags
}

module "security_baseline" {
  source = "../../modules/security-baseline"

  env                 = local.env
  monthly_budget_usd  = 215
  budget_alert_emails = var.budget_alert_emails

  tags = local.common_tags
}

module "secrets" {
  source = "../../modules/secrets"

  name_prefix             = "tracker/${local.env}"
  recovery_window_in_days = 30 # prod는 복구 윈도우 길게

  tags = local.common_tags
}

module "s3_archive" {
  source = "../../modules/s3-archive"

  bucket_name_prefix   = "tracker-archive"
  env                  = local.env
  crawler_role_arn     = module.iam.crawler_role_arn
  access_log_bucket_id = module.security_baseline.cloudtrail_bucket_id

  tags = local.common_tags
}

module "iam" {
  source = "../../modules/iam"

  name_prefix           = var.name_prefix
  archive_bucket_arn    = module.s3_archive.bucket_arn
  detection_secret_arns = module.secrets.detection_secret_arns
  api_secret_arns       = module.secrets.api_secret_arns
  tfstate_bucket_name   = var.tfstate_bucket_name

  # OIDC provider는 dev에서 1회 생성. prod는 그 ARN을 참조.
  create_oidc_provider       = false
  existing_oidc_provider_arn = var.existing_oidc_provider_arn

  github_actions_sub_patterns = [
    "repo:${var.github_repository}:environment:prod",
  ]

  tags = local.common_tags
}

module "rds" {
  source = "../../modules/rds"

  identifier               = var.name_prefix
  engine_version           = "16.13"
  major_engine_version     = "16"
  parameter_group_family   = "postgres16"
  instance_class           = "db.t4g.micro"
  allocated_storage        = 20
  db_name                  = "tracker"
  username                 = "tracker_admin"
  admin_password_secret_id = module.secrets.rds_admin_password_secret_id

  multi_az                = false # 학생 예산 (architecture.md:245)
  backup_retention_period = 7
  deletion_protection     = true  # prod
  skip_final_snapshot     = false # prod

  private_subnet_ids = module.networking.private_subnet_ids
  security_group_id  = module.security_groups.rds_sg_id

  tags = local.common_tags
}

module "ec2_crawler" {
  source = "../../modules/ec2-service"

  service_name         = "${var.name_prefix}-crawler"
  instance_type        = "r6g.large"
  subnet_id            = module.networking.public_subnet_ids[0]
  security_group_id    = module.security_groups.crawler_sg_id
  iam_instance_profile = module.iam.crawler_instance_profile_name
  root_volume_size_gb  = 50

  tags = local.common_tags
}

module "ec2_detection" {
  source = "../../modules/ec2-service"

  service_name         = "${var.name_prefix}-detection"
  instance_type        = "t4g.medium"
  subnet_id            = module.networking.public_subnet_ids[0]
  security_group_id    = module.security_groups.detection_sg_id
  iam_instance_profile = module.iam.detection_instance_profile_name
  root_volume_size_gb  = 30

  tags = local.common_tags
}

module "ec2_api" {
  source = "../../modules/ec2-service"

  service_name         = "${var.name_prefix}-api"
  instance_type        = "t4g.large"
  subnet_id            = module.networking.public_subnet_ids[1]
  security_group_id    = module.security_groups.api_sg_id
  iam_instance_profile = module.iam.api_instance_profile_name
  root_volume_size_gb  = 30

  tags = local.common_tags
}
