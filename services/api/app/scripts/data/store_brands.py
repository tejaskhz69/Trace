"""Supermarket private-label brands, US + Europe, as Open Food Facts tags.

WHY THIS IS ITS OWN COVERAGE PROBLEM
A private label is invisible to every "top brands" import. Nobody's list of
famous food brands contains Kirkland Signature, Great Value, Hacendado or
Gut&Günstig -- and yet for a Costco shopper, a Walmart shopper, or anyone in
Spain, those ARE the products in the cupboard. Missing them means the barcode
scanner fails on the specific items a person buys every single week, which is
the fastest way to lose them.

They are also disproportionately worth having locally rather than via the live
API: a store-brand shopper re-scans the same twenty barcodes, so caching them
turns their common path into a millisecond index lookup.

THE TAGS
Each entry lists Open Food Facts `brands_tags` slugs. OFF slugs are lowercased
and hyphenated, with apostrophes becoming hyphens -- "Trader Joe's" is
`trader-joe-s` and "Member's Mark" is `member-s-mark`. Slugs that return
nothing are skipped by the ingester with a warning rather than aborting the
run; brand tagging in OFF is crowd-sourced and a slug can simply be unused in
a given country.

MULTIPLE SLUGS PER RETAILER IS NORMAL
Retailers run tiers: a value line, a standard line, and a premium line, each
with its own brand (Tesco / Tesco Finest / Stockwell's). They are listed
together because the user thinks "Tesco", not "Stockwell's".
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Retailer:
    name: str
    country: str          # ISO-ish label, for the log and for --country filtering
    brands: tuple[str, ...]  # OFF brands_tags slugs


# ---------------------------------------------------------------------------
# United States (and the Canadian banners that share a private label)
# ---------------------------------------------------------------------------

US: tuple[Retailer, ...] = (
    Retailer("Costco", "us", (
        "kirkland-signature", "kirkland",
    )),
    Retailer("Walmart", "us", (
        "great-value", "marketside", "sam-s-choice", "equate",
        "freshness-guaranteed", "bettergoods", "parent-s-choice",
        "clear-american",
    )),
    Retailer("Sam's Club", "us", (
        "member-s-mark",
    )),
    Retailer("Target", "us", (
        "good-gather", "market-pantry", "favorite-day", "archer-farms",
        "simply-balanced", "up-up",
    )),
    Retailer("Trader Joe's", "us", (
        "trader-joe-s",
    )),
    Retailer("Whole Foods", "us", (
        "365-by-whole-foods-market", "365-everyday-value", "365",
        "whole-foods-market",
    )),
    Retailer("Kroger", "us", (
        "kroger", "simple-truth", "simple-truth-organic", "private-selection",
        "home-chef", "value-wise",
    )),
    Retailer("Albertsons / Safeway", "us", (
        "signature-select", "o-organics", "lucerne", "open-nature",
        "waterfront-bistro", "signature-cafe",
    )),
    Retailer("Publix", "us", (
        "publix", "greenwise",
    )),
    Retailer("Aldi US", "us", (
        "simply-nature", "specially-selected", "millville", "friendly-farms",
        "clancy-s", "fit-active", "never-any", "earth-grown", "burman-s",
        "baker-s-corner", "southern-grove", "happy-farms",
    )),
    Retailer("Wegmans", "us", (
        "wegmans",
    )),
    Retailer("H-E-B", "us", (
        "h-e-b", "hill-country-fare", "central-market",
    )),
    Retailer("Meijer", "us", (
        "meijer", "true-goodness",
    )),
    Retailer("Amazon", "us", (
        "amazon-fresh", "happy-belly", "solimo", "aplenty",
    )),
    Retailer("Ahold (Giant / Stop & Shop / Food Lion)", "us", (
        "nature-s-promise", "guaranteed-value", "taste-of-inspirations",
        "se-grocers", "food-lion",
    )),
    Retailer("Sprouts", "us", (
        "sprouts", "sprouts-farmers-market",
    )),
    Retailer("Hy-Vee", "us", (
        "hy-vee", "that-s-smart",
    )),
    Retailer("Dollar General", "us", (
        "clover-valley",
    )),
    Retailer("CVS / Walgreens", "us", (
        "gold-emblem", "nice",
    )),
    Retailer("Loblaws (Canada)", "ca", (
        "president-s-choice", "no-name", "pc-organics",
    )),
    Retailer("Metro / Sobeys (Canada)", "ca", (
        "compliments", "irresistibles", "selection",
    )),
)


# ---------------------------------------------------------------------------
# United Kingdom & Ireland
# ---------------------------------------------------------------------------

UK: tuple[Retailer, ...] = (
    Retailer("Tesco", "uk", (
        "tesco", "tesco-finest", "stockwell-co", "tesco-plant-chef",
        "tesco-free-from",
    )),
    Retailer("Sainsbury's", "uk", (
        "sainsbury-s", "by-sainsbury-s", "taste-the-difference",
        "sainsbury-s-plant-pioneers",
    )),
    Retailer("ASDA", "uk", (
        "asda", "asda-extra-special", "just-essentials-by-asda",
        "asda-plant-based",
    )),
    Retailer("Morrisons", "uk", (
        "morrisons", "morrisons-the-best", "morrisons-savers",
    )),
    Retailer("Waitrose", "uk", (
        "waitrose", "waitrose-partners", "essential-waitrose", "waitrose-no-1",
        "duchy-organic",
    )),
    Retailer("Marks & Spencer", "uk", (
        "marks-spencer", "m-s", "m-s-food",
    )),
    Retailer("Co-op", "uk", (
        "co-op", "co-op-irresistible", "gro",
    )),
    Retailer("Aldi UK", "uk", (
        "everyday-essentials", "bramwells", "cowbelle", "village-bakery",
        "the-foodie-market", "inspired-cuisine", "roosters",
    )),
    Retailer("Lidl UK", "uk", (
        "deluxe", "crownfield", "milbona", "vemondo", "harvest-basket",
    )),
    Retailer("Iceland", "uk", (
        "iceland",
    )),
    Retailer("Ocado", "uk", (
        "ocado",
    )),
    Retailer("Dunnes / SuperValu (Ireland)", "ie", (
        "dunnes-stores", "supervalu", "signature-tastes",
    )),
)


# ---------------------------------------------------------------------------
# Continental Europe
# ---------------------------------------------------------------------------

EU: tuple[Retailer, ...] = (
    # --- France
    Retailer("Carrefour", "fr", (
        "carrefour", "carrefour-bio", "carrefour-selection",
        "carrefour-classic", "reflets-de-france", "simpl",
        "carrefour-extra", "carrefour-kids",
    )),
    Retailer("E.Leclerc", "fr", (
        "marque-repere", "eco", "nos-regions-ont-du-talent", "delisse",
        "rustica", "tradilege",
    )),
    Retailer("Intermarché", "fr", (
        "netto", "paturages", "chabrior", "monique-ranou", "itineraire-des-saveurs",
        "labell", "top-budget",
    )),
    Retailer("Auchan", "fr", (
        "auchan", "auchan-bio", "pouce", "mmm",
    )),
    Retailer("Casino / Monoprix", "fr", (
        "casino", "casino-bio", "leader-price", "monoprix", "monoprix-bio",
        "monoprix-gourmet",
    )),
    Retailer("Système U", "fr", (
        "u", "u-bio", "u-saveurs", "bien-vu",
    )),
    Retailer("Franprix / Picard", "fr", (
        "franprix", "picard",
    )),
    # --- Germany & Austria
    Retailer("Lidl (DE)", "de", (
        "milbona", "combino", "chef-select", "freeway", "solevita", "pilos",
        "dulano", "alesto", "cien", "belbake", "vemondo", "bioorganic",
        "saskia", "italiamo", "eridanous",
    )),
    Retailer("Aldi (DE)", "de", (
        "gut-bio", "milsani", "moser-roth", "choceur", "cucina-nobile",
        "trader-joe-s-de", "gutbio", "all-seasons", "mamia",
    )),
    Retailer("Rewe", "de", (
        "rewe", "rewe-bio", "rewe-beste-wahl", "ja", "rewe-feine-welt",
    )),
    Retailer("Edeka", "de", (
        "edeka", "edeka-bio", "gut-gunstig", "edeka-selection",
    )),
    Retailer("Kaufland", "de", (
        "k-classic", "k-bio", "k-take-it-veggie", "k-purland",
    )),
    Retailer("Netto / Penny / Norma", "de", (
        "biobio", "netto", "penny", "penny-ready", "norma",
    )),
    Retailer("dm / Rossmann", "de", (
        "dmbio", "ener-bio", "enerbio",
    )),
    Retailer("Spar / Billa / Hofer (AT)", "at", (
        "spar", "spar-natur-pur", "s-budget", "billa", "clever", "hofer",
        "spar-vital", "spar-premium",
    )),
    # --- Spain & Portugal
    Retailer("Mercadona", "es", (
        "hacendado", "deliplus", "bosque-verde",
    )),
    Retailer("Dia", "es", (
        "dia", "delicious", "as",
    )),
    Retailer("Eroski / Alcampo", "es", (
        "eroski", "eroski-basic", "eroski-natur", "alcampo", "produccion-controlada",
    )),
    Retailer("Carrefour ES / Lidl ES", "es", (
        "carrefour-selection-es", "el-corte-ingles", "aliada",
    )),
    Retailer("Pingo Doce / Continente", "pt", (
        "pingo-doce", "continente", "continente-equilibrio", "seleccao-continente",
    )),
    # --- Italy
    Retailer("Coop Italia", "it", (
        "coop", "vivi-verde-coop", "fior-fiore-coop", "crescendo",
    )),
    Retailer("Conad", "it", (
        "conad", "conad-percorso-qualita", "conad-sapori-dintorni", "verso-natura-conad",
    )),
    Retailer("Esselunga / Carrefour IT", "it", (
        "esselunga", "esselunga-bio", "esselunga-top",
    )),
    Retailer("Selex / Despar", "it", (
        "despar", "despar-premium", "consilia", "vivibene",
    )),
    # --- Benelux
    Retailer("Albert Heijn", "nl", (
        "ah", "albert-heijn", "ah-biologisch", "ah-basic", "ah-excellent",
        "ah-terra",
    )),
    Retailer("Jumbo", "nl", (
        "jumbo", "jumbo-biologisch",
    )),
    Retailer("Lidl NL / Aldi NL", "nl", (
        "vemondo-nl", "gut-bio-nl",
    )),
    Retailer("Delhaize / Colruyt", "be", (
        "delhaize", "delhaize-bio", "365-delhaize", "boni", "boni-selection",
        "everyday", "graindor",
    )),
    # --- Switzerland
    Retailer("Migros", "ch", (
        "migros", "m-budget", "m-classic", "anna-s-best", "migros-bio",
        "farmer", "aha",
    )),
    Retailer("Coop CH / Denner", "ch", (
        "coop-naturaplan", "qualite-prix", "pro-montagna", "karma", "denner",
    )),
    # --- Nordics
    Retailer("ICA / Coop (SE)", "se", (
        "ica", "ica-basic", "ica-i-love-eco", "ica-selection", "anglamark",
        "garant", "eldorado",
    )),
    Retailer("Rema 1000 / Coop (NO/DK)", "no", (
        "rema-1000", "first-price", "x-tra", "prima", "levevis",
    )),
    Retailer("Kesko / S-Group (FI)", "fi", (
        "pirkka", "rainbow", "kotimaista", "k-menu",
    )),
    # --- Central & Eastern Europe
    Retailer("Biedronka / Żabka (PL)", "pl", (
        "biedronka", "go-vege", "dobra-kaloria", "kuchnia-swiata", "zabka",
    )),
    Retailer("Lidl PL / Kaufland PL", "pl", (
        "pilos-pl", "k-classic-pl",
    )),
    Retailer("Tesco / Albert (CZ, SK, HU)", "cz", (
        "albert", "albert-quality", "tesco-value", "billa-cz",
    )),
)


ALL_RETAILERS: tuple[Retailer, ...] = US + UK + EU


def brand_slugs(countries: set[str] | None = None) -> list[tuple[str, str, str]]:
    """Flatten to [(slug, retailer_name, country), ...], de-duplicated.

    De-duplication is on the SLUG, keeping the first retailer that claims it:
    several banners genuinely share a tag (Lidl's `deluxe` shows up across
    Europe), and importing it twice would just do the same upsert twice.
    """
    seen: set[str] = set()
    out: list[tuple[str, str, str]] = []
    for r in ALL_RETAILERS:
        if countries and r.country not in countries:
            continue
        for slug in r.brands:
            if slug in seen:
                continue
            seen.add(slug)
            out.append((slug, r.name, r.country))
    return out


def summary() -> str:
    by_country: dict[str, int] = {}
    for r in ALL_RETAILERS:
        by_country[r.country] = by_country.get(r.country, 0) + len(r.brands)
    parts = ", ".join(f"{k}:{v}" for k, v in sorted(by_country.items()))
    return (
        f"{len(ALL_RETAILERS)} retailers, "
        f"{sum(len(r.brands) for r in ALL_RETAILERS)} brand tags ({parts})"
    )
