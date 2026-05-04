output "vpc_id" {
  description = "Default VPC ID (학생 계정)."
  value       = module.networking.vpc_id
}

output "rds_endpoint" {
  description = "RDS endpoint (publicly_accessible=true 학생 계정 강제, SG로 1차 방어)."
  value       = module.rds.endpoint
}

output "archive_bucket_name" {
  value = module.s3_archive.bucket_name
}

output "ec2_crawler_id" {
  value = module.ec2_crawler.instance_id
}

output "ec2_detection_id" {
  value = module.ec2_detection.instance_id
}

output "ec2_api_id" {
  value = module.ec2_api.instance_id
}

output "ec2_api_public_ip" {
  description = "API EC2 public IP (Default VPC subnet 자동 할당)."
  value       = module.ec2_api.public_ip
}

output "github_actions_role_arn" {
  description = "GitHub Actions OIDC assume role ARN."
  value       = module.iam.github_actions_role_arn
}

output "oidc_provider_arn" {
  description = "GitHub OIDC provider ARN (계정당 1개, 본 dev에서 생성)."
  value       = module.iam.oidc_provider_arn
}
