"""add food item source metadata

Revision ID: b1c4e7a92f30
Revises: a05140b6e849
Create Date: 2026-08-22

SIX ADD COLUMNs ON A 578,773-ROW TABLE, AND WHY THAT IS SAFE
Every default here is a CONSTANT LITERAL. PostgreSQL 11+ stores a constant
DEFAULT in pg_attribute and adds the column by catalog update alone -- no
table rewrite, no row touched, sub-second regardless of table size. A
non-constant default such as now() would rewrite all 578,773 rows under an
ACCESS EXCLUSIVE lock, which is why last_verified_at defaults to NULL.

NOTHING EXISTING IS TOUCHED. barcode, names_i18n, search_text, data_quality
and is_verified are not referenced by this migration at all.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401 -- may be unused; the template imports it because
                 # autogenerate emits sqlmodel.sql.sqltypes.AutoString().


# revision identifiers, used by Alembic.
revision: str = "b1c4e7a92f30"
down_revision: Union[str, Sequence[str], None] = "a05140b6e849"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: (name, type, nullable, server_default)
_COLUMNS = (
    ("source_licence", sa.Text(), False, "unknown"),
    ("source_url", sa.Text(), True, None),
    ("verification_tier", sa.SmallInteger(), False, "6"),
    ("last_verified_at", sa.DateTime(timezone=True), True, None),
    ("gtin14", sa.Text(), True, None),
    ("name_normalized", sa.Text(), False, ""),
)


def upgrade() -> None:
    """Upgrade schema."""
    # Fail fast rather than queueing behind a conflicting lock. Without this,
    # the migration waits for the lock -- and every query arriving behind it
    # waits too, which is the classic way a "safe" migration takes a service
    # down. A timeout here means the migration errors and is simply re-run.
    op.execute("SET lock_timeout = '5s'")

    for name, type_, nullable, default in _COLUMNS:
        op.add_column(
            "food_items",
            sa.Column(name, type_, nullable=nullable, server_default=default),
        )


def downgrade() -> None:
    """Downgrade schema.

    A genuine rollback, unlike the baseline: these six columns did not exist
    before this phase, so dropping them restores the previous schema exactly.
    No pre-existing column or row is affected.
    """
    op.execute("SET lock_timeout = '5s'")

    for name, *_ in reversed(_COLUMNS):
        op.drop_column("food_items", name)
