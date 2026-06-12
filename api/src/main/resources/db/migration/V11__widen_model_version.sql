-- Story 3-7 후속: agentic model_version 컬럼을 TEXT로 확장 (2026-06-12)
--
-- 배경: AgentOrchestrator.model_version은 "agentic:v1:{model}:{release}" 형식.
-- 현재 OpenAI/Anthropic 모델명은 최대 ~58자지만 Bedrock ARN 형식
-- (arn:aws:bedrock:...) 은 100자를 초과한다.
-- PostgreSQL은 VARCHAR 초과 시 ERROR로 트랜잭션 전체를 실패시키므로
-- 상한 없는 TEXT로 전환한다. TEXT와 VARCHAR는 PostgreSQL 내부 표현이 동일해
-- 성능 차이 없음.
--
-- 멱등: TEXT로 이미 변경된 상태에서 재실행해도 no-op.
ALTER TABLE detections
    ALTER COLUMN model_version TYPE TEXT;
