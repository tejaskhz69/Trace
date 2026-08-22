"""create food aliases

Revision ID: c2d5f8b03a41
Revises: b1c4e7a92f30
Create Date: 2026-08-22

INDEXES ARE BUILT INLINE AND NON-CONCURRENTLY, DELIBERATELY.
The table is empty at this instant, so each build is instant and the lock is
on a table no query has ever read. CREATE INDEX CONCURRENTLY here would be
cargo-cult: slower, unable to run inside this transaction, and protecting
against contention that cannot exist. Contrast e4f7b0d25c63, where the same
operation on food_items genuinely does need it.

`lang` IS NOT NULL, AND THAT IS LOAD-BEARING.
PostgreSQL treats NULLs as DISTINCT inside a UNIQUE constraint. A nullable
lang would let ('poha-id', 'avalakki', NULL) be inserted an unlimited number
of times without ever violating uq_alias_food_norm_lang -- silently disabling
the constraint for exactly the rows least likely to carry a language tag,
which is transliterations. NULLS NOT DISTINCT would also fix it but needs
PG 15+; the '' sentinel works on every version.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401 -- AutoString below is emitted by autogenerate
                 # without an import; see alembic/script.py.mako.


# revision identifiers, used by Alembic.
revision: str = "c2d5f8b03a41"
down_revision: Union[str, Sequence[str], None] = "b1c4e7a92f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "food_aliases",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        # AutoString, not Text, to match food_items.id exactly. The FK would
        # work across varchar/text -- they are binary-coercible -- but a
        # schema that says what it means is worth more than that.
        sa.Column("food_item_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("normalized", sa.Text(), nullable=False),
        sa.Column("lang", sa.Text(), nullable=False, server_default=""),
        sa.Column("script", sa.Text(), nullable=False, server_default="latn"),
        sa.Column("alias_type", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["food_item_id"], ["food_items.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "food_item_id", "normalized", "lang", name="uq_alias_food_norm_lang"
        ),
        # Text + CHECK rather than PG enums, per the reviewed plan: extending
        # the vocabulary later is DROP/ADD CONSTRAINT inside an ordinary
        # transaction, instead of the ALTER TYPE dance that cannot run in one.
        sa.CheckConstraint(
            "alias_type IN ('canonical','regional','transliteration',"
            "'colloquial','misspelling','brand_variant')",
            name="ck_alias_type",
        ),
        sa.CheckConstraint(
            "source IN ('curated','import','ai','user')",
            name="ck_alias_source",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_alias_confidence",
        ),
    )

    # Exact-match probe. The fast path: 'avalakki' resolves to Poha through a
    # single btree lookup rather than through trigram noise.
    op.create_index("ix_alias_normalized", "food_aliases", ["normalized"])
    # Roll an alias hit back up to its food.
    op.create_index("ix_alias_food", "food_aliases", ["food_item_id"])
    # Fuzzy alias match. gin_trgm_ops is not decoration -- without the
    # operator class this index exists, the app still starts, and every alias
    # query silently falls back to a sequential scan.
    op.create_index(
        "ix_alias_normalized_trgm",
        "food_aliases",
        ["normalized"],
        postgresql_using="gin",
        postgresql_ops={"normalized": "gin_trgm_ops"},
    )


def downgrade() -> None:
    """Downgrade schema.

    DROP TABLE takes the indexes, the CHECKs, the UNIQUE and the FK with it.
    food_items is untouched -- the FK points the other way.
    """
    op.drop_table("food_aliases")
