## AI gym trainer and workout programming

The workout system should function as a complete adaptive gym trainer.

It must not only display exercises or record completed sets. It should help users decide:

- Which exercises to perform today.
- Which muscle groups to train.
- How many exercises to perform.
- The order of exercises.
- Number of sets.
- Repetition ranges.
- Suggested weight or effort level.
- Rest time.
- Warm-up requirements.
- When to increase or reduce training difficulty.
- When to change the workout split.
- When to reduce volume because of fatigue, limited time, or excessive cardio.

The primary training goals are:

1. Hypertrophy.
2. Progressive overload.
3. Consistent long-term training.
4. Appropriate fatigue management.
5. Safe and practical workouts that fit the user's available time and equipment.

Do not present AI-generated training advice as medical advice. Include appropriate warnings for pain, injury, medical conditions, pregnancy, and rehabilitation situations. Encourage consultation with a qualified trainer or healthcare professional when appropriate.

## User information for programming

The trainer should consider:

- Training goal: muscle gain, fat loss, maintenance, strength, general fitness, or recomposition.
- Current phase: cut, bulk, maintenance, or performance phase.
- Number of gym days per week.
- Available training days.
- Preferred session duration.
- Cardio frequency.
- Cardio duration and intensity.
- Sports participation.
- Training age.
- Experience level.
- Age.
- Sex, if the user chooses to provide it.
- Height and body weight, if available.
- Recovery quality.
- Sleep.
- Stress.
- Soreness.
- Energy level.
- Pain or injury limitations.
- Available equipment.
- Preferred exercises.
- Disliked exercises.
- Previous workout performance.
- Recent muscle-group volume.
- Recent exercise frequency.
- Personal records.
- User's gym schedule.

Do not require sensitive information if it is not necessary. Allow users to skip optional fields.

## Training split generation

Generate a suitable split based on the user's available gym days.

Possible splits include:

- Full body.
- Upper/lower.
- Push/pull/legs.
- Upper/lower/full body.
- Push/pull.
- Bro split.
- Glute-focused split.
- Strength and hypertrophy split.
- Hybrid gym and cardio split.
- Home and gym combination.
- Custom split.

Do not force a fixed split on every user.

Examples:

- 2 gym days: full body.
- 3 gym days: full body or push/pull/legs rotation.
- 4 gym days: upper/lower or upper/lower repeated.
- 5 gym days: upper/lower plus specialized sessions.
- 6 gym days: push/pull/legs, only when recovery is adequate.

The actual recommendation must depend on the user's training experience, recovery, cardio, schedule, and goal rather than only the number of available days.

## Cardio-aware programming

Adjust resistance-training volume and exercise selection based on cardio.

Consider:

- Total weekly cardio duration.
- Cardio intensity.
- Whether cardio is performed before or after lifting.
- Running versus cycling versus swimming.
- Leg fatigue from cardio.
- Cardio-specific recovery demands.
- The user's cut, bulk, or maintenance phase.
- Whether the user plays sports in addition to gym training.

Avoid scheduling demanding leg training immediately before a long run, intense cycling session, match, or similar activity unless the user specifically chooses that arrangement.

When cardio volume is high:

- Reduce unnecessary lower-body volume.
- Avoid excessive duplicate exercises.
- Preserve high-value compound movements.
- Use fatigue-aware exercise selection.
- Schedule recovery days where appropriate.
- Explain the tradeoff to the user.

Do not automatically treat all cardio calories as extra food calories. Follow the application's existing calorie and TDEE rules.

## Hypertrophy programming

Prioritize hypertrophy using:

- Appropriate weekly sets per muscle group.
- Repeated exposure to muscle groups when useful.
- Stable exercises that can be progressed over time.
- Suitable repetition ranges.
- Sufficient rest.
- Full or practical range of motion.
- Controlled technique.
- Proximity to failure.
- Reasonable fatigue management.
- Progressive overload.

Use different repetition ranges where appropriate instead of assigning the same range to every exercise.

Examples:

- Heavy compound movements: approximately 4–8 repetitions.
- Moderate compound and machine movements: approximately 6–12 repetitions.
- Isolation exercises: approximately 10–20 repetitions.
- Calves, abs, and selected accessory exercises: flexible ranges based on the movement.

These are starting ranges, not rigid rules. The trainer should modify them based on the exercise, user experience, recovery, technique, and goal.

Do not claim that one precise repetition range is universally optimal.

## Progressive overload system

The trainer should track progression for each exercise using:

- Weight.
- Repetitions.
- Sets.
- Repetition quality.
- RPE.
- RIR.
- Tempo, where available.
- Range of motion.
- Exercise variation.
- Machine and equipment.
- Previous performance.
- Technique notes.
- Personal records.

Use a clear progression method such as double progression.

Example:

- Target: 3 sets of 8–12 repetitions.
- Keep the same weight until the user reaches the upper end of the range with the planned RIR.
- Increase the weight by a small increment.
- Return to the lower end of the repetition range.
- Continue tracking performance.

The trainer should not increase weight automatically after a poor-quality or painful set.

If the user reports:

- Missed repetitions.
- High RPE.
- Low RIR.
- Poor sleep.
- High soreness.
- Low energy.
- Pain.
- Reduced performance.

the trainer may reduce weight, sets, repetitions, exercise complexity, or total session volume.

## Plateau detection and progression recovery

The trainer must detect performance plateaus and respond to them without blindly telling the user to add more weight.

A plateau is not one repeated workout or one failed set.

Treat a plateau as possible only when all of the following hold:

- The same exercise, or an explicitly equivalent movement, was performed.
- Equipment and setup are comparable.
- There are at least 3 qualifying exposures.
- The exposures span approximately 3–4 weeks of training history.
- At least 80% of the prescribed sets were completed.
- No deload was active.
- No pain or safety flag was recorded.
- No materially poor readiness signal explains the performance.
- No meaningful improvement appears in any of the tracked metrics below.

Track these metrics when comparing exposures:

- Top-set estimated 1RM.
- Total volume.
- Repetitions at the same load.
- RIR at the same load.
- Completed sets.
- Repetition quality, where available.

Use the existing SetLog, WorkoutSession, strength and estimated 1RM, and volume data where possible.

Do not classify the user as plateaued when:

- There are fewer than 3 qualifying exposures.
- The exercise, equipment, setup, or range of motion changed materially.
- The user missed most of the prescribed sets.
- The user was deloading.
- The user is improving repetitions at the same load.
- The user's estimated 1RM is improving.
- The user is improving total volume.
- Readiness, sleep, soreness, stress, or recent sport and cardio load explains the performance.
- The exercise was intentionally replaced.

Return an explainable status rather than only true or false. Supported statuses:

- insufficient_data.
- progressing.
- not_comparable.
- incomplete_execution.
- deload_period.
- confounded.
- watch.
- confirmed_plateau.
- persistent_plateau.
- safety_stop.

Every assessment must include:

- Status.
- Confidence.
- Evidence sessions.
- Baseline performance.
- Current performance.
- The metric that stopped improving.
- Reason.
- Recommended next step.
- Whether user confirmation is required.

The user must be able to see which sessions were considered.

When a possible or confirmed plateau is detected, work through the following responses in order.

First, verify execution:

- Confirm the user completed the prescribed sets.
- Check repetitions, RIR and RPE, range of motion, tempo, equipment, and exercise identity.
- Check whether kilograms and pounds may have been confused.
- Check whether technique or setup changed.

Second, continue double progression:

- If repetitions are increasing within the target range, keep the weight unchanged.
- Once all prescribed sets reach the upper end of the range at the planned RIR, increase weight by the smallest available increment.
- After increasing load, return toward the lower end of the repetition range.

Third, use microloading:

- Use the smallest load increment the equipment supports.
- Never prescribe a load that cannot actually be loaded.
- For bodyweight or band exercises with no smaller increment, recommend a valid progression such as repetitions, tempo, range of motion, pause, leverage, or an approved variation.
- Never make a large automatic weight jump.

Fourth, offer a controlled adjustment, and only after the user confirms it:

- Add one set within safe volume limits.
- Adjust the repetition range.
- Adjust rest time.
- Use a controlled tempo.
- Use an approved equivalent exercise.
- Reduce fatigue from lower-priority exercises.

Fifth, consider a deload:

- Recommend a deload when repeated high effort, poor recovery, soreness, missed repetitions, or declining performance support it.
- The system may recommend a deload but must not apply it automatically.
- The user must confirm.
- Record whether the action was system-recommended or user-initiated once persistence is implemented.

Sixth, consider exercise variation:

- Recommend a reviewed equivalent only when appropriate.
- Preserve the original exercise and all performed history.
- Create a new prescription or programme revision.
- Never overwrite historical SetLog records.

The trainer must never:

- Add a large amount of weight automatically.
- Prescribe a one-repetition maximum attempt.
- Change an exercise after one poor session.
- Treat pain as an ordinary plateau.
- Diagnose an injury or medical condition.
- Tell the user to train through sharp, severe, worsening, or unusual pain.
- Silently modify an active programme.
- Erase or rewrite performed history.
- Use cardio calories to justify extra food automatically.
- Blame the user.

For pain or safety concerns, stop normal progression advice and use conservative wording that encourages appropriate professional guidance where warranted.

Explain the result in plain language, for example:

"Your dumbbell bench press has stayed at 20 kg for four qualifying sessions. You are still completing 8–9 reps with about 2 RIR, so this looks like a progression plateau rather than a failed session. We can keep the weight and aim for 10 reps, try the smallest available increase, add one set, or review a temporary variation. What would you like to do?"

The explanation must show:

- The evidence that triggered the assessment.
- The sessions considered.
- The available options.
- The trade-offs of each option.
- Confirm and cancel controls.
- A way to postpone or dismiss the recommendation.

Derive the plateau detector from existing performance history where possible. Do not require a new table for detection in the first implementation phase.

If persistence is needed to remember a user decision, document a future plateau-event record containing:

- user_id.
- exercise_id.
- The evidence window.
- Status.
- Recommendation.
- User decision.
- initiated_by.
- applied_at.
- Cooldown or dismissal period.

A dismissed recommendation must not repeatedly reappear immediately. The exact postponement cooldown is an unresolved product decision.

Treat the following as MVP scope:

- A pure deterministic plateau detector.
- Explainable statuses.
- The watch and confirmed_plateau levels.
- Execution verification.
- Double progression.
- Smallest-increment and microloading recommendations.
- A read-only assessment on the exercise screen.
- No automatic programme changes.
- No medical diagnosis.

Treat the following as deferred:

- Persistent plateau-event history.
- Persistent dismissal cooldown.
- Automatic programme revisions.
- Persistent readiness-confounding.
- Automatic deload application.
- Advanced exercise-equivalence learning.
- AI-generated plateau explanations.

## Daily readiness adjustment

Before generating the day's workout, ask for:

- Available time.
- Energy level.
- Sleep quality.
- Muscle soreness.
- Stress.
- Pain or discomfort.
- Readiness to train.
- Equipment availability.
- Whether the user has done cardio or sport recently.

Classify the session as:

- Normal session.
- Reduced-volume session.
- Technique-focused session.
- Recovery session.
- Cardio-priority session.
- Deload recommendation.
- Stop-and-seek-professional-advice situation when appropriate.

Do not diagnose injuries. If the user reports sharp, severe, worsening, or unusual pain, do not encourage them to train through it.

## Time-based workout generation

Generate workouts that fit the user's available time.

Support:

- 15-minute session.
- 20-minute session.
- 30-minute session.
- 45-minute session.
- 60-minute session.
- 75-minute session.
- 90-minute session.

For a short session:

- Prioritize the most important movement patterns.
- Reduce isolation work.
- Use efficient supersets only when they do not reduce safety or performance.
- Avoid unnecessary warm-up or exercise duplication.
- Clearly identify what was omitted.

For a longer session:

- Add accessory exercises.
- Add isolation work.
- Add additional sets only when recovery and weekly volume support it.
- Do not fill time with low-value exercises.

Every generated workout should show:

- Estimated duration.
- Exercise order.
- Warm-up.
- Sets.
- Repetitions.
- RIR or RPE target.
- Rest time.
- Equipment.
- Progression instruction.
- Substitution options.
- Cool-down or optional finishing work.

## Exercise prioritization

Prioritize exercises in this order:

1. User safety and limitations.
2. Planned muscle groups and movement patterns.
3. Exercises that support the current goal.
4. Exercises that can be progressively overloaded.
5. User's available equipment.
6. User's preferences and previous performance.
7. Time efficiency.
8. Variety, only when useful.

Do not select exercises solely because they are popular or trending on social media.

If a branded machine is unavailable, suggest an equivalent movement and explain the substitution.

Example:

- PRIME chest press → generic machine chest press.
- Hammer Strength row → chest-supported row or cable row.
- Arsenal pendulum squat → hack squat or leg press, depending on the user's equipment and limitations.

## Recovery and deloading

Track accumulated training stress using:

- Weekly sets.
- Performance trends.
- Repeated high-RPE sets.
- Soreness.
- Missed repetitions.
- Sleep.
- User-reported fatigue.
- Cardio and sport load.
- Training consistency.

Suggest a deload or reduced-volume week when the pattern supports it, but do not make a medical diagnosis.

A deload should be configurable, for example:

- Reduce sets.
- Reduce load.
- Increase RIR.
- Reduce exercise count.
- Keep technique practice while reducing fatigue.

## AI trainer response format

When generating a workout, return structured data and a user-readable explanation.

Example structure:

```json
{
  "session_name": "Upper Body Hypertrophy",
  "goal": "hypertrophy",
  "estimated_minutes": 55,
  "readiness_status": "normal",
  "exercises": [
    {
      "exercise_id": "verified-id",
      "name": "Incline Dumbbell Press",
      "equipment": "dumbbell",
      "sets": 3,
      "rep_min": 8,
      "rep_max": 12,
      "target_rir": 2,
      "rest_seconds": 120,
      "progression_rule": "Increase weight after 3 sets reach 12 reps at RIR 2",
      "substitutions": ["Incline machine chest press"]
    }
  ],
  "notes": [
    "Stop if you experience sharp or unusual pain.",
    "Adjust load if technique breaks down."
  ]
}
```

The backend must validate AI-generated workout output before displaying or saving it.

## User control

The user must be able to:

- Replace an exercise.
- Skip an exercise.
- Change the available time.
- Change the target muscle group.
- Adjust sets and repetitions.
- Mark an exercise as painful or unsuitable.
- Add unavailable equipment.
- Request a simpler workout.
- Request a harder workout.
- Pause or disable AI recommendations.
- Edit the generated workout before starting it.

The trainer should learn from these choices without silently changing the user's plan.

## Testing requirements

Test:

- Different numbers of gym days.
- Cut, bulk, maintenance, and strength goals.
- Low, medium, and high cardio volumes.
- Different session durations.
- Beginner, intermediate, and advanced users.
- Low readiness and high readiness.
- Missing equipment.
- Branded machine substitutions.
- Exercise replacement.
- Pain reports.
- Missed sessions.
- Progressive overload calculations.
- Deload recommendations.
- Invalid AI-generated responses.
- Workout history and personal records.
- Insufficient plateau history.
- Three qualifying exposures.
- A four-week plateau.
- Improving repetitions at a constant weight.
- Improving estimated 1RM.
- Improving total volume.
- Missed or incomplete sets.
- A changed exercise.
- Changed equipment.
- A changed setup.
- A deload period.
- Poor readiness.
- A pain flag.
- Kilogram and pound confusion.
- Double-progression recommendations.
- The smallest available increment.
- Bodyweight exercises with no smaller increment.
- No impossible load recommendation.
- No large automatic weight jump.
- A user accepting a recommendation.
- A user declining a recommendation.
- Performed history remaining unchanged.
- Deterministic plateau output.
- Absence of diagnostic language.

Do not implement all features at once. First inspect the existing codebase, identify what already exists, and propose the smallest safe implementation phase.
