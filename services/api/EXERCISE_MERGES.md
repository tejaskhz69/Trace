# Exercise catalogue merges

Last updated 2026-08-26 14:00 UTC. Rendered from `EXERCISE_MERGES.json`, which accumulates across runs -- this file covers every round, not just the most recent.

Each row below was a second catalogue entry for a movement that already had one. Two seeds wrote to one table and neither checked the other's alias space. The consequence was not cosmetic: adjudication needs 8 exposures on one `exercise_id`, so a lifter alternating between the two names built two half-height trends and got a verdict on neither.

**To reverse a merge:** recreate the absorbed row with the id and name below, move its aliases back off the survivor, and repoint the listed references. The ids are recorded precisely so this is possible.

## Merged

| Survivor | Absorbed | Absorbed id | Aliases folded in | References repointed | Why |
|---|---|---|---|---|---|
| Machine Crunch | Ab Crunch Machine | `6750ee88-5855-4fcb-905a-5c099e808732` | none | none | same machine, word order |
| Barbell Back Squat | Barbell Squat | `f0e01909-8102-4177-92a8-02191d4dd886` | none | none | bar position is the qualifier, not a movement |
| Conventional Deadlift | Barbell Deadlift | `55941702-ae1a-49c3-adc7-086e13598601` | `barbell deadlift`, `conventional deadlift` | none | Sumo Deadlift is the separate row; this is its sibling |
| Hip Thrust | Barbell Hip Thrust | `c314dfac-e2e8-452f-9981-91641d6e72b6` | `hip thrust` | none | implement is not a movement axis here |
| Barbell Row | Bent Over Barbell Row | `ba6ea9c0-12a1-43d6-8c1a-279d34b458f3` | `bent over barbell row`, `barbell row` | set_logs.exercise_id×3 | same lift, longer name |
| Bayesian Curl | Bayesian Cable Curl | `6ded6e10-6edf-41e1-9732-c839b3efc61d` | `cable curl behind` | none | three names for one cable curl behind the body |
| Bayesian Curl | Face-Away Bayesian Cable Curl | `f4dff052-4eb1-495d-934d-d7a1cdb63d7e` | `face-away bayesian cable curl`, `bayesian curl`, `face away curl` | none | three names for one cable curl behind the body |
| Pec Deck | Butterfly | `92989406-bad0-4ad9-895a-1cdbd3b964e8` | `butterfly` | none | one machine, three names |
| Pec Deck | Pec Deck Fly | `cd4a64db-d327-4e35-b718-7842e48c13af` | `pec deck fly`, `pec deck`, `machine fly` | none | one machine, three names |
| Cable Chest Fly | Cable Crossover | `3d878e1c-2c17-424b-8099-a16c7360d9a9` | none | none | one movement, three names |
| Cable Chest Fly | Standing Cable Fly | `54d4d84c-729f-454c-8d66-7e976967035e` | `standing cable fly`, `standing fly` | none | one movement, three names |
| Cable Crunch | Rope Crunch | `0963c895-3348-4c3b-b985-2a390c40c210` | none | none | attachment is not a movement axis |
| Reverse Cable Crossover | Cable Rear Delt Fly | `b0e548bc-a897-4caf-8f52-97d01abaa673` | `rear delt cable fly`, `cable reverse fly` | none | same movement |
| Leg Press Calf Raise | Calf Press | `c5365896-59d8-4dcd-8904-62b6daa58386` | none | none | same movement on the same machine |
| Chest Press Machine | Machine Chest Press | `f23a48dc-3bee-4c3e-a1f8-f22ef83ac6ab` | `chest press machine`, `machine press` | none | word order |
| Chest-Supported Row | Seal Row | `6adcab1b-cede-4530-b547-383958a1b761` | `seal rows`, `bench row`, `prone row` | none | bench angle is a station property, not a movement |
| Machine Triceps Dip | Dip Machine | `e980a564-8e19-478e-812a-549e0a161fad` | none | none | word order |
| Dumbbell Curl | Dumbbell Bicep Curl | `75ebd75a-7130-481d-9e72-0704e985d76d` | `dumbbell bicep curl`, `dumbbell curl` | none | same lift, longer name |
| Preacher Curl | EZ-Bar Preacher Curl | `11cd6f0c-265e-4568-80fa-9d542128f0e3` | `ez-bar preacher curl`, `ez preacher curl`, `preacher curl` | none | bar type is not a movement axis |
| Face Pull | Rope Face Pull | `b3de461c-ecf0-4c77-9db5-adee8a4cdaf9` | `face pull`, `rope facepull` | none | the rope is the only way it is done |
| Guillotine Press | Neck Press | `adbd203e-12cb-4da0-98d3-33a154860867` | none | none | Gironda neck press -- one lift, two names |
| Hammer Curl | Hammer Curls | `20e8ad41-ca1f-4726-9342-a02e89acfb29` | `hammer curl` | none | plural |
| Hip Abduction | Machine Hip Abduction | `3c6861a4-8605-4f55-a278-f60a8ac6eaf9` | `machine hip abduction`, `hip abduction`, `glute medius machine` | none | word order |
| Hip Adduction | Machine Hip Adduction | `5babb4ca-d19d-44b9-ba05-fa16f05ec173` | `machine hip adduction`, `hip adduction` | none | word order |
| Leg Press | Horizontal Leg Press | `41b9f0d6-e149-4314-a43c-73b888dac576` | `seated leg press` | none | sled angle is a station property, not a movement |
| Leg Extension | Leg Extensions | `98c672c3-7804-4216-b402-7ea3653928b4` | none | none | plural |
| Shoulder Press Machine | Machine Shoulder Press | `8ed5a788-beb1-433f-8dd3-96d0da94e25f` | `shoulder press machine`, `machine ohp` | none | word order |
| Triceps Extension Machine | Machine Triceps Extension | `5c024838-c137-4aa9-827e-c492b548e2ad` | none | none | word order |
| Nordic Curl | Nordic Hamstring Curl | `9d5db5ad-5acf-449b-8b4c-76590d564c74` | `nordic curl`, `nordics` | none | same lift, longer name |
| Overhead Press | Standing Military Press | `ac83c101-c3f6-4076-a527-664d35cc314a` | `standing military press`, `overhead press` | none | same lift, two names |
| Barbell Bench Press | Barbell Bench Press - Medium Grip | `d0e23de3-593a-4b59-ac84-3d82d0becb32` | `barbell bench press - medium grip`, `barbell bench press medium grip` | set_logs.exercise_idx1 | medium grip IS the bench press; the qualifier is a dataset artifact |
| Barbell Front Squat | Front Barbell Squat | `e53bcc21-44fb-4d31-b7a2-ddd53e71e4a6` | `front barbell squat` | none | word order |
| Triceps Pushdown | Cable Triceps Pressdown, Rope | `3d059d3b-e538-4d0b-b354-ccd304495eac` | `cable triceps pressdown, rope`, `rope pressdown` | none | same movement; the rope is the usual attachment |
| Chest-Supported Row | Chest-Supported Machine Row | `97ec2696-c703-47d8-a5e3-de21b7ab0af5` | `chest-supported machine row`, `chest supported row machine` | none | same movement; 'machine' is not a qualifier here |
| Close-Grip Bench Press | Close-Grip Barbell Bench Press | `f66c4261-a062-4b7a-a5cb-d152409205a1` | `close-grip barbell bench press`, `close grip barbell bench press` | none | same lift, longer name |
| Dumbbell Pullover | Dumbbell Lat Pullover | `0e56cf63-6d59-44fc-8935-540b9199e1af` | `dumbbell lat pullover` | none | lat vs chest emphasis is a cue, not a movement |
| Dumbbell Lateral Raise | Side Lateral Raise | `aade718d-7a53-4463-a33b-60bbb833cd82` | `side lateral raise` | none | one movement, two names |
| Skull Crusher | EZ-Bar Skullcrusher | `4189ced2-c6b0-46b6-ac4d-8df76b882d88` | `ez-bar skullcrusher` | none | bar type is not a movement axis -- as with Preacher Curl |
| Neutral-Grip Lat Pulldown | Hammer-Grip Lat Pulldown | `5afebd9d-1d3f-402c-b6a9-94980be7506d` | `hammer-grip lat pulldown`, `wide hammer pulldown` | none | hammer grip IS neutral grip: synonyms, not two grip variants |
| Katana Cable Extension | Katana Cable Triceps Extension | `1189eb29-c469-41d4-b2b8-26fd86e541e9` | `katana cable triceps extension` | none | same lift, longer name |
| Pec Deck | Machine Chest Fly | `0cb83476-5b8b-49b8-9943-dcab092ea4c5` | `machine chest fly`, `seated machine fly` | none | one machine, two names |
| Machine Pullover | Machine Lat Pullover | `7702d8b1-ce56-4c59-a4ca-214fbb6dd004` | `machine lat pullover` | none | lat vs chest emphasis is a cue, not a movement |
| Seated Cable Row (single arm) | Single-Arm Cable Row | `4e910300-4262-46ac-8a9f-2a35d7dfbdb6` | `single-arm cable row` | none | same movement, two names |

## Considered and deliberately NOT merged

Each of these has one row's name sitting in another row's alias list, so an automated detector flags them as duplicates. They are different movements. A merge here is not reversible by adding the alias back, because by then the two trends are one series.

| Kept | Also kept | Why |
|---|---|---|
| Zottman Curl | Inverse Zottman Curl | opposite rotation -- supinate up/pronate down vs the reverse |
| Glute Kickback | Cable Kickback | bodyweight vs cable: different equipment class, which IS a substitution axis |
| Walking Lunge | Dumbbell Lunge | travelling vs stationary -- different stability demand |
| Landmine Row | Meadows Row | a Meadows Row is one specific landmine row, not the category |
| Clean | Power Clean | full clean catches below parallel; power catches above -- different lifts |
| Snatch | Power Snatch | same distinction as clean vs power clean |
| Wide-Grip Lat Pulldown | Lat Pulldown | grip variants are separate rows throughout (close, neutral, hammer, V-bar); this one is consistent with them |
| Seated Cable Fly | Cable Chest Fly | seated vs standing: different setup and stability demand |
| Chest-Supported T-Bar Row | T-Bar Row | supported vs free -- the support is the point of the variant |
| Seated Dumbbell Shoulder Press | Dumbbell Shoulder Press | seated vs standing: different core demand |
| Lean-In Dumbbell Lateral Raise | Lean-Away Lateral Raise | opposite bias -- one loads the lengthened end, the other the shortened |
| Pullups | Weighted Pull-Up | loaded vs bodyweight: added load is the whole variant |
| Stiff-Legged Barbell Deadlift | Romanian Deadlift | knee angle differs and so does the loading; commonly conflated, genuinely distinct |
| Seated Cable Row, Neutral Grip | Seated Cable Row | grip variant, kept for the same reason as Wide-Grip Lat Pulldown |

## Aliases removed

Aliases that pointed one distinct movement's *name* at a different row. Removing them stops the pair looking like a duplicate without merging anything.

| Row | Alias removed | Why |
|---|---|---|
| Chest-Supported T-Bar Row | `t bar row` | that is the other row's name |
| Seated Cable Row, Neutral Grip | `cable row` | the bare term belongs to Seated Cable Row |
| Dumbbell Shoulder Press | `seated db press` | names Seated Dumbbell Shoulder Press |
| Lean-Away Lateral Raise | `leaning lateral raise` | ambiguous between lean-away and lean-in |
| Weighted Pull-Up | `pull up` | names Pullups -- unloaded |
| Weighted Pull-Up | `pullup` | names Pullups -- unloaded |
| Romanian Deadlift | `stiff leg deadlift` | names Stiff-Legged Barbell Deadlift |
| Romanian Deadlift | `sldl` | names Stiff-Legged Barbell Deadlift |
| Dumbbell Lunge | `walking lunge` | names Walking Lunge -- travelling |
| Meadows Row | `landmine row` | names Landmine Row, the general category |
| Cable Kickback | `glute kickback` | names Glute Kickback -- bodyweight |
| Power Clean | `clean` | names Clean -- the full lift |
| Power Snatch | `snatch` | names Snatch -- the full lift |
