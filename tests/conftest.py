"""Shared fixtures.

The domain layer is tested without a server and without a database: the only
thing the pantry needs from Postgres is rows, and anything more would be
testing psycopg rather than this project.
"""

import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.domain.pantry import PantryRepository, PantrySheet  # noqa: E402


def spreadsheet() -> pathlib.Path:
    """The seed file, wherever it is mounted.

    On a developer machine it sits in the repository; inside the image it is
    mounted read-only. Honouring PANTRY_XLSX runs the same tests in both places
    against the same file.
    """
    configured = os.environ.get('PANTRY_XLSX')
    if configured and pathlib.Path(configured).exists():
        return pathlib.Path(configured)
    return pathlib.Path(__file__).resolve().parents[1] / 'data' / 'despensa_dona_maria.xlsx'


class FakeDatabase:
    """Postgres replaced by the rows a seed would have written."""

    def __init__(self, rows):
        self.rows = rows
        self.package_sizes: list[dict] = []
        # Append-only, exactly like the table: a test that lets a dish rewrite
        # the stock row would not be testing what production does.
        self.usage: list[dict] = []

    def query(self, sql, params=()):
        if 'pantry_items' in sql:
            return list(self.rows)
        if 'package_sizes' in sql:
            return list(self.package_sizes)
        if 'pantry_usage' in sql and 'sum(quantity)' in sql:
            totals: dict[str, float] = {}
            for row in self.usage:
                totals[row['ingredient_key']] = (
                    totals.get(row['ingredient_key'], 0.0) + float(row['quantity'])
                )
            return [{'ingredient_key': k, 'spent': v} for k, v in totals.items()]
        if 'pantry_usage' in sql:
            key = (params or {}).get('key') if isinstance(params, dict) else None
            return [row for row in self.usage if row['ingredient_key'] == key]
        return []

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql, params=()):
        pass

    def connect(self):
        return _FakeConnection(self)


class _FakeConnection:
    """Just enough of a psycopg connection for the pantry's writes."""

    def __init__(self, db):
        self.db = db
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self

    def executemany(self, sql, rows):
        if 'pantry_usage' in sql:
            self.db.usage.extend(dict(row) for row in rows)

    def execute(self, sql, params=()):
        if 'DELETE FROM pantry_usage' in sql:
            dish = (params or {}).get('dish')
            before = len(self.db.usage)
            self.db.usage = [r for r in self.db.usage if r['dish'] != dish]
            self.rowcount = before - len(self.db.usage)
        return self

    def commit(self):
        pass


@pytest.fixture(scope='session')
def sheet_rows() -> list[dict]:
    """Her real spreadsheet, joined. Fixtures that lie are worse than none."""
    return PantrySheet(spreadsheet()).rows()


@pytest.fixture
def database(sheet_rows) -> FakeDatabase:
    return FakeDatabase(sheet_rows)


@pytest.fixture
def pantry(database) -> PantryRepository:
    """The repository over exactly what the seed would have written."""
    return PantryRepository(database)


async def capture_her_message(built, text: str) -> None:
    """Put her words on the record the way the runtime does.

    Not through `chat_save_turn`: a turn the agent typed is exactly what the
    server refuses to treat as evidence of what she said. The tests have to use
    the same door the hook script uses, or they test a path nothing takes.
    """
    import httpx

    transport = httpx.ASGITransport(app=built.root.http_app())
    async with httpx.AsyncClient(transport=transport, base_url='http://mcp') as wire:
        await wire.post(
            '/hooks/her-message',
            json={'session_id': 'testes', 'user_message': text},
        )
