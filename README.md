# Tracker

Tracker는 한·중·대만 게임 커뮤니티에 올라오는 불법 프로그램 유포 게시글을 자동으로 찾아 NC AI 게임 보안 담당자에게 5분 SLA 안에 띄워주는 사내 운영 도구입니다.

- **자동 수집** — Playwright 기반 크롤러가 8개 사이트를 1시간 주기로 돕니다.
- **다국어 AI 탐지** — VARCO Translation·LLM 파이프라인이 중국어·번체를 한국어로 번역하고 불법 여부를 분류합니다.
- **신뢰도 필터** — 신뢰도 0.70 이상 후보만 React 대시보드에 노출합니다. 담당자는 원본 URL로 바로 점프해 신고를 진행합니다.

[![CI](https://github.com/byungju0/261RCOSE45700/actions/workflows/ci.yml/badge.svg)](https://github.com/byungju0/261RCOSE45700/actions/workflows/ci.yml)
[![Deploy](https://github.com/byungju0/261RCOSE45700/actions/workflows/deploy.yml/badge.svg)](https://github.com/byungju0/261RCOSE45700/actions/workflows/deploy.yml)

[Wiki](https://github.com/byungju0/261RCOSE45700/wiki) ·
[Architecture](https://github.com/byungju0/261RCOSE45700/wiki/Architecture-Overview) ·
[Getting Started](https://github.com/byungju0/261RCOSE45700/wiki/Getting-Started) ·
[Sprint Status](https://github.com/byungju0/261RCOSE45700/wiki/Sprint-Status)

## 시작하기

Python 3.11+, Java 21 LTS, Node.js 22 LTS, Docker가 필요합니다. Java가 없어도 `./gradlew build` 첫 실행 때 Foojay가 받아옵니다. Windows라면 `bin/` 대신 `Scripts\`, `./gradlew` 대신 `gradlew.bat`을 사용하세요.

```bash
git clone https://github.com/byungju0/261RCOSE45700.git
cd 261RCOSE45700

# Redis + PostgreSQL
cp infra/.env.example infra/.env
docker compose -f infra/docker-compose.yml up -d

# 서브시스템 셋업
python3 -m venv crawler/.venv && crawler/.venv/bin/pip install -r crawler/requirements.txt
crawler/.venv/bin/playwright install chromium
python3 -m venv detection/.venv && detection/.venv/bin/pip install -r detection/requirements.txt
cp detection/.env.example detection/.env
cd api && ./gradlew build && cd ..
cd dashboard && corepack enable && pnpm install && cd ..
```

화면만 빠르게 확인하려면 `cd dashboard && pnpm dev`로 충분합니다. `VITE_API_BASE_URL`이 비어 있으면 MSW v2 mock이 백엔드 응답을 흉내내어, 백엔드 없이도 4개 페이지가 그대로 뜹니다.

자세한 셋업 절차, 환경변수, 흔한 문제는 [Getting Started](https://github.com/byungju0/261RCOSE45700/wiki/Getting-Started)에 정리돼 있습니다.

## 저장소 구성

```
crawler/      Python · crawl4ai 크롤링 + APScheduler + S3 아카이브
detection/    Python · Redis 컨슈머 + VARCO Translation/LLM + 토큰 버킷 + DLQ
api/          Java Spring Boot 3.5 · REST 4종 + Flyway
dashboard/    React 19 + Vite 8 · TanStack Query v5 · MSW v2 mock
shared/       Python 공유 모듈 (correlation_id, CrawlEvent, VarcoInterface)
infra/        docker-compose + Caddy + Grafana/Prometheus
docs/         ADR + 배포 runbook
_bmad-output/ PRD · architecture · UX spec · 스토리 · 회고
```

각 서브시스템 내부 구조는 [Wiki](https://github.com/byungju0/261RCOSE45700/wiki) 서브시스템 페이지에서 더 자세히 다룹니다.

## 검증

```bash
crawler/.venv/bin/python -m pytest crawler/tests/unit -q
detection/.venv/bin/python -m pytest detection/tests/unit -q
cd api && ./gradlew build && cd ..
cd dashboard && pnpm build && pnpm test && cd ..
```

E2E는 Playwright로 데스크톱과 Pixel 7 모바일 viewport 두 프로젝트가 분리돼 있습니다.

```bash
cd dashboard && pnpm exec playwright install --with-deps && pnpm e2e
```

## 배포

main 브랜치 머지가 GitHub Actions `deploy.yml`을 트리거합니다. GHCR에 이미지를 빌드해 push하고, EC2에 SSH로 직결해서 `docker compose pull` + 60초 healthcheck + 자동 롤백까지 한 번에 처리합니다. VARCO/RDS 셋업이 끝나기 전 화면만 시연할 때는 `deploy-demo.yml`을 `workflow_dispatch`로 수동 트리거하면 dashboard만 mock 빌드로 띄울 수 있습니다 (`tracker.o-r.kr`, Let's Encrypt 자동 발급).

자세한 사양은 [CI/CD Pipeline](https://github.com/byungju0/261RCOSE45700/wiki/CI-CD-Pipeline), 운영 절차는 [docs/deployment.md](docs/deployment.md), 시크릿 결정은 [ADR 0001](docs/adr/0001-secret-management-strategy.md)에 있습니다.

## 프로젝트 상태

5개 Epic 중 1, 2는 완료, 3·4·5는 진행 중입니다. 데스크톱 대시보드와 모바일 지원이 머지됐고, 운영 자동 배포 파이프라인도 들어왔습니다. VARCO 실 API 명세가 확정되면 detection이 mockup에서 실 호출로 전환됩니다.

스토리 단위 현황은 [Sprint Status](https://github.com/byungju0/261RCOSE45700/wiki/Sprint-Status), 원본 SoT는 [`sprint-status.yaml`](_bmad-output/implementation-artifacts/sprint-status.yaml)에 있습니다.
