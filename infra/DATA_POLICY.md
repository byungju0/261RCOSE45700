# Tracker — 데이터 사용·공개 정책

본 문서는 Tracker 시스템이 수집·저장·처리하는 모든 데이터의 사용 목적과 공개 범위를 정의한다. NFR9(데이터 거버넌스) 준수.

> **2026-05-04 PIVOT — 학생 계정 SCP 제약 적용**
> 본래 production-grade 결정(custom VPC + private subnet + CloudTrail/KMS CMK/Budgets/Flow Logs)을 학생 계정 SCP에 맞춰 다운그레이드. 본 정책은 PIVOT 후 실제 운영 형태를 반영. 졸업 후 production 계정 확보 시 [git history](#10-갱신-이력)에서 PIVOT 이전 정책 복원.

## 1. 수집 대상

| 데이터 | 출처 | 저장 위치 |
|---|---|---|
| 게시글 원본 HTML | 외부 사이트 (taobao, tailstar 등) | S3 `tracker-archive-{env}-*` (SSE-S3, 비공개) |
| 게시글 메타데이터 | 크롤러 추출 결과 | RDS `posts` 테이블 |
| 번역 결과 (한국어) | VARCO Translation API | RDS `translations` 테이블 |
| 탐지 결과 (불법 여부 + confidence + 근거) | VARCO LLM 분류 결과 | RDS `detections` 테이블 |
| 시스템 로그 | 애플리케이션 로그 | CloudWatch Logs (애플리케이션 측 send) |
| 감사 로그 (AWS API 호출 이력) | 학교 organization CloudTrail | 학교 관리 (학생 계정 자체 trail 미생성) |

## 2. 사용 목적 — **탐지 전용**

수집 데이터는 **불법 게시글 탐지 시스템의 학습·운영·검증 목적으로만** 사용된다. 다음 용도는 **금지**:

- 외부 공개 / 배포 / 판매
- 학술 발표·논문 게재 (사전 협의 없이)
- 다른 시스템·서비스로의 이전
- 탐지 외 분석(마케팅, 트렌드 분석 등)
- 개인 식별이 가능한 형태로의 가공

## 3. 외부 공개 금지

- **원본 HTML**: S3 버킷은 퍼블릭 차단(`block_public_*` 4종 true), Crawler IAM Role만 PutObject 가능. 비-TLS 접근 deny (`aws:SecureTransport=false`).
- **탐지 결과**: API는 인증된 내부 사용자만 접근. 외부 공개 API 미제공.
- **로그**: 학교 organization trail은 운영 감사 목적으로만 학교 관리자 접근.

## 4. 보관 기간

| 데이터 | 보관 |
|---|---|
| S3 원본 HTML | 90일 후 STANDARD_IA 전환, 365일 후 자동 삭제 |
| S3 비최신 버전 | 30일 후 자동 삭제 |
| RDS 자동 백업 | 7일 (point-in-time recovery) |
| Secrets Manager (삭제 후 복구) | dev 7일 (prod 환경 미사용) |
| CloudWatch Logs (애플리케이션) | default 영구 — 콘솔 1회 retention 14일 설정 권장 (deferred-work) |

## 5. 암호화 (PIVOT 적용)

저장 시 (at rest):
- **S3 (archive + access logs)**: **SSE-S3 (AES256)** — 학생 계정 KMS CMK 생성 권한 부족 가정으로 KMS 폴백
- **RDS**: `storage_encrypted = true` (region default `alias/aws/rds` key, 자동)
- **EBS**: region default 정책 의존 (`aws_ebs_encryption_by_default` 자체 자원은 학생 계정 권한 부족으로 미생성. 학교 default 정책에 의존 — 콘솔 EC2 → "EBS encryption" 1회 확인 필요)
- **Secrets Manager**: AWS-managed key (`alias/aws/secretsmanager`) 자동
- **CloudTrail**: 학교 organization trail에 의존 (학생 계정 자체 trail 미생성 — KMS CMK 권한 부족)

전송 시 (in transit):
- **S3 버킷 정책**: `aws:SecureTransport = false` deny (archive 버킷)
- **RDS**: **Parameter group `rds.force_ssl = 1`로 TLS만 허용**, 평문 접속 거절 (publicly_accessible=true 보안 보강)
- **EC2 운영 접근**: **SSH `.pem` only** (2026-05-06 Story 5-2 PIVOT — 학생 IAM이 SSM Session Manager / EC2 Instance Connect 권한 차단으로 SSM 사용 불가). 22번 인바운드 `0.0.0.0/0` + ed25519 + fail2ban (3 fail / 10분 / 24h ban)으로 안전화. host fingerprint verification은 운영 단순화 trade-off로 미적용 (commit `75e9ac5`)

## 6. 접근 통제 (PIVOT 적용)

- **EC2 → S3**: IGW 경유 (Default VPC 사용). VPC Gateway Endpoint는 학생 계정 라우트 테이블 수정 권한 불확실로 미생성 (deferred-work). Crawler IAM Role의 `s3:PutObject` 권한이 archive 버킷 ARN 한정.
- **EC2 → Secrets Manager**: Detection / API IAM Role만 GetSecretValue (특정 Secret ARN 한정). 다른 EC2 Role은 접근 불가.
- **EC2 운영 접근**: **SSH `.pem` only** (2026-05-06 PIVOT). 단일 `.pem` 키페어 (관리자 접속 + GHA 자동 배포 공용). 22번 인바운드 `0.0.0.0/0` + defense-in-depth (ed25519 + password auth 비활성 + fail2ban). 학생 IAM이 SSM Session Manager·EC2 Instance Connect·IAM Role 생성 모두 차단으로 SSM 통로 불가.
- **RDS 네트워크 (PIVOT)**: 학생 계정 SCP가 `publicly_accessible=true` 강제. **Default VPC 안에서 SG inbound 5432 source = {api-sg} ID만 허용**으로 인터넷 라우팅을 SG 단계에서 차단 (3차 PIVOT 단일 EC2로 회귀하면서 detection-sg 분리 불필요). 추가로 `rds.force_ssl=1`로 평문 접속 거절. 실효 보안은 `publicly_accessible=false` + SG와 동등.
- **GitHub Actions → AWS**: **AWS API 직접 호출 통로 0개** (2026-05-06 PIVOT — OIDC + IAM Role 봉인, Access Key 발급 차단). 실 흐름: GHA → GHCR push (`GITHUB_TOKEN`) → SSH (`.pem` GH Secret) → EC2 내 `docker pull` + `docker compose`. AWS 자원 변경은 콘솔 ClickOps만 가능.

## 7. 감사 (PIVOT 적용)

| 감사 항목 | 메커니즘 | PIVOT 영향 |
|---|---|---|
| AWS API 호출 이력 | 학교 organization CloudTrail | 학생 계정 자체 trail 미생성. 학교 organization trail이 활성인지 학교 관리자에게 1회 확인 필요 (deferred-work) |
| 네트워크 트래픽 | (미수집) | VPC Flow Logs 학생 계정 권한 부족으로 미생성. 콘솔 1회 enable 또는 학교 default 정책 의존 (deferred-work) |
| 인프라 변경 | (ClickOps PIVOT) 콘솔 변경 시점 스크린샷으로 추적 | 2026-05-06 PIVOT 이후 — Terraform/CI 자동 추적 통로 0 |
| RDS 접근 시도 | RDS PostgreSQL logs (`postgresql`/`upgrade` → CloudWatch) | 동일 |

## 8. 시크릿 관리

- 평문 시크릿이 다음 위치에 존재해선 안 된다:
  - Git 저장소 (GitHub Push Protection 활성)
  - GitHub Secrets (장기 Access Key 금지)
- 모든 시크릿은 AWS Secrets Manager에 저장하고 EC2 IAM Role의 GetSecretValue 권한으로만 조회한다.
- RDS 비밀번호는 RDS-managed master password(Secrets Manager 자동 생성)로 처리한다.

## 9. 정책 위반 발견 시

- 즉시 운영 담당자(`@gitjay3`)에게 보고
- 영향 범위 평가 후 회수 / rotation
- 재발 방지를 위해 본 문서 / Checkov 룰 / pre-commit 훅 갱신

## 10. 갱신 이력

| 날짜 | 변경 | 출처 |
|---|---|---|
| 2026-05-04 | 초안 작성 | Story 5.3 1차 |
| 2026-05-04 | **PIVOT 적용** — S3 SSE-S3 폴백 / RDS publicly_accessible=true(SG+force_ssl 보강) / CloudTrail/KMS CMK/Flow Logs 미생성(학교 default 의존) / VPC Gateway Endpoint 미생성 / Default VPC 사용 | Story 5.3 PIVOT (학생 계정 SCP 제약) |

## 11. PIVOT 후 보안 등급 평가

| 항목 | 본래 production-grade | 학생 계정 PIVOT | 위험도 변화 |
|---|---|---|---|
| 데이터 at-rest 암호화 | KMS CMK | AWS-managed key (SSE-S3) | 낮음 — 둘 다 강한 암호화 |
| 데이터 in-transit 암호화 | TLS 강제 | TLS 강제 (RDS force_ssl=1 추가) | **개선** — RDS TLS 강제 추가 |
| RDS 네트워크 격리 | private subnet | Default VPC + SG 한정 | **중간 위험** — SG 한정으로 실효 동등하나 정책 명목 위반 |
| 감사 trail | 자체 multi-region CloudTrail | 학교 organization trail 의존 | **중간 위험** — 학교 trail 활성 미검증 |
| 접근 통제 (IAM) | EC2 Instance Role + ARN 한정 | 동일 | 동일 |
| 시크릿 관리 | Secrets Manager + KMS CMK | Secrets Manager + AWS-managed key | 낮음 |

→ 졸업 후 production 계정 확보 시 본 표의 "본래" 컬럼으로 복원 권장.
