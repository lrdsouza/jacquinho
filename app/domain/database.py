'''Postgres: everything that is a record about Dona Maria.

The split across the two stores is by lifetime, not by convenience. Redis holds
the conversation window, which is hot, rewritten constantly and worthless once
summarised. Postgres holds what the conversation decided: what she owns, what
she ruled out and why, what she committed to buy, what went on the menu. Those
outlive any session, are asked relational questions, and must never be lost to
an eviction policy.
'''

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row


class DatabaseUnavailable(RuntimeError):
    '''Raised when Postgres cannot be reached.'''


SCHEMA = '''
-- ---------------------------------------------------------------- recipes
CREATE TABLE IF NOT EXISTS recipes (
    slug            TEXT PRIMARY KEY,
    dish            TEXT NOT NULL,
    source_url      TEXT,
    source_title    TEXT,
    ingredients     JSONB NOT NULL DEFAULT '[]'::jsonb,
    pantry_coverage NUMERIC(4,3),
    notes           TEXT DEFAULT '',
    accepted        BOOLEAN NOT NULL DEFAULT FALSE,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recipe_requirements (
    recipe_slug TEXT NOT NULL REFERENCES recipes(slug) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('equipment', 'technique')),
    item        TEXT NOT NULL,
    PRIMARY KEY (recipe_slug, kind, item)
);

CREATE TABLE IF NOT EXISTS recipe_blocks (
    id             BIGSERIAL PRIMARY KEY,
    recipe_slug    TEXT NOT NULL REFERENCES recipes(slug) ON DELETE CASCADE,
    reason         TEXT NOT NULL,
    blocking_item  TEXT,
    note           TEXT DEFAULT '',
    conditional    BOOLEAN NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    lifted_at      TIMESTAMPTZ,
    lifted_because TEXT
);

-- ------------------------------------------------------------- her kitchen
CREATE TABLE IF NOT EXISTS kitchen_capabilities (
    category   TEXT NOT NULL CHECK (category IN ('equipment','techniques','constraints')),
    item       TEXT NOT NULL,
    state      TEXT NOT NULL CHECK (state IN ('confirmed_yes','confirmed_no','unknown')),
    note       TEXT DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (category, item)
);

CREATE TABLE IF NOT EXISTS elicitation_items (
    key            TEXT PRIMARY KEY,
    category       TEXT NOT NULL,
    question       TEXT NOT NULL,
    why_it_matters TEXT NOT NULL,
    priority       SMALLINT NOT NULL DEFAULT 2,
    triggers       JSONB NOT NULL DEFAULT '[]'::jsonb
);

-- -------------------------------------------------------------- her money
CREATE TABLE IF NOT EXISTS budget_entries (
    entry_id     TEXT PRIMARY KEY,
    dish         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    amount       NUMERIC(10,2) NOT NULL CHECK (amount > 0),
    committed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------ her pantry
-- Seeded once from the spreadsheet; the application reads from here. The raw
-- sheet values are kept alongside the derived unit cost so the derivation can
-- be re-run and audited without going back to the file.
CREATE TABLE IF NOT EXISTS pantry_items (
    ingredient_key   TEXT PRIMARY KEY,
    ingredient       TEXT NOT NULL,
    stock_quantity   NUMERIC NOT NULL,
    stock_unit       TEXT NOT NULL,
    bought_quantity  NUMERIC NOT NULL CHECK (bought_quantity > 0),
    bought_unit      TEXT NOT NULL,
    price_paid       NUMERIC(10,2) NOT NULL CHECK (price_paid >= 0),
    seeded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS package_sizes (
    ingredient_key TEXT PRIMARY KEY,
    quantity       NUMERIC NOT NULL CHECK (quantity > 0),
    unit           TEXT NOT NULL,
    recorded_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------ her cardapio
CREATE TABLE IF NOT EXISTS dish_categories (
    key             TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    search_terms    JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_groups JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS dish_feedback (
    slug          TEXT PRIMARY KEY,
    dish          TEXT NOT NULL,
    likes_cooking BOOLEAN NOT NULL,
    comment       TEXT DEFAULT '',
    impediments   JSONB NOT NULL DEFAULT '[]'::jsonb,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS menu_items (
    slug            TEXT PRIMARY KEY,
    dish            TEXT NOT NULL,
    category        TEXT NOT NULL,
    cmv             NUMERIC(10,2) NOT NULL,
    price           NUMERIC(10,2) NOT NULL,
    she_receives    NUMERIC(10,2) NOT NULL,
    profit          NUMERIC(10,2) NOT NULL,
    confidence_band TEXT NOT NULL,
    notes           TEXT DEFAULT '',
    added_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The recipe of a dish is settled once, not renegotiated on every costing. The
-- agent used to pass a slightly different ingredient list each time it costed
-- the same dish, so the CMV wandered - 9,90 then 8,18 then 7,15 - with nothing
-- in the system able to say which one was the dish. Locking the lines makes the
-- cost a property of the dish instead of a property of the last call.
CREATE TABLE IF NOT EXISTS recipe_costing (
    slug            TEXT PRIMARY KEY,
    dish            TEXT NOT NULL,
    lines           JSONB NOT NULL,
    portions        INTEGER NOT NULL DEFAULT 1,
    cmv             NUMERIC(10,2),
    locked_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    reopened_at     TIMESTAMPTZ,
    reopened_because TEXT
);

CREATE TABLE IF NOT EXISTS answer_assessments (
    id                  BIGSERIAL PRIMARY KEY,
    dish                TEXT NOT NULL,
    draft_answer        TEXT NOT NULL,
    mode                TEXT NOT NULL,
    claim               TEXT NOT NULL DEFAULT 'price',
    deterministic_score NUMERIC(4,3) NOT NULL,
    judge_score         NUMERIC(4,3),
    final_score         NUMERIC(4,3) NOT NULL,
    band                TEXT NOT NULL,
    badge               TEXT NOT NULL,
    blocking_issues     JSONB NOT NULL DEFAULT '[]'::jsonb,
    signals             JSONB NOT NULL DEFAULT '[]'::jsonb,
    assessed_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Confidence moved from 0..100 to 0..1. An existing table keeps the old column
-- type, which would silently round 0.87 to 0.9, so widen it once. The old rows
-- are on the other scale and meaningless either way.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'answer_assessments'
           AND column_name = 'final_score'
           AND numeric_scale <> 3
    ) THEN
        -- Drop the old-scale rows FIRST: a 100.0 does not fit NUMERIC(4,3),
        -- so altering before deleting fails and takes the schema with it.
        DELETE FROM answer_assessments WHERE final_score > 1;
        ALTER TABLE answer_assessments
            ADD COLUMN IF NOT EXISTS claim TEXT NOT NULL DEFAULT 'price',
            ALTER COLUMN deterministic_score TYPE NUMERIC(4,3),
            ALTER COLUMN judge_score         TYPE NUMERIC(4,3),
            ALTER COLUMN final_score         TYPE NUMERIC(4,3);
    END IF;
END $$;

-- The query behind every 'what else is there': only blocks still in force
-- matter, so the partial index covers exactly those rows and stays small no
-- matter how long the block history grows.
CREATE INDEX IF NOT EXISTS recipe_blocks_active
    ON recipe_blocks (recipe_slug) WHERE lifted_at IS NULL;
CREATE INDEX IF NOT EXISTS recipe_blocks_pending_item
    ON recipe_blocks (blocking_item) WHERE lifted_at IS NULL AND conditional;
CREATE INDEX IF NOT EXISTS recipe_requirements_item
    ON recipe_requirements (item);
'''


class Database:
    '''One connection factory, one schema, shared by every record store.'''

    def __init__(self, dsn: str, connect_timeout: int = 10):
        self.dsn = dsn
        self.connect_timeout = connect_timeout
        self._ready = False

    def connect(self):
        try:
            return psycopg.connect(
                self.dsn, row_factory=dict_row, connect_timeout=self.connect_timeout
            )
        except psycopg.Error as error:
            raise DatabaseUnavailable(f'postgres unreachable: {error}') from error

    def ensure_schema(self) -> None:
        '''Create anything missing. Safe to call on every request.'''
        if self._ready:
            return
        with self.connect() as conn:
            conn.execute(SCHEMA)
            conn.commit()
        self._ready = True

    def query(self, sql: str, params: tuple = ()) -> list[dict]:
        self.ensure_schema()
        with self.connect() as conn:
            return conn.execute(sql, params).fetchall()

    def one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.ensure_schema()
        with self.connect() as conn:
            conn.execute(sql, params)
            conn.commit()

    def returning(self, sql: str, params: tuple = ()) -> list[dict]:
        self.ensure_schema()
        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            conn.commit()
            return rows
