"""add food item lookup indexes

Revision ID: e4f7b0d25c63
Revises: d3e6a9c14b52
Create Date: 2026-08-22

CONCURRENTLY IS REQUIRED EVEN THOUGH BOTH COLUMNS ARE STILL EMPTY.
gtin14 is all NULL and name_normalized all '' until the Checkpoint 3 script
populates them -- but building an index still scans all 578,773 heap rows. An
ordinary CREATE INDEX would hold ACCESS EXCLUSIVE on food_items for the whole
of that scan, and food search would be down for its duration.

THE FAILURE MODE TO KNOW ABOUT
CREATE INDEX CONCURRENTLY cannot run inside a transaction, which is what the
autocommit_block below is for -- Alembic wraps every migration in one by
default. If a concurrent build is cancelled or fails partway, it leaves behind
an INVALID index: it exists, it is maintained on every write, and the planner
never uses it. Nothing errors; the index is simply dead weight, and a naive
re-run would then fail on the duplicate name.

    -- Detect
    SELECT indexrelid::regclass AS index, indrelid::regclass AS table
    FROM pg_index WHERE NOT indisvalid;

    -- Remove, then re-run this migration
    DROP INDEX CONCURRENTLY IF EXISTS ix_food_gtin14;
    DROP INDEX CONCURRENTLY IF EXISTS ix_food_name_normalized;

if_not_exists below is what makes the retry idempotent, and
test_concurrent_indexes_are_valid asserts indisvalid rather than merely
asserting the indexes exist -- an invalid index would pass the weaker check.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa  # noqa: F401
import sqlmodel  # noqa: F401 -- see alembic/script.py.mako.


# revision identifiers, used by Alembic.
revision: str = "e4f7b0d25c63"
down_revision: Union[str, Sequence[str], None] = "d3e6a9c14b52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES = (
    ("ix_food_gtin14", "gtin14"),
    ("ix_food_name_normalized", "name_normalized"),
)


def upgrade() -> None:
    """Upgrade schema."""
    with op.get_context().autocommit_block():
        # SHARE UPDATE EXCLUSIVE only -- reads and writes both continue
        # throughout. The timeout still matters: a concurrent build waits for
        # existing transactions to drain before it starts, and one
        # long-running transaction would otherwise stall it indefinitely.
        op.execute("SET lock_timeout = '5s'")

        for name, column in _INDEXES:
            op.create_index(
                name,
                "food_items",
                [column],
                postgresql_concurrently=True,
                if_not_exists=True,
            )


def downgrade() -> None:
    """Downgrade schema.

    Dropped concurrently as well, so a rollback does not take the lock that
    the upgrade was careful to avoid. IF EXISTS covers the invalid-index case
    described above, where the index may or may not be present.
    """
    with op.get_context().autocommit_block():
        op.execute("SET lock_timeout = '5s'")

        for name, _column in reversed(_INDEXES):
            op.drop_index(
                name,
                table_name="food_items",
                postgresql_concurrently=True,
                if_exists=True,
            )
