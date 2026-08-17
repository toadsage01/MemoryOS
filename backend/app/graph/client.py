"""Neo4j driver wrapper.

A thin layer over the official `neo4j` driver — nothing fancy:
- one driver per process (lazy-init singleton)
- convenience `run()` / `run_read()` / `run_write()` helpers
- `ensure_schema()` applied on first connect

No async driver — the official `neo4j` async API is still maturing; the
sync driver is fine at solo-user throughput. FastAPI calls are wrapped in
`BackgroundTasks` for the ingest pipeline so the request still returns fast.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator

from neo4j import Driver, GraphDatabase, ManagedTransaction

from ..config import get_settings
from . import schema

log = logging.getLogger(__name__)

_driver: Driver | None = None


def get_driver() -> Driver:
    """Lazy-init the global driver. Singleton — one connection pool per process."""
    global _driver
    if _driver is None:
        s = get_settings()
        log.info("connecting to neo4j at %s (user=%s)", s.neo4j_uri, s.neo4j_user)
        _driver = GraphDatabase.driver(
            s.neo4j_uri,
            auth=(s.neo4j_user, s.neo4j_password),
        )
        # Verify connectivity eagerly so the user sees a clear error at boot
        # rather than on the first request.
        _driver.verify_connectivity()
        ensure_schema(_driver)
    return _driver


def ensure_schema(driver: Driver) -> None:
    """Apply all constraints/indexes from schema.py. Idempotent."""
    with driver.session() as sess:
        for stmt in schema.all_statements():
            sess.run(stmt).consume()


@contextmanager
def session() -> Iterator[Any]:
    """Context manager yielding a session. Use for one-off reads/writes."""
    driver = get_driver()
    with driver.session() as s:
        yield s


def run_read(query: str, params: dict | None = None) -> list[dict]:
    """Execute a read query, return list of dict records."""
    with session() as s:
        result = s.run(query, parameters=params or {})
        return [r.data() for r in result]


def run_write(query: str, params: dict | None = None) -> list[dict]:
    """Execute a write query inside a managed transaction."""
    def _txfn(tx: ManagedTransaction) -> list[dict]:
        result = tx.run(query, parameters=params or {})
        return [r.data() for r in result]

    with session() as s:
        return list(s.execute_write(_txfn))


def close() -> None:
    """Close the driver. Call on app shutdown."""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
