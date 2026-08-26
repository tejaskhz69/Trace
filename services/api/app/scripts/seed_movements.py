#!/usr/bin/env python3
"""Seed the MOVEMENT catalogue.

THE ONE DESIGN DECISION THAT MATTERS
------------------------------------
A row is a **movement**, never a machine. "Chest-Supported Row" is one row;
a PRIME Extreme Row, a Hammer Strength Iso-Lateral Row and a Panatta seal row
are three *stations* you can perform it on.

That split exists because of a hard constraint in adjudication.py:
`MIN_SESSIONS = 8`. A verdict needs eight sessions of a lift. Split one
movement into five brand rows and a lifter who trains it weekly waits forty
weeks for any of them to trend -- the strength engine gets *worse* the more
equipment you add. Machines as rows would quietly break the feature this
whole product is built on.

SO HOW DOES A USER IN CANADA FIND THEIR PRIME MACHINE?
------------------------------------------------------
Through `aliases`. Brand and model names are search terms attached to the
movement, not rows of their own:

    "prime row"            -> Chest-Supported Row
    "hammer strength row"  -> Chest-Supported Row
    "iso lateral row"      -> Chest-Supported Row
    "1fe001"               -> Lat Pulldown          (Panatta model code)
    "pw412"                -> Hack Squat            (Atlantis model code)

369 aliases across 154 movements. Search finds the machine; the catalogue
stays one row per movement; the trend stays continuous.

The machine itself is then recorded as a **station** on the set (see
Station in models.py) -- brand, model, loading type, and for PRIME-style
adjustable-cam machines the profile setting, which genuinely changes the
exercise at the same load.

WHY LOADING TYPE LIVES ON THE STATION, NOT HERE
-----------------------------------------------
The same movement is plate-loaded on one machine and pin-loaded on another.
`equipment` below is the *coarse* class used for filtering and for the
bodyweight/barbell distinction the e1RM maths needs. Precise loading is a
property of the physical machine, which only the user standing in front of
it can tell us.

WHAT IS DELIBERATELY ABSENT
---------------------------
Any cross-brand load conversion. There is no published dataset of effective
load ratios for plate-loaded machines -- leverage runs somewhere between 2:1
and 5:1, undisclosed and brand-specific, and it changes through the range of
motion. Manufacturers themselves describe printed numbers as "an estimate of
effective resistance, not a promise". Shipping a converter would be
pseudo-precision. Progress is compared within a station, never across.

Also absent: anyone's program content. Exercise names and movement
descriptions are facts and are used freely here. Set/rep schemes, exercise
rankings and tier lists are their authors' work product and are not.

USAGE
    python -m app.scripts.seed_movements
    python -m app.scripts.seed_movements --dry-run
    python -m app.scripts.seed_movements --pattern h-pull
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from collections import Counter

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ..db import SessionLocal
from ..services.catalogue import CatalogueEntry, merge_aliases, plan_seed
from ._catalogue_report import report_collisions
from ._schema_guard import require_tables
from ..models import Exercise

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed.movements")

# (name, muscle, secondary[], equipment, is_compound, pattern, profile, unilateral, aliases[])
#
# `profile` is where in the range of motion the movement is hardest --
# lengthened / mid / shortened. It drives exercise SELECTION advice (a
# programme wants both ends covered) and it is the axis the 2023-26
# stretch-mediated-hypertrophy literature is about. It is NOT a load figure.
#
# `aliases` absorbs brand and model names on purpose. See the docstring.
E: list[tuple] = []


def add(name, muscle, sec, equip, comp, pattern, profile, uni, aliases):
    E.append((name, muscle, sec, equip, comp, pattern, profile, uni, aliases))



# ---------------- SQUAT PATTERN ----------------
add("Barbell Back Squat","quads",["glutes","hamstrings","core"],"barbell",True,"squat","mid",False,
    ["back squat","bb squat","barbell squat","high bar squat","low bar squat"])
add("Barbell Front Squat","quads",["glutes","core"],"barbell",True,"squat","lengthened",False,
    ["front squat","bb front squat"])
add("Hack Squat","quads",["glutes"],"machine",True,"squat","lengthened",False,
    ["hack squat machine","panatta hack","atlantis hack squat","pw412"])
add("Pendulum Squat","quads",["glutes"],"machine",True,"squat","lengthened",False,
    ["pendulum","prime pendulum squat","panatta pendulum","arsenal pendulum"])
add("Smith Machine Squat","quads",["glutes"],"smith",True,"squat","mid",False,["smith squat"])
add("Leg Press","quads",["glutes","hamstrings"],"machine",True,"squat","mid",False,
    ["leg press machine","45 degree leg press","hammer strength leg press","cybex leg press",
     "panatta leg press","horizontal leg press"])
add("Single-Leg Press","quads",["glutes"],"machine",True,"squat","mid",True,
    ["unilateral leg press","one leg press","pw419"])
add("Goblet Squat","quads",["glutes","core"],"dumbbell",True,"squat","lengthened",False,["goblet"])
add("Bulgarian Split Squat","quads",["glutes"],"dumbbell",True,"lunge","lengthened",True,
    ["split squat","bss","rear foot elevated split squat","rfess"])
add("Dumbbell Lunge","quads",["glutes","hamstrings"],"dumbbell",True,"lunge","mid",True,
    ["db lunge"])
add("Reverse Lunge","quads",["glutes"],"dumbbell",True,"lunge","mid",True,["backward lunge"])
add("Cyclist Squat","quads",["glutes"],"barbell",True,"squat","lengthened",False,
    ["heels elevated squat","narrow stance squat","quad squat"])
add("Zercher Squat","quads",["glutes","core","upper back"],"barbell",True,"squat","mid",False,["zercher"])
add("Hatfield Squat","quads",["glutes"],"barbell",True,"squat","mid",False,
    ["safety bar squat with handles","hatfield"])
add("Anderson Squat","quads",["glutes"],"barbell",True,"squat","shortened",False,
    ["pin squat","dead stop squat"])
add("Sissy Squat","quads",[],"bodyweight",False,"squat","lengthened",False,["sissy"])
add("Belt Squat","quads",["glutes"],"machine",True,"squat","mid",False,["belt squat machine","pit shark"])
add("Step-Up","quads",["glutes"],"dumbbell",True,"lunge","mid",True,["box step up","dumbbell step up"])

# ---------------- HINGE ----------------
add("Conventional Deadlift","hamstrings",["glutes","back","traps"],"barbell",True,"hinge","mid",False,
    ["deadlift","dl","conventional dl"])
add("Sumo Deadlift","glutes",["quads","hamstrings","back"],"barbell",True,"hinge","mid",False,["sumo dl","sumo"])
add("Romanian Deadlift","hamstrings",["glutes","back"],"barbell",True,"hinge","lengthened",False,
    ["rdl","romanian dl"])
add("Dumbbell Romanian Deadlift","hamstrings",["glutes"],"dumbbell",True,"hinge","lengthened",False,["db rdl"])
add("Single-Leg Romanian Deadlift","hamstrings",["glutes","core"],"dumbbell",True,"hinge","lengthened",True,
    ["sl rdl","single leg rdl"])
add("Deficit Deadlift","hamstrings",["glutes","back"],"barbell",True,"hinge","lengthened",False,["deficit dl"])
add("Trap Bar Deadlift","glutes",["quads","hamstrings","back"],"barbell",True,"hinge","mid",False,
    ["hex bar deadlift","trap bar dl"])
add("Rack Pull","back",["traps","glutes"],"barbell",True,"hinge","shortened",False,["block pull"])
add("Jefferson Deadlift","glutes",["quads","back"],"barbell",True,"hinge","mid",False,
    ["jefferson lift","straddle deadlift"])
add("Dimel Deadlift","hamstrings",["glutes"],"barbell",True,"hinge","lengthened",False,["dimel"])
add("Good Morning","hamstrings",["glutes","back"],"barbell",True,"hinge","lengthened",False,["gm"])
add("Hip Thrust","glutes",["hamstrings"],"barbell",True,"hinge","shortened",False,
    ["barbell hip thrust","glute bridge","glute drive","nautilus glute drive"])
add("Machine Hip Thrust","glutes",["hamstrings"],"machine",True,"hinge","shortened",False,
    ["hip thrust machine","glute drive machine","booty builder","glutebuilder","precor glutebuilder"])
add("Back Extension","back",["glutes","hamstrings"],"bodyweight",False,"hinge","lengthened",False,
    ["hyperextension","45 degree back extension","roman chair"])
add("Reverse Hyperextension","glutes",["hamstrings","back"],"machine",False,"hinge","shortened",False,["reverse hyper"])
add("Nordic Curl","hamstrings",[],"bodyweight",False,"hinge","lengthened",False,
    ["nordic ham curl","nordic hamstring curl"])
add("Kettlebell Swing","glutes",["hamstrings","back"],"other",True,"hinge","mid",False,["kb swing","swing"])

# ---------------- HORIZONTAL PRESS ----------------
add("Barbell Bench Press","chest",["triceps","front delts"],"barbell",True,"h-press","mid",False,
    ["bench","bench press","flat bench","bb bench"])
add("Incline Barbell Bench Press","chest",["front delts","triceps"],"barbell",True,"h-press","lengthened",False,
    ["incline bench","incline barbell"])
add("Decline Barbell Bench Press","chest",["triceps"],"barbell",True,"h-press","mid",False,["decline bench"])
add("Dumbbell Bench Press","chest",["triceps","front delts"],"dumbbell",True,"h-press","lengthened",False,
    ["db bench","dumbbell press","flat db press"])
add("Incline Dumbbell Press","chest",["front delts","triceps"],"dumbbell",True,"h-press","lengthened",False,
    ["incline db press","incline dumbbell bench"])
add("Chest Press Machine","chest",["triceps","front delts"],"machine",True,"h-press","mid",False,
    ["machine chest press","hammer strength chest press","iso lateral chest press","hammer chest press",
     "prime chest press","panatta chest press","technogym chest press","seated chest press"])
add("Incline Press Machine","chest",["front delts","triceps"],"machine",True,"h-press","lengthened",False,
    ["machine incline press","iso lateral incline press","hammer strength incline","panatta super inclined"])
add("Smith Machine Bench Press","chest",["triceps"],"smith",True,"h-press","mid",False,["smith bench"])
add("Weighted Dip","chest",["triceps","front delts"],"bodyweight",True,"h-press","lengthened",False,
    ["dip","dips","weighted dips","chest dip"])
add("Larsen Press","chest",["triceps"],"barbell",True,"h-press","mid",False,["larsen bench","legs up bench"])
add("Spoto Press","chest",["triceps"],"barbell",True,"h-press","mid",False,["spoto bench","paused above chest"])
add("Guillotine Press","chest",["front delts"],"barbell",True,"h-press","lengthened",False,
    ["gironda neck press","neck press"])
add("Deficit Push-Up","chest",["triceps","front delts"],"bodyweight",False,"h-press","lengthened",False,
    ["deficit pushup","push up on handles","parallette push up"])
add("Push-Up","chest",["triceps","front delts","core"],"bodyweight",False,"h-press","mid",False,["pushup","press up"])

# ---------------- VERTICAL PRESS ----------------
add("Overhead Press","shoulders",["triceps","core"],"barbell",True,"v-press","mid",False,
    ["ohp","military press","strict press","shoulder press","standing press"])
add("Seated Barbell Overhead Press","shoulders",["triceps"],"barbell",True,"v-press","mid",False,["seated ohp"])
add("Dumbbell Shoulder Press","shoulders",["triceps"],"dumbbell",True,"v-press","lengthened",False,
    ["db shoulder press","dumbbell overhead press"])
add("Shoulder Press Machine","shoulders",["triceps"],"machine",True,"v-press","mid",False,
    ["machine shoulder press","hammer strength shoulder press","iso lateral shoulder press",
     "panatta deltoid press","mts shoulder press"])
add("Arnold Press","shoulders",["triceps"],"dumbbell",True,"v-press","lengthened",False,["arnold"])
add("Z-Press","shoulders",["triceps","core"],"barbell",True,"v-press","mid",False,["z press","seated floor press"])
add("Push Press","shoulders",["triceps","quads"],"barbell",True,"v-press","mid",False,["push jerk"])
add("Bradford Press","shoulders",["triceps"],"barbell",False,"v-press","mid",False,["bradford"])
add("Scott Press","shoulders",[],"dumbbell",False,"v-press","shortened",False,["larry scott press"])
add("Landmine Press","shoulders",["chest","triceps"],"barbell",True,"v-press","mid",True,
    ["landmine shoulder press","half kneeling landmine press"])

# ---------------- HORIZONTAL PULL ----------------
add("Barbell Row","back",["biceps","rear delts"],"barbell",True,"h-pull","mid",False,
    ["bent over row","bb row","barbell bent over row"])
add("Pendlay Row","back",["biceps","rear delts"],"barbell",True,"h-pull","lengthened",False,
    ["pendlay","dead stop row"])
add("Yates Row","back",["biceps"],"barbell",True,"h-pull","mid",False,["yates","underhand barbell row"])
add("Dumbbell Row","back",["biceps","rear delts"],"dumbbell",True,"h-pull","lengthened",True,
    ["db row","single arm row","one arm row"])
add("Kroc Row","back",["biceps","forearms"],"dumbbell",True,"h-pull","lengthened",True,["kroc"])
add("Meadows Row","back",["biceps","rear delts"],"barbell",True,"h-pull","lengthened",True,
    ["meadows","john meadows row"])
add("Chest-Supported Row","back",["biceps","rear delts"],"machine",True,"h-pull","mid",False,
    ["hammer strength row","iso lateral row","hammer row","prime row","prime extreme row",
     "arsenal row","panatta row","seal row","machine row","t bar chest supported row","mts row"])
add("Seated Cable Row","back",["biceps","rear delts"],"cable",True,"h-pull","lengthened",False,
    ["cable row","seated row","low row","panatta pulley row"])
add("T-Bar Row","back",["biceps","rear delts"],"barbell",True,"h-pull","mid",False,["tbar row","t bar row"])
add("High Row Machine","back",["biceps","rear delts"],"machine",True,"h-pull","lengthened",False,
    ["hammer strength high row","iso lateral high row","panatta high row convergent","mts high row"])
add("Inverted Row","back",["biceps"],"bodyweight",True,"h-pull","mid",False,["body row","australian pull up"])
add("Kelso Shrug","traps",["rear delts"],"barbell",False,"h-pull","shortened",False,
    ["kelso","bent over shrug","prone shrug"])
add("Seated Cable Row (single arm)","back",["biceps"],"cable",True,"h-pull","lengthened",True,
    ["one arm cable row","single arm row cable"])

# ---------------- VERTICAL PULL ----------------
add("Weighted Pull-Up","back",["biceps","forearms"],"bodyweight",True,"v-pull","lengthened",False,
    ["weighted pullup"])
add("Chin-Up","back",["biceps"],"bodyweight",True,"v-pull","lengthened",False,["chinup","chin ups"])
add("Lat Pulldown","back",["biceps"],"cable",True,"v-pull","lengthened",False,
    ["pulldown","lat pull down","panatta lat pulldown","hammer strength pulldown","front pulldown","1fe001"])
add("Neutral-Grip Lat Pulldown","back",["biceps"],"cable",True,"v-pull","lengthened",False,
    ["hammer grip pulldown","parallel grip pulldown"])
add("Single-Arm Lat Pulldown","back",["biceps"],"cable",True,"v-pull","lengthened",True,
    ["one arm pulldown","unilateral pulldown","pw623"])
add("Cross-Body Lat Pulldown","back",["biceps"],"cable",True,"v-pull","lengthened",True,
    ["crossbody pulldown","across body pulldown"])
add("Sternum Chin-Up","back",["biceps"],"bodyweight",True,"v-pull","shortened",False,["gironda chin up"])
add("Cable Lat Prayer","back",[],"cable",False,"v-pull","lengthened",False,
    ["lat prayer","kneeling cable pullover","straight arm kneeling pulldown"])
add("Straight-Arm Pulldown","back",[],"cable",False,"v-pull","mid",False,
    ["straight arm lat pulldown","cable pullover standing"])
add("Machine Pullover","back",[],"machine",False,"v-pull","lengthened",False,
    ["pullover machine","nautilus pullover","hammer strength pullover","panatta pullover","1fe039"])
add("Dumbbell Pullover","back",["chest"],"dumbbell",False,"v-pull","lengthened",False,["db pullover"])

# ---------------- SHOULDERS: ISOLATION ----------------
add("Dumbbell Lateral Raise","shoulders",[],"dumbbell",False,"lateral","shortened",False,
    ["lateral raise","side raise","lat raise","db lateral raise"])
add("Cable Lateral Raise","shoulders",[],"cable",False,"lateral","lengthened",True,
    ["cable side raise","one arm cable lateral"])
add("Behind-the-Back Cable Lateral Raise","shoulders",[],"cable",False,"lateral","lengthened",True,
    ["btb cable lateral","cuffed lateral raise","behind back lateral raise"])
add("Cross-Body Cable Lateral Raise","shoulders",[],"cable",False,"lateral","lengthened",True,
    ["crossbody lateral raise","across body raise"])
add("Lean-Away Lateral Raise","shoulders",[],"dumbbell",False,"lateral","lengthened",True,
    ["lean away raise"])
add("Machine Lateral Raise","shoulders",[],"machine",False,"lateral","shortened",False,
    ["lateral raise machine","standing lateral raise machine","atlantis lateral raise","watson lateral raise",
     "hammer strength lateral raise","panatta lateral deltoid"])
add("Cable Y-Raise","shoulders",["traps"],"cable",False,"lateral","mid",False,["y raise","scaption cable"])
add("Poliquin Lateral Raise","shoulders",[],"dumbbell",False,"lateral","shortened",False,["poliquin raise"])
add("Front Raise","shoulders",[],"dumbbell",False,"lateral","mid",False,["db front raise"])
add("Rear Delt Fly","shoulders",["back"],"dumbbell",False,"h-pull","shortened",False,
    ["reverse fly","rear delt raise","bent over fly"])
add("Reverse Pec Deck","shoulders",["back"],"machine",False,"h-pull","shortened",False,
    ["rear delt machine","reverse fly machine","rear delt pec deck"])
add("Reverse Cable Crossover","shoulders",["back"],"cable",False,"h-pull","lengthened",False,
    ["cable rear delt fly","reverse crossover"])
add("Face Pull","shoulders",["back"],"cable",False,"h-pull","mid",False,["face pulls","rope face pull"])
add("Svend Press","chest",["front delts"],"other",False,"h-press","shortened",False,["plate pinch press"])

# ---------------- CHEST: ISOLATION ----------------
add("Cable Chest Fly","chest",[],"cable",False,"h-press","lengthened",False,
    ["cable fly","pec fly","chest fly","cable crossover"])
add("Low-to-High Cable Fly","chest",[],"cable",False,"h-press","shortened",False,["low cable fly","incline cable fly"])
add("High-to-Low Cable Fly","chest",[],"cable",False,"h-press","shortened",False,["high cable fly","decline cable fly"])
add("Pec Deck","chest",[],"machine",False,"h-press","mid",False,
    ["pec deck machine","butterfly machine","panatta pectoral","nautilus pec fly"])
add("Dumbbell Fly","chest",[],"dumbbell",False,"h-press","lengthened",False,["db fly","flat fly"])
add("Incline Dumbbell Fly","chest",[],"dumbbell",False,"h-press","lengthened",False,["incline fly"])
add("Cable Press-Around","chest",["front delts"],"cable",False,"h-press","shortened",True,["press around","cable adduction"])
add("Seated Cable Pec Fly","chest",[],"cable",False,"h-press","lengthened",False,["chest supported cable fly"])

# ---------------- BICEPS ----------------
add("Barbell Curl","biceps",["forearms"],"barbell",False,"elbow-flex","mid",False,["bicep curl","bb curl"])
add("EZ-Bar Curl","biceps",["forearms"],"barbell",False,"elbow-flex","mid",False,["ez curl"])
add("Dumbbell Curl","biceps",["forearms"],"dumbbell",False,"elbow-flex","mid",False,
    ["db curl","alternating curl","standing db curl"])
add("Incline Dumbbell Curl","biceps",[],"dumbbell",False,"elbow-flex","lengthened",False,
    ["incline curl","seated incline curl"])
add("Bayesian Curl","biceps",[],"cable",False,"elbow-flex","lengthened",True,
    ["bayesian cable curl","behind body cable curl","facing away cable curl"])
add("Preacher Curl","biceps",[],"barbell",False,"elbow-flex","lengthened",False,
    ["ez bar preacher curl","scott curl","scott bench curl","b856"])
add("Machine Preacher Curl","biceps",[],"machine",False,"elbow-flex","lengthened",False,
    ["preacher curl machine","panatta curling","hammer strength biceps curl","mts biceps curl"])
add("Hammer Curl","biceps",["forearms"],"dumbbell",False,"elbow-flex","mid",False,["hammer curls","neutral grip curl"])
add("Cable Curl","biceps",["forearms"],"cable",False,"elbow-flex","mid",False,["standing cable curl"])
add("Zottman Curl","biceps",["forearms"],"dumbbell",False,"elbow-flex","mid",False,["zottman"])
add("Drag Curl","biceps",[],"barbell",False,"elbow-flex","shortened",False,["gironda drag curl"])
add("Spider Curl","biceps",[],"dumbbell",False,"elbow-flex","shortened",False,["prone incline curl"])
add("Concentration Curl","biceps",[],"dumbbell",False,"elbow-flex","mid",True,["conc curl"])
add("Reverse Curl","forearms",["biceps"],"barbell",False,"elbow-flex","mid",False,["pronated curl"])

# ---------------- TRICEPS ----------------
add("Triceps Pushdown","triceps",[],"cable",False,"elbow-ext","shortened",False,
    ["tricep pushdown","rope pushdown","pushdown","cable pushdown"])
add("Overhead Cable Triceps Extension","triceps",[],"cable",False,"elbow-ext","lengthened",False,
    ["overhead rope extension","cable overhead extension"])
add("Overhead Dumbbell Extension","triceps",[],"dumbbell",False,"elbow-ext","lengthened",False,
    ["french press","db overhead extension","seated overhead extension"])
add("Skull Crusher","triceps",[],"barbell",False,"elbow-ext","lengthened",False,
    ["lying triceps extension","ez bar skullcrusher"])
add("JM Press","triceps",["chest"],"barbell",True,"elbow-ext","mid",False,["jm","jm blakley press"])
add("Close-Grip Bench Press","triceps",["chest"],"barbell",True,"h-press","mid",False,["cgbp","close grip bench"])
add("Katana Cable Extension","triceps",[],"cable",False,"elbow-ext","lengthened",False,
    ["katana extension","crossed cable triceps"])
add("Tate Press","triceps",[],"dumbbell",False,"elbow-ext","mid",False,["tate"])
add("Triceps Extension Machine","triceps",[],"machine",False,"elbow-ext","mid",False,
    ["machine triceps extension","panatta french press","mts triceps extension","t262"])
add("Bench Dip","triceps",["front delts"],"bodyweight",False,"elbow-ext","lengthened",False,["tricep dip bench"])

# ---------------- LEGS: ISOLATION ----------------
add("Leg Extension","quads",[],"machine",False,"knee-ext","shortened",False,
    ["quad extension","leg extensions","panatta leg extension","prime leg extension"])
add("Lying Leg Curl","hamstrings",[],"machine",False,"knee-flex","shortened",False,
    ["leg curl","hamstring curl","prone leg curl"])
add("Seated Leg Curl","hamstrings",[],"machine",False,"knee-flex","lengthened",False,["seated hamstring curl"])
add("Reverse Nordic Curl","quads",[],"bodyweight",False,"knee-ext","lengthened",False,
    ["reverse nordic","kneeling quad stretch curl"])
add("Standing Calf Raise","calves",[],"machine",False,"calf","lengthened",False,["calf raise","calves"])
add("Seated Calf Raise","calves",[],"machine",False,"calf","lengthened",False,["soleus raise"])
add("Leg Press Calf Raise","calves",[],"machine",False,"calf","lengthened",False,["calf press"])
add("Tibialis Raise","calves",[],"other",False,"calf","shortened",False,["tib raise","dorsiflexion raise"])
add("Hip Abduction","glutes",[],"machine",False,"abduction","shortened",False,
    ["abductor machine","hip abductor","pw429"])
add("Hip Adduction","quads",[],"machine",False,"abduction","lengthened",False,["adductor machine"])
add("Cable Kickback","glutes",["hamstrings"],"cable",False,"hinge","shortened",True,["cable glute kickback"])

# ---------------- TRAPS / NECK / CORE ----------------
add("Barbell Shrug","traps",["forearms"],"barbell",False,"shrug","shortened",False,["shrugs","trap shrug"])
add("Dumbbell Shrug","traps",["forearms"],"dumbbell",False,"shrug","shortened",False,["db shrug"])
add("Haney Shrug","traps",[],"barbell",False,"shrug","shortened",False,["behind the back shrug","haney"])
add("Cable Crunch","core",[],"cable",False,"trunk-flex","shortened",False,["kneeling cable crunch","rope crunch"])
add("Hanging Leg Raise","core",[],"bodyweight",False,"trunk-flex","lengthened",False,
    ["leg raise","hanging knee raise","toes to bar"])
add("Plank","core",[],"bodyweight",False,"anti-ext","mid",False,["front plank"])
add("Ab Wheel Rollout","core",[],"other",False,"anti-ext","lengthened",False,["ab wheel","rollout"])
add("Pallof Press","core",[],"cable",False,"anti-rot","mid",True,["anti rotation press"])
add("Machine Crunch","core",[],"machine",False,"trunk-flex","shortened",False,
    ["ab crunch machine","abdominal machine","mts abdominal crunch"])
add("Rotary Torso","core",[],"machine",False,"anti-rot","mid",False,["torso rotation machine"])

# ---------------- OLYMPIC / POWER ----------------
add("Power Clean","back",["quads","traps","shoulders"],"barbell",True,"pull","mid",False,["power cleans"])
add("Hang Clean","back",["quads","traps"],"barbell",True,"pull","mid",False,["hang power clean"])
add("Power Snatch","shoulders",["back","quads","traps"],"barbell",True,"pull","mid",False,[])
add("Barbell Jammer","shoulders",["chest","triceps"],"barbell",True,"v-press","mid",False,
    ["ground base jammer","jammer press","1hp534","landmine jammer"])



async def run(dry_run: bool, pattern: str | None) -> None:
    selected = [e for e in E if not pattern or e[5] == pattern]
    rows = [
        {
            "name": name,
            "muscle_group": muscle,
            "secondary_muscles": sec,
            "equipment": equip,
            "is_compound": comp,
            # THE MOVEMENT PATTERN AND RESISTANCE PROFILE ARE NOT ALIASES.
            # They used to be folded in here, so that "hinge" and
            # "lengthened" were searchable without new columns. That was a
            # shortcut and it cost more than it saved: an alias list is the
            # search index, so every one of these 155 rows answered to a
            # classification token. Searching "mid" returned 58 unrelated
            # movements, and alias search is the one thing the exercise/
            # station split depends on being precise.
            #
            # They stay in the tuple above -- this file remains the source of
            # truth for both -- and land in `exercise_attributes` once that
            # table has a resistance-profile column and a movement-pattern
            # vocabulary wide enough for all 19 values used here.
            "aliases": sorted(set(aliases)),
        }
        for (name, muscle, sec, equip, comp, pat, profile, uni, aliases) in selected
    ]

    log.info(
        "%d movements (%d compound), %d aliases",
        len(rows),
        sum(1 for r in rows if r["is_compound"]),
        sum(len(r["aliases"]) for r in rows),
    )
    log.info("patterns: %s", dict(Counter(e[5] for e in selected).most_common(6)))

    if dry_run:
        log.info("--dry-run: nothing written")
        return

    # Seeds insert data; migrations own schema. This line used to
    # call create_all, which changed the schema behind Alembic's
    # back and broke the next upgrade.
    await require_tables("exercises")

    # Exercise has no natural unique constraint, so upsert by name manually.
    # Re-running must never duplicate a row -- a duplicate silently halves
    # somebody's strength history.
    #
    # Existing rows are UPDATED rather than skipped. Skipping them was a real
    # bug: an earlier seed's "Hack Squat" kept its old alias list forever, so
    # adding "pw412" or "prime hack squat" to this file changed nothing and
    # the brand search silently failed for exactly the machines people own.
    # Identity (the name) is what must not change; the metadata should track
    # this file.
    async with SessionLocal() as session:
        # "Already there?" is a question about the whole NAME AND ALIAS
        # space, not the name list. Asking it about names alone is what let
        # this table accumulate 42 rows whose name was another row's alias --
        # one movement, two half-height strength trends, neither reaching the
        # 8 exposures adjudication needs. See app/services/catalogue.py.
        current = (
            await session.execute(select(Exercise.name, Exercise.aliases))
        ).all()
        plan = plan_seed(
            [CatalogueEntry(name=n, aliases=tuple(a or [])) for n, a in current],
            [CatalogueEntry(name=r["name"], aliases=tuple(r["aliases"])) for r in rows],
            refresh_existing=True,
        )
        report_collisions(plan, logger=log)

        insertable, refreshable = set(plan.insert), set(plan.update)
        new_rows = [r for r in rows if r["name"] in insertable]
        upd_rows = [r for r in rows if r["name"] in refreshable]

        if new_rows:
            await session.execute(pg_insert(Exercise).values(new_rows))

        # ALIASES ARE UNIONED, NOT REPLACED, AND THAT IS LOAD-BEARING.
        # This file is not the only writer of the alias list.
        # `merge_duplicate_exercises.py` folds a retired row's name in here
        # so that "butterfly" still finds "Pec Deck" after the duplicate row
        # is gone. Replacing the list wholesale silently deleted 11 such
        # names on the first seed run after a merge, making those movements
        # unsearchable -- the exact failure the merge existed to prevent.
        #
        # The cost is that an alias cannot be removed by deleting it from
        # this file. Deliberate removals go through ALIAS_REMOVALS in
        # `merge_duplicate_exercises.py`, where they are recorded with a
        # reason.
        held = {n: set(a or []) for n, a in current}
        for r in upd_rows:
            await session.execute(
                update(Exercise)
                .where(Exercise.name == r["name"])
                .values(
                    muscle_group=r["muscle_group"],
                    secondary_muscles=r["secondary_muscles"],
                    equipment=r["equipment"],
                    is_compound=r["is_compound"],
                    aliases=merge_aliases(held.get(r["name"], ()), r["aliases"]),
                )
            )

        await session.commit()
        log.info("Wrote %d new, refreshed %d existing", len(new_rows), len(upd_rows))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--pattern", default=None, help="e.g. h-pull, squat, hinge")
    a = ap.parse_args()
    asyncio.run(run(a.dry_run, a.pattern))


if __name__ == "__main__":
    main()
