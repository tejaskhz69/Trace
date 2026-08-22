"""Exercises the 2015 free-exercise-db never had.

WHY THIS FILE EXISTS
The seeded catalogue comes from free-exercise-db, which was assembled around
2015 and reflects the machines and conventions of that era. Ten years of
hypertrophy practice later, it is missing the movements people actually
program — a user reported not being able to log a chest-supported dumbbell
row, a chest-supported machine row, or an incline machine chest press, and
none of those are obscure. They are staples.

Measured against the seeded 736:

    chest supported row    0 entries
    seal row               0
    pendlay row            0
    machine chest press    0
    incline machine press  0
    pec deck               0
    cable lateral raise    0
    meadows row            0

WHERE THE LIST COMES FROM
Jeff Nippard's published exercise tier lists (back, chest, shoulders, quads,
glutes, biceps, triceps), which are themselves built from the hypertrophy
literature, plus the movements that recur across current physique programming.
`tier` is recorded on each row for the ones that were ranked, because it is
genuinely useful information — but see the note on it below.

WHAT `tier` IS AND IS NOT
It is one coach's ranking, published for general trainees, and it is stored so
the app can ORDER a search result sensibly — a beginner typing "row" is better
served by chest-supported row above renegade row. It must never be rendered as
a verdict on the user's own programming. Someone whose gym has no hack squat
is not doing something wrong by doing leg press, and an app that implies
otherwise is being obnoxious with someone else's opinion.

Rows here are additive. The seeder upserts on name, so re-running is safe and
anything already present keeps its existing row.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModernExercise:
    name: str
    muscle_group: str
    equipment: str
    is_compound: bool
    secondary: tuple[str, ...] = field(default_factory=tuple)
    aliases: tuple[str, ...] = field(default_factory=tuple)
    #: S/A/B/C/D/F where a published ranking exists, else None.
    tier: str | None = None


#: Muscle groups match MUSCLE_TO_GROUP in seed_exercises.py:
#: chest, back, shoulders, legs, biceps, triceps, core, forearms, neck.
#: Equipment matches EQUIPMENT_MAP: barbell, dumbbell, cable, machine,
#: bodyweight, kettlebell, band, ezbar, smith, other.

EXERCISES: tuple[ModernExercise, ...] = (
    # =====================================================================
    # BACK — the reported gap, and the biggest one
    # =====================================================================
    ModernExercise(
        "Chest-Supported Dumbbell Row", "back", "dumbbell", True,
        ("biceps", "shoulders"),
        ("chest supported row", "csr", "chest supported db row", "incline bench row"),
        tier="S",
    ),
    ModernExercise(
        "Chest-Supported Barbell Row", "back", "barbell", True,
        ("biceps", "shoulders"),
        ("chest supported bb row", "incline barbell row"),
        tier="S",
    ),
    ModernExercise(
        "Chest-Supported Machine Row", "back", "machine", True,
        ("biceps", "shoulders"),
        ("machine row", "chest supported row machine", "hammer strength row"),
        tier="S",
    ),
    ModernExercise(
        "Chest-Supported T-Bar Row", "back", "machine", True,
        ("biceps", "shoulders"),
        ("t bar row", "tbar row", "supported t-bar"),
        tier="S",
    ),
    ModernExercise(
        "Seal Row", "back", "barbell", True, ("biceps",),
        ("seal rows", "bench row", "prone row"), tier="S",
    ),
    ModernExercise(
        "Pendlay Row", "back", "barbell", True, ("biceps", "shoulders"),
        ("pendlay", "dead stop row"), tier="B",
    ),
    ModernExercise(
        "Deficit Pendlay Row", "back", "barbell", True, ("biceps",),
        ("deficit row",), tier="A",
    ),
    ModernExercise(
        "Meadows Row", "back", "barbell", True, ("biceps", "shoulders"),
        ("meadows", "landmine row"), tier="S",
    ),
    ModernExercise(
        "Kroc Row", "back", "dumbbell", True, ("biceps", "forearms"),
        ("kroc", "heavy db row"), tier="A",
    ),
    ModernExercise(
        "Cross-Body Lat Pull-Around", "back", "cable", False, (),
        ("lat pull around", "pull around", "cross body pulldown"), tier="A",
    ),
    ModernExercise(
        "Half-Kneeling One-Arm Lat Pulldown", "back", "cable", True, ("biceps",),
        ("kneeling pulldown", "single arm pulldown"), tier="S",
    ),
    ModernExercise(
        "Neutral-Grip Lat Pulldown", "back", "cable", True, ("biceps",),
        ("neutral pulldown", "close grip pulldown"), tier="S",
    ),
    ModernExercise(
        "Cable Lat Pullover", "back", "cable", False, (),
        ("lat pullover", "straight arm pulldown", "cable pullover"), tier="S",
    ),
    ModernExercise(
        "Dumbbell Lat Pullover", "back", "dumbbell", False, ("chest",),
        ("db pullover",), tier="A",
    ),
    ModernExercise(
        "Neutral-Grip Pull-Up", "back", "bodyweight", True, ("biceps",),
        ("neutral pullup", "hammer grip pull up"), tier="S",
    ),
    ModernExercise(
        "Wide-Grip Pull-Up", "back", "bodyweight", True, ("biceps",),
        ("wide pullup",), tier="S",
    ),
    ModernExercise(
        "Seated Cable Row, Neutral Grip", "back", "cable", True, ("biceps",),
        ("cable row", "seated row"), tier="S",
    ),
    ModernExercise(
        "Single-Arm Cable Row", "back", "cable", True, ("biceps",),
        ("one arm cable row",), tier="S",
    ),
    ModernExercise(
        "Inverted Row", "back", "bodyweight", True, ("biceps",),
        ("body row", "australian pull up"), tier="C",
    ),
    ModernExercise(
        "Yates Row", "back", "barbell", True, ("biceps",),
        ("underhand row", "reverse grip row"), tier="C",
    ),

    # =====================================================================
    # CHEST — the other reported gap
    # =====================================================================
    ModernExercise(
        "Machine Chest Press", "chest", "machine", True, ("triceps", "shoulders"),
        ("chest press machine", "machine press", "hammer strength chest press"),
        tier="S",
    ),
    ModernExercise(
        "Incline Machine Chest Press", "chest", "machine", True,
        ("triceps", "shoulders"),
        ("incline machine press", "incline chest press machine"),
        tier="S",
    ),
    ModernExercise(
        "Decline Machine Chest Press", "chest", "machine", True, ("triceps",),
        ("decline machine press",), tier="A",
    ),
    ModernExercise(
        "Seated Cable Fly", "chest", "cable", False, ("shoulders",),
        ("seated fly", "cable flye", "cable fly"), tier="S",
    ),
    ModernExercise(
        "Standing Cable Fly", "chest", "cable", False, ("shoulders",),
        ("cable crossover", "standing fly"), tier="A",
    ),
    ModernExercise(
        "High-to-Low Cable Fly", "chest", "cable", False, (),
        ("low cable fly", "decline cable fly"), tier="A",
    ),
    ModernExercise(
        "Low-to-High Cable Fly", "chest", "cable", False, ("shoulders",),
        ("incline cable fly", "upward cable fly"), tier="A",
    ),
    ModernExercise(
        "Pec Deck Fly", "chest", "machine", False, ("shoulders",),
        ("pec deck", "machine fly", "butterfly"), tier="A",
    ),
    ModernExercise(
        "Cable Press-Around", "chest", "cable", False, (),
        ("press around", "cable press around"), tier="A",
    ),
    ModernExercise(
        "Smith Machine Bench Press", "chest", "smith", True,
        ("triceps", "shoulders"),
        ("smith bench", "smith press"), tier="A",
    ),
    ModernExercise(
        "Incline Smith Machine Bench Press", "chest", "smith", True,
        ("triceps", "shoulders"),
        ("incline smith press", "smith incline"), tier="A",
    ),
    ModernExercise(
        "Weighted Dip", "chest", "bodyweight", True, ("triceps", "shoulders"),
        ("dips", "chest dip", "weighted dips"), tier="A",
    ),

    # =====================================================================
    # SHOULDERS
    # =====================================================================
    ModernExercise(
        "Cable Lateral Raise", "shoulders", "cable", False, (),
        ("cable lat raise", "single arm cable lateral"), tier="S",
    ),
    ModernExercise(
        "Behind-the-Back Cable Lateral Raise", "shoulders", "cable", False, (),
        ("behind back lateral", "cuffed lateral raise"), tier="S",
    ),
    ModernExercise(
        "Cable Y-Raise", "shoulders", "cable", False, ("back",),
        ("y raise",), tier="S",
    ),
    ModernExercise(
        "Reverse Pec Deck", "shoulders", "machine", False, ("back",),
        ("reverse fly machine", "rear delt machine", "reverse pec dec"),
        tier="S",
    ),
    ModernExercise(
        "Reverse Cable Crossover", "shoulders", "cable", False, ("back",),
        ("rear delt cable", "reverse crossover"), tier="S",
    ),
    ModernExercise(
        "Machine Lateral Raise", "shoulders", "machine", False, (),
        ("lateral raise machine", "seated machine lateral"), tier="A",
    ),
    ModernExercise(
        "Machine Shoulder Press", "shoulders", "machine", True, ("triceps",),
        ("shoulder press machine", "machine ohp"), tier="A",
    ),
    ModernExercise(
        "Lean-In Dumbbell Lateral Raise", "shoulders", "dumbbell", False, (),
        ("lean in lateral", "leaning lateral raise"), tier="A",
    ),
    ModernExercise(
        "Side-Lying Dumbbell Lateral Raise", "shoulders", "dumbbell", False, (),
        ("lying lateral raise", "arnold side lying"), tier="A",
    ),
    ModernExercise(
        "Seated Dumbbell Shoulder Press", "shoulders", "dumbbell", True,
        ("triceps",), ("seated db press", "seated shoulder press"), tier="A",
    ),
    ModernExercise(
        "Rope Face Pull", "shoulders", "cable", False, ("back",),
        ("face pull", "rope facepull"), tier="A",
    ),
    ModernExercise(
        "Smith Machine Overhead Press", "shoulders", "smith", True, ("triceps",),
        ("smith ohp", "smith shoulder press"),
    ),

    # =====================================================================
    # LEGS — quads
    # =====================================================================
    ModernExercise(
        "Hack Squat", "legs", "machine", True, ("glutes",),
        ("hack squat machine", "hacks"), tier="S",
    ),
    ModernExercise(
        "Pendulum Squat", "legs", "machine", True, ("glutes",),
        ("pendulum",), tier="S",
    ),
    ModernExercise(
        "Smith Machine Squat", "legs", "smith", True, ("glutes",),
        ("smith squat",), tier="S",
    ),
    ModernExercise(
        "Bulgarian Split Squat", "legs", "dumbbell", True, ("glutes",),
        ("bulgarian", "rear foot elevated split squat", "rfess"), tier="S",
    ),
    ModernExercise(
        "45-Degree Leg Press", "legs", "machine", True, ("glutes",),
        ("leg press 45", "angled leg press"), tier="A",
    ),
    ModernExercise(
        "Horizontal Leg Press", "legs", "machine", True, ("glutes",),
        ("seated leg press",), tier="C",
    ),
    ModernExercise(
        "Reverse Nordic Curl", "legs", "bodyweight", False, (),
        ("reverse nordic",), tier="A",
    ),
    ModernExercise(
        "Sissy Squat", "legs", "bodyweight", False, (),
        ("sissy",), tier="B",
    ),
    ModernExercise(
        "Belt Squat", "legs", "machine", True, ("glutes",),
        ("belt squat machine",),
    ),
    ModernExercise(
        "Goblet Squat", "legs", "dumbbell", True, ("glutes", "core"),
        ("goblet",), tier="B",
    ),

    # ---- hamstrings and glutes ------------------------------------------
    ModernExercise(
        "Seated Leg Curl", "legs", "machine", False, (),
        ("seated hamstring curl",), tier="S",
    ),
    ModernExercise(
        "Lying Leg Curl", "legs", "machine", False, (),
        ("lying hamstring curl", "prone leg curl"), tier="A",
    ),
    ModernExercise(
        "Nordic Hamstring Curl", "legs", "bodyweight", False, (),
        ("nordic curl", "nordics"), tier="A",
    ),
    ModernExercise(
        "Dumbbell Romanian Deadlift", "legs", "dumbbell", True, ("back",),
        ("db rdl", "dumbbell rdl"), tier="A",
    ),
    ModernExercise(
        "Single-Leg Romanian Deadlift", "legs", "dumbbell", True, ("back", "core"),
        ("single leg rdl", "sl rdl"),
    ),
    ModernExercise(
        "Machine Hip Abduction", "legs", "machine", False, (),
        ("hip abduction", "abductor machine", "glute medius machine"), tier="S",
    ),
    ModernExercise(
        "Machine Hip Adduction", "legs", "machine", False, (),
        ("hip adduction", "adductor machine"),
    ),
    ModernExercise(
        "Machine Hip Thrust", "legs", "machine", True, ("hamstrings",),
        ("hip thrust machine", "glute drive"), tier="S",
    ),
    ModernExercise(
        "Cable Kickback", "legs", "cable", False, (),
        ("glute kickback", "cable glute kickback"),
    ),
    ModernExercise(
        "Back Extension", "legs", "bodyweight", True, ("back",),
        ("hyperextension", "45 degree back extension"), tier="A",
    ),
    ModernExercise(
        "Standing Calf Raise", "legs", "machine", False, (),
        ("calf raise", "standing calves"),
    ),
    ModernExercise(
        "Seated Calf Raise", "legs", "machine", False, (),
        ("seated calves", "soleus raise"),
    ),

    # =====================================================================
    # BICEPS
    # =====================================================================
    ModernExercise(
        "Face-Away Bayesian Cable Curl", "biceps", "cable", False, (),
        ("bayesian curl", "face away curl", "behind body cable curl"),
        tier="S",
    ),
    ModernExercise(
        "Bayesian Cable Curl", "biceps", "cable", False, (),
        ("cable curl behind",), tier="A",
    ),
    ModernExercise(
        "Dumbbell Preacher Curl", "biceps", "dumbbell", False, (),
        ("db preacher",), tier="S",
    ),
    ModernExercise(
        "Machine Preacher Curl", "biceps", "machine", False, (),
        ("preacher machine", "curl machine"), tier="S",
    ),
    ModernExercise(
        "Preacher Hammer Curl", "biceps", "dumbbell", False, ("forearms",),
        ("preacher hammer",), tier="S",
    ),
    ModernExercise(
        "Incline Dumbbell Curl", "biceps", "dumbbell", False, (),
        ("incline curl",), tier="A",
    ),
    ModernExercise(
        "Lying Dumbbell Curl", "biceps", "dumbbell", False, (),
        ("lying curl",), tier="A",
    ),
    ModernExercise(
        "Cable Curl", "biceps", "cable", False, (),
        ("standing cable curl",), tier="A",
    ),
    ModernExercise(
        "Inverse Zottman Curl", "biceps", "dumbbell", False, ("forearms",),
        ("zottman curl", "reverse zottman"), tier="A",
    ),
    ModernExercise(
        "Reverse Curl", "biceps", "ezbar", False, ("forearms",),
        ("reverse grip curl",),
    ),

    # =====================================================================
    # TRICEPS
    # =====================================================================
    ModernExercise(
        "Overhead Cable Triceps Extension", "triceps", "cable", False, (),
        ("overhead cable extension", "overhead tricep extension", "octe"),
        tier="S",
    ),
    ModernExercise(
        "Overhead Rope Triceps Extension", "triceps", "cable", False, (),
        ("rope overhead extension",), tier="A",
    ),
    ModernExercise(
        "Katana Cable Triceps Extension", "triceps", "cable", False, (),
        ("katana extension",), tier="A",
    ),
    ModernExercise(
        "Cable Triceps Pressdown, Bar", "triceps", "cable", False, (),
        ("bar pressdown", "straight bar pushdown"), tier="A",
    ),
    ModernExercise(
        "Cable Triceps Pressdown, Rope", "triceps", "cable", False, (),
        ("rope pressdown", "rope pushdown"), tier="B",
    ),
    ModernExercise(
        "Dumbbell Skullcrusher", "triceps", "dumbbell", False, (),
        ("db skullcrusher", "db skull crusher"), tier="A",
    ),
    ModernExercise(
        "Smith Machine JM Press", "triceps", "smith", True, ("chest",),
        ("smith jm press",), tier="A",
    ),
    ModernExercise(
        "Cable Triceps Kickback", "triceps", "cable", False, (),
        ("cable kickback tricep",), tier="A",
    ),
    ModernExercise(
        "Machine Triceps Dip", "triceps", "machine", True, ("chest",),
        ("dip machine", "machine dips"), tier="B",
    ),
    ModernExercise(
        "Single-Arm Dumbbell Overhead Extension", "triceps", "dumbbell", False, (),
        ("one arm overhead extension",), tier="A",
    ),

    # =====================================================================
    # CORE
    # =====================================================================
    ModernExercise(
        "Cable Crunch", "core", "cable", False, (),
        ("kneeling cable crunch", "rope crunch"),
    ),
    ModernExercise(
        "Hanging Leg Raise", "core", "bodyweight", False, (),
        ("hanging knee raise", "leg raise"),
    ),
    ModernExercise(
        "Captain's Chair Knee Raise", "core", "bodyweight", False, (),
        ("captains chair", "vertical knee raise"),
    ),
    ModernExercise(
        "Ab Wheel Rollout", "core", "other", False, (),
        ("ab wheel", "ab rollout"),
    ),
    ModernExercise(
        "Machine Crunch", "core", "machine", False, (),
        ("ab machine", "crunch machine"),
    ),
    ModernExercise(
        "Pallof Press", "core", "cable", False, (),
        ("pallof", "anti rotation press"),
    ),
    ModernExercise(
        "Weighted Plank", "core", "bodyweight", False, (),
        ("loaded plank",),
    ),
    ModernExercise(
        "Copenhagen Plank", "core", "bodyweight", False, ("legs",),
        ("copenhagen", "adductor plank"),
    ),

    # =====================================================================
    # FOREARMS AND TRAPS
    # =====================================================================
    ModernExercise(
        "Dumbbell Shrug", "back", "dumbbell", False, (),
        ("db shrug",),
    ),
    ModernExercise(
        "Cable Shrug", "back", "cable", False, (),
        ("cable trap shrug",),
    ),
    ModernExercise(
        "Farmer's Carry", "forearms", "dumbbell", True, ("core", "back"),
        ("farmers walk", "farmer carry", "loaded carry"),
    ),
    ModernExercise(
        "Wrist Roller", "forearms", "other", False, (),
        ("forearm roller",),
    ),

    # =====================================================================
    # FROM CHRIS BUMSTEAD'S PUBLISHED SPLIT
    #
    # Cross-checked against the tier lists above rather than taken on trust:
    # a Mr Olympia's programme is built around his own leverages and a drug
    # protocol most users do not share. What it IS good for is surfacing the
    # machine and cable variations that competitive physique training leans
    # on and a 2015 database has never heard of -- which is exactly the gap
    # reported here. His back day alone contains three chest-supported row
    # variations, all of which were missing.
    # =====================================================================
    ModernExercise(
        "Single-Leg Press", "legs", "machine", True, ("glutes",),
        ("unilateral leg press", "one leg press", "single leg leg press"),
    ),
    ModernExercise(
        "Standing Leg Curl", "legs", "machine", False, (),
        ("standing hamstring curl", "single leg standing curl"),
    ),
    ModernExercise(
        "Incline Dumbbell Fly", "chest", "dumbbell", False, ("shoulders",),
        ("incline fly", "incline db fly"),
    ),
    ModernExercise(
        "Incline Dumbbell Skullcrusher", "triceps", "dumbbell", False, (),
        ("incline skullcrusher", "incline skull crusher"),
    ),
    ModernExercise(
        "EZ-Bar Preacher Curl", "biceps", "ezbar", False, (),
        ("ez preacher curl", "preacher curl"),
    ),
    ModernExercise(
        "Cross-Body Cable Triceps Extension", "triceps", "cable", False, (),
        ("cross body triceps", "cable cross body extension"),
    ),
    ModernExercise(
        "V-Bar Cable Curl", "biceps", "cable", False, (),
        ("low pulley curl", "v bar curl"),
    ),
    ModernExercise(
        "Close-Grip Underhand Lat Pulldown", "back", "cable", True, ("biceps",),
        ("underhand pulldown", "reverse grip pulldown", "supinated pulldown"),
    ),
    ModernExercise(
        "Machine Chest Fly", "chest", "machine", False, ("shoulders",),
        ("machine fly", "seated machine fly"),
    ),
    ModernExercise(
        "Cable Lat Extension", "back", "cable", False, (),
        ("lat extension", "cable lat pushdown"),
    ),
    ModernExercise(
        "Seated Dumbbell Lateral Raise", "shoulders", "dumbbell", False, (),
        ("seated lateral raise", "seated lat raise"),
    ),
    ModernExercise(
        "Hammer Strength Incline Press", "chest", "machine", True,
        ("triceps", "shoulders"),
        ("hammer incline", "plate loaded incline press"),
    ),

    # =====================================================================
    # BATCH 2 - VARIATION, not novelty
    #
    # From the wider coaching corpus: John Meadows (Mountain Dog), Sam
    # Sulek's machine-heavy split, Nick Walker and Derek Lunsford's Olympia
    # prep, and Renaissance Periodization's programming.
    #
    # THE SELECTION RULE, because "more exercises" is not automatically
    # better: a variation earns a row only when it is A DIFFERENT THING TO
    # LOG - a different angle, grip, unilateral/bilateral split, or machine -
    # such that its working weight and its progression are genuinely separate
    # from the parent movement. A single-arm lat pulldown qualifies, because
    # 40 kg means something different there and it tracks its own progression.
    # "Bench press but with your feet up" does not, and adding it would only
    # make search worse for everyone.
    # =====================================================================

    # ---- back ------------------------------------------------------------
    ModernExercise(
        "Meadows Run", "back", "barbell", True, ("biceps",),
        ("meadows run",),
    ),
    ModernExercise(
        "Machine Low Row", "back", "machine", True, ("biceps",),
        ("low row machine", "seated machine low row"),
    ),
    ModernExercise(
        "Machine Lat Pullover", "back", "machine", False, (),
        ("pullover machine", "nautilus pullover"),
    ),
    ModernExercise(
        "Single-Arm Lat Pulldown", "back", "cable", True, ("biceps",),
        ("one arm pulldown", "unilateral pulldown"),
    ),
    ModernExercise(
        "Single-Arm Straight-Arm Pulldown", "back", "cable", False, (),
        ("one arm straight arm pulldown", "side straight arm lat pulldown"),
    ),
    ModernExercise(
        "Wide-Grip Seated Cable Row", "back", "cable", True, ("biceps", "shoulders"),
        ("wide cable row", "wide grip row"),
    ),
    ModernExercise(
        "Hammer-Grip Lat Pulldown", "back", "cable", True, ("biceps",),
        ("hammer grip pulldown", "wide hammer pulldown"),
    ),
    ModernExercise(
        "Landmine Row", "back", "barbell", True, ("biceps",),
        ("landmine rows",),
    ),
    ModernExercise(
        "Chest-Supported Cable Row", "back", "cable", True, ("biceps",),
        ("supported cable row",),
    ),
    ModernExercise(
        "Rack Pull", "back", "barbell", True, ("legs",),
        ("rack pulls", "block pull"),
    ),
    ModernExercise(
        "Snatch-Grip Deadlift", "back", "barbell", True, ("legs",),
        ("snatch grip dl",),
    ),

    # ---- chest -----------------------------------------------------------
    ModernExercise(
        "Bent-Over Cable Fly", "chest", "cable", False, ("shoulders",),
        ("bent over cable chest fly", "hinged cable fly"),
    ),
    ModernExercise(
        "Single-Arm Cable Fly", "chest", "cable", False, (),
        ("one arm cable fly", "unilateral cable fly"),
    ),
    ModernExercise(
        "Single-Arm Machine Chest Press", "chest", "machine", True, ("triceps",),
        ("one arm machine press", "unilateral chest press"),
    ),
    ModernExercise(
        "Deficit Push-Up", "chest", "bodyweight", True, ("triceps",),
        ("deficit pushup", "elevated handle push up"),
    ),
    ModernExercise(
        "Incline Cable Press", "chest", "cable", True, ("triceps", "shoulders"),
        ("cable incline press",),
    ),
    ModernExercise(
        "Floor Press", "chest", "barbell", True, ("triceps",),
        ("barbell floor press",),
    ),

    # ---- shoulders -------------------------------------------------------
    ModernExercise(
        "Incline Y-Raise", "shoulders", "dumbbell", False, ("back",),
        ("incline y raise", "prone y raise"),
    ),
    ModernExercise(
        "Lying Face Pull", "shoulders", "cable", False, ("back",),
        ("lying facepull", "prone face pull"),
    ),
    ModernExercise(
        "Cable Rear Delt Fly", "shoulders", "cable", False, ("back",),
        ("rear delt cable fly", "cable reverse fly"),
    ),
    ModernExercise(
        "Single-Arm Dumbbell Lateral Raise", "shoulders", "dumbbell", False, (),
        ("one arm lateral raise",),
    ),
    ModernExercise(
        "Cable Upright Row", "shoulders", "cable", True, ("back",),
        ("cable upright rows",),
    ),
    ModernExercise(
        "Landmine Press", "shoulders", "barbell", True, ("chest", "triceps"),
        ("landmine shoulder press", "viking press"),
    ),
    ModernExercise(
        "Arnold Press", "shoulders", "dumbbell", True, ("triceps",),
        ("arnold presses",),
    ),
    ModernExercise(
        "Z-Press", "shoulders", "barbell", True, ("core", "triceps"),
        ("z press", "seated overhead press floor"),
    ),

    # ---- legs ------------------------------------------------------------
    ModernExercise(
        "Heel-Elevated Back Squat", "legs", "barbell", True, ("glutes",),
        ("heel elevated squat", "plate elevated squat"),
    ),
    ModernExercise(
        "Single-Leg Extension", "legs", "machine", False, (),
        ("unilateral leg extension", "one leg extension"),
    ),
    ModernExercise(
        "Single-Leg Curl", "legs", "machine", False, (),
        ("unilateral leg curl", "one leg curl"),
    ),
    ModernExercise(
        "Front-Foot-Elevated Split Squat", "legs", "dumbbell", True, ("glutes",),
        ("deficit split squat",),
    ),
    ModernExercise(
        "Walking Lunge", "legs", "dumbbell", True, ("glutes",),
        ("walking lunges",),
    ),
    ModernExercise(
        "Reverse Lunge", "legs", "dumbbell", True, ("glutes",),
        ("reverse lunges", "backward lunge"),
    ),
    ModernExercise(
        "Cyclist Squat", "legs", "barbell", True, (),
        ("close stance heel elevated squat",),
    ),
    ModernExercise(
        "Landmine Squat", "legs", "barbell", True, ("glutes",),
        ("landmine goblet squat",),
    ),
    ModernExercise(
        "Glute-Ham Raise", "legs", "bodyweight", True, ("back",),
        ("ghr", "glute ham developer"),
    ),
    ModernExercise(
        "Good Morning", "legs", "barbell", True, ("back",),
        ("good mornings",),
    ),
    ModernExercise(
        "Donkey Calf Raise", "legs", "machine", False, (),
        ("donkey calves",),
    ),
    ModernExercise(
        "Leg Press Calf Raise", "legs", "machine", False, (),
        ("calf press", "leg press calves"),
    ),
    ModernExercise(
        "Tibialis Raise", "legs", "bodyweight", False, (),
        ("tib raise", "tibialis anterior raise"),
    ),

    # ---- arms ------------------------------------------------------------
    ModernExercise(
        "Dual Rope Triceps Extension", "triceps", "cable", False, (),
        ("dual rope extension", "double rope pushdown"),
    ),
    ModernExercise(
        "Machine Biceps Curl", "biceps", "machine", False, (),
        ("seated machine curl", "biceps curl machine"),
    ),
    ModernExercise(
        "Single-Arm Cable Curl", "biceps", "cable", False, (),
        ("one arm cable curl",),
    ),
    ModernExercise(
        "Concentration Curl", "biceps", "dumbbell", False, (),
        ("concentration curls",),
    ),
    ModernExercise(
        "Cable Hammer Curl", "biceps", "cable", False, ("forearms",),
        ("rope hammer curl", "rope curl"),
    ),
    ModernExercise(
        "Overhead Cable Curl", "biceps", "cable", False, (),
        ("high cable curl", "double biceps curl"),
    ),
    ModernExercise(
        "Single-Arm Cable Pressdown", "triceps", "cable", False, (),
        ("one arm pushdown",),
    ),
    ModernExercise(
        "Tate Press", "triceps", "dumbbell", False, (),
        ("tate presses",),
    ),
    ModernExercise(
        "Barbell Wrist Curl", "forearms", "barbell", False, (),
        ("wrist curl",),
    ),
    ModernExercise(
        "Reverse Wrist Curl", "forearms", "barbell", False, (),
        ("reverse wrist curls", "wrist extension"),
    ),
)


def by_group() -> dict[str, list[ModernExercise]]:
    out: dict[str, list[ModernExercise]] = {}
    for e in EXERCISES:
        out.setdefault(e.muscle_group, []).append(e)
    return out
