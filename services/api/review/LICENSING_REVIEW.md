# Licensing review — OPEN, NEEDS QUALIFIED LEGAL INPUT

**This document is not legal advice, and nothing in this repository asserts
that Trace is legally compliant.** It records what the code does, what the
catalogue actually contains, and the questions a qualified lawyer needs to
answer. It is deliberately written so that someone who has never seen this
codebase can act on it.

Status: **open.** No item below has been reviewed by a lawyer.

---

## 1. What is actually in the catalogue

Measured against the live database, read-only, on 2026-08-24:

| Source | Rows | Share | `source_licence` | Attribution owed? |
|---|---:|---:|---|---|
| Open Food Facts | 565,814 | 97.76% | `odbl` | **Yes** — ODbL |
| USDA FoodData Central | 12,612 | 2.18% | `public-domain` | Credit given; not required |
| Trace curated dishes | 347 | 0.06% | `user` | No third party |
| **Total** | **578,773** | | | |

Three further sources are mapped in `app/services/licensing.py` and can reach
a user, but have no rows today:

| Source | Licence | Notes |
|---|---|---|
| `nutritionix` | `proprietary` | Metered vendor feed. Written by `services/paid_sources.py`. **Redistribution prohibited by contract** — terms not in this repo. |
| `user` | `user` | Foods a user creates via `POST /api/foods/custom`. |
| `ai_estimated` | `user` | Photo-scan estimates produced by Trace. |
| `ifct` | `unknown` | Indian Food Composition Tables. Mapped, deliberately unusable — see §6. |

**The ODbL share is the whole issue.** 97.76% of the catalogue is one
share-alike licensed database.

---

## 2. Display versus redistribution

These are different acts with different obligations, and the codebase treats
them differently on purpose.

**What Trace does today — display.** A user searches, the API returns rows,
the app renders nutrition figures and a per-row credit. This is ordinary use
of the data.

**What Trace does not do today — redistribution.** There is no bulk export,
no public API, no data sync to a third party, and no "download my data"
endpoint. `services/licensing.is_exportable()` exists so that when one is
built it has to ask this module rather than decide for itself; it returns
`False` for `odbl` and for `unknown`, and `True` only for `public-domain` and
`user`.

**Questions for review:**

1. Does serving individual ODbL rows through an authenticated mobile app
   constitute "Use" or "Publicly Use" of the database under ODbL §4.2/§4.3?
2. Does an authenticated API that any registered user may query count as
   public conveyance of the database, or only of individual contents?
3. At what point does query volume or result-set size turn "displaying
   contents" into "conveying a Derivative Database"?

---

## 3. ODbL share-alike

ODbL §4.4 requires that a Derivative Database offered to the public be offered
under ODbL. The practical risk is that a feature added later — an export, a
partner integration, a public search endpoint — pulls the whole derived
catalogue under share-alike, including the 347 curated rows Trace wrote itself
and any user-created rows caught up in the same table.

**Questions for review:**

4. Is `food_items` as a whole a Derivative Database, a Collective Database, or
   neither, given it merges ODbL, public-domain and original records in one
   table?
5. If a bulk export is built, does excluding ODbL rows (which
   `is_exportable()` already does) actually avoid share-alike, or does the
   remaining set still count as derived because it was selected and normalised
   using an ODbL-derived pipeline?
6. Does the alias layer (`food_aliases`, 1,353 rows, generated from
   `names_i18n` on ODbL rows — see `alias_import_plan.json`) constitute a
   Derivative Database in its own right?

---

## 4. Derived and computed values

Trace does not only display upstream numbers. It computes.

- **Curated dishes** (347) are composed from published food composition tables
  and standard recipes. Some ingredient values may originate in ODbL rows.
- **Recipes** (`app/routers/recipes.py`) compute per-serving nutrition by
  summing ingredient rows, which may include ODbL rows.
- **Preparation adjustments** (`app/services/preparation.py`) transform a dry
  ingredient's figures into an as-eaten figure.
- **`search_text`, `name_normalized`, `gtin14`** are normalised columns
  derived from ODbL fields.
- **Photo-scan estimates** (`ai_estimated`) may be anchored on catalogue rows.

**Questions for review:**

7. Is a computed per-serving figure for a recipe built partly from ODbL rows
   a "Produced Work" (§4.5, attribution only) or a Derivative Database (§4.4,
   share-alike)?
8. Do normalised/derived columns (`search_text`, `gtin14`) change that answer?
9. If a user exports their own meal log, and a logged meal references an ODbL
   row's figures, is that redistribution of the database or of a Produced Work?

---

## 5. Database extraction and export

There is no export path today. When one is built, these must be settled first.

**Questions for review:**

10. What exactly may a user receive in a personal data export — their own log
    entries only, or also the nutrition figures those entries reference?
11. Does GDPR/DPDP data-portability create an obligation to export figures
    that ODbL restricts redistributing, and how do the two interact?
12. If ODbL rows are withheld from an export, must the user be told what was
    withheld and why? (`licensing.export_filter_summary()` produces the
    counts to do so; nothing consumes it yet.)
13. Do database backups (`pg_dump`) or a move to a managed host count as
    conveyance?

---

## 6. User-generated and curated records

Three categories are **not** third-party data and are never labelled as such.
`attribution_line()` returns `None` for all three, and both the API tests and
the client tests assert it.

| Category | Source value | Who owns it | Shown as |
|---|---|---|---|
| Trace curated dishes | `curated` | Trace | no credit line |
| User-created foods | `user` | the user | no credit line |
| Photo estimates | `ai_estimated` | Trace | no credit line |

**Questions for review:**

14. Do the Terms of Service grant Trace a licence to a user's created foods,
    and is that licence broad enough for the curation and moderation the
    `moderation_status` column implies?
15. If a user-created food is later approved and served to other users, what
    licence does it carry, and does the creator need to be told?
16. **IFCT is mapped to `unknown` on purpose.** Indian government works are
    not automatically public domain, and IFCT 2017 is an ICMR-NIN publication
    sold as a book. Nobody has confirmed terms in writing. Confirming them is
    a review item, not an engineering one.

---

## 7. Required source notices — what the app shows today

**Where attribution appears, exactly:**

| Location | File | What is shown |
|---|---|---|
| Search result row | `apps/mobile/app/food-search.tsx` | Uppercase tag, e.g. `OPEN FOOD FACTS`, one line, truncated |
| Search result row, screen reader | same | Full sentence inside the row's `accessibilityLabel` |
| Food detail sheet | same | Full sentence above the "Log it" button |
| Profile → Data sources | `apps/mobile/app/(tabs)/profile.tsx` | Five named sources with a one-line note each |
| API response | `app/routers/foods.py` `_public()` | `source`, `source_licence`, `verification_tier`, `source_name`, `attribution` per row |

**The exact ODbL wording currently rendered:**

> Nutrition data from Open Food Facts, made available under the Open Database
> License (ODbL).

Composed by `licensing.attribution_line()`. Per row, never global.

**What the implementation deliberately does not do:**

- No hyperlink to opendatacommons.org or to openfoodfacts.org. The app has no
  external-link affordance anywhere else, and a compliance string is a poor
  place to introduce one. `source_url` **is** returned by the API and is
  currently **not rendered**.
- No claim of compliance anywhere. Tests in `tests/test_licensing.py` and
  `src/lib/__tests__/attribution.test.ts` fail on the words "compliant",
  "compliance", "permitted", "we own", "all rights".
- No copy of the licence text is bundled.

**Questions for review:**

17. Is a per-row source name plus licence name sufficient notice under ODbL
    §4.2, or must the notice be a link to the licence text and to the source
    database?
18. Must the notice be reachable without a network connection, and must it
    persist offline?
19. Is a truncated uppercase tag in a list row adequate where the full
    sentence is one tap away, or must the full notice be visible at the point
    of display?
20. Does the profile "Data sources" panel need to name the ODbL version
    (1.0) and link to it?
21. Is a screen-reader-only full sentence acceptable as the "complete" notice
    for a list row?

---

## 8. Where the wording lives

Change any of it only with legal input.

| Concern | File |
|---|---|
| Source → licence, tier, credit, display name | `app/services/licensing.py` |
| Export gating (`is_exportable`) | `app/services/licensing.py` |
| Per-row serialisation | `app/routers/foods.py` → `_public()` |
| Client rendering + fallback table | `apps/mobile/src/lib/attribution.ts` |
| Profile panel copy | `apps/mobile/app/(tabs)/profile.tsx` → `DATA_SOURCES` |
| Server-side tests | `tests/test_licensing.py`, `tests/test_search_ranking_api.py` |
| Client-side tests | `apps/mobile/src/lib/__tests__/attribution.test.ts` |

The server owns the wording; the client renders what it is handed and keeps a
fallback table only for responses that predate the `source_name` /
`attribution` fields. That split exists because the client's copy of the
mapping **had already drifted**: `nutritionix` was added to the API and never
to the client, so metered rows rendered "SOURCE UNKNOWN" — dropping a credit
owed by contract, silently, with no way for a user to notice.

---

## 9. Summary for the reviewer

Twenty-one numbered questions above. The four that block a public release:

- **§2 Q1–Q3** — is display-only attribution inside an authenticated app
  sufficient for ODbL?
- **§3 Q4** — what is `food_items`, as a whole, under ODbL?
- **§4 Q7** — are computed recipe and preparation figures Produced Works or
  Derivative Databases?
- **§7 Q17** — is the current notice wording and placement sufficient?

Everything else can be settled before the first export or partner integration
ships, whichever comes first.
