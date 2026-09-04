# Collecting the eval set from a dorm room

You don't need to cook. You need to **weigh**. Those are different problems and
only the first one requires a kitchen.

`manifest.csv` is now the dorm version. 18 of its 26 rows are `label` tier —
which is *better* truth than weighing your own cooking, because the
manufacturer already measured the oil you can't see. The original
cook-it-yourself plan is kept as `manifest_cook.csv` if you ever get a kitchen.

## The one thing you have to buy

A **digital kitchen scale, ₹400–600** on Amazon/Flipkart. Look for 1 g
resolution and a tare button. There is no substitute and nothing else on this
page works without it.

## Where the truth comes from, in order of quality

### 1. Ready-to-eat pouches — the unlock

MTR and Haldiram's sell the exact dishes you need, fully cooked, with a
nutrition panel printed on the pouch **including the cooking fat**:

> dal makhani · paneer butter masala · palak paneer · chole · rajma masala ·
> navratan korma · aloo mutter · bisibele bath · upma · poha · pongal ·
> sambar rice

₹60–100 each, 300 g, shelf-stable, heat in hot water or a microwave. About
₹800 covers every pouch row in the manifest.

The protocol, ~90 seconds:

1. Note the panel: kcal **per 100 g**, and the **net weight**.
2. Tare your plate on the scale. Plate the curry. **Record the grams.**
3. Add rice or roti (from the mess) and weigh that separately.
4. Photograph normally — phone in hand, whatever light you're in.
5. `truth_kcal = (curry_g / 100) × panel_kcal_per_100g` + the rice/roti.

That's ±2% truth on paneer butter masala, in a dorm, without a stove.

> **Watch the panel units.** Some brands print per 100 g, some per serving,
> some "as prepared". Photograph the panel each time as a second shot you
> don't put in `photos/` — it settles the argument a week later when you can't
> remember.

### 2. Mess food — weigh what's on your plate

You can't know the recipe, but you *can* know the mass. Weigh each component on
your own plate, take density from IFCT, and label it `recipe`. Four rows in the
manifest are these, and that's the right proportion — enough for realism,
not enough to weaken the conclusion.

**Ask the mess cook.** Hostel kitchens cook in known batches and the answer is
usually freely given: *"how much oil goes into one batch of sambar, and how
many people does it serve?"* Two litres across sixty servings is 33 ml a head —
about 300 kcal that no camera will ever see. Write it in `notes`. Even
approximate, it's the single most valuable number you can collect, and it's
the thing no competitor has bothered to ask.

If they'll tell you the whole recipe, that row is as good as weighed.

### 3. Assembled plates — real meals, no cooking

A plate doesn't have to be cooked to be a valid test:

- mess rice (weighed) + a packaged curd cup (label) = curd rice
- 2 bread slices + butter + 2 boiled eggs — all three have known values, and
  butter is the Western invisible-fat case
- banana (weighed, IFCT) + 4 biscuits (panel)

### 4. Kettle food

If you have a kettle or immersion rod: Maggi, cup noodles, instant poha, masala
oats. Whole packet, panel on the wrapper. If you add oil or butter, **weigh it**
and write it in `notes` — a teaspoon of ghee is 45 kcal and it's exactly the
error you're trying to measure.

### 5. Chain restaurants — `menu` tier

McDonald's, Domino's, Burger King, KFC publish nutrition. Record the exact
items ordered. Two rows only — published values are themselves averages, so
don't lean on them.

**Local restaurants and canteens don't count.** No published data means no
truth, and "I looked up a similar dish" is the `estimate` tier the validator
rejects.

## What you lose, and why it's fine

Pouch food is more consistent than home cooking, so your set slightly
understates real-world variance. That's an honest limitation to note in the
report — not a reason to skip it. A dataset of 18 label-tier rows with a stated
caveat beats 25 guessed rows with none, and it beats zero rows by an infinite
margin.

The four `recipe`-tier mess rows are what keep it honest, because a real mess
thali is messy in exactly the way the pouches aren't.

## Order of work

1. **Buy the scale.** Everything is blocked on this.
2. **Do the packaged rows first** — bar, milk, biscuits, banana, Maggi. Five
   rows in one evening, no shopping trip. It teaches you the routine on rows
   where mistakes are cheap.
3. **Order the pouches** in one go. Do 2–3 a week so it stays a normal week
   rather than a project.
4. **Weigh mess meals** whenever you remember. Aim for four.
5. **Adversarial last**, because by then you'll know what a normal shot looks
   like and can deliberately break it.

`ad-003` (half-eaten) needs the plate weighed **before and after** — the truth
is what you ate, not what you were served.

## The habit that saves the most rework

Photograph the scale readout, and the nutrition panel, as extra shots you
*don't* put in `photos/`. When you sit down to compute `truth_kcal` a week
later, "dal, 150g" in a note is worth nothing if you can't remember whether
that was the pouch weight or the plated weight. A photo settles it in a second.
