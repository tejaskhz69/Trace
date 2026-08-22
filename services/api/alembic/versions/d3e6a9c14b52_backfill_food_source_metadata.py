"""backfill food source metadata

Revision ID: d3e6a9c14b52
Revises: c2d5f8b03a41
Create Date: 2026-08-22

THE MAPPING IS STATIC AND INLINE. NOTHING FROM app.services IS IMPORTED.
A migration is a frozen historical record. Importing application code that
keeps changing means re-running this revision later produces different output
than it did the first time. services/licensing.py holds the same mapping for
runtime use; this copy is deliberate duplication, and test_migrations asserts
the two agree so they cannot drift silently.

SOURCE VALUES, NOT NAMES. The foodsource enum was created by the baseline as
Enum('openfoodfacts','usda_fdc','ifct','curated','user','ai_estimated',
'nutritionix') -- the VALUES -- because models.py pins it with
values_callable. Matching on 'off' or 'usda' here would update zero rows and
report success.

WHAT THIS DOES NOT TOUCH
barcode and source_id are READ to construct source_url and are never written.
names_i18n, search_text, data_quality and is_verified are not referenced.

gtin14 and name_normalized are NOT backfilled here. They derive from
services/gtin.py and services/food_text.py, so filling them from a frozen
migration would bake in whatever those functions happened to do today. They
get a re-runnable script instead, which is also what lets them be recomputed
when the normaliser changes.
"""
from typing import Optional, Sequence, Tuple, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401 -- see alembic/script.py.mako.


# revision identifiers, used by Alembic.
revision: str = "d3e6a9c14b52"
down_revision: Union[str, Sequence[str], None] = "c2d5f8b03a41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


#: Rows per committed batch. Small enough that row locks are held briefly and
#: autovacuum can keep up with the dead tuples; large enough that 578,773 rows
#: take ~116 round trips rather than 116,000.
BATCH = 5_000

USDA_URL = "https://fdc.nal.usda.gov/fdc-app.html#/food-details/"
OFF_URL = "https://world.openfoodfacts.org/product/"

#: (source value, licence, tier, url prefix, url source column)
#:
#: The url columns are NULL where a source has no deterministic public record.
#: They are ALSO effectively NULL per-row when that column is empty on a given
#: row -- see the CASE in _drain. A fabricated link is worse than no link,
#: because a link is what a user clicks to verify a number.
_MAPPING: Tuple[Tuple[str, str, int, Optional[str], Optional[str]], ...] = (
    ("usda_fdc",      "public-domain", 2, USDA_URL, "source_id"),
    ("openfoodfacts", "odbl",          6, OFF_URL,  "barcode"),
    ("nutritionix",   "proprietary",   3, None,     None),
    ("curated",       "user",          5, None,     None),
    ("user",          "user",          6, None,     None),
    ("ai_estimated",  "user",          7, None,     None),
    # Indian government works are not automatically public domain, and IFCT
    # 2017 is an ICMR-NIN publication sold as a book. This stays 'unknown',
    # which services/licensing.is_exportable refuses, until somebody confirms
    # terms in writing. Do not "tidy" this to public-domain.
    ("ifct",          "unknown",       5, None,     None),
)


def _drain(
    conn,
    source: str,
    licence: str,
    tier: int,
    prefix: Optional[str],
    column: Optional[str],
) -> None:
    """Update one source's rows in committed batches.

    THE DRAIN PREDICATE IS "not already at the target state", NOT
    "source_licence = 'unknown'".

    The obvious predicate is an infinite loop. `ifct` maps TO 'unknown', so
    its rows would satisfy `source_licence = 'unknown'` after every pass and
    this function would never terminate. Testing BOTH target columns
    terminates for every source in the mapping, because each one differs from
    the (unknown, 6) column defaults in at least one of them: ifct by tier,
    the other six by licence.

    A source absent from _MAPPING is never selected, so it keeps
    source_licence='unknown' and is excluded from exports. Fail-closed.
    """
    if prefix and column:
        # Deterministic or NULL, never invented. An OFF row with no barcode
        # and a USDA row with no source_id both get NULL rather than a URL
        # ending in nothing.
        url_expr = (
            f"CASE WHEN {column} IS NOT NULL AND {column} <> '' "
            f"THEN :prefix || {column} ELSE NULL END"
        )
    else:
        url_expr = "NULL"

    select_sql = sa.text(
        """
        SELECT id FROM food_items
         WHERE source::text = :src
           AND (source_licence IS DISTINCT FROM :lic
                OR verification_tier IS DISTINCT FROM :tier)
         ORDER BY id
         LIMIT :n
        """
    )
    update_sql = sa.text(
        f"""
        UPDATE food_items
           SET source_licence = :lic,
               verification_tier = :tier,
               source_url = {url_expr}
         WHERE id = ANY(:ids)
        """
    )

    while True:
        # Keyset by id, not OFFSET. `OFFSET 500000` rescans half a million
        # rows on every single batch, turning a linear job into a quadratic
        # one.
        ids = (
            conn.execute(
                select_sql,
                {"src": source, "lic": licence, "tier": tier, "n": BATCH},
            )
            .scalars()
            .all()
        )
        if not ids:
            return

        params = {"lic": licence, "tier": tier, "ids": list(ids)}
        if prefix and column:
            params["prefix"] = prefix
        conn.execute(update_sql, params)


def upgrade() -> None:
    """Upgrade schema. Batched and resumable.

    A single UPDATE over 578,773 rows would hold row locks for its whole
    duration, write one WAL record per row inside one transaction, and bloat
    the table by ~100% because every update creates a new row version.

    autocommit_block is what makes the batching real: Alembic otherwise wraps
    the entire migration in one transaction, and per-batch commits would be
    cosmetic. Inside the block each statement commits on its own, so an
    interruption loses at most one batch -- and because the revision is not
    stamped on failure, re-running `alembic upgrade` resumes from where it
    stopped rather than starting over.
    """
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        for source, licence, tier, prefix, column in _MAPPING:
            _drain(conn, source, licence, tier, prefix, column)


def downgrade() -> None:
    """Downgrade schema.

    Restores the column defaults set by b1c4e7a92f30. Honest rather than
    clever: there is no prior value to put back, because these three columns
    did not exist before this phase. Their pre-migration state IS the default.

    Batched for the same reason as upgrade, and resumable by the same
    not-yet-at-target predicate.
    """
    with op.get_context().autocommit_block():
        conn = op.get_bind()
        select_sql = sa.text(
            """
            SELECT id FROM food_items
             WHERE source_licence <> 'unknown'
                OR verification_tier <> 6
                OR source_url IS NOT NULL
             ORDER BY id
             LIMIT :n
            """
        )
        update_sql = sa.text(
            """
            UPDATE food_items
               SET source_licence = 'unknown',
                   verification_tier = 6,
                   source_url = NULL
             WHERE id = ANY(:ids)
            """
        )
        while True:
            ids = conn.execute(select_sql, {"n": BATCH}).scalars().all()
            if not ids:
                return
            conn.execute(update_sql, {"ids": list(ids)})
