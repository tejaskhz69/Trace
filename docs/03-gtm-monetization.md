# Trace — Go-to-Market & Monetization Playbook
*Global launch. Benchmarks are 2026 data; every number is a lever you should re-measure with your own cohorts.*

---

## 0. The uncomfortable math you need to see first

Health & Fitness is the best subscription category there is — **$35.64 median realized LTV per payer after year one**, more than triple gaming — and it also has brutal paid-acquisition economics for anyone with a generous free tier. Here's why that tension decides your entire launch plan.

**Assume:** $39.99/yr, Apple's 15% Small Business rate → **$34 net/payer/yr**. First renewal in this category runs ~67.7%.

```
3-year LTV per payer ≈ $34 + ($34 × 0.68) + ($34 × 0.68 × 0.80)  ≈ $75
minus inference cost (~$0.60/mo across the lifetime)              ≈ −$16
NET CONTRIBUTION per payer                                       ≈ $59
Healthy CAC ceiling (LTV/3)                                      ≈ $20/payer
```

Now the two paths:

| | Generous free tier | Hard onboarding paywall |
|---|---|---|
| Install → paid | ~2.1% | ~10.7% |
| At $2.50 CPI (TikTok/UGC), CAC per payer | **$119** ❌ | **$23** ✅ |
| At $3.83 CPI (Apple Search Ads, H&F US median) | **$182** ❌ | **$36** ⚠️ |

**Paid acquisition only works behind a hard paywall.** That is the mechanic Cal AI used to turn $1M/month of ad spend into $5.7M/month of revenue. It is not a moral failing — it's arithmetic.

But a hard paywall from day one starves you of the two things you need most in months 1–6: **reviews, and the correction dataset that makes your AI better than the clones.**

**So: sequence them.**

---

## 1. The three-phase launch

### Phase 1 — Months 1–3: Earn the right to spend (organic only, ~$0 ad budget)

Generous free tier. 3 photo scans/day, unlimited barcode, unlimited workout logging. Goal is not revenue.

**Targets:** 5,000 installs · 300+ ratings at 4.6★+ · 2,000+ AI corrections captured · Day-30 retention >25%

**Channels:**
- **Reddit, done honestly.** r/fitness, r/loseit, r/gainit, r/xxfitness, r/nutrition, r/bodybuilding. Do *not* drop a launch link. Answer questions about body recomposition for weeks first. Then post a genuinely interesting analysis — *"I analysed 200 lifters' data: here's how often weight gain is actually muscle"* — with the app as the footnote. This is slow and it is the only Reddit strategy that doesn't get you banned.
- **Build in public on X/Threads.** Cal AI's founder got 40M views on an unrelated personal post and it drove real installs. You have a genuinely interesting technical story: *"I'm building the first tracker that tells you if your bulk is working."* Post the algorithm. Post the failure cases. Technical honesty is a growth channel in this niche.
- **20 micro-creators, gifted not paid.** 5k–50k followers, actual lifters, not fitness models. Free lifetime Pro in exchange for honest use. At this size you get real engagement and near-zero cost. Ask for *nothing* scripted.
- **Product Hunt + Hacker News.** One shot each. Lead with the strength-adjudication angle, not "another AI calorie counter" — that framing will get you mocked on HN, and rightly so.

**The one thing that matters in Phase 1:** every AI correction a user makes is training data. 2,000 corrections on real, messy, home-cooked food is a moat the 40+ Cal AI clones don't have. Optimise for logging volume, not revenue.

### Phase 2 — Months 4–6: Find the paywall that works (small paid tests, $3–5k/mo)

Now introduce the **onboarding paywall with a trial** — shown after the personalisation flow, before the first scan. Onboarding paywalls with trials convert best in this category (~1.78% install-to-paid on average; top performers far higher).

Test ruthlessly, one variable at a time:

| Test | Variants | What you're learning |
|---|---|---|
| Paywall placement | After onboarding vs. after first scan (the "aha") | Does experiencing the magic first lift or hurt conversion? |
| Trial length | 3-day vs. **14-day** vs. none | See §3 — this one is special for you |
| Price | $29.99 / $39.99 / $49.99 annual | Where does LTV peak, not conversion rate? |
| Hard vs. soft | Dismissible vs. not | The 5x conversion vs. review-score tradeoff |
| Hook | "Unlimited scans" vs. **"Know if it's muscle"** | Which promise sells? |

Run each to significance before moving on. Use RevenueCat or Adapty — do not build paywall A/B testing yourself.

### Phase 3 — Months 7+: Scale what works ($20k+/mo, scaling to whatever ROAS supports)

Only when Day-7 ROAS on a test cohort clears ~60% and Day-30 clears ~100%. Then:

- **TikTok first** — cheapest CPI of the major channels (~$2.45 global) and the best fit for a demoable feature.
- **Meta second** — better targeting, higher CPI, better for retargeting installers who didn't convert.
- **Apple Search Ads always-on** — expensive per install ($3.83 median CPI for H&F in the US) but the highest-intent traffic on earth. Bid on competitor brand terms.
- **UK before the US if budget is tight** — UK CPIs run 20–40% below US across most genres for a very similar audience.

**Creative is the whole ballgame.** Introducing UGC to a campaign lifts impression-to-install by ~152% on average. Budget for **20 new creatives/month**, minimum. Ad fatigue in this category is measured in days.

---

## 2. Pricing

| Tier | Price | Notes |
|---|---|---|
| Free | $0 | 3 scans/day, unlimited barcode + workout logging, basic dashboard |
| **Pro annual** | **$39.99/yr** | The default. Category median annual is $39.94 — you're at market, above Cal AI's $29.99, which you can defend because you do more |
| Pro monthly | $9.99/mo | Exists to make annual look good. Expect <25% of subs |
| Lifetime | $99.99 | Offer only as a win-back to churning annual subscribers |

**Push annual hard.** Health & Fitness is the only App Store category where annual plans are *gaining* share (51% → 61% of revenue, 2023–2025). Annual buyers have 4x the LTV of low-priced plan buyers and retain better.

**Localise pricing.** Geographic variance in this category is enormous — Germany pays 4.4x what Turkey pays for the same annual sub. Localisation testing has the highest LTV win rate of any experiment type (~62%). Since you're going global from day one: don't charge $39.99 in India. Set India/SEA at roughly $12–15/yr equivalent — realized LTV there is ~$14/payer vs. ~$32 in North America, and download-to-paid is 0.7% vs. 2.8%. Price to the market or you'll get neither users nor revenue.

---

## 3. The trial length decision — where your product and your funnel agree

Most apps are shortening trials: ≤4-day trials are now 46.5% of the market, up from 42.1%. The data says that's backwards — **trials of 17–32 days convert at 42.5% vs. 25.5% for short trials.**

For you this isn't a close call, because **your headline feature does not exist until week three.** The Strength Adjudication Engine needs 8 workouts and 14 weigh-ins before it will say anything. A 3-day trial shows a user a photo scanner and nothing else — you'd be selling the commodity feature and hiding the moat.

**Run a 14-day trial minimum. Consider 21.** Structure it so the first verdict lands *inside* the trial:

```
Day 0   Sign up → onboarding → paywall → trial starts. First scan.
Day 1   "Log your weight every morning — this is how I learn your metabolism."
Day 7   First adaptive calorie adjustment. Show the math.
Day 14  ★ FIRST STRENGTH VERDICT ★  "Your bench e1RM is up 3.1% while
        trend weight rose 0.3 kg. You're gaining lean mass."
Day 15  Trial converts.
```

That Day-14 moment is your entire pitch, delivered as a product experience rather than a marketing claim. Also: conversion in this category is bimodal — 86.1% of conversions happen on Day 0 and a second peak lands at Days 4–7. Design for both: a compelling Day-0 paywall *and* a Day-14 payoff.

---

## 4. The creative playbook

Cal AI's channel progression is the map: **influencers to $2M/mo → plateau → performance ads to $5.7M/mo.** Follow the shape, change the message.

**Do not lead with the photo scan.** It's a commodity — 40+ apps do it, the ad auction for it is saturated, and it's what Cal AI (now backed by MyFitnessPal's budget) owns. Lead with the thing nobody else can say.

Five creative angles, ranked:

1. **"Is your bulk actually working?"** — split screen: two guys, both +3 kg. One's bench is +8%, the other's is flat. *One built muscle. One built fat. Your scale can't tell the difference. Trace can.* This is the ad.
2. **The Sunday verdict** — screen recording of the weekly report landing. Real numbers, real explanation, real "show the math" button. Zero acting.
3. **"AI calorie apps lie to you"** — scan the same meal 5 times in a competitor, get 5 different numbers. Then Trace: same number every time, with an honest ±range. Attacks Cal AI's most-complained-about behaviour directly.
4. **"It found the ghee"** — the clarifying-question moment. A curry, and the app asks how much oil. Educational, surprising, and demonstrates real intelligence rather than a party trick.
5. **The 90-day transformation, with data** — not a before/after body shot. A *chart*. Weight flat, four lifts climbing. Recomposition made visible.

**Creative ops:** 20 new creatives/month, 3 hooks per concept, kill anything below 1.5% CTR after 1,000 impressions. UGC over polished — always.

---

## 5. ASO

**Don't fight for "calorie counter."** MyFitnessPal owns it, and Cal AI now has MFP's budget behind it. You will lose and it will be expensive.

**Own the question people actually ask:**

| Tier | Keywords |
|---|---|
| Primary | body recomposition, am i gaining muscle or fat, muscle gain tracker, lean bulk tracker, strength and nutrition tracker |
| Secondary | macro tracker with workouts, adaptive calorie tracker, tdee calculator app, progressive overload tracker |
| Competitor | macrofactor alternative, cal ai alternative, hevy + nutrition, myfitnesspal alternative |
| Long tail | is my bulk working, cutting without losing strength, recomp tracker |

**Title:** `Trace: Muscle or Fat Tracker` — the keyword *is* the value proposition.
**Subtitle:** `Know if your diet is working`

**Screenshots** (this is 60% of your conversion — most users never read the description):
1. The weekly verdict card. Full stop. Lead with the moat.
2. Weight flat + strength climbing chart, with the "Recomposition" label.
3. Photo scan showing an honest **±range** and the ghee question.
4. The "show the math" screen — transparency as a selling point.
5. Workout logging, to signal "this replaces Hevy too."

**Reviews:** prompt at the moment of *earned delight* — right after a user accepts their first strength verdict — never on app open. Reply to every negative review within 24h. Rating is the single biggest organic-conversion lever you control.

---

## 6. Retention

Retention is where you win, because it's the only place your architecture is genuinely better. Cal AI does ~30% retention on the strength of a single fast feature. You should beat it, because you have two habit loops instead of one.

| Loop | Cadence | Hook |
|---|---|---|
| Food logging | Daily | Fast enough to not resent (target <10s/meal) |
| Weigh-in | Daily, morning | 5 seconds; feeds the algorithm |
| Workout logging | 3–5×/week | Auto-filled previous performance = 2 taps |
| **The verdict** | **Weekly** | **The payoff that makes the other three worth doing** |

**Notifications, sparingly:**
- Morning weigh-in nudge (user-scheduled)
- "Sunday verdict is ready" — your highest-value push, treat it like an event
- Streak protection at 8pm *only* if nothing logged
- Nothing else. Every extra notification costs you a permission you can't get back.

**The single best retention feature you can build:** make the weekly verdict *interesting even when the news is boring*. "Everything's on track" is a churn message. "You're 3 weeks into the best lean-gain phase you've logged — here's how it compares to your last bulk" is a reason to open the app.

**Watch for:** the Day-14 cliff. Users who haven't logged a workout by Day 5 will never see a verdict and are effectively already churned. Trigger a specific intervention there.

---

## 7. Revenue model — plausible year one

Deliberately conservative. Blended $28 net revenue per payer (global mix, India priced lower).

| | Installs | Install→paid | Payers | Net revenue |
|---|---|---|---|---|
| **Months 1–3** (organic) | 5,000 | 2.0% | 100 | ~$2.8k |
| **Months 4–6** (testing) | 20,000 | 4.0% | 800 | ~$22k |
| **Months 7–9** (scaling) | 80,000 | 7.0% | 5,600 | ~$157k |
| **Months 10–12** (scaled) | 200,000 | 8.5% | 17,000 | ~$476k |
| **Year 1 total** | **305,000** | | **~23,500** | **~$658k** |

Minus ~$400–500k of ad spend in months 7–12 → roughly break-even to modestly profitable in year one, with a subscriber base that renews at ~68%. Year two is where the money is, because renewals arrive with zero CAC.

**Sanity check:** Cal AI hit $1M MRR in 6 months. They had a demoable feature at exactly the moment TikTok's algorithm rewarded it, plus a 250-creator network. Treat their curve as the ceiling, not the plan.

---

## 8. What kills this

| Risk | Mitigation |
|---|---|
| **Refunds and 1-star billing reviews** | Cal AI got pulled from the App Store in April 2026 for deceptive billing. Show the price before signup. Email before the trial ends. One-tap cancel *inside the app*. This is free differentiation — take it. |
| CAC rises faster than LTV | Never scale spend past Day-30 ROAS 100%. Check weekly, not monthly. |
| Inference cost at free-tier scale | 3 scans/day cap, Haiku-first routing with escalation, phash caching. At 100k free MAU budget ~$15k/mo and monitor it from week one. |
| MyFitnessPal ships the same thing | They won't build a lifter-specific adjudication engine for a 200M mass-market base. Move fast, own lifters, make the correction dataset compound. |
| The verdict is wrong and someone posts about it | This is the real existential risk. Every guardrail in `adjudication.py` exists for this. **Refusing to give a verdict is always better than giving a wrong one.** |

---

## 9. The first 30 days, concretely

**Week 1** — Fix the login (docs/04). Wire the barcode chain (docs/05). Ship the photo scan with confidence ranges. Get the correction-capture endpoint live.
**Week 2** — Workout logging with auto-filled previous performance. Adaptive TDEE running on real data. Instrument every zero-result search.
**Week 3** — Strength Adjudication Engine wired end to end. App Store listing built around the verdict, not the scanner.
**Week 4** — 20 gifted micro-creators. First Reddit value posts. TestFlight to 100 lifters. Start counting corrections.

Then: don't spend a dollar on ads until Day-30 retention clears 25% and you have 300 ratings above 4.6.

---

## Sources

- [Adapty — Health & Fitness subscription benchmarks](https://adapty.io/blog/health-fitness-app-subscription-benchmarks/)
- [RevenueCat — State of Subscription Apps 2026](https://www.revenuecat.com/state-of-subscription-apps)
- [Cal AI growth case study — Superframeworks](https://superframeworks.com/case-study/cal-ai)
- [AppTweak — Apple Ads benchmarks 2026](https://www.apptweak.com/en/aso-blog/apple-ads-benchmarks)
- [Mobile app CPI benchmarks 2026 — The Social Outline](https://thesocialoutline.com/blog/mobile-app-cpi-benchmarks-2026)
- [Cal AI pricing & App Store removal — eesel AI](https://www.eesel.ai/blog/cal-ai-pricing)
- [Cal AI review + MyFitnessPal acquisition — Calzy](https://calzy-app.com/blog/cal-ai-review)
