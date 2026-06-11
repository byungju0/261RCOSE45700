# Production Deployment — Story 5.2 PIVOT (SSH `.pem` 직결, 단일 EC2)

main 브랜치 머지가 GHCR 이미지 빌드와 EC2 배포까지 자동화됩니다. 이 문서는
운영자가 알아야 할 ClickOps 사전 셋업, 시크릿 회전 절차, 자동 롤백 동작,
비상 수동 트리거, 보안 트레이드오프를 정리합니다.

> **사양 결정 배경**:
> 1. 학생 IAM 사용자 `<student-iam-user>`에서 OIDC / IAM Role / Access Key /
>    SSM Session Manager / EC2 Instance Connect 모두 차단 → SSH `.pem` 키만 가능.
> 2. (2026-05-07 보강 시도) 메모리 OOM 우려로 2대 분리(crawler + app)를 시도했으나
>    학생 SCP가 **cross-SG ingress 룰 추가를 차단** — `app-sg`에 redis 6379 source
>    = `crawler-sg` 한정 룰을 만들 수 없음. IP cidr 우회도 동일 패턴으로 막힐
>    가능성 + EIP 발급 권한 불명. → **단일 EC2 합반으로 회귀**.
> 3. 단일 EC2의 메모리 위험은 t3.xlarge 16GB 상향 + compose 레벨 `mem_limit`
>    격리로 방어 (워킹셋 추정 1.7~3.3GB / 16GB ≈ 21% — swap 셋업 불필요).
>    [§6.3](#63-단일-ec2-합반-결정과-메모리-방어-전략) 참조.

## 호스트 토폴로지 한 표

| EC2 호스트 | 인스턴스 타입 | 컨테이너 | 추정 메모리 | 노출 포트 |
|---|---|---|---|---|
| `tracker-prod` (단일) | **t3.xlarge 16GB** | redis + crawler + detection + api + dashboard + caddy | 워킹셋 1.7~3.3GB / 16GB (~21%) | 22 (SSH), 80/443 (Caddy TLS), 8080 (api). redis 6379는 docker network 내부 only |

---

## 1. 자동 배포 흐름

```
[feature 브랜치 PR]
        │
        ▼ branch protection: ci/aggregator + 1 review + auto-merge OFF
[main 머지]
        │
        ▼ on: push (main)
.github/workflows/deploy.yml
  1. lint-test-{crawler,detection,api,dashboard}   (reusable workflow_call)
  2. build-push (matrix, BuildKit registry cache mode=max → GHCR :sha + :latest)
  3. deploy   (concurrency: deploy-prod / serial — environment: production은 §6.2 결정으로 미사용)
        │
        ▼ scp-action → /opt/app/compose.prod.yml 업로드
        ▼ ssh-action → docker login ghcr → compose pull → compose up -d
        ▼ healthcheck 폴링 180초 (6 컨테이너: redis crawler detection api dashboard caddy)
        │
   ┌────┴────┐
   │ healthy │  → /opt/app/IMAGE_TAG 갱신, exit 0
   │ failed  │  → 이전 SHA 태그로 자동 롤백, exit 1 (GHA UI 빨강)
```

`concurrency: { group: deploy-prod, cancel-in-progress: false }`로 main 머지가
연속될 때도 배포가 직렬 처리됩니다 — state 일관성 보호.

---

## 2. 사전 ClickOps 셋업 (1회성)

> **이 절은 AWS 콘솔 / GitHub UI / EC2 SSH 직접 작업입니다 — 코드로 자동화 불가.**

### 2.1 EC2 인스턴스 1대 launch (또는 기존 `tracker-crawler` 스케일 업)

| 항목 | 값 |
|---|---|
| Name | `tracker-prod` (또는 기존 `tracker-crawler` 그대로 재활용) |
| AMI | **Ubuntu Server 24.04 LTS** (x86_64) |
| 인스턴스 타입 | **t3.xlarge** (4 vCPU, 16GB) — 학생 SCP 허용 인스턴스 중 RAM 가장 큼 |
| 키페어 | 기존 `.pem` 재사용 |
| VPC | Default VPC |
| Subnet | us-east-1a (또는 RDS와 동일 AZ) |
| Auto-assign public IP | Enable |
| 스토리지 | 30 GiB gp3 |
| 보안그룹 | `tracker-prod-sg` 또는 기존 `crawler-sg`/`launch-wizard-N` 재사용 (§2.2 룰 보강) |
| SSH 사용자 | `ubuntu` |

**비용 (us-east-1, 환율 1452원/USD)**: EC2 시간당 $0.1664 → 월 ~17.6만원,
EBS 30GB $2.4 → 월 ~3,500원 → **EC2 합 약 18만원/월**.

`.pem` 키 백업: 1Password 등 안전한 보관소에 저장. **분실 시 학생 계정
권한으로 EC2 키페어 재발급 불가**. launch 시점에 추가 SSH 공개키를
`~/.ssh/authorized_keys`에 미리 등록해 두면 복구용 백도어가 됩니다.

### 2.2 보안그룹

**`tracker-prod-sg`**:

| Type | Port | Source | 용도 |
|---|---|---|---|
| SSH | 22 | `0.0.0.0/0` | GHA 러너 IP 동적 → fail2ban으로 보강 |
| HTTP | 80 | `0.0.0.0/0` | Caddy (HTTP → HTTPS redirect) |
| HTTPS | 443 | `0.0.0.0/0` | Caddy (TLS termination + reverse proxy) |
| Custom TCP | 8080 | `0.0.0.0/0` | api Spring Boot |

> redis 6379는 docker network 내부에서만 접근하므로 호스트 포트 노출 X →
> SG 룰 불필요. 학생 SCP의 cross-SG ingress 차단을 자연스럽게 회피.

### 2.3 EC2 안전화 (Ubuntu 24.04)

EC2에 SSH 접속 후:

```bash
ssh -i <key>.pem ubuntu@<ec2-ip>

# Docker (공식 convenience script — Compose v2까지 한 번에)
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
# 로그아웃 후 재접속해야 docker 그룹 권한 적용 (또는 newgrp docker)

# fail2ban
sudo apt update
sudo apt install -y fail2ban
sudo tee /etc/fail2ban/jail.local <<'EOF'
[sshd]
enabled  = true
port     = ssh
maxretry = 3
findtime = 600
bantime  = 86400
EOF
sudo systemctl enable --now fail2ban
```

> Ubuntu 24.04 sshd는 ed25519 키만 받도록 기본 설정되어 있고 password 인증
> 비활성. fail2ban이 brute-force 99% 차단 layer로 추가됩니다.
>
> **swap 셋업 불필요** — t3.xlarge 16GB에서는 워킹셋이 메모리의 21% 수준이라
> swap 진입 가능성 사실상 0.

> **EC2 host fingerprint 검증 생략 결정** — 본 워크플로는 `appleboy/*-action`의
> `fingerprint:` 파라미터를 등록하지 않습니다. 학생 프로젝트 trade-off: MITM 방어
> + EC2 host key 변경 감지를 포기하는 대신 운영 단순화. EC2 교체 시점에는 어차피
> `EC2_HOST` secret 갱신이 필요하므로 fingerprint 별도 갱신 부담을 줄임. AWS
> 네트워크 내 직결이라 MITM 현실 위험은 0에 가까움.

### 2.4 GitHub Secrets 등록

> **2026-05-07 결정**: 본 repo가 byungju0 personal repo + 사용자가 collaborator라
> GitHub Environments 관리 권한이 owner 외에 부여 불가능합니다(GitHub 구조적 제약 —
> personal repo는 owner/collaborator 2단계 role만, admin 부여 불가). Repository
> secrets로 우회하고 deploy.yml의 `environment: production` 줄을 제거했습니다.
> Required reviewers 같은 release 게이트는 잃지만 학생 프로젝트 규모에서 수용.

**owner(byungju0)가** 다음 3개를 Repository scope에 등록:

Repo Settings → **Secrets and variables → Actions** → **Secrets** 탭 →
**New repository secret** 3번:

| Secret 이름 | 값 |
|---|---|
| `EC2_SSH_KEY` | `.pem` 파일 통째 (`-----BEGIN ... -----END ...`) |
| `EC2_USER` | `ubuntu` |
| `EC2_HOST` | tracker-prod EC2 public IP |

> **Personal repo + collaborator 한계 — 미래 옵션**: 권한 격리·release 게이트가
> 필요해지면 repo를 GitHub Organization으로 transfer 후 collaborator에게 Admin
> role 부여 → Environment 사용 가능. 학생 기간 종료 후 검토.

### 2.5 main branch protection

Repo Settings → Branches → **Add rule** (또는 기존 `main` 룰 편집):

- Branch name pattern: `main`
- ☑ Require a pull request before merging (1 approval)
- ☑ Require status checks to pass
  - Required: **`ci / aggregator`** (Story 5.2 추가, strict gate 단일 진입점)
  - 필요 시 `deploy / deploy`도 추가 (배포 실패 시 후속 PR 차단)
- ☑ Do not allow bypassing the above settings
- **Allow auto-merge: OFF** (자동 배포 흐름과 충돌)

> **순서 주의**: branch protection은 **첫 PR을 한 번 머지한 다음에** 설정하세요.
> 지금 거는 순간 첫 PR을 본인이 못 머지함 (`ci / aggregator`가 아직 한 번도
> 실행된 적 없어서 required check 후보로 안 뜸).

### 2.5.1 RDS readiness 사전 확인 (첫 배포 전 필수)

첫 배포에서 `/opt/app/IMAGE_TAG` cold-start 가드가 자동 롤백을 차단하므로, RDS가 **Available** 상태일 때만 워크플로 실행을 시작해야 한다. 시작 전 검증:

```bash
# AWS Console — RDS 인스턴스 status = "Available" + Storage status = "OK" 확인

# EC2에서 RDS 접속 검증 (psql client 필요)
sudo apt install -y postgresql-client
PGPASSWORD='<rds-master-password>' psql \
  -h <rds-endpoint> -U postgres -d postgres \
  --set=sslmode=require \
  -c "SELECT version();"
# 기대: PostgreSQL 18.3 ... 라인 출력
```

연결 실패 시 자가진단:
- `Connection refused` / `timeout` → RDS 보안그룹 inbound 5432 미허용 (EC2 SG ID source로 추가 — §2.2 RDS 보안그룹 표)
- `password authentication failed` → master password 오타
- `SSL connection required` → `--set=sslmode=require` 옵션 누락

**RDS가 Available 상태이고 EC2에서 SELECT version()이 통과해야 첫 배포 시작 가능.** 미통과 상태로 시작하면 Spring Boot startup이 60s start-period 내 Flyway 마이그레이션 실패 → api 컨테이너 unhealthy → 자동 롤백 발화 → IMAGE_TAG cold-start 가드(`exit 4`)로 deploy job fail. 수동 복구 필요.

### 2.6 EC2 디렉토리 + 시크릿 파일 + .env

EC2에 SSH 접속 후:

```bash
sudo mkdir -p /opt/app/secrets
sudo chmod 700 /opt/app/secrets
sudo chown root:root /opt/app/secrets

# 시크릿 파일 — 평문 1줄 (개행 없음)
echo -n "<openai-api-key>" | sudo tee /opt/app/secrets/openai_api_key >/dev/null
echo -n "<rds-password>"   | sudo tee /opt/app/secrets/db_password    >/dev/null
echo -n "<redis-password>" | sudo tee /opt/app/secrets/redis_password >/dev/null
# /opt/app/secrets 디렉토리 자체가 root 전용(700)이므로 호스트 일반 사용자는 접근 불가.
# 컨테이너는 appuser(UID 1001)로 실행되며 /run/secrets/*를 읽어야 하므로 파일은 read-only로 둔다.
sudo chown root:root /opt/app/secrets/*
sudo chmod 0444 /opt/app/secrets/*

# 비-시크릿 환경 (chmod 600 권장)
sudo tee /opt/app/.env <<'EOF'
# -------- PostgreSQL --------
DB_HOST=<rds-endpoint>
DB_PORT=5432
# api/application.properties는 ${DB_HOST_PORT:5432}로 읽음 — 둘 다 정의해 두면 안전
DB_HOST_PORT=5432
DB_NAME=tracker
DB_USER=tracker_user
# RDS는 parameter group `rds.force_ssl=1` 적용 시 비-SSL 거부 — require 필수
DB_SSL_MODE=require

# -------- Redis --------
# Python 서비스(crawler, detection)는 REDIS_URL 단일 변수를 사용 — compose 내부 호스트네임 `redis`.
# REDIS_PASSWORD는 /run/secrets/redis_password에서 secret-shim이 주입한다.
REDIS_URL=redis://redis:6379
# Spring Boot API는 host/port 별도 사용
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_MQ_DB=0
# detection BRPOPLPUSH 대기보다 길게 설정해야 Redis read timeout으로 consumer가 종료되지 않음
REDIS_MQ_SOCKET_TIMEOUT_SEC=40
REDIS_DEDUP_DB=1
REDIS_RATELIMIT_DB=2
REDIS_CACHE_DB=3

# -------- OpenAI LLM --------
# secret-shim이 /run/secrets/openai_api_key를 OPENAI_API_KEY env로 노출한다.
LLM_MODEL=gpt-4o
LLM_DAILY_COST_CAP_USD=5
LLM_SEND_IMAGES=false
LLM_SPLIT_TEXT_IMAGE=false
LLM_TIMEOUT_SEC=30
LLM_RATE_LIMIT_CAPACITY=60
LLM_RATE_LIMIT_REFILL_PER_SEC=1
LLM_RATE_LIMIT_MAX_WAIT_SEC=120

# -------- Notifications --------
# 운영에서는 32자 이상 난수 사용. 예: openssl rand -base64 32
NOTIFICATION_ENCRYPTION_KEY=<notification-encryption-key>

# -------- AWS --------
AWS_REGION=us-east-1
S3_BUCKET_NAME=<bucket-name>
# S3 업로드 활성 여부 (crawler/src/storage.py). 학생 IAM이 Crawler EC2에 IAM Role
# attach 불가능 → 첫 배포에는 false 권장, IAM Role 확보 후 true로 변경
ENABLE_S3_UPLOAD=false

# -------- Crawler 운영 profile --------
# EC2 1대 + RDS 1대 기준. listing 후보 폭은 확보하고 detail fetch는 priority budget으로 제어.
CRAWL_INTERVAL_MINUTES=60
MAX_POSTS_PER_BOARD=30
CRAWL_PRIORITY_BUDGET_ENABLED=true
CRAWL_P3_DEFAULT_CAP_PER_BOARD=1
CRAWL_P3_MIXED_CAP_PER_BOARD=5
CRAWL_P3_52POJIE_CAP_PER_BOARD=1
CRAWL_DETAIL_FETCH_CONCURRENCY=3
CRAWL_DETAIL_SOURCE_CONCURRENCY=dcard=1,dcard_online=1,52pojie=1
CRAWL_DETAIL_FETCH_STAGGER_SECONDS=0.25
# Dcard/52pojie 차단은 reason 기록 후 통과. retry/cooldown은 운영 기본 off.
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES=0
CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS=0
CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS=0
CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS=0
INTER_SITE_DELAY_SECONDS=15
INTER_BOARD_DELAY_SECONDS=3

LOG_LEVEL=INFO
EOF
sudo chmod 600 /opt/app/.env
```

> `SERVICE_NAME`은 compose 파일에서 서비스별로 주입되므로 `.env`에 두지 않습니다.
>
> ⚠️ **위 env 템플릿 누락 시 첫 배포 실패 패턴**:
> - `REDIS_URL` 누락 또는 Redis password 누락 → crawler/detection가 Redis 인증 실패. healthcheck 실패 → 자동 롤백.
> - `/opt/app/secrets/*` 누락 또는 `0400 root:root`처럼 appuser가 읽을 수 없는 mode → secret-shim이 해당 secret을 건너뜀. healthcheck 실패 → 자동 롤백.
> - `DB_HOST_PORT` 누락은 default `:5432`로 rescue됨 (subtle bug, 표준 포트만 안전).

### 2.7 기존 EC2 VARCO → OpenAI 전환

이미 VARCO 기준으로 `/opt/app`이 준비된 EC2라면, 첫 OpenAI 배포 전에 호스트
상태를 새 compose와 맞춘다.

```bash
# 1) 새 OpenAI secret 작성 (개행 없는 1줄)
echo -n "<openai-api-key>" | sudo tee /opt/app/secrets/openai_api_key >/dev/null
sudo chown root:root /opt/app/secrets/openai_api_key
sudo chmod 0444 /opt/app/secrets/openai_api_key

# 2) /opt/app/.env에서 VARCO_* 항목 제거 후 LLM_* 항목 추가/확인
sudo nano /opt/app/.env

# 3) 더 이상 쓰지 않는 VARCO secret은 즉시 삭제하지 말고 백업명으로 격리
if [ -f /opt/app/secrets/varco_api_key ]; then
  sudo mv /opt/app/secrets/varco_api_key \
    "/opt/app/secrets/varco_api_key.bak.$(date -u +%Y%m%d%H%M%S)"
fi

# 4) GitHub Actions deploy workflow_dispatch 실행
#    deploy.yml이 새 compose.prod.yml을 /opt/app/compose.prod.yml로 업로드하고
#    detection 컨테이너에 openai_api_key + db_password secret을 마운트한다.
```

`crawler`는 더 이상 OpenAI/DB secret을 마운트하지 않는다. `detection`만
`openai_api_key`, `db_password`를 사용하고, `api`는 `db_password`만 사용한다.

---

## 3. 시크릿 추가 / 회전

### 새 시크릿 추가
1. EC2: `/opt/app/secrets/<name>` 작성 (chmod 0444, owner root:root).
2. `infra/compose.prod.yml`의 `secrets:` 블록 + 사용 service의 `secrets:` 리스트에 추가.
3. main 머지 → 자동 배포.
4. shim이 `<NAME>` 환경변수로 자동 노출 (대문자 변환, dash/dot → underscore).

### OpenAI API key 회전
1. EC2: `/opt/app/secrets/openai_api_key`만 새 값으로 갱신.
2. `docker compose -f /opt/app/compose.prod.yml restart detection`.
3. (코드 변경 없음 → workflow_dispatch 불필요)

### DB 비밀번호 회전
RDS 콘솔에서 비번 변경 후 동일 절차.

---

## 4. 자동 롤백 동작

`deploy.yml`의 deploy 잡 마지막 단계가 180초간 healthcheck를 폴링합니다.

| 결과 | 동작 |
|---|---|
| 6개 서비스 모두 `healthy` | `/opt/app/IMAGE_TAG`에 새 SHA 기록 → `exit 0` |
| 180초 내 한 개라도 실패 | 직전 `IMAGE_TAG` 파일 값(이전 성공 SHA)으로 `IMAGE_TAG` env 재설정 → `compose up -d` 재기동 → `exit 1` (GHA UI 실패 표시) |

**첫 배포 cold-start 주의**: `/opt/app/IMAGE_TAG` 파일이 없는 상태에서 첫 배포가
healthcheck 실패하면 fallback 태그가 `latest`로 떨어지는데, 이미 `latest`도 동일한
실패 이미지일 수 있습니다. 첫 배포 시에는 healthcheck 동작을 별도로 검증하고
필요하면 수동 롤백 (`workflow_dispatch` + `rollback_to: <known-good-sha>`) 사용.

---

## 5. 비상 수동 트리거

GitHub UI → Actions → `deploy` 워크플로 → **Run workflow** 버튼:

| 입력 | 동작 |
|---|---|
| (비어 있음) | 현재 main HEAD를 다시 빌드 + 배포 |
| `rollback_to: <sha>` | 해당 git SHA의 이미지(GHCR에 이미 push된)로만 재배포 — build-push 잡은 그래도 실행되지만 deploy 잡이 입력 SHA를 우선 사용 |

> **주의**: `rollback_to` 모드는 build-push에서 새 이미지를 만들지 않고 기존 GHCR
> 태그를 사용합니다. 따라서 GHCR retention 정책(기본 무기한)에 따라 오래된 SHA는
> 사라질 수 있습니다 — 운영 시작 후 retention 정책을 한번 확인하세요.

---

## 6. 보안 트레이드오프

### 6.1 22번 인바운드 0.0.0.0/0

- **이유**: 학생 IAM 사용자가 AWS API 자격증명 통로를 모두 봉인당해 GHA 러너 IP에
  맞춰 SG 룰을 동적 갱신할 수 없습니다. 외부 SaaS(Cloudflare Tunnel / Tailscale)
  가입은 사용자 정책상 회피합니다 (memory `feedback_no_external_services.md`).
- **Defense-in-depth 3 layer** (host fingerprint 검증은 운영 단순화 위해 생략):
  1. **ed25519 키 + password 비활성** (EC2 sshd 기본).
  2. **fail2ban 3 fail / 10분 / 24h ban** — brute-force 99% 차단.
  3. **GH Secret + Repository scope** — `.pem`이 GitHub Actions 실행 시점에만
     단기적으로 컨테이너 메모리에 노출.

### 6.2 단일 `.pem` 키

관리자 접속용과 GHA 자동 배포용을 분리하지 않았습니다. 분리 시 보안 폭발 반경
축소 효과가 있으나 학생 프로젝트 규모에서 키 관리 부담이 더 큽니다. `.pem` 노출
시 즉시:
1. EC2 `~/.ssh/authorized_keys`에서 해당 공개키 제거 (별도 admin 키로 접속).
2. GH Secret `EC2_SSH_KEY` 신규 키로 교체.

### 6.3 단일 EC2 합반 결정과 메모리 방어 전략

**결정 흐름** (2026-05-07):

1차) Story 5.2 PIVOT 박스가 "단일 EC2 docker compose"로 적은 사양 그대로 작성.

2차) t3.medium 4GB 한도에 5컨테이너 합반 시 OOM 위험(1.7~3.3GB 워킹셋) 분석 후
**2대 분리(crawler/app)로 보강**. `app-sg`에 redis 6379 source = `crawler-sg` 한정
ingress 룰을 추가해야 했음.

3차) 학생 IAM SCP가 **cross-SG ingress 룰 추가를 차단**(메시지: `explicit deny in
identity-based policy: ControlOnlyOwnResources`). IP /32 우회도 동일 패턴으로
막힐 가능성 + EIP 발급 권한 불명. → **단일 EC2 회귀**. 대신 학생 SCP가
허용하는 인스턴스 4종(t3.{nano,micro,small,medium}, t3.xlarge) 중 가장 큰
**t3.xlarge (16GB)** 로 상향 — 메모리 OOM 위험 사실상 제거.

**왜 t3.xlarge인가**:

| 항목 | t3.medium (4GB) + swap | t3.xlarge (16GB) |
|---|---|---|
| 5 컨테이너 워킹셋 1.7~3.3GB | 메모리 42~83% 점유 → 위험 | 메모리 11~21% 점유 → 한참 여유 |
| Playwright Chromium 동시 세션 | `max_session_permit=2~3` 한계 | 4~8 세션도 가능 |
| JVM heap | 576MB | 1.5~2GB |
| swap 셋업 | 필수 | 불필요 |
| OOM-killer | 항상 모니터링 | 사실상 무관 |
| 월 EC2 비용 (us-east-1, 환율 1452원) | ~4.8만원 | **~18만원** |

학생 budget 30만원/월의 70%이지만, 발표 데모 안정성 + `crawler_ram_priority`
메모리 정합성을 사는 것이 합리적이라 판단.

**docker compose mem_limit 정책**:

16GB 환경에서 mem_limit는 hard cap이 아니라 한 컨테이너 폭주가 다른 컨테이너를
굶기지 않게 하는 가벼운 격리 hint:

| 서비스 | mem_limit | mem_reservation |
|---|---|---|
| redis | (없음, redis maxmemory 1GB) | - |
| crawler | 4 GB | 1 GB |
| detection | 1 GB | 256 MB |
| api | 2 GB | 768 MB |
| dashboard | 256 MB | - |
| caddy | 128 MB | - |
| **hard cap 합** | **~7.4 GB** | (16GB의 46%) |

**향후 확장**:

- 학생 기간 종료 후 개인 계정으로 옮기면 IAM Role + cross-SG ingress 자유 →
  2대 분리 옵션 다시 가능 (코드는 git history에 분리 사양 보존: `infra/compose.crawler.yml` / `infra/compose.app.yml`).
- 실측 후 RAM 8GB로 충분하면 t3.large 옵션 학생 SCP 풀린 시점에 다운사이즈로 비용 절감.

---

## 7. 트러블슈팅

| 증상 | 진단 / 조치 |
|---|---|
| `permission denied (publickey)` | `EC2_SSH_KEY` BEGIN/END 라인 포함 통째 등록됐는지 확인. 줄바꿈 보존 필수. |
| `command not found: docker` | EC2에 `docker compose` plugin 설치 확인. SSH script가 `command -v docker`로 경로 자동 resolve. |
| GHCR 401 | workflow `permissions: { packages: write }` 누락 점검. |
| Healthcheck 항상 실패 | `docker compose -f /opt/app/compose.prod.yml ps` + `docker logs <service>` 직접 확인. |
| 자동 롤백 무한 루프 | `IMAGE_TAG` 파일을 known-good SHA로 직접 갱신 후 `workflow_dispatch` 재트리거. |

---

## 8. 참고

- [Source: `.github/workflows/deploy.yml`](../.github/workflows/deploy.yml) — 운영 자동 배포
- [Source: `.github/workflows/deploy-demo.yml`](../.github/workflows/deploy-demo.yml) — frontend-only 데모 배포(PR #42). OpenAI/RDS 셋업 전 화면만 시연할 때 `workflow_dispatch`로 수동 트리거. `infra/compose.demo.yml` + `infra/Caddyfile`(Let's Encrypt ACME)로 dashboard + Caddy 2컨테이너 토폴로지. 운영 `deploy.yml`과 EC2 호스트를 공유하지만 GHCR 태그(`:demo-*` 분리)와 compose 파일이 분리돼 충돌하지 않음 — 동시 운영은 피하고 배포 전환 시 `docker compose -f compose.demo.yml down` 선행.
- [Source: `.github/workflows/ci.yml`](../.github/workflows/ci.yml)
- [Source: `infra/compose.prod.yml`](../infra/compose.prod.yml)
- [Source: `infra/compose.demo.yml`](../infra/compose.demo.yml)
- [Source: `infra/Caddyfile`](../infra/Caddyfile)
- [Source: `infra/docker-secret-shim.sh`](../infra/docker-secret-shim.sh)
- [`docs/ci-setup.md`](./ci-setup.md) — Story 1.5 deferred 항목이 본 스토리에서 어떻게 해결됐는지
- [`docs/adr/0001-secret-management-strategy.md`](./adr/0001-secret-management-strategy.md) — 시크릿 관리 결정(Docker secrets + EC2 SSH 수동 작성)
- Story 5.2 spec — [`_bmad-output/implementation-artifacts/5-2-github-actions-완전-통합-ci-cd-파이프라인.md`](../_bmad-output/implementation-artifacts/5-2-github-actions-완전-통합-ci-cd-파이프라인.md)
