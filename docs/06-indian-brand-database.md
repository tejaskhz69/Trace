# The Indian brand database — MTR, Gits, Aachi and the rest

*What I found pulling nutrition data for South Indian ready-mix brands, and why it changed the design.*

---

## The headline finding

I went looking for MTR's nutrition data. I found it — and it's wrong.

**Open Food Facts entry `8901042954516` (MTR Rava Idli Mix) declares 1.5 g protein per 100 g.**

That product is 80% semolina. Semolina is ~12 g protein/100 g, so the semolina alone contributes 9.6 g. Add Bengal gram splits (~20 g protein/100 g) and the floor is ~11 g. Cross-checks:

| Product | Protein /100 g |
|---|---|
| MTR Dosa Mix | 12 g |
| Gits Rava Idli Mix | 12 g |
| MTR Multigrain Dosa | 10 g |
| **MTR Rava Idli (OFF)** | **1.5 g** ← wrong by ~7× |

The same entry lists 9 g salt per 100 g (3,600 mg sodium), also implausible.

**Why this specifically matters to you:** protein is the input your Strength Adjudication Engine reads. A user eating rava idli four mornings a week would show as chronically under-eating protein, and the engine would tell them their bulk isn't working when it is. A wrong number here doesn't just make one meal inaccurate — it corrupts the feature you're selling.

---

## It isn't one bad row

I swept ~55 products across 12 brands (MTR, Gits, Aachi, Sakthi, Eastern, Nirapara, Double Horse, Brahmins, Melam, Bambino, Anil, iD Fresh). **Roughly a third had at least one implausible value.**

| Product | Defect | Why it's wrong |
|---|---|---|
| MTR Rava Idli (OFF) | 1.5 g protein | 80% semolina — impossible |
| Aachi Rice Idli (OFF `8904209305541`) | 133 kcal/100 g | That's an **as-prepared** panel filed under a dry-mix barcode. A dry idli mix is 330–360 |
| Gits Sambar Mix (USDA) | 5,480 mg sodium | 13.7 g salt per 100 g |
| Eastern Rice Rava (USDA) | 46.7 g fibre | Physically impossible outside pure bran |
| Bambino Multigrain Vermicelli | sodium "16.29 **g**" | g/mg unit error — should be 16.29 mg |
| Aachi Idli Podi | 2.3 mg sodium, 0.1 g sat fat on 40 g fat | Salted, oil-roasted product. No edible oil is 0.25% saturated |
| Sakthi Sambar Powder (OFF) | only ~25 g of 100 g accounted for | Community estimate, not a label transcription |
| Eastern (4 SKUs) | identical `354/8/78/1/0.5/0.2` panel | One generic block copy-pasted across four products |
| Nirapara, Double Horse, Brahmins podis | fat = 0.0 g | Rice flour is 0.5–1.5 g. Label rounding, not a true zero |

**Conclusion: you cannot bulk-import Indian food data unvalidated.** That's why the pipeline now has three stages instead of one.

---

## 1. Ingestion — by GS1 prefix, not brand name

Brand-name matching in Open Food Facts fails: the same company appears as "MTR", "MTR Foods", "M.T.R.", "Mtr Foods Pvt Ltd", and blank. The **GS1 company prefix** is assigned by GS1 India and is stable across every SKU a company registers.

Confirmed prefixes (India's country prefix is `890`; the next digits identify the company):

| Brand | Prefix | Brand | Prefix |
|---|---|---|---|
| MTR | `8901042` | Nirapara | `8904010` |
| Gits | `8901155` | Double Horse | `8904011` |
| Aachi | `8906021`, `8904209` | Brahmins | `8906014` |
| Sakthi | `8906002` | Melam | `8901743` |
| Eastern | `8901440`, `8902850` | Anil | `8906042` |
| Bambino | `8904287` | Pintola | `8906136` |

```bash
wget https://static.openfoodfacts.org/data/openfoodfacts-products.jsonl.gz

python -m app.scripts.ingest_indian_brands --dump openfoodfacts-products.jsonl.gz
python -m app.scripts.ingest_indian_brands --dump ... --brand MTR --dry-run
python -m app.scripts.ingest_indian_brands --dump ... --all-india   # every 890 product
```

Failed rows go to `quarantine.json`, not the catalogue. **Read that file** — every entry is a product your users can physically scan but would get wrong data for. It's a prioritised worklist.

---

## 2. Validation — `services/nutrition_validator.py`

Ten checks. Each one exists because of a specific defect above.

| Check | Catches |
|---|---|
| **Ingredient consistency** | MTR's 1.5 g protein. If ≥50% of the product is identified and those ingredients imply ~11 g protein, 1.5 g is a transcription error |
| **Category bands** | Aachi's 133 kcal. A dry mix below 60% of its band is almost certainly an as-prepared panel — flagged as exactly that |
| **Mass balance** | Sakthi's 25-of-100 g. Cereal products floor at 60 g accounted; masalas at 45 g (they legitimately carry 10–25% salt and ash) |
| **Sodium unit error** | Bambino's "16.29 g". If the value is absurd but plausible ÷1000, it's a g/mg slip |
| **Near-zero sodium on salted product** | Aachi's 2.3 mg |
| **Saturated fat ratio** | 0.1 g saturated on 40.3 g fat. No edible oil is under ~7% saturated; coconut and palm are 50–90% |
| **Atwater reconciliation** | Declared kcal vs macro-derived kcal (>35% drift = error) |
| **Fibre, sugar, macro-sum ceilings** | 46.7 g fibre; sugar > carbs; macros > 100 g |
| **Zero-fat artefact** | Rice flour at 0.0 g |
| **Duplicate panel fingerprinting** | Eastern's four-SKU shared block |

Plus a compounding rule: **four independent warnings on one panel = quarantine**, even when no single check is fatal. A panel that trips four different sanity checks isn't marginal, it's wrong.

Verdicts are `accept` / `accept_with_corrections` (serves at reduced `data_quality`, so it ranks below verified rows in search) / `quarantine` (never served).

**A note on tuning it honestly.** When I first ran this against my own curated catalogue it quarantined two of my rows. Both were the *validator's* fault, not the data's:

- *Double Horse Coconut Chutney Powder* — a 60 g mass-balance floor is right for flour but wrong for spice blends, which carry unlisted salt and ash. Split the threshold by category.
- *Brahmins Chukku Kappi* — 90.7 g carbs of which 85.4 g sugar. It's jaggery and dry ginger, not a savoury masala. Needed its own `sweet_powder` category.

Both fixed. If your validator never fires false positives it isn't strict enough; if you never investigate them, you'll tune it into uselessness.

---

## 3. As-prepared conversion — `services/preparation.py`

**This is the part that's actually a competitive advantage.**

Every label on an Indian ready-mix is per 100 g of **dry mix**. Nobody eats dry mix. A 200 g pack of rava idli mix becomes ~608 g of idli once you add 415 g of curd.

Measured dilution factors, all verified against manufacturer "makes N per pack" claims:

| Preparation | Dry mix | Prepared | **Dilution** | Per piece |
|---|---|---|---|---|
| Upma | 200 g | 865 g | **4.32×** | 216 g serving, 229 kcal |
| Rice idli | 200 g | 670 g | **3.35×** | 37 g idli, 43 kcal |
| Gulab jamun | 175 g | 535 g | **3.06×** | 27 g, 77 kcal |
| Rava idli | 200 g | 608 g | **3.04×** | 51 g idli, 85 kcal |
| Dhokla | 200 g | 441 g | **2.21×** | 18 g piece, 43 kcal |
| Dosa | 200 g | 432 g | **2.16×** | 54 g dosa, 139 kcal |
| Medu vada | 200 g | 350 g | **1.75×** | 19 g vada, 70 kcal |

**Logging the label value against the finished dish overstates intake by 1.75× to 4.3×.** Cal AI, MacroFactor and MyFitnessPal all get this wrong.

The model handles three transforms:

- **Hydration** — water, curd, milk added. The curd in rava idli contributes ~250 kcal and 13 g protein; it is *not* a rounding detail.
- **Evaporation** — dosa loses 42% of its batter water on the tawa, rava dosa 50%.
- **Fat uptake** — deep-fried items *absorb* oil. Medu vada takes on 18% of its **finished** weight (anchored on Sakhale et al. 2011, which measured 18.34% in control samosa). Applying that percentage to raw dough instead — which is the intuitive mistake — overstates by ~20%, because the item also *loses* water before it gains oil.
- **Syrup soak** — a finished gulab jamun is **more absorbed syrup than dough**: 1.2–1.9 g of syrup per gram of fried ball.

### Two things this unlocks in the UI

**Better logging.** Don't ask "how many grams of dry mix?" — nobody knows. Ask **"how many idlis?"**

```
POST /api/preparations/convert
  { "food_item_id": "...", "preparation_key": "rava_idli" }
→ 12 idlis, 51 g each, 85 kcal each
  warning: "The label is per 100 g of DRY MIX. Prepared, it weighs 3.0× more."
```

**The pan-oil question.** Cooking fat is usually a bigger swing than the mix itself:

| | Dry (no oil) | Home (1 tsp/dosa) | Restaurant (3 tsp) |
|---|---|---|---|
| kcal per dosa | 88 | 139 | 220 |

Upma is the same story — 20 g of oil on 200 g of mix is 180 kcal of a ~920 kcal batch. So oil is an **editable field**, not a baked-in constant. It pairs exactly with the photo scanner's clarifying question ("how much ghee?") from the product blueprint.

---

## What shipped

```
services/api/app/
├── services/
│   ├── nutrition_validator.py    10 checks, 3 verdicts, category bands
│   └── preparation.py            7 preparations, 3 transforms, 15 ingredients
├── routers/preparations.py       GET /api/preparations · POST /convert
└── scripts/
    ├── ingest_indian_brands.py   GS1-prefix import + quarantine file
    └── seed_indian_brands.py     44 curated products, 12 brands
tests/test_food_data.py           26 tests (56 total in the suite)
```

Every correction is recorded in `data_notes` on the row, so the decision is auditable rather than a silent overwrite.

```bash
python -m app.scripts.seed_indian_brands --dry-run   # 44/44 pass
python -m pytest tests/ -q                           # 56 passed
```

---

## What I'd do next

1. **Photograph the packs.** Ten minutes in a supermarket beats any amount of scraping. Every brand site — gitsfood.com, aachifoods.com, sakthimasala.com, nirapara.com, melam.com, doublehorse.in, brahminsfoods.com — publishes product pages with **no nutrition panel at all**. The label is the only authoritative source, and OCR-ing a photo into the validator is a 30-line script.

2. **Mine the barcode-miss log.** Every failed scan in production is a demand-ranked request for a specific product. That log tells you which prefixes to add next — for free, ordered by how much your users actually care.

3. **Add the remaining preparations.** Poha, appam, idiyappam, puttu, sambar, payasam-from-mix. The framework is there; each one is ~15 lines of spec.

4. **Ship "makes N per pack" as a first-class field.** Gits prints it on every pack and it's the single best normalisation anchor you have — it's machine-readable straight out of Amazon.in listing titles.

5. **Resist the row-count goal.** 44 verified products with correct serving sizes will serve your users better than 10,000 imported blind. The MTR entry is the proof: it was *available*, it was *free*, and it was *wrong*.

---

*Sources: [Open Food Facts](https://world.openfoodfacts.org/data) (ODbL) · [MTR Rava Idli on OFF](https://world.openfoodfacts.org/product/8901042954516/rava-idli-mtr) · [USDA FoodData Central](https://fdc.nal.usda.gov) · [Sakhale et al. 2011, oil uptake in samosa](https://pmc.ncbi.nlm.nih.gov/articles/PMC3551041) · [deep-fat frying oil uptake review](https://academic.oup.com/ijfst/article/43/8/1410/7864485) · [Gupta et al. 2019, PLOS ONE, 75 Indian snacks](https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0225798)*
