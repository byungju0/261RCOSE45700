"""PostgreSQL 연결 설정 (Story 3-4).

`infra/.env`의 DB_HOST/PORT/NAME/USER/PASSWORD/SSL_MODE를 읽어 connection pool 생성.
psycopg3 ConnectionPool을 단일 모듈 글로벌로 관리 — detection은 single-worker MVP라 OK.
multi-worker로 확장 시 fork 직후 자식 프로세스에서 pool을 새로 생성해야 한다.
"""

from __future__ import annotations

import os

from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool

_pool: ConnectionPool | None = None


def _build_conninfo() -> str:
    """`infra/.env`의 값으로 conninfo 문자열 구성.

    `make_conninfo`가 비번에 공백/`=`/특수문자가 있어도 안전하게 quote/escape.
    """
    password = os.environ.get("DB_PASSWORD", "")
    if not password:
        raise RuntimeError("DB_PASSWORD 환경변수 미설정. infra/.env 확인 필요.")
    return make_conninfo(
        host=os.environ.get("DB_HOST", "localhost"),
        port=os.environ.get("DB_PORT", "5432"),
        dbname=os.environ.get("DB_NAME", "tracker"),
        user=os.environ.get("DB_USER", "tracker_user"),
        password=password,
        sslmode=os.environ.get("DB_SSL_MODE", "disable"),
        client_encoding="utf8",  # psycopg3 str→bytes 인코딩 명시 (RDS default가 SQL_ASCII일 때 대비)
    )


def get_pool() -> ConnectionPool:
    """프로세스 전역 connection pool. 첫 호출 시 lazy init."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            conninfo=_build_conninfo(),
            min_size=int(os.environ.get("DB_POOL_MIN_SIZE", "1")),
            max_size=int(os.environ.get("DB_POOL_MAX_SIZE", "5")),
            open=True,
        )
    return _pool


def close_pool() -> None:
    """테스트/종료 시 명시적 close."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
