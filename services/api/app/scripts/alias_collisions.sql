-- Every alias string owned by two or more movements.
--
-- WHY THIS IS A FILE AND NOT A ONE-OFF
-- Promoting an exact alias to rank 1 in exercise search makes collisions
-- consequential: a colliding term no longer just appears in a long list, it
-- decides which movement comes first. So "how many collide" has to be a
-- number anyone can re-derive, not a claim in a report.
--
--   psql "$DATABASE_URL" -f app/scripts/alias_collisions.sql
--
-- The normalisation here must match `services/catalogue.normalise_term`:
-- lowercase, trim, collapse internal whitespace. If that function changes,
-- change this too or the two will disagree about what "the same alias" is.

WITH owned AS (
    SELECT
        e.id,
        e.name,
        e.equipment,
        regexp_replace(btrim(lower(alias)), '\s+', ' ', 'g') AS term
    FROM exercises e,
         LATERAL jsonb_array_elements_text(e.aliases) AS alias
),
-- A movement's own name is part of the namespace: an alias colliding with
-- another row's NAME is the same defect as two rows sharing an alias.
names AS (
    SELECT id, name, equipment,
           regexp_replace(btrim(lower(name)), '\s+', ' ', 'g') AS term
    FROM exercises
),
namespace AS (
    SELECT * FROM owned
    UNION ALL
    SELECT * FROM names
)
SELECT
    term,
    count(DISTINCT id)                        AS movements,
    array_agg(DISTINCT name ORDER BY name)    AS owners,
    array_agg(DISTINCT equipment)             AS equipment
FROM namespace
GROUP BY term
HAVING count(DISTINCT id) > 1
ORDER BY count(DISTINCT id) DESC, term;
