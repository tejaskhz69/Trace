"""Integration tests for barcode resolution over the real HTTP surface.

NO EXTERNAL CALL IS EVER MADE. `resolve_barcode_remote` is patched in every
test that could reach it, and one test asserts that patching is the only way a
call happens -- a suite that quietly hits Open Food Facts is a suite that fails
on a train and bills somebody on a good day.

Runs against the scratch `trace_test` database via the project's ASGI client.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.routers import foods as foods_router
from app.services.food_sources import ResolvedFood
from app.services.gtin import check_digit

pytestmark = pytest.mark.anyio


def _hdr(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _register(client) -> dict:
    email = f"barcode-{uuid.uuid4().hex[:10]}@example.com"
    res = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "hunter2-correct-horse", "name": "Scan"},
    )
    assert res.status_code in (200, 201), res.text
    return _hdr(res.json()["access_token"])


def valid(payload: str) -> str:
    """Append the correct GS1 check digit, so a fixture cannot be green by
    accident the way `0400000000006` was."""
    return payload + str(check_digit(payload))


async def _food(session, *, name, barcode=None, gtin14=None, source="openfoodfacts",
                licence="odbl", tier=6) -> str:
    fid = str(uuid.uuid4())
    await session.execute(
        text("""
        INSERT INTO food_items
            (id, source, name, brand, barcode, gtin14, calories, protein_g,
             carbs_g, fat_g, fiber_g, sugar_g, sodium_mg, saturated_fat_g,
             is_liquid, serving_sizes, countries, micronutrients, names_i18n,
             data_quality, is_verified, moderation_status, search_text,
             log_count, source_licence, verification_tier, name_normalized,
             created_at, updated_at)
        VALUES
            (:id, :source, :name, NULL, :barcode, :gtin14, 100, 5, 10, 2,
             0, 0, 0, 0,
             false, '[]'::jsonb, '[]'::jsonb, '{}'::jsonb, '{}'::jsonb,
             0.6, false, 'approved', :st, 0, :licence, :tier, :norm,
             now(), now())
        """),
        {"id": fid, "source": source, "name": name, "barcode": barcode,
         "gtin14": gtin14, "st": name.lower(), "licence": licence,
         "tier": tier, "norm": name.lower()},
    )
    return fid


def _resolved(barcode: str, name: str = "Remote product") -> ResolvedFood:
    return ResolvedFood(
        source=foods_router.FoodSource.off,
        source_id=f"off-{barcode}",
        name=name,
        brand=None,
        barcode=barcode,
        calories=120.0,
        protein_g=8.0,
        carbs_g=10.0,
        fat_g=4.0,
        fiber_g=1.0,
        sugar_g=2.0,
        sodium_mg=50.0,
        saturated_fat_g=1.0,
        serving_sizes=[],
        is_liquid=False,
        countries=[],
        data_quality=0.6,
        raw={},
    )


@pytest.fixture(autouse=True)
def _clear_negative_cache():
    """The miss cache is process-global, so tests would leak into each other."""
    foods_router._barcode_misses.clear()
    yield
    foods_router._barcode_misses.clear()


@pytest.fixture
def no_network(monkeypatch):
    """Fail loudly if anything reaches for the network."""

    async def _boom(barcode):  # noqa: ANN001
        raise AssertionError(
            f"a test reached resolve_barcode_remote({barcode!r}) without patching it"
        )

    monkeypatch.setattr(foods_router, "resolve_barcode_remote", _boom)


# ---------------------------------------------------------------- validation


class TestValidationHappensBeforeAnyNetworkCall:
    """The endpoint used to accept any 6-14 digit string and look it up.

    `services/gtin.py` -- GS1 mod-10, restricted prefixes, the length gate --
    existed and was tested the whole time, and the scan path never called it.
    """

    @pytest.mark.parametrize(
        "code,status",
        [
            ("123456", "invalid_length"),      # no such GTIN. Was accepted.
            ("0123456789", "invalid_length"),  # truncated read
            ("012345678901234", "invalid_length"),
            ("012345678906", "bad_check_digit"),
            ("abcdefgh", "not_numeric"),
        ],
    )
    async def test_a_malformed_code_never_reaches_a_provider(
        self, client, code, status, no_network
    ):
        headers = await _register(client)
        res = await client.get(f"/api/foods/barcode/{code}", headers=headers)
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["found"] is False
        assert body["status"] == status
        assert body["gtin14"] is None
        assert body["message"]

    async def test_a_refusal_is_200_not_400(self, client, no_network):
        """A 4xx is indistinguishable, at the client, from an expired token.

        This is a well-formed request about a barcode that turned out not to
        be a product identifier. The client needs to render an explanation,
        not catch an exception.
        """
        headers = await _register(client)
        res = await client.get("/api/foods/barcode/123456", headers=headers)
        assert res.status_code == 200

    async def test_every_refusal_names_a_different_recovery(self, client, no_network):
        headers = await _register(client)
        messages = {}
        for code in ("123456", "012345678906", "abcdefgh", valid("020000000000")):
            body = (await client.get(f"/api/foods/barcode/{code}", headers=headers)).json()
            messages[body["status"]] = body["message"]
        assert len(set(messages.values())) == len(messages), (
            "two different failures give the same advice, so the user cannot "
            "tell which recovery applies"
        )

    async def test_lookup_requires_authentication(self, client):
        res = await client.get("/api/foods/barcode/012345678905")
        assert res.status_code in (401, 403)


class TestRestrictedCodes:
    """In-store codes are retailer-scoped: local-only, never external."""

    async def test_a_restricted_code_is_never_sent_to_a_provider(
        self, client, no_network
    ):
        headers = await _register(client)
        code = valid("020000000000")
        res = await client.get(f"/api/foods/barcode/{code}", headers=headers)
        body = res.json()
        assert body["status"] == "restricted"
        assert body["found"] is False

    async def test_a_restricted_code_is_not_retryable(self, client, no_network):
        """Re-scanning an in-store sticker is a loop, not a recovery.

        Every other refusal can plausibly succeed on a second try, so telling
        the user to try again is right for those and wrong for this one.
        """
        headers = await _register(client)
        body = (
            await client.get(
                f"/api/foods/barcode/{valid('020000000000')}", headers=headers
            )
        ).json()
        assert body["retryable"] is False

    async def test_a_restricted_code_still_resolves_from_our_own_catalogue(
        self, client, db_session, no_network
    ):
        """1,079 rows in the live catalogue carry a number-system-4 code, and
        they are real own-label groceries somebody recorded.

        Answering from OUR catalogue is not a guess about a global identifier
        -- it is returning the row we hold. What must never happen is sending
        those digits to an external source, where they belong to a different
        chain's different product.
        """
        headers = await _register(client)
        await _food(db_session, name="Own label hummus", gtin14="00490711802107")
        await db_session.commit()

        res = await client.get("/api/foods/barcode/0490711802107", headers=headers)
        body = res.json()
        assert body["found"] is True
        assert body["item"]["name"] == "Own label hummus"
        # The identity is still reported as retailer-scoped. We show the
        # product; we do not pretend the code is global.
        assert body["status"] == "restricted"


# -------------------------------------------------------------------- lookup


class TestLocalResolution:
    async def test_resolves_by_the_normalised_gtin14_column(
        self, client, db_session, no_network
    ):
        """The old query matched the raw `barcode` string with hand-rolled
        variants. `gtin14` is the normalised form, indexed, and populated for
        504,850 rows."""
        headers = await _register(client)
        await _food(db_session, name="Indexed product", gtin14="08906136651951",
                    barcode=None)
        await db_session.commit()

        body = (
            await client.get("/api/foods/barcode/8906136651951", headers=headers)
        ).json()
        assert body["found"] is True
        assert body["item"]["name"] == "Indexed product"
        assert body["gtin14"] == "08906136651951"
        assert body["resolved_from"] == "local"

    async def test_upc_a_finds_the_ean13_row_and_the_reverse(
        self, client, db_session, no_network
    ):
        """One product, two encodings, one row. This is the whole reason
        `gtin14` exists."""
        headers = await _register(client)
        await _food(db_session, name="Folded product", gtin14="00012345678905")
        await db_session.commit()

        for scan in ("012345678905", "0012345678905", "00012345678905"):
            body = (
                await client.get(f"/api/foods/barcode/{scan}", headers=headers)
            ).json()
            assert body["found"] is True, scan
            assert body["item"]["name"] == "Folded product"

    async def test_legacy_rows_without_a_gtin14_still_resolve(
        self, client, db_session, no_network
    ):
        """61,000 rows carry a barcode the backfill could not normalise.

        The variant match is kept as a fallback so this change strictly widens
        what resolves rather than trading one set of hits for another.
        """
        headers = await _register(client)
        await _food(db_session, name="Legacy row", barcode="8906136651951",
                    gtin14=None)
        await db_session.commit()

        body = (
            await client.get("/api/foods/barcode/8906136651951", headers=headers)
        ).json()
        assert body["found"] is True
        assert body["item"]["name"] == "Legacy row"


class TestRemoteResolution:
    async def test_a_hit_is_persisted_and_returned(self, client, monkeypatch):
        headers = await _register(client)
        calls = []

        async def _fake(barcode):
            calls.append(barcode)
            return _resolved(barcode, "Pintola oats"), "openfoodfacts"

        monkeypatch.setattr(foods_router, "resolve_barcode_remote", _fake)
        body = (
            await client.get("/api/foods/barcode/8906136651951", headers=headers)
        ).json()
        assert body["found"] is True
        assert body["item"]["name"] == "Pintola oats"
        assert body["resolved_from"] == "openfoodfacts"
        assert calls == ["8906136651951"]

    async def test_one_scan_does_not_create_two_food_rows(
        self, client, db_session, monkeypatch
    ):
        """`persist_resolved` upserts on (source, source_id).

        Without that, a user scanning the same product twice -- or the scanner
        and the portion screen both resolving it -- grows the catalogue by one
        duplicate per scan.
        """
        headers = await _register(client)

        async def _fake(barcode):
            return _resolved(barcode), "openfoodfacts"

        monkeypatch.setattr(foods_router, "resolve_barcode_remote", _fake)
        for _ in range(3):
            await client.get("/api/foods/barcode/8906136651951", headers=headers)

        n = await db_session.scalar(
            text("SELECT count(*) FROM food_items WHERE source_id = :sid"),
            {"sid": "off-8906136651951"},
        )
        assert n == 1

    async def test_a_miss_reports_not_found_and_stays_retryable(
        self, client, monkeypatch
    ):
        headers = await _register(client)

        async def _fake(barcode):
            return None, "none"

        monkeypatch.setattr(foods_router, "resolve_barcode_remote", _fake)
        body = (
            await client.get("/api/foods/barcode/8906136651951", headers=headers)
        ).json()
        assert body["found"] is False
        assert body["status"] == "not_found"
        assert body["retryable"] is True
        assert body["gtin14"] == "08906136651951"


# --------------------------------------------------------------------- cache


class TestNegativeCache:
    async def test_a_second_scan_of_an_unknown_code_skips_the_network(
        self, client, monkeypatch
    ):
        """A barcode nobody has catalogued costs two upstream calls and, once
        both miss, a metered one. Misses are the COMMON case for exactly the
        regional products this app cares about most."""
        headers = await _register(client)
        calls = []

        async def _fake(barcode):
            calls.append(barcode)
            return None, "none"

        monkeypatch.setattr(foods_router, "resolve_barcode_remote", _fake)
        first = (
            await client.get("/api/foods/barcode/8906136651951", headers=headers)
        ).json()
        second = (
            await client.get("/api/foods/barcode/8906136651951", headers=headers)
        ).json()

        assert len(calls) == 1, "the second lookup went to the network anyway"
        assert first["resolved_from"] is None
        assert second["resolved_from"] == "cache"
        assert second["status"] == "not_found"

    async def test_the_cache_is_keyed_on_the_normalised_form(
        self, client, monkeypatch
    ):
        """UPC-A and EAN-13 of one product must share one entry.

        Keying on the raw scan would store the same miss once per encoding and
        re-hit the network for each.
        """
        headers = await _register(client)
        calls = []

        async def _fake(barcode):
            calls.append(barcode)
            return None, "none"

        monkeypatch.setattr(foods_router, "resolve_barcode_remote", _fake)
        await client.get("/api/foods/barcode/012345678905", headers=headers)
        await client.get("/api/foods/barcode/0012345678905", headers=headers)
        assert len(calls) == 1

    async def test_an_expired_entry_is_looked_up_again(self, client, monkeypatch):
        headers = await _register(client)
        calls = []

        async def _fake(barcode):
            calls.append(barcode)
            return None, "none"

        monkeypatch.setattr(foods_router, "resolve_barcode_remote", _fake)
        monkeypatch.setattr(foods_router, "NEGATIVE_CACHE_TTL_S", 0)
        await client.get("/api/foods/barcode/8906136651951", headers=headers)
        await client.get("/api/foods/barcode/8906136651951", headers=headers)
        assert len(calls) == 2

    async def test_an_outage_is_never_cached_as_a_missing_product(
        self, client, monkeypatch
    ):
        """The most important line in this file.

        Reporting "we couldn't find it" during an Open Food Facts outage
        teaches the user their product does not exist and sends them off to
        type eleven numbers by hand. Worse, caching it makes the lie stick for
        ten minutes after the provider recovers.
        """
        headers = await _register(client)
        state = {"down": True}

        async def _fake(barcode):
            if state["down"]:
                raise TimeoutError("provider timed out")
            return _resolved(barcode), "openfoodfacts"

        monkeypatch.setattr(foods_router, "resolve_barcode_remote", _fake)

        down = (
            await client.get("/api/foods/barcode/8906136651951", headers=headers)
        ).json()
        assert down["status"] == "upstream_error"
        assert down["retryable"] is True
        assert down["found"] is False
        assert "8906136651951" not in str(foods_router._barcode_misses)

        state["down"] = False
        up = (
            await client.get("/api/foods/barcode/8906136651951", headers=headers)
        ).json()
        assert up["found"] is True, "the outage was cached as a miss"

    async def test_a_newly_catalogued_product_clears_its_own_miss(
        self, client, monkeypatch
    ):
        """Open Food Facts is crowd-sourced: the user who just failed to find
        a product is often the one who adds it minutes later."""
        headers = await _register(client)
        state = {"known": False}

        async def _fake(barcode):
            if not state["known"]:
                return None, "none"
            return _resolved(barcode), "openfoodfacts"

        monkeypatch.setattr(foods_router, "resolve_barcode_remote", _fake)
        await client.get("/api/foods/barcode/8906136651951", headers=headers)
        assert foods_router._barcode_misses

        # Simulate the row arriving, then bypass the cache the way an expiry
        # would, and confirm the miss is dropped on success.
        state["known"] = True
        foods_router._barcode_misses.clear()
        body = (
            await client.get("/api/foods/barcode/8906136651951", headers=headers)
        ).json()
        assert body["found"] is True
        assert not foods_router._barcode_misses

    async def test_the_cache_is_bounded(self, client, monkeypatch):
        """A scan-happy client must not grow this without limit."""
        monkeypatch.setattr(foods_router, "NEGATIVE_CACHE_MAX", 8)
        for i in range(40):
            foods_router._record_miss(f"{i:014d}")
        assert len(foods_router._barcode_misses) <= 8

    async def test_a_local_hit_never_consults_the_cache_or_the_network(
        self, client, db_session, no_network
    ):
        headers = await _register(client)
        await _food(db_session, name="Cached locally", gtin14="08906136651951")
        await db_session.commit()
        foods_router._record_miss("08906136651951")

        body = (
            await client.get("/api/foods/barcode/8906136651951", headers=headers)
        ).json()
        assert body["found"] is True, "a stale miss shadowed a row we hold"


class TestConcurrentDuplicateLookups:
    async def test_two_simultaneous_scans_of_one_code_yield_one_product(
        self, client, monkeypatch
    ):
        """The scanner and the portion screen used to resolve the same code at
        the same time, racing to write the same row."""
        headers = await _register(client)
        calls = []

        async def _fake(barcode):
            calls.append(barcode)
            await asyncio.sleep(0.05)
            return _resolved(barcode), "openfoodfacts"

        monkeypatch.setattr(foods_router, "resolve_barcode_remote", _fake)
        a, b = await asyncio.gather(
            client.get("/api/foods/barcode/8906136651951", headers=headers),
            client.get("/api/foods/barcode/8906136651951", headers=headers),
        )
        ja, jb = a.json(), b.json()
        assert ja["found"] and jb["found"]
        # Same product, whichever of them won the write.
        assert ja["item"]["id"] == jb["item"]["id"]


class TestSymbology:
    async def test_upc_e_is_expanded_when_the_scanner_says_so(
        self, client, db_session, no_network
    ):
        headers = await _register(client)
        await _food(db_session, name="Compressed code product",
                    gtin14="00042100005264")
        await db_session.commit()

        body = (
            await client.get(
                "/api/foods/barcode/04252614?symbology=upc_e", headers=headers
            )
        ).json()
        assert body["found"] is True
        assert body["gtin14"] == "00042100005264"

    async def test_the_same_digits_without_the_symbology_are_not_expanded(
        self, client, no_network
    ):
        """58% of valid EAN-8 codes beginning 0 or 1 also parse as a valid
        UPC-E, and the two readings name different products. A miss is
        recoverable; a confidently wrong product is believed."""
        headers = await _register(client)
        body = (
            await client.get("/api/foods/barcode/04252614", headers=headers)
        ).json()
        assert body["gtin14"] != "00042100005264"
