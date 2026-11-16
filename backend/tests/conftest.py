import os
import uuid

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo


@pytest.fixture(autouse=True)
def disable_external_tracing(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "")


@pytest.fixture
def test_db_url():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set TEST_DATABASE_URL to a disposable PostgreSQL database, or use compose.test.yaml.")
    schema = "test_" + uuid.uuid4().hex
    with psycopg.connect(url, autocommit=True) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            yield make_conninfo(url, options=f"-c search_path={schema}")
        finally:
            # Only this fixture's freshly generated schema is removed.
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
