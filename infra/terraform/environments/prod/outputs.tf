output "vpc_id" {
  value = module.networking.vpc_id
}

output "rds_endpoint" {
  value = module.rds.endpoint
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
  value = module.ec2_api.public_ip
}

output "github_actions_role_arn" {
  description = "prod GitHub Actions OIDC assume role ARN — terraform.yml apply prod 잡의 role-to-assume."
  value       = module.iam.github_actions_role_arn
}

output "cloudtrail_bucket" {
  value = module.security_baseline.cloudtrail_bucket_id
}
