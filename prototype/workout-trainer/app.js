/* Trace workout-trainer prototype — interactions.
 *
 * All state is in memory. Nothing is written to localStorage, to a server, or
 * to the real app. Reloading the page resets everything, which is the point:
 * a prototype that remembers things starts to feel like a product that stores
 * things, and this one stores nothing.
 *
 * No network calls. No fake latency. Where a screen demonstrates a loading
 * state it is a state you switch to, not a delay you wait through — a fake
 * spinner teaches the reviewer the wrong thing about how fast the real screen
 * will be. The one real timer in here is the rest countdown, which is a
 * feature rather than a simulation.
 */

/* global MOCK, SOURCE */
'use strict';

(function () {
  // ---- helpers ---------------------------------------------------------

  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.prototype.slice.call((root || document).querySelectorAll(sel));

  function esc(value) {
    return String(value).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
  const round1 = (n) => Math.round(n * 10) / 10;

  function toast(message) {
    const rail = $('#toast-rail');
    const node = document.createElement('p');
    node.className = 'toast';
    node.textContent = message;
    rail.appendChild(node);
    window.setTimeout(() => node.remove(), 4200);
  }

  /** The provenance chip. Always rendered beside a SAMPLE tag, never instead
   *  of one, so "what kind of record is this" and "is this real" stay two
   *  separate answers. */
  function src(label) {
    const slug = String(label).split(' ')[0].toLowerCase();
    return '<span class="src src-' + esc(slug) + '">' + esc(label) + '</span>';
  }
  const sample = () => '<span class="tag demo">Sample</span>';

  function panel(head, body, opts) {
    const o = opts || {};
    return '<div class="panel"' + (o.id ? ' id="' + o.id + '"' : '') + '>'
      + '<div class="panel-head">' + head + '</div><hr class="rule">' + body + '</div>';
  }

  const headLeft = (label, cls) => '<p class="label ' + (cls || '') + '">' + esc(label) + '</p>';

  // ---- charts, drawn from primitives -----------------------------------

  function lineChart(series, opts) {
    const o = opts || {};
    const w = 320, h = o.height || 76, pad = 4;
    const clean = series.filter((v) => v !== null && v !== undefined);
    if (!clean.length) return '';
    const min = Math.min.apply(null, clean), max = Math.max.apply(null, clean);
    const span = (max - min) || 1;
    const x = (i) => pad + (i * (w - pad * 2)) / Math.max(1, series.length - 1);
    const y = (v) => h - pad - ((v - min) / span) * (h - pad * 2);
    const pts = series.map((v, i) => x(i) + ',' + round1(y(v))).join(' ');
    const stroke = o.colour || 'var(--s-strength)';
    let out = '<svg class="linechart" viewBox="0 0 ' + w + ' ' + h + '" role="img" aria-label="'
      + esc(o.label || 'Trend chart, sample data') + '">'
      + '<g stroke="var(--hairline)" stroke-width="1">'
      + '<path d="M0 ' + (h / 2) + 'H' + w + '"></path></g>'
      + '<polyline fill="none" stroke="' + stroke + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" points="' + pts + '"></polyline>';
    if (o.overlay) {
      const oc = o.overlay.filter((v) => v !== null && v !== undefined);
      const omin = Math.min.apply(null, oc), omax = Math.max.apply(null, oc);
      const ospan = (omax - omin) || 1;
      const oy = (v) => h - pad - ((v - omin) / ospan) * (h - pad * 2);
      const opts2 = o.overlay.map((v, i) => x(i) + ',' + round1(oy(v))).join(' ');
      out += '<polyline fill="none" stroke="' + (o.overlayColour || 'var(--s-sleep)')
        + '" stroke-width="1.5" stroke-dasharray="4 3" points="' + opts2 + '"></polyline>';
    }
    const last = series[series.length - 1];
    out += '<circle cx="' + round1(x(series.length - 1)) + '" cy="' + round1(y(last))
      + '" r="3.5" fill="var(--surface)" stroke="' + stroke + '" stroke-width="2"></circle></svg>';
    return out;
  }

  function sparkbar(values, opts) {
    const o = opts || {};
    const clean = values.filter((v) => v !== null);
    const max = clean.length ? Math.max.apply(null, clean) : 1;
    const bars = values.map((v, i) => {
      if (v === null) return '<i class="none" style="height:100%"></i>';
      const cls = o.classify ? o.classify(v, i) : (i === values.length - 1 ? 'on' : '');
      return '<i class="' + cls + '" style="height:' + Math.max(4, Math.round((v / max) * 100)) + '%"></i>';
    }).join('');
    const axis = (o.labels || []).map((l) => '<span>' + esc(l) + '</span>').join('');
    return '<div class="spark" role="img" aria-label="' + esc(o.label || 'Bar chart, sample data') + '">'
      + bars + '</div>' + (axis ? '<div class="spark-axis" aria-hidden="true">' + axis + '</div>' : '');
  }

  /** Movement diagrams. Simple original shapes — a torso line, a limb line,
   *  a weight square. Nothing traced from any reference. */
  function movementSVG(shape) {
    const frames = {
      squat: '<line class="mv-body" x1="100" y1="34" x2="100" y2="78"></line>'
        + '<circle cx="100" cy="24" r="9" class="mv-body"></circle>'
        + '<polyline class="mv-limb" points="100,78 84,104 84,126"></polyline>'
        + '<polyline class="mv-limb" points="100,78 116,104 116,126"></polyline>'
        + '<rect class="mv-load" x="90" y="42" width="20" height="20" rx="3"></rect>',
      press: '<line class="mv-body" x1="60" y1="96" x2="140" y2="96"></line>'
        + '<circle cx="52" cy="96" r="9" class="mv-body"></circle>'
        + '<polyline class="mv-limb" points="96,96 96,64"></polyline>'
        + '<polyline class="mv-limb" points="120,96 120,64"></polyline>'
        + '<rect class="mv-load" x="88" y="52" width="16" height="14" rx="2"></rect>'
        + '<rect class="mv-load" x="112" y="52" width="16" height="14" rx="2"></rect>',
      row: '<line class="mv-body" x1="66" y1="70" x2="134" y2="70"></line>'
        + '<circle cx="140" cy="66" r="9" class="mv-body"></circle>'
        + '<polyline class="mv-limb" points="90,70 90,112"></polyline>'
        + '<rect class="mv-load" x="81" y="112" width="18" height="16" rx="3"></rect>'
        + '<polyline class="mv-limb" points="120,70 120,104"></polyline>',
      hinge: '<line class="mv-body" x1="100" y1="30" x2="100" y2="62"></line>'
        + '<circle cx="100" cy="22" r="8" class="mv-body"></circle>'
        + '<polyline class="mv-body" points="100,62 128,74"></polyline>'
        + '<polyline class="mv-limb" points="128,74 128,124"></polyline>'
        + '<rect class="mv-load" x="112" y="86" width="16" height="16" rx="3"></rect>',
      core: '<line class="mv-body" x1="64" y1="104" x2="136" y2="104"></line>'
        + '<circle cx="56" cy="104" r="9" class="mv-body"></circle>'
        + '<polyline class="mv-limb" points="96,104 78,72"></polyline>'
        + '<polyline class="mv-limb" points="120,104 140,80"></polyline>',
    };
    return '<svg viewBox="0 0 200 150" role="img" aria-labelledby="mv-t mv-d">'
      + '<title id="mv-t">Simplified movement diagram</title>'
      + '<desc id="mv-d">An original line drawing standing in for a demonstration. '
      + 'It shows the general shape of the movement, not correct technique for any individual.</desc>'
      + '<line class="mv-ground" x1="20" y1="134" x2="180" y2="134"></line>'
      + '<g class="mv-anim">' + (frames[shape] || frames.core) + '</g></svg>';
  }

  // ---- state -----------------------------------------------------------

  function makeRow(ex, i, warm) {
    return {
      id: ex.id, source: ex, order: i,
      compound: !warm && i < 4,
      warmup: !!warm,
      status: 'pending',
      replacedWith: null,
      logged: [],
      draft: { kg: ex.loadKg, reps: ex.repLow, rir: null },
    };
  }

  const state = {
    screen: 'home',
    history: [],
    openId: null,
    focusedId: 'p2',
    minutes: MOCK.user.preferredMinutes,
    rows: MOCK.exercises.map((ex, i) => makeRow(ex, i)),
    session: 'idle',           // idle | active | paused | done
    rest: { remaining: 0, timer: null, forId: null },
    readiness: Object.assign({ applied: false, skipped: false }, MOCK.readiness.defaults),
    sleepDraft: { hours: 7.0, quality: 'Good', bedtime: '23:15', wake: '06:15' },
    sleepNights: MOCK.sleep.nights.map((n) => Object.assign({}, n)),
    cardio: 'outdoor',
    cardioEmpty: false,
    rideState: 'finished',     // idle | active | paused | finished
    routeVisible: true,
    rides: MOCK.cardio.recent.map((r) => Object.assign({}, r)),
    volState: 'data',
    overlay: 'none',           // none | sleep | cardio
    plateau: { chosen: 'reps', decision: null },
    ai: { decision: null, edited: false, items: MOCK.aiDraft.items.map((i) => Object.assign({}, i)) },
    independent: { picked: [], generated: null },
    setup: {
      goal: MOCK.user.goal, phase: MOCK.user.phase, days: 3,
      available: ['Mon', 'Wed', 'Fri'], minutes: 50,
      equipment: ['Dumbbells', 'Bench', 'Mat'],
      liked: [], disliked: [], cardio: '2 a week',
      recoveryOptIn: false, aiOptIn: false, confirmed: false,
    },
    motion: 'system',
  };

  const QUALITIES = ['Good', 'Broken', 'Poor'];
  const SCALES = [
    { key: 'energy', label: 'Energy', low: 'Flat', high: 'Sharp' },
    { key: 'soreness', label: 'Soreness', low: 'None', high: 'Very sore' },
    { key: 'stress', label: 'Stress', low: 'Calm', high: 'High' },
  ];

  // ---- derived ---------------------------------------------------------

  const WARMUP_MIN = 6;
  const rowMinutes = (r) => (r.source.sets * (r.source.restSec + 45)) / 60 + 1.5;

  function plan() {
    const live = state.rows.filter((r) => r.status !== 'skipped');
    const included = live.slice();
    const omitted = [];
    let minutes = WARMUP_MIN + included.reduce((s, r) => s + rowMinutes(r), 0);

    for (let i = included.length - 1; i >= 0 && minutes > state.minutes; i--) {
      if (included[i].compound) continue;
      minutes -= rowMinutes(included[i]);
      omitted.push(included[i]);
      included.splice(i, 1);
    }
    let setsTrimmed = false;
    if (minutes > state.minutes && included.length) {
      setsTrimmed = true;
      minutes = WARMUP_MIN + included.reduce(
        (s, r) => s + (Math.max(2, r.source.sets - 1) * (r.source.restSec + 45)) / 60 + 1.5, 0);
    }
    const sets = included.reduce((n, r) => n + r.source.sets, 0);
    const done = state.rows.filter((r) => r.status === 'done').length;
    return { included, omitted: omitted.reverse(), minutes: Math.round(minutes), sets, setsTrimmed, done };
  }

  const displayName = (row) => row.replacedWith || row.source.name;

  function prescriptionLine(row) {
    const ex = row.source;
    const load = ex.loadKg == null ? 'Bodyweight' : ex.loadKg + ' kg';
    const each = ex.unilateral ? ' each side' : '';
    return ex.sets + ' × ' + ex.repLow + '–' + ex.repHigh + each + ' · ' + load
      + ' · ' + ex.rir + ' RIR · rest ' + ex.restSec + 's';
  }

  function readinessScore() {
    const r = state.readiness;
    const parts = {
      sleep: 0.30 * clamp(r.sleepHours / 8, 0, 1),
      quality: 0.15 * ({ Good: 1, Broken: 0.35, Poor: 0.15 }[r.quality]),
      energy: 0.20 * ((r.energy - 1) / 4),
      soreness: 0.175 * (1 - (r.soreness - 1) / 4),
      stress: 0.175 * (1 - (r.stress - 1) / 4),
    };
    const total = Object.keys(parts).reduce((s, k) => s + parts[k], 0);
    return { score: Math.round(total * 100), parts };
  }

  function readinessBand(score) {
    if (score >= 75) return { name: 'Good', cls: 'ok', fill: '', intensity: 'Train as planned' };
    if (score >= 50) return { name: 'Moderate', cls: 'watch', fill: 'warn', intensity: 'Reduced volume would fit' };
    return { name: 'Low', cls: 'watch', fill: 'warn', intensity: 'Technique focus, or rest' };
  }

  const SUGGESTIONS = {
    Good: 'Nothing to change. Today&rsquo;s plan stands as written.',
    Moderate: 'A reduced-volume session would fit — one fewer set on the two heaviest lifts. This is a suggestion. Nothing has been changed.',
    Low: 'A technique-focused session at lighter loads, or a rest day, would fit better than the plan as written. This is a suggestion. Nothing has been changed.',
  };

  function sleepStats() {
    const nights = state.sleepNights;
    const have = nights.filter((n) => n.asleep !== null);
    const avg = have.length ? have.reduce((s, n) => s + n.asleep, 0) / have.length : null;
    const shortest = have.length ? have.reduce((a, b) => (a.asleep < b.asleep ? a : b)) : null;
    const consistency = have.length >= 2
      ? Math.round(100 - Math.min(100, (Math.max.apply(null, have.map((n) => n.asleep))
        - Math.min.apply(null, have.map((n) => n.asleep))) * 14))
      : null;
    return { avg, shortest, consistency, missing: nights.length - have.length };
  }

  const cardioActivity = () => MOCK.cardio[state.cardio];

  // ---- screen registry -------------------------------------------------

  const SCREENS = {
    home:        { tab: 'home',     kind: 'Dashboard',        cls: 'kind-progress',    render: renderHome },
    train:       { tab: 'train',    kind: 'Programming',      cls: 'kind-programming', render: renderTrain },
    exercise:    { tab: 'train',    kind: 'Programming',      cls: 'kind-programming', render: renderExercise, parent: 'train' },
    summary:     { tab: 'train',    kind: 'Performed log',    cls: 'kind-logging',     render: renderSummary,  parent: 'train' },
    independent: { tab: 'train',    kind: 'Performed log',    cls: 'kind-logging',     render: renderIndependent, parent: 'home' },
    ai:          { tab: 'train',    kind: 'Programming',      cls: 'kind-programming', render: renderAI,       parent: 'train' },
    setup:       { tab: 'train',    kind: 'Setup',            cls: 'kind-setup',       render: renderSetup,    parent: 'home' },
    recover:     { tab: 'recover',  kind: 'Sleep & recovery', cls: 'kind-recovery',    render: renderRecover },
    sleep:       { tab: 'recover',  kind: 'Sleep & recovery', cls: 'kind-recovery',    render: renderSleep,    parent: 'recover' },
    cardio:      { tab: 'cardio',   kind: 'Cardio',           cls: 'kind-cardio',      render: renderCardio },
    ride:        { tab: 'cardio',   kind: 'Cardio',           cls: 'kind-cardio',      render: renderRide,     parent: 'cardio' },
    eat:         { tab: 'eat',      kind: 'Nutrition',        cls: 'kind-nutrition',   render: renderEat },
    progress:    { tab: 'progress', kind: 'Progress',         cls: 'kind-progress',    render: renderProgress },
    profile:     { tab: null,       kind: 'Setup',            cls: 'kind-setup',       render: renderProfile,  parent: 'home' },
  };

  const TABS = [
    { id: 'home', label: 'Home', glyph: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 7l6-5 6 5v7H2z"/></svg>' },
    { id: 'train', label: 'Train', glyph: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 5v6M13 5v6M5 8h6M1.5 6.5v3M14.5 6.5v3"/></svg>' },
    { id: 'recover', label: 'Recover', glyph: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M13 9.5A5.5 5.5 0 016.5 3a5.5 5.5 0 106.5 6.5z"/></svg>' },
    { id: 'cardio', label: 'Cardio', glyph: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="4" cy="11" r="3"/><circle cx="12" cy="11" r="3"/><path d="M4 11l3-5h4"/></svg>' },
    { id: 'eat', label: 'Eat', glyph: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 2v6M4 8v6M2.5 2v3.5a1.5 1.5 0 003 0V2M11 2c-1 2-1 4 0 5v7"/></svg>' },
    { id: 'progress', label: 'Progress', glyph: '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M2 12l4-4 3 3 5-6"/></svg>' },
  ];

  function screenHead(id, title, sub) {
    const meta = SCREENS[id];
    const back = meta.parent
      ? '<button class="backlink" data-action="back">&larr; Back</button>' : '';
    return '<div class="screen-head">' + back
      + '<div class="eyebrow"><span class="kind ' + meta.cls + '">' + esc(meta.kind) + '</span>' + sample() + '</div>'
      + '<h1 class="title">' + esc(title) + '</h1>'
      + (sub ? '<p class="caption">' + sub + '</p>' : '') + '</div>';
  }

  // ---- 1 · HOME --------------------------------------------------------

  function renderHome() {
    const p = plan();
    const r = readinessScore();
    const band = readinessBand(r.score);
    const s = sleepStats();
    const c = cardioActivity();
    const n = MOCK.nutrition;
    const left = n.targetKcal - n.eatenKcal;
    const pr = MOCK.progress;
    const comp = pr.composition;

    return screenHead('home', 'Good morning, ' + MOCK.user.name,
      esc(MOCK.user.goal) + ' · ' + esc(MOCK.user.phase) + ' · ' + MOCK.user.daysPerWeek + ' days a week ' + src(MOCK.user.source))

      // Train / Eat split — the reference pattern, in Trace's words.
      + '<div class="grid-2">'
      + panel(headLeft('Train', 'signal') + '<span class="tag ok">Today</span>',
        '<div class="panel-body tight"><p class="value-sm">' + esc(MOCK.programme.name.split(' · ')[1] || MOCK.programme.name) + '</p>'
        + '<p class="caption">' + p.included.length + ' exercises · ' + p.minutes + ' min · ' + p.sets + ' sets</p>'
        + '<p class="caption">' + src(MOCK.programme.source) + '</p>'
        + '<button class="btn primary block" data-action="start-workout" style="margin-top:4px">Start</button></div>')
      + panel(headLeft('Eat', 'warn') + '<span class="tag demo">Read-only</span>',
        '<div class="panel-body tight"><p class="value-sm">' + left.toLocaleString() + ' <span class="unit">kcal left</span></p>'
        + '<p class="caption">' + n.eatenKcal.toLocaleString() + ' of ' + n.targetKcal.toLocaleString() + ' · P ' + n.protein.eaten + ' g</p>'
        + '<p class="caption">' + src(n.source) + '</p>'
        + '<button class="btn block" data-action="goto" data-target="eat" style="margin-top:4px">Open log</button></div>')
      + '</div>'

      // Programme
      + panel(headLeft('Programme') + '<span class="tag muted">Week ' + MOCK.programme.week + ' of ' + MOCK.programme.totalWeeks + '</span>',
        '<div class="panel-body tight"><p class="value-sm">' + esc(MOCK.programme.name) + '</p>'
        + '<p class="caption">' + esc(MOCK.programme.split) + ' · ' + esc(MOCK.programme.dayLabel) + '</p>'
        + '<div class="gauge" style="margin-top:6px" role="img" aria-label="Programme adherence ' + MOCK.programme.adherencePct + ' percent, sample value"><i style="width:' + MOCK.programme.adherencePct + '%"></i></div>'
        + '<p class="caption">' + MOCK.programme.adherencePct + '% adherence — ' + esc(MOCK.programme.adherenceNote) + '</p></div>')

      // Readiness
      + panel(headLeft('Readiness') + '<span class="tag ' + band.cls + '">' + esc(band.name) + '</span>',
        '<div class="panel-body tight">'
        + '<div style="display:flex;align-items:baseline;gap:10px"><p class="figure">' + r.score + '</p>'
        + '<p class="caption">' + (state.readiness.skipped ? 'Check-in skipped — nothing was assumed' : esc(band.intensity)) + '</p></div>'
        + '<div class="gauge" role="img" aria-label="Readiness ' + r.score + ' out of 100, sample value"><i class="' + band.fill + '" style="width:' + r.score + '%"></i></div>'
        + '<p class="caption">' + src(MOCK.readiness.source) + ' — your own answers, not a measurement.</p>'
        + '<button class="btn sm" data-action="goto" data-target="recover" style="align-self:flex-start;margin-top:4px">Review recovery</button></div>')

      // Sleep + cardio side by side
      + '<div class="grid-2">'
      + panel(headLeft('Sleep', 'sleep') + '<span class="tag sleep">7 nights</span>',
        '<div class="panel-body tight"><p class="value-sm">' + (s.avg ? round1(s.avg) + ' <span class="unit">h avg</span>' : '<span class="ghost-text">&mdash;</span>') + '</p>'
        + '<p class="caption">target ' + MOCK.sleep.targetHours + ' h · ' + s.missing + ' night not recorded</p>'
        + '<p class="caption">' + src(MOCK.sleep.source) + '</p>'
        + '<button class="btn sm block" data-action="goto" data-target="sleep" style="margin-top:4px">Sleep detail</button></div>')
      + panel(headLeft('Cardio', 'cardio') + '<span class="tag demo">' + esc(c.label) + '</span>',
        '<div class="panel-body tight"><p class="value-sm">' + c.durationMin + ' <span class="unit">min</span></p>'
        + '<p class="caption">' + c.distanceKm + ' km · ' + esc(c.when) + '</p>'
        + '<p class="caption">' + src(c.source) + '</p>'
        + '<button class="btn sm block" data-action="goto" data-target="cardio" style="margin-top:4px">Open cardio</button></div>')
      + '</div>'

      // Consistency
      + panel(headLeft('This week') + '<span class="tag ok">' + pr.streakWeeks + '-week streak</span>',
        '<div class="panel-body tight">'
        + '<div style="display:flex;align-items:baseline;gap:8px"><p class="figure">' + pr.sessionsThisWeek + '</p>'
        + '<p class="caption">of ' + pr.sessionsTarget + ' planned sessions</p></div>'
        + sparkbar(pr.weeks, { labels: pr.weekLabels, label: 'Sessions per week over eight weeks, sample data' })
        + '</div>')

      // Progress highlight — the product claim
      + panel(headLeft('Is it working?') + '<span class="tag ok">' + esc(comp.verdict) + '</span>',
        '<div class="panel-body tight">'
        + '<div style="display:flex;align-items:baseline;gap:8px"><p class="figure">+' + comp.gainedKg + ' <span class="unit">kg</span></p>'
        + '<p class="caption">since ' + esc(comp.since) + '</p></div>'
        + '<div class="split" role="img" aria-label="Of the gain, ' + comp.leanKg + ' kilograms lean and ' + comp.fatKg + ' kilograms fat, sample estimate">'
        + '<i class="lean" style="width:' + Math.round((comp.leanKg / comp.gainedKg) * 100) + '%"></i>'
        + '<i class="fat" style="width:' + Math.round((comp.fatKg / comp.gainedKg) * 100) + '%"></i></div>'
        + '<div class="legend"><span><i style="background:var(--s-strength)"></i>' + comp.leanKg + ' kg lean</span>'
        + '<span><i style="background:var(--s-energy)"></i>' + comp.fatKg + ' kg fat</span></div>'
        + '<p class="caption">' + src(comp.source) + ' from weight and strength trend. Not a body scan.</p></div>')

      // Plateau / fatigue notice
      + '<div class="callout"><p class="label warn">Worth a look · advisory</p>'
      + '<p class="caption"><strong>' + esc(MOCK.plateau.exercise) + '</strong> has not moved in '
      + MOCK.plateau.evidence.length + ' qualifying sessions, and your fatigue trend is at its highest of the block. '
      + 'Nothing has been changed — this is a notice, not an adjustment.</p>'
      + '<button class="btn sm" data-action="goto" data-target="progress" style="align-self:flex-start">See the evidence</button></div>'

      // Quick actions
      + panel(headLeft('Quick actions'),
        '<div class="panel-body"><div class="quick">'
        + qa('start-workout', 'Start today&rsquo;s workout', 'Programming')
        + qa('goto:independent', 'Log an independent workout', 'Performed log')
        + qa('goto:sleep', 'Record sleep', 'Recovery')
        + qa('goto:cardio', 'Add cycling or cardio', 'Cardio')
        + qa('goto:recover', 'Review recovery', 'Recovery')
        + qa('goto:eat', 'View nutrition', 'Nutrition')
        + qa('goto:progress', 'View progress', 'Progress')
        + qa('goto:setup', 'Edit programme', 'Setup')
        + '</div></div>');
  }

  function qa(action, name, sub) {
    const parts = action.split(':');
    const attrs = parts[0] === 'goto'
      ? 'data-action="goto" data-target="' + parts[1] + '"'
      : 'data-action="' + parts[0] + '"';
    return '<button type="button" ' + attrs + '><span class="qa-name">' + name + '</span>'
      + '<span class="qa-sub">' + esc(sub) + '</span></button>';
  }

  // ---- 2 · TRAIN — today's session -------------------------------------

  function renderTrain() {
    const p = plan();
    const r = readinessScore();
    const band = readinessBand(r.score);

    let html = screenHead('train', MOCK.programme.name,
      esc(MOCK.programme.split) + ' · ' + esc(MOCK.programme.dayLabel) + ' ' + src(MOCK.programme.source));

    // Session header: n/m exercises, minutes, state.
    html += panel(
      headLeft('Session') + '<div class="right"><span class="tag ' + (state.session === 'active' ? 'ok' : 'muted') + '">'
      + esc(sessionLabel()) + '</span></div>',
      '<div class="stats"><div><p class="label sm">Exercises</p><p class="stat-value">' + p.done + ' / ' + p.included.length + '</p></div>'
      + '<div><p class="label sm">Elapsed / plan</p><p class="stat-value">' + estimateElapsed(p) + ' <span class="unit">/ ' + p.minutes + ' min</span></p></div>'
      + '<div><p class="label sm">Working sets</p><p class="stat-value">' + p.sets + '</p></div></div>'
      + '<hr class="rule"><div class="panel-body tight">'
      + '<div class="gauge" role="img" aria-label="Session progress"><i style="width:'
      + Math.round((p.done / Math.max(1, p.included.length)) * 100) + '%"></i></div>'
      + '<p class="caption">Readiness ' + r.score + ' · ' + esc(band.intensity)
      + '. <span class="ghost-text">Shown, not applied.</span></p></div>'
      + '<hr class="rule"><div class="panel-body">' + sessionControls()
      + '<button class="btn ghost block" data-action="goto" data-target="summary">Session summary</button>'
      + '</div>');

    // Muscle groups
    html += panel(headLeft('Target muscle groups'),
      '<div class="panel-body tight"><div class="chips">'
      + MOCK.programme.muscleGroups.map((m) => '<span class="chip static">' + esc(m) + '</span>').join('')
      + '</div></div>');

    // Time
    html += panel(headLeft('Time available') + '<span class="tag muted">' + state.minutes + ' min</span>',
      '<div class="panel-body tight"><div class="chips" role="group" aria-label="Time available today">'
      + MOCK.timeOptions.map((m) => '<button type="button" class="chip" data-minutes="' + m + '" aria-pressed="'
        + (m === state.minutes) + '">' + m + '</button>').join('')
      + '</div></div>');

    // Warm-up
    html += panel(headLeft('Warm-up') + '<span class="tag muted">Not working sets</span>',
      '<div class="panel-body tight">'
      + MOCK.programme.warmup.map((w) => '<div class="row"><div class="main">'
        + '<p class="heading">' + esc(w.label) + '</p><p class="caption">' + esc(w.detail) + '</p></div>'
        + '<div class="trail"><span class="tag muted">Warm-up</span></div></div>').join('')
      + '</div>');

    // Exercise list
    html += '<div><p class="label" style="margin-bottom:8px">Exercise order · tap to expand</p>'
      + '<div id="ov-list" style="display:flex;flex-direction:column;gap:8px">'
      + state.rows.map((row) => exerciseRow(row, p)).join('');

    if (p.omitted.length) {
      html += '<div class="callout"><p class="label warn">Left out to fit ' + state.minutes + ' minutes</p>'
        + '<p class="caption">' + esc(p.omitted.map(displayName).join(', '))
        + '. Dropped because they are accessory work, not because you finished them. '
        + 'Give yourself more time and they come back.</p></div>';
    }
    if (p.setsTrimmed) {
      html += '<div class="callout"><p class="label warn">Sets reduced</p>'
        + '<p class="caption">Even with the accessories out, the session does not fit. Each exercise shows one fewer set. '
        + 'The compound movements are kept.</p></div>';
    }
    html += '</div></div>';

    html += '<button class="btn block" data-action="open-add-exercise">Add an exercise</button>';

    html += '<div class="callout signal"><p class="label signal">Progression rule</p>'
      + '<p class="caption">' + esc(MOCK.programme.progressionRule) + '</p></div>';

    // A static coach prompt. No model, no chat.
    html += '<div class="callout info"><p class="label info">Trace</p>'
      + '<p class="caption">Short on time, need to swap a movement, or something feels off? '
      + 'Change the time budget above, replace an exercise, or skip it — the programme keeps your history either way.</p>'
      + '<p class="caption ghost-text">A static prompt in this prototype. No model is running.</p></div>';

    return html;
  }

  function sessionLabel() {
    return { idle: 'Not started', active: 'In progress', paused: 'Paused', done: 'Complete' }[state.session];
  }

  function estimateElapsed(p) {
    const done = state.rows.filter((r) => r.status === 'done');
    return Math.round(done.reduce((s, r) => s + rowMinutes(r), 0) + (state.session === 'idle' ? 0 : WARMUP_MIN));
  }

  function sessionControls() {
    if (state.session === 'idle') {
      return '<button class="btn primary block" data-action="start-workout">Start workout</button>';
    }
    if (state.session === 'active') {
      return '<div class="btn-row"><button class="btn" data-action="pause-session">Pause</button>'
        + '<button class="btn" data-action="finish-session">Finish</button></div>';
    }
    if (state.session === 'paused') {
      return '<div class="callout"><p class="label warn">Paused</p>'
        + '<p class="caption">The rest timer is stopped and nothing advances until you resume.</p></div>'
        + '<div class="btn-row"><button class="btn primary" data-action="resume-session">Resume</button>'
        + '<button class="btn" data-action="finish-session">Finish</button></div>';
    }
    return '<button class="btn block" data-action="goto" data-target="summary">See the summary</button>';
  }

  /** The "where this goes" table. One shape, used by the session summary and
   *  by both cardio screens, so the calorie-target row always reads the same. */
  function whereThisGoes(rows, note) {
    return '<div class="callout info"><p class="label info">Where this goes</p>'
      + '<div class="table-wrap"><table><caption class="sr-only">What this changes</caption><tbody>'
      + rows.map(([name, cls, verdict]) => '<tr><td>' + name + '</td><td><span class="tag ' + cls + '">'
        + verdict + '</span></td></tr>').join('')
      + '</tbody></table></div>'
      + (note ? '<p class="caption">' + note + '</p>' : '') + '</div>';
  }

  function exerciseRow(row, p) {
    const ex = row.source;
    const isOmitted = p.omitted.indexOf(row) !== -1;
    const open = state.openId === row.id;
    const cls = ['ex'];
    if (row.status === 'active') cls.push('active');
    if (row.status === 'skipped' || isOmitted) cls.push('skipped');

    let tag = '';
    if (row.status === 'done') tag = '<span class="tag ok">Done</span>';
    else if (row.status === 'active') tag = '<span class="tag ok">Now</span>';
    else if (row.status === 'skipped') tag = '<span class="tag muted">Skipped</span>';
    else if (isOmitted) tag = '<span class="tag muted">Not today</span>';
    else if (ex.plateau) tag = '<span class="tag watch">Watch</span>';

    let detail = '';
    if (open) {
      detail = '<div class="ex-detail">'
        + '<dl class="dl">'
        + '<dt>Primary</dt><dd>' + esc((ex.primary || []).join(', ')) + '</dd>'
        + '<dt>Secondary</dt><dd>' + esc((ex.secondary || []).join(', ') || '—') + '</dd>'
        + '<dt>Pattern</dt><dd>' + esc(ex.pattern || '—') + '</dd>'
        + '<dt>Equipment</dt><dd>' + esc(ex.equipment) + '</dd>'
        + '<dt>Rest</dt><dd>' + ex.restSec + ' seconds between sets</dd>'
        + '<dt>Swap to</dt><dd>' + esc(ex.substitute || '—') + '</dd>'
        + '</dl>'
        + (row.status === 'active' && state.session === 'active' ? setLogger(row) : '')
        + (state.session === 'paused' && row.status === 'active'
          ? '<div class="callout"><p class="caption">Session paused. Resume to log a set.</p></div>' : '')
        + '<div class="btn-row">'
        + '<button class="btn sm" data-action="open-exercise" data-id="' + row.id + '">Full detail</button>'
        + '<button class="btn sm" data-action="open-replace" data-id="' + row.id + '">Replace</button>'
        + '<button class="btn sm" data-action="skip" data-id="' + row.id + '">'
        + (row.status === 'skipped' ? 'Undo skip' : 'Skip') + '</button>'
        + '</div></div>';
    }

    return '<div class="' + cls.join(' ') + '" data-open="' + open + '">'
      + '<button class="ex-head" data-action="toggle" data-id="' + row.id + '" aria-expanded="' + open + '">'
      + '<span class="ex-index" aria-hidden="true">' + (row.order + 1) + '</span>'
      + '<span class="ex-name"><span class="heading">' + esc(displayName(row)) + '</span>'
      + (row.replacedWith ? '<span class="ex-prescription">Replaced ' + esc(ex.name) + '</span>' : '')
      + '<span class="ex-prescription">' + esc(prescriptionLine(row)) + '</span></span>'
      + tag + '<span class="chev" aria-hidden="true">&#9662;</span>'
      + '</button>' + detail + '</div>';
  }

  /** The compact set logger. Adopted from the reference: log the set where
   *  the exercise already is, rather than pushing the lifter to another
   *  screen mid-session. The reps-in-reserve row is Trace's own vocabulary —
   *  `set_logs.rir` already exists. */
  function setLogger(row) {
    const ex = row.source;
    const d = row.draft;
    const n = Math.min(row.logged.length + 1, ex.sets);

    const kgField = ex.loadKg == null
      ? '<div class="field"><p class="label sm">Load</p><div class="stepper"><output style="font-size:14px">Bodyweight</output></div></div>'
      : '<div class="field"><p class="label sm" id="lbl-kg-' + row.id + '">Kg</p>'
        + '<div class="stepper" role="group" aria-labelledby="lbl-kg-' + row.id + '">'
        + '<button type="button" data-action="draft" data-id="' + row.id + '" data-field="kg" data-delta="-2.5" aria-label="Decrease load">&minus;</button>'
        + '<output>' + d.kg + '</output>'
        + '<button type="button" data-action="draft" data-id="' + row.id + '" data-field="kg" data-delta="2.5" aria-label="Increase load">+</button>'
        + '</div></div>';

    const logged = row.logged.map((s, i) =>
      '<p class="set-line done"><span class="dot"></span>Set ' + (i + 1) + ' · '
      + (s.kg == null ? 'bodyweight' : s.kg + ' kg') + ' × ' + s.reps + ' reps · ' + s.rir + ' RIR</p>').join('');
    const pending = [];
    for (let i = row.logged.length + 1; i <= ex.sets; i++) {
      pending.push('<p class="set-line"><span class="dot"></span>Set ' + i + ' · not logged</p>');
    }

    const rir = ['0', '1', '2', '3', '4', '5+'].map((v, i) =>
      '<button type="button" data-action="rir" data-id="' + row.id + '" data-rir="' + i + '"'
      + ' aria-pressed="' + (d.rir === i) + '" aria-label="' + v + ' reps in reserve">' + v + '</button>').join('');

    const restRow = state.rest.forId === row.id && state.rest.remaining > 0
      ? '<div class="callout signal"><p class="label signal">Rest · ' + fmtTime(state.rest.remaining) + '</p>'
        + '<p class="caption">Target ' + ex.restSec + ' s between sets.</p>'
        + '<button class="btn sm" data-action="skip-rest" style="align-self:flex-start">Skip rest</button></div>'
      : '';

    return '<div class="setbox">'
      + '<div style="display:flex;justify-content:space-between;align-items:baseline">'
      + '<p class="label signal">Set ' + n + ' of ' + ex.sets + '</p>'
      + '<p class="label sm">Target ' + ex.repLow + '–' + ex.repHigh + ' · ' + ex.rir + ' RIR</p></div>'
      + '<div class="setgrid">' + kgField
      + '<div class="field"><p class="label sm" id="lbl-reps-' + row.id + '">Reps</p>'
      + '<div class="stepper" role="group" aria-labelledby="lbl-reps-' + row.id + '">'
      + '<button type="button" data-action="draft" data-id="' + row.id + '" data-field="reps" data-delta="-1" aria-label="Decrease reps">&minus;</button>'
      + '<output>' + d.reps + '</output>'
      + '<button type="button" data-action="draft" data-id="' + row.id + '" data-field="reps" data-delta="1" aria-label="Increase reps">+</button>'
      + '</div></div></div>'
      + '<div><p class="label sm" id="lbl-rir-' + row.id + '">How many more reps could you have done?</p>'
      + '<div class="rir-row" role="group" aria-labelledby="lbl-rir-' + row.id + '" style="margin-top:6px">' + rir + '</div>'
      + '<p class="caption" style="margin-top:6px">Reps in reserve. It sets the next load — and it is the number the plateau check reads.</p></div>'
      + '<button class="btn primary block" data-action="log-set" data-id="' + row.id + '"'
      + (d.rir === null ? ' disabled' : '') + '>Log set</button>'
      + restRow
      + '<div class="set-list">' + logged + pending.join('') + '</div></div>';
  }

  const fmtTime = (s) => Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0');

  // ---- 3 · EXERCISE DETAIL ---------------------------------------------

  function renderExercise() {
    const row = state.rows.filter((r) => r.id === state.focusedId)[0] || state.rows[0];
    const ex = row.source;
    const pool = MOCK.substitutionPool[row.id] || [];
    const pStatus = {
      progressing: ['ok', 'Progressing'],
      confirmed: ['watch', 'Plateau · confirmed'],
      insufficient_data: ['muted', 'Not enough data yet'],
    }[ex.plateauStatus] || ['muted', 'Unknown'];

    let html = screenHead('exercise', displayName(row),
      esc(prescriptionLine(row)) + ' ' + src(ex.source));

    html += '<figure class="movement" style="margin:0">' + movementSVG(ex.shape)
      + '<figcaption><p class="label warn">Illustration · not a demonstration</p>'
      + '<p class="caption" style="margin-top:3px">An original diagram drawn from simple shapes. '
      + 'It shows the shape of the movement, not correct technique for any individual body.</p></figcaption></figure>';

    html += panel(headLeft('Muscles'),
      '<div class="panel-body tight"><dl class="dl">'
      + '<dt>Primary</dt><dd>' + esc((ex.primary || []).join(', ')) + '</dd>'
      + '<dt>Secondary</dt><dd>' + esc((ex.secondary || []).join(', ')) + '</dd>'
      + '<dt>Pattern</dt><dd>' + esc(ex.pattern) + '</dd>'
      + '<dt>Equipment</dt><dd>' + esc(ex.equipment) + '</dd></dl></div>');

    html += panel(headLeft('What this is', 'signal'),
      '<div class="panel-body tight"><p class="body">' + esc(ex.beginner) + '</p></div>');

    html += panel(headLeft('Form cues'),
      '<div class="panel-body"><ol class="cues">'
      + ex.cues.map((c) => '<li><span>' + esc(c) + '</span></li>').join('') + '</ol></div>');

    html += panel(headLeft('Common mistakes', 'warn'),
      '<div class="panel-body tight"><ul class="bullets">'
      + ex.mistakes.map((c) => '<li>' + esc(c) + '</li>').join('') + '</ul></div>');

    html += panel(headLeft('What you should feel'),
      '<div class="panel-body tight"><p class="body">' + esc(ex.feel) + '</p>'
      + '<p class="caption">If you feel sharp or unusual pain instead, stop the movement. '
      + 'This screen cannot tell you what is wrong, and does not try.</p></div>');

    html += panel(headLeft('Make it easier or harder'),
      '<div class="panel-body tight">'
      + '<div class="row"><div class="main"><p class="heading">Easier</p><p class="caption">' + esc(ex.easier) + '</p></div></div>'
      + '<div class="row"><div class="main"><p class="heading">Harder</p><p class="caption">' + esc(ex.harder) + '</p></div></div>'
      + '</div>');

    // Progression history
    if (ex.e1rm) {
      const first = ex.e1rm[0], last = ex.e1rm[ex.e1rm.length - 1];
      const delta = round1(last - first);
      html += panel(headLeft('Estimated 1RM') + '<span class="tag ' + (delta > 0 ? 'ok' : 'watch') + '">'
        + (delta > 0 ? '+' : '') + delta + ' kg / 8 wk</span>',
        '<div class="panel-body tight">'
        + '<div style="display:flex;align-items:baseline;gap:8px"><p class="figure">' + last + ' <span class="unit">kg</span></p>'
        + '<p class="caption">' + src(SOURCE.ESTIMATED) + '</p></div>'
        + lineChart(ex.e1rm, { label: 'Estimated one-rep max over eight weeks, sample data' })
        + '<p class="caption">Estimated from your logged sets and reps in reserve. Not a tested maximum — '
        + 'this prototype never asks you to attempt one.</p></div>');
    }

    html += panel(headLeft('Recent performance') + '<span class="tag muted">' + ex.history.length + ' sessions</span>',
      '<div class="panel-body tight"><div class="table-wrap"><table>'
      + '<caption class="sr-only">Recent sessions for this exercise, sample data</caption>'
      + '<thead><tr><th scope="col">Date</th><th scope="col">Load</th><th scope="col">Reps</th><th scope="col">RIR</th></tr></thead><tbody>'
      + ex.history.map((h) => '<tr><td>' + esc(h.date) + '</td><td>'
        + (h.load == null ? 'body' : h.load + ' kg') + '</td><td>' + h.reps + '</td><td>' + h.rir + '</td></tr>').join('')
      + '</tbody></table></div></div>');

    html += panel(headLeft('Plateau status') + '<span class="tag ' + pStatus[0] + '">' + esc(pStatus[1]) + '</span>',
      '<div class="panel-body tight"><p class="caption">'
      + (ex.plateauStatus === 'confirmed'
        ? esc(MOCK.plateau.reason) + ' Options are on the Progress screen — nothing changes here.'
        : ex.plateauStatus === 'insufficient_data'
          ? 'Fewer than three qualifying sessions. The check says so rather than guessing.'
          : 'Load or reps are still moving. No action needed.')
      + '</p></div>');

    html += panel(headLeft('Swap to') + '<span class="tag muted">' + pool.length + ' options</span>',
      '<div class="panel-body tight"><p class="caption">' + esc(ex.substituteWhy) + '</p>'
      + '<div class="chips" style="margin-top:6px">'
      + pool.map((name) => '<button type="button" class="chip" data-action="pick-sub" data-id="' + row.id
        + '" data-name="' + esc(name) + '" aria-pressed="' + (row.replacedWith === name) + '">'
        + esc(name) + '</button>').join('') + '</div></div>');

    if (row.replacedWith) {
      html += '<div class="callout signal"><p class="label signal">Replaced</p>'
        + '<p class="caption">Doing ' + esc(row.replacedWith) + ' instead of ' + esc(ex.name)
        + '. Your history for ' + esc(ex.name) + ' stays exactly as it is.</p></div>';
    }

    html += '<div class="btn-row">'
      + '<button class="btn" data-action="open-replace" data-id="' + row.id + '">Replace</button>'
      + '<button class="btn" data-action="skip" data-id="' + row.id + '">'
      + (row.status === 'skipped' ? 'Undo skip' : 'Skip today') + '</button></div>';

    return html;
  }

  // ---- 4 · SESSION SUMMARY ---------------------------------------------

  function renderSummary() {
    const done = state.rows.filter((r) => r.status === 'done');
    const skipped = state.rows.filter((r) => r.status === 'skipped');
    const sets = done.reduce((n, r) => n + r.logged.length, 0);
    const reps = done.reduce((n, r) => n + r.logged.reduce((m, s) => m + s.reps, 0), 0);
    const volume = done.reduce((n, r) => n + r.logged.reduce((m, s) => m + (s.kg || 0) * s.reps, 0), 0);

    if (!done.length && state.session !== 'done') {
      return screenHead('summary', 'Session summary', 'Nothing logged yet')
        + '<div class="panel"><div class="state-box"><p class="glyph" aria-hidden="true">&mdash;</p>'
        + '<p class="value-sm">No sets logged</p>'
        + '<p class="caption">Start the session and log a set — the summary fills in as you go.</p>'
        + '<button class="btn sm" data-action="goto" data-target="train" style="margin-top:6px">Back to the session</button>'
        + '</div></div>'
        + whereThisGoes([
          ['Your training history', 'muted', 'Nothing yet'],
          ['Today&rsquo;s calorie target', 'muted', 'Unchanged'],
        ], 'A session you never start changes nothing — and even a finished one leaves your calorie target alone.');
    }

    return screenHead('summary', 'Session summary',
      esc(MOCK.programme.name) + ' ' + src(SOURCE.DEMO))
      + '<div class="stats panel">'
      + '<div><p class="label sm">Exercises</p><p class="stat-value">' + done.length + '</p></div>'
      + '<div><p class="label sm">Sets</p><p class="stat-value">' + sets + '</p></div>'
      + '<div><p class="label sm">Reps</p><p class="stat-value">' + reps + '</p></div>'
      + '<div><p class="label sm">Volume</p><p class="stat-value">' + Math.round(volume) + ' <span class="unit">kg</span></p></div>'
      + '</div>'
      + panel(headLeft('What you did'),
        '<div class="panel-body tight">'
        + (done.length ? done.map((r) => '<div class="row"><div class="main">'
          + '<p class="heading">' + esc(displayName(r)) + '</p>'
          + '<p class="caption">' + r.logged.map((s) => (s.kg == null ? 'BW' : s.kg + ' kg') + '×' + s.reps).join(' · ') + '</p></div>'
          + '<div class="trail"><span class="tag ok">Done</span></div></div>').join('')
          : '<p class="caption">Nothing completed.</p>')
        + '</div>')
      + (skipped.length ? panel(headLeft('Skipped', 'warn'),
        '<div class="panel-body tight">' + skipped.map((r) => '<div class="row"><div class="main">'
          + '<p class="heading">' + esc(displayName(r)) + '</p>'
          + '<p class="caption">Still in your programme for next time.</p></div></div>').join('')
        + '</div>') : '')
      + whereThisGoes([
        ['Your training history', 'ok', 'Added'],
        ['Weekly volume by muscle', 'ok', 'Added'],
        ['Programme adherence', 'ok', 'Added'],
        ['Today&rsquo;s calorie target', 'muted', 'Unchanged'],
      ], 'Training energy is already inside your calorie target. Adding it back is the single most reliable '
        + 'way to turn a lean gain into a fat one. In this prototype nothing is written at all.')
      + '<div class="btn-row"><button class="btn" data-action="goto" data-target="progress">See progress</button>'
      + '<button class="btn ghost" data-action="reset-session">Reset the prototype session</button></div>';
  }

  // ---- 5 · INDEPENDENT WORKOUT (performed logging) ----------------------

  function renderIndependent() {
    const picked = state.independent.picked;
    let html = screenHead('independent', 'Train anyway',
      'Not a programme day. Pick what you are training and this builds a session from it. ' + src(SOURCE.DEMO));

    html += '<div class="callout info"><p class="label info">This is logging, not programming</p>'
      + '<p class="caption">A session you build here is recorded as something you did. It does not change your '
      + 'programme week and it does not overwrite a planned session.</p></div>';

    html += panel(headLeft('What are we training?') + '<span class="tag muted">' + picked.length + ' selected</span>',
      '<div class="panel-body tight"><div class="chips" role="group" aria-label="Muscle groups to train">'
      + MOCK.muscleGroups.map((m) => '<button type="button" class="chip wide" data-action="pick-muscle" data-name="'
        + esc(m) + '" aria-pressed="' + (picked.indexOf(m) !== -1) + '">' + esc(m) + '</button>').join('')
      + '</div></div>');

    if (state.independent.generated) {
      html += panel(headLeft('Built for you', 'signal') + '<span class="tag ok">' + state.independent.generated.length + ' exercises</span>',
        '<div class="panel-body tight">'
        + state.independent.generated.map((e, i) => '<div class="row"><div class="main">'
          + '<p class="heading">' + (i + 1) + ' · ' + esc(e.name) + '</p>'
          + '<p class="caption">' + e.sets + ' × ' + e.repLow + '–' + e.repHigh + ' · ' + e.rir + ' RIR · '
          + esc(e.equipment) + '</p></div>'
          + '<div class="trail">' + src(e.source) + '</div></div>').join('')
        + '<p class="caption" style="margin-top:6px">Built against your current logged loads. '
        + 'Nothing here has been saved.</p></div>');
    } else {
      html += '<div class="panel"><div class="state-box"><p class="glyph" aria-hidden="true">&mdash;</p>'
        + '<p class="value-sm">Nothing selected yet</p>'
        + '<p class="caption">Pick one or more muscle groups above.</p></div></div>';
    }

    html += '<button class="btn primary block" data-action="generate-independent"'
      + (picked.length ? '' : ' disabled') + '>Build session · ' + picked.length + ' group'
      + (picked.length === 1 ? '' : 's') + '</button>';

    return html;
  }

  // ---- 6 · RECOVERY ----------------------------------------------------

  function renderRecover() {
    const r = readinessScore();
    const band = readinessBand(r.score);
    const s = sleepStats();
    const trend = MOCK.readiness.trend;

    let html = screenHead('recover', 'Recovery',
      'Every question here is optional. You can train without answering any of them.');

    html += '<div class="callout info"><p class="label info">What this is, and what it is not</p>'
      + '<p class="caption">These are questions you answer about yourself. They are not measurements, '
      + 'not a health assessment, and not a diagnosis. In this prototype the values are pre-filled '
      + 'samples and nothing is stored anywhere.</p></div>';

    // Readiness result first — the answer before the inputs.
    html += panel(headLeft('Readiness') + '<span class="tag ' + band.cls + '">' + esc(band.name) + '</span>',
      '<div class="panel-body tight">'
      + '<div style="display:flex;align-items:baseline;gap:10px"><p class="readout">' + r.score + '</p>'
      + '<p class="caption">out of 100<br>from your own answers</p></div>'
      + '<div class="gauge tall" role="img" aria-label="Readiness ' + r.score + ' out of 100, sample value">'
      + '<i class="' + band.fill + '" style="width:' + r.score + '%"></i></div>'
      + '<p class="caption" style="margin-top:4px"><strong>' + esc(band.intensity) + '.</strong> '
      + SUGGESTIONS[band.name] + '</p>'
      + '<p class="caption ghost-text">' + src(MOCK.readiness.source) + ' — nothing has been applied to your programme.</p>'
      + '</div>');

    // Why — per-factor contribution. The reference's "show your working".
    const rows = [
      ['Sleep length', r.parts.sleep, 0.30],
      ['Sleep quality', r.parts.quality, 0.15],
      ['Energy', r.parts.energy, 0.20],
      ['Soreness', r.parts.soreness, 0.175],
      ['Stress', r.parts.stress, 0.175],
    ];
    html += panel(headLeft('Why this number'),
      '<div class="panel-body tight">'
      + rows.map(([name, got, weight]) => {
        const pct = Math.round((got / weight) * 100);
        return '<div class="vol-row"><span class="name">' + esc(name) + '</span>'
          + '<span class="bar"><span class="gauge"><i class="' + (pct < 50 ? 'warn' : '')
          + '" style="width:' + pct + '%"></i></span></span>'
          + '<span class="n">' + Math.round(got * 100) + ' / ' + Math.round(weight * 100) + '</span></div>';
      }).join('')
      + '<p class="caption">Each answer contributes up to the points shown. The weights are fixed in this '
      + 'prototype and are illustrative, not validated.</p></div>');

    html += panel(headLeft('Recovery trend', 'sleep') + '<span class="tag demo">7 days</span>',
      '<div class="panel-body tight">'
      + lineChart(trend.map((t) => t.score), { colour: 'var(--s-sleep)', label: 'Readiness over seven days, sample data' })
      + '<div class="spark-axis" aria-hidden="true">' + trend.map((t) => '<span>' + esc(t.day) + '</span>').join('') + '</div>'
      + '<p class="caption">Trending down across the week. ' + src(SOURCE.DEMO) + '</p></div>');

    // Sleep summary + link to detail
    html += panel(headLeft('Sleep', 'sleep') + '<button class="btn sm" data-action="goto" data-target="sleep">Detail</button>',
      '<div class="stats"><div><p class="label sm">Last night</p><p class="stat-value">'
      + fmtHours(state.sleepNights[state.sleepNights.length - 1].asleep) + '</p></div>'
      + '<div><p class="label sm">7-night avg</p><p class="stat-value">' + fmtHours(s.avg) + '</p></div>'
      + '<div><p class="label sm">Bed / wake</p><p class="stat-value" style="font-size:13px">'
      + esc(state.sleepNights[state.sleepNights.length - 1].bedtime || '—') + ' · '
      + esc(state.sleepNights[state.sleepNights.length - 1].wake || '—') + '</p></div></div>');

    // Inputs
    html += panel(headLeft('Your answers') + '<div class="right">' + src(MOCK.readiness.source) + sample() + '</div>',
      '<div class="panel-body">'
      + '<div class="field"><p class="label sm" id="lbl-sleep">Hours asleep</p>'
      + '<div class="stepper" role="group" aria-labelledby="lbl-sleep">'
      + '<button type="button" data-step="sleepHours" data-delta="-0.5" aria-label="Decrease hours asleep">&minus;</button>'
      + '<output id="out-sleepHours" aria-live="polite">' + round1(state.readiness.sleepHours).toFixed(1) + '</output>'
      + '<button type="button" data-step="sleepHours" data-delta="0.5" aria-label="Increase hours asleep">+</button>'
      + '</div></div>'
      + '<div><p class="label sm" id="lbl-quality">Sleep quality</p>'
      + '<div class="chips" role="group" aria-labelledby="lbl-quality" style="margin-top:6px">'
      + QUALITIES.map((q) => '<button type="button" class="chip" data-quality="' + q + '" aria-pressed="'
        + (state.readiness.quality === q) + '">' + q + '</button>').join('') + '</div></div>'
      + SCALES.map((sc) => '<div><div style="display:flex;justify-content:space-between">'
        + '<p class="label sm" id="lbl-' + sc.key + '">' + esc(sc.label) + '</p>'
        + '<p class="label sm ghost-text">' + esc(sc.low) + ' &rarr; ' + esc(sc.high) + '</p></div>'
        + '<div class="rir-row" role="group" aria-labelledby="lbl-' + sc.key + '" style="margin-top:6px">'
        + [1, 2, 3, 4, 5].map((n) => '<button type="button" data-scale="' + sc.key + '" data-value="' + n
          + '" aria-pressed="' + (state.readiness[sc.key] === n) + '" aria-label="' + esc(sc.label)
          + ' ' + n + ' of 5">' + n + '</button>').join('') + '</div></div>').join('')
      + '<div class="btn-row"><button class="btn primary" data-action="save-readiness">Use for today</button>'
      + '<button class="btn ghost" data-action="skip-readiness">Skip for now</button></div>'
      + '<p class="caption">Skipping leaves today&rsquo;s plan exactly as it is.</p>'
      + '</div>');

    html += '<div class="callout"><p class="label warn">Pain</p>'
      + '<p class="caption">If something hurts, this prototype does not ask you to train through it and does not '
      + 'try to work out why. It stops suggesting extra load and points you to a qualified professional. '
      + 'It cannot tell you what is wrong.</p></div>';

    return html;
  }

  const fmtHours = (h) => (h === null || h === undefined ? '<span class="ghost-text">&mdash;</span>'
    : Math.floor(h) + '<span class="unit">h</span> ' + String(Math.round((h % 1) * 60)).padStart(2, '0') + '<span class="unit">m</span>');

  // ---- 7 · SLEEP DETAIL ------------------------------------------------

  function renderSleep() {
    const s = sleepStats();
    const nights = state.sleepNights;
    const conn = MOCK.sleep.connection;

    let html = screenHead('sleep', 'Sleep',
      'Seven nights. ' + src(MOCK.sleep.source));

    html += '<div class="callout sleep"><p class="label sleep">Nothing here was measured</p>'
      + '<p class="caption">Trace has not read sleep from any device in this prototype. No sleep permission '
      + 'has been requested and no health data has been imported. Every value below was typed in, '
      + 'estimated, or is marked unavailable.</p></div>';

    html += '<div class="stats panel">'
      + '<div><p class="label sm">7-night avg</p><p class="stat-value">' + fmtHours(s.avg) + '</p></div>'
      + '<div><p class="label sm">Target</p><p class="stat-value">' + fmtHours(MOCK.sleep.targetHours) + '</p></div>'
      + '<div><p class="label sm">Consistency</p><p class="stat-value">' + (s.consistency === null ? '&mdash;' : s.consistency + '%') + '</p></div>'
      + '</div>';

    html += panel(headLeft('Nights', 'sleep'),
      '<div class="panel-body tight">'
      + sparkbar(nights.map((n) => n.asleep), {
        labels: nights.map((n) => n.day),
        label: 'Hours asleep per night over seven nights, sample data',
        classify: (v) => (v < 6 ? 'short' : 'sleep'),
      })
      + (s.shortest ? '<p class="caption" style="margin-top:6px">' + esc(s.shortest.day) + ' was short at '
        + round1(s.shortest.asleep) + ' h. If your lifts feel flat the next day, that is worth knowing before '
        + 'you change anything about your food.</p>' : '')
      + '<p class="caption ghost-text">Hatched bar = no record for that night.</p></div>');

    html += panel(headLeft('History') + '<span class="tag muted">' + nights.length + ' nights</span>',
      '<div class="panel-body tight">'
      + nights.slice().reverse().map((n, idx) => {
        const i = nights.length - 1 - idx;
        const unavailable = n.asleep === null;
        return '<div class="row"><div class="main">'
          + '<p class="heading">' + esc(n.day) + ' · ' + esc(n.date) + '</p>'
          + '<p class="caption">' + (unavailable ? 'No record'
            : esc(n.bedtime) + ' &rarr; ' + esc(n.wake) + ' · ' + n.awakenings + ' awakenings · ' + esc(n.quality)) + '</p>'
          + '<p class="caption">' + src(n.source) + '</p></div>'
          + '<div class="trail"><p class="value-sm">' + (unavailable ? '<span class="ghost-text">&mdash;</span>' : round1(n.asleep) + ' h') + '</p>'
          + (unavailable ? '' : '<button class="btn sm" data-action="delete-night" data-index="' + i + '" style="margin-top:6px">Delete</button>')
          + '</div></div>';
      }).join('')
      + '</div>');

    // Manual entry
    html += panel(headLeft('Add a night by hand') + '<div class="right">' + src(SOURCE.MANUAL) + '</div>',
      '<div class="panel-body">'
      + '<div class="field"><p class="label sm" id="lbl-mh">Hours asleep</p>'
      + '<div class="stepper" role="group" aria-labelledby="lbl-mh">'
      + '<button type="button" data-sleepdraft="hours" data-delta="-0.25" aria-label="Decrease hours">&minus;</button>'
      + '<output id="out-mh">' + state.sleepDraft.hours.toFixed(2) + '</output>'
      + '<button type="button" data-sleepdraft="hours" data-delta="0.25" aria-label="Increase hours">+</button>'
      + '</div></div>'
      + '<div><p class="label sm" id="lbl-mq">Quality</p>'
      + '<div class="chips" role="group" aria-labelledby="lbl-mq" style="margin-top:6px">'
      + QUALITIES.map((q) => '<button type="button" class="chip" data-sleepquality="' + q + '" aria-pressed="'
        + (state.sleepDraft.quality === q) + '">' + q + '</button>').join('') + '</div></div>'
      + '<button class="btn primary block" data-action="add-night">Add night</button>'
      + '<p class="caption">Records added here are marked <strong>manually recorded</strong>, which is a different '
      + 'kind of fact from something a device measured. The real app cannot store this yet — its sleep rows '
      + 'assume a device wrote them.</p></div>');

    html += panel(headLeft('Sources') + '<span class="tag muted">' + esc(conn.state || 'Not connected') + '</span>',
      '<div class="panel-body tight">'
      + '<div class="row"><div class="main"><p class="heading">' + esc(conn.provider) + '</p>'
      + '<p class="caption">' + esc(conn.note) + '</p></div>'
      + '<div class="trail">' + src(conn.source) + '</div></div></div>');

    html += '<div class="callout"><p class="label warn">Privacy</p>'
      + '<p class="caption">Sleep, pain and stress are health information in a way a bench-press number is not. '
      + 'How long records are kept, whether they appear in an account export, and whether deleting one removes '
      + 'it permanently are open questions in the design documents — not settled behaviour. This prototype '
      + 'stores nothing, so nothing here can be exported or leaked.</p></div>';

    return html;
  }

  // ---- 8 · CARDIO ------------------------------------------------------

  function renderCardio() {
    const c = cardioActivity();
    const week = MOCK.cardio;

    if (state.cardioEmpty) {
      return screenHead('cardio', 'Cardio', 'Nothing recorded ' + src(SOURCE.UNAVAILABLE))
        + '<div class="seg" role="group" aria-label="Sample activity type">'
        + '<button type="button" data-cardio="outdoor" aria-pressed="' + (state.cardio === 'outdoor') + '">Outdoor</button>'
        + '<button type="button" data-cardio="indoor" aria-pressed="' + (state.cardio === 'indoor') + '">Indoor</button></div>'
        + '<div class="panel"><div class="state-box"><p class="glyph" aria-hidden="true">&mdash;</p>'
        + '<p class="value-sm">No cardio recorded</p>'
        + '<p class="caption">Nothing to factor in. Today&rsquo;s plan stays as written.</p></div></div>'
        + '<button class="btn ghost block" data-action="toggle-cardio-empty">Show the sample activity</button>';
    }

    let html = screenHead('cardio', 'Cardio', esc(c.when) + ' ' + src(c.source));

    html += '<div class="seg" role="group" aria-label="Sample activity type">'
      + '<button type="button" data-cardio="outdoor" aria-pressed="' + (state.cardio === 'outdoor') + '">Outdoor</button>'
      + '<button type="button" data-cardio="indoor" aria-pressed="' + (state.cardio === 'indoor') + '">Indoor</button></div>';

    html += panel(headLeft('Weekly cardio load', 'cardio') + '<span class="tag demo">' + week.weekSessions + ' sessions</span>',
      '<div class="panel-body tight">'
      + '<div style="display:flex;align-items:baseline;gap:8px"><p class="figure">' + week.weekMinutes + ' <span class="unit">min</span></p>'
      + '<p class="caption">of ' + week.weekTargetMinutes + ' min this week</p></div>'
      + '<div class="gauge" role="img" aria-label="Weekly cardio minutes against target"><i class="cardio" style="width:'
      + Math.round((week.weekMinutes / week.weekTargetMinutes) * 100) + '%"></i></div></div>');

    html += panel(headLeft(c.title) + '<div class="right"><span class="tag demo">' + esc(c.label) + '</span></div>',
      '<div class="stats">'
      + '<div><p class="label sm">Duration</p><p class="stat-value">' + c.durationMin + ' <span class="unit">min</span></p></div>'
      + '<div><p class="label sm">Distance</p><p class="stat-value">' + c.distanceKm + ' <span class="unit">km</span></p></div>'
      + '<div><p class="label sm">Avg speed</p><p class="stat-value">' + c.avgSpeed + ' <span class="unit">km/h</span></p></div>'
      + '</div><hr class="rule"><div class="stats">'
      + '<div><p class="label sm">Elevation</p><p class="stat-value">' + c.elevationM + ' <span class="unit">m</span></p></div>'
      + '<div><p class="label sm">Energy</p><p class="stat-value">' + c.energyKcal + ' <span class="unit">kcal</span></p></div>'
      + '<div><p class="label sm">Basis</p><p class="stat-value" style="font-size:13px">Estimated</p></div>'
      + '</div><hr class="rule"><div class="panel-body tight">'
      + '<p class="value-sm">' + esc(c.intensity) + '</p>'
      + '<button class="btn sm" data-action="goto" data-target="ride" style="align-self:flex-start;margin-top:4px">Open detail</button></div>');

    html += routeBlock(c);

    // The invariant, in Trace's words.
    html += '<div class="callout info"><p class="label info">Where this goes</p>'
      + '<div class="table-wrap"><table><caption class="sr-only">What this ride changes</caption><tbody>'
      + '<tr><td>Activity list</td><td><span class="tag ok">Added</span></td></tr>'
      + '<tr><td>Weekly cardio load</td><td><span class="tag ok">Added</span></td></tr>'
      + '<tr><td>Today&rsquo;s calorie target</td><td><span class="tag muted">Unchanged</span></td></tr>'
      + '</tbody></table></div>'
      + '<p class="caption">' + c.energyKcal + ' kcal does <strong>not</strong> become ' + c.energyKcal
      + ' kcal to eat. Your target already contains the riding you normally do, and adding it back is the '
      + 'single most reliable way to turn a lean gain into a fat one.</p></div>';

    html += '<div class="callout cardio"><p class="label cardio">Effect on today&rsquo;s leg work</p>'
      + '<p class="caption">' + esc(c.effect) + '</p>'
      + '<p class="caption ghost-text">An explanation, not an adjustment. Sample reasoning only.</p></div>';

    html += panel(headLeft('Recent') + '<span class="tag muted">' + state.rides.length + '</span>',
      '<div class="panel-body tight">'
      + (state.rides.length ? state.rides.map((r, i) => '<div class="row"><div class="main">'
        + '<p class="heading">' + esc(r.title) + '</p>'
        + '<p class="caption">' + esc(r.when) + ' · ' + r.distanceKm + ' km · ' + esc(r.kind) + '</p>'
        + '<p class="caption">' + src(r.source)
        + (r.illustrative ? ' <span class="tag muted">Illustrative only</span>' : '') + '</p></div>'
        + '<div class="trail"><p class="value-sm">' + r.energyKcal + ' <span class="unit">kcal</span></p>'
        + '<button class="btn sm" data-action="delete-ride" data-index="' + i + '" style="margin-top:6px">Delete</button>'
        + '</div></div>').join('')
        : '<p class="caption">No activities.</p>')
      + '<p class="caption ghost-text" style="margin-top:6px">The <strong>imported</strong> row shows what a '
      + 'record from a connected app would look like. Nothing was imported — every source is disconnected.</p>'
      + '</div>');

    html += '<button class="btn ghost block" data-action="toggle-cardio-empty">Show the empty state</button>';
    return html;
  }

  /** Route preview. Outdoor only, and only when the user leaves it visible.
   *  An indoor session has no geography, so drawing a line would be a claim
   *  about where the numbers came from. */
  function routeBlock(c) {
    if (!c.routeAvailable) {
      return '<div class="callout"><p class="label warn">No route</p>'
        + '<p class="caption">This is an indoor session. There is no route, so none is drawn — '
        + 'a map here would be a claim about somewhere you never went.</p></div>';
    }
    if (!state.routeVisible) {
      return '<div class="callout"><p class="label warn">Route hidden</p>'
        + '<p class="caption">You have hidden the route for this activity.</p>'
        + '<button class="btn sm" data-action="toggle-route" style="align-self:flex-start">Show route</button></div>';
    }
    return '<figure class="route" style="margin:0">'
      + '<svg viewBox="0 0 400 180" role="img" aria-labelledby="route-title route-desc">'
      + '<title id="route-title">Placeholder route illustration</title>'
      + '<desc id="route-desc">A decorative drawn line standing in for a map. It is not a recorded route '
      + 'and does not correspond to any real location.</desc>'
      + '<rect width="400" height="180" fill="#141A20"></rect>'
      + '<g stroke="#1C2126" stroke-width="1"><path d="M0 45H400M0 90H400M0 135H400M100 0V180M200 0V180M300 0V180"></path></g>'
      + '<path d="M30 150 C 80 120, 70 70, 120 60 S 200 100, 250 70 S 330 40, 370 55" fill="none" '
      + 'stroke="#3DDC84" stroke-width="2.5" stroke-linecap="round"></path>'
      + '<circle cx="30" cy="150" r="4" fill="#3DDC84"></circle>'
      + '<circle cx="370" cy="55" r="4" fill="#0E1216" stroke="#3DDC84" stroke-width="2.5"></circle></svg>'
      + '<figcaption><p class="label warn">Demo route · not recorded</p>'
      + '<p class="caption" style="margin-top:3px">A drawn placeholder. Trace did not record a route, did not '
      + 'use location services, and this line is not a map of anywhere.</p>'
      + '<button class="btn sm" data-action="toggle-route" style="margin-top:8px">Hide route</button>'
      + '</figcaption></figure>';
  }

  // ---- 9 · RIDE DETAIL -------------------------------------------------

  function renderRide() {
    const c = cardioActivity();
    const st = state.rideState;

    let html = screenHead('ride', c.title, esc(c.when) + ' · ' + esc(c.label) + ' ' + src(c.source));

    html += panel(headLeft('Recording state') + '<span class="tag ' + (st === 'active' ? 'ok' : 'muted') + '">'
      + esc(st) + '</span>',
      '<div class="panel-body">'
      + '<div class="seg" role="group" aria-label="Recording state">'
      + ['idle', 'active', 'paused', 'finished'].map((s) =>
        '<button type="button" data-ridestate="' + s + '" aria-pressed="' + (st === s) + '">' + s + '</button>').join('')
      + '</div>'
      + '<p class="caption">These are display states only. This prototype does not record anything, does not '
      + 'access location, and no timer is running behind them.</p></div>');

    html += '<div class="stats panel">'
      + '<div><p class="label sm">Distance</p><p class="stat-value">' + c.distanceKm + ' <span class="unit">km</span></p></div>'
      + '<div><p class="label sm">Moving</p><p class="stat-value">' + fmtTime(c.durationMin * 60).replace(':', 'h ') + '</p></div>'
      + '<div><p class="label sm">Climb</p><p class="stat-value">' + c.elevationM + ' <span class="unit">m</span></p></div>'
      + '</div>';

    html += routeBlock(c);

    html += panel(headLeft('Energy') + '<span class="tag watch">Estimated</span>',
      '<div class="panel-body tight">'
      + '<div style="display:flex;align-items:baseline;gap:8px"><p class="figure">' + c.energyKcal + ' <span class="unit">kcal</span></p></div>'
      + '<p class="caption">Estimated from duration, distance and your body weight. There is no power meter and '
      + 'no heart-rate stream behind this number, so it carries real uncertainty — which is why it never '
      + 'becomes food.</p></div>');

    html += '<div class="callout info"><p class="label info">Where this goes</p>'
      + '<div class="table-wrap"><table><caption class="sr-only">What this activity changes</caption><tbody>'
      + '<tr><td>Activity list</td><td><span class="tag ok">Added</span></td></tr>'
      + '<tr><td>Weekly cardio load</td><td><span class="tag ok">Added</span></td></tr>'
      + '<tr><td>Lower-body volume</td><td><span class="tag watch">Suggestion only</span></td></tr>'
      + '<tr><td>Today&rsquo;s calorie target</td><td><span class="tag muted">Unchanged</span></td></tr>'
      + '</tbody></table></div></div>';

    html += '<div class="callout"><p class="label warn">Location</p>'
      + '<p class="caption">No location permission has been requested and none is needed to use this prototype. '
      + 'If a real version ever drew a route, the track would be precise location history — among the most '
      + 'sensitive data an app can hold — and would need its own consent, retention rule and delete control '
      + 'before it shipped.</p></div>';

    html += '<div class="callout"><p class="label warn">Duplicates</p>'
      + '<p class="caption">If the same ride arrived from two connected apps it should appear once, not twice. '
      + 'Nothing is connected here, so there is nothing to reconcile.</p></div>';

    html += '<button class="btn danger block" data-action="confirm-delete-activity">Delete this activity</button>';
    return html;
  }

  // ---- 10 · NUTRITION --------------------------------------------------

  function renderEat() {
    const n = MOCK.nutrition;
    const left = n.targetKcal - n.eatenKcal;

    let html = screenHead('eat', 'Today', 'A read-only mirror of the food log. ' + src(n.source));

    html += '<div class="callout info"><p class="label info">Read-only</p>'
      + '<p class="caption">This prototype shows how the food log sits beside training. It does not add, edit '
      + 'or delete food, and it does not change how the food database behaves.</p></div>';

    html += panel(headLeft('Remaining today', 'warn') + '<span class="tag ok">On track</span>',
      '<div class="panel-body tight">'
      + '<div style="display:flex;align-items:baseline;gap:8px"><p class="readout">' + left.toLocaleString() + '</p>'
      + '<p class="caption">kcal left<br>' + n.eatenKcal.toLocaleString() + ' of ' + n.targetKcal.toLocaleString() + '</p></div>'
      + '<div class="gauge tall" role="img" aria-label="Calories eaten against target"><i style="width:'
      + Math.round((n.eatenKcal / n.targetKcal) * 100) + '%"></i></div></div>'
      + '<hr class="rule"><div class="stats">'
      + macroCell('Protein', n.protein) + macroCell('Carbs', n.carbs) + macroCell('Fat', n.fat)
      + '</div>');

    html += panel(headLeft('Worth watching'),
      '<div class="panel-body tight">'
      + n.watch.map((w) => '<div class="vol-row"><span class="name">' + esc(w.name) + '</span>'
        + '<span class="bar"><span class="gauge"><i class="' + (w.over ? 'warn' : '') + '" style="width:'
        + Math.min(100, Math.round((w.value / w.target) * 100)) + '%"></i></span></span>'
        + '<span class="n">' + w.value + '</span></div>').join('')
      + '<p class="caption">Against a ' + n.watch[0].target + ' ' + n.watch[0].unit + ' guide. ' + src(SOURCE.DEMO) + '</p></div>');

    html += panel(headLeft('Add food') + '<span class="tag demo">Entry points</span>',
      '<div class="panel-body"><div class="quick">'
      + '<button type="button" data-action="scan-note"><span class="qa-name">Scan a plate</span><span class="qa-sub">Returns a range</span></button>'
      + '<button type="button" data-action="scan-note"><span class="qa-name">Barcode</span><span class="qa-sub">Off the label</span></button>'
      + '<button type="button" data-action="scan-note"><span class="qa-name">Search</span><span class="qa-sub">Food database</span></button>'
      + '<button type="button" data-action="scan-note"><span class="qa-name">My foods</span><span class="qa-sub">Saved and corrected</span></button>'
      + '</div><p class="caption">These are entry points only. Scanning already works in the real app — this '
      + 'prototype deliberately does not reimplement it.</p></div>');

    html += panel(headLeft('Today&rsquo;s log') + '<span class="tag muted">' + n.meals.length + ' meals</span>',
      '<div class="panel-body tight">'
      + n.meals.map((m) => '<div style="padding:6px 0">'
        + '<div style="display:flex;justify-content:space-between;align-items:baseline">'
        + '<p class="heading">' + esc(m.name) + '</p>'
        + '<p class="value-sm">' + m.kcal + (m.band ? ' <span class="unit">±' + Math.round((m.band[1] - m.band[0]) / 2) + '</span>' : '') + '</p></div>'
        + m.items.map((it) => '<div class="row"><div class="main">'
          + '<p class="caption" style="color:var(--dim)">' + esc(it.name) + '</p>'
          + '<p class="caption">' + esc(it.portion) + ' · ' + esc(it.attribution) + '</p>'
          + '<p class="caption">' + src(it.source) + ' '
          + (it.verification === 'verified'
            ? '<span class="tag ok">Verified</span>'
            : '<span class="tag watch">Estimated</span>')
          + (it.kind === 'ai_estimate' ? ' <span class="tag mock">Photo estimate</span>' : '')
          + '</p></div>'
          + '<div class="trail"><p class="value-sm">' + it.kcal
          + (it.band ? '<span class="unit"> ±' + Math.round((it.band[1] - it.band[0]) / 2) + '</span>' : '')
          + '</p></div></div>').join('')
        + '</div>').join('')
      + '</div>');

    html += '<div class="callout"><p class="label warn">Three different kinds of number</p>'
      + '<p class="caption"><strong>Verified</strong> came off a label or a checked database row. '
      + '<strong>Estimated</strong> came from a photo and carries a ± band, because a single confident number '
      + 'for a guess is the lie this product exists to avoid. Everything on this screen is also '
      + '<strong>sample</strong> data, which is a third thing again.</p></div>';

    html += panel(headLeft('Meal plan') + '<span class="tag muted">Not built</span>',
      '<div class="state-box"><p class="glyph" aria-hidden="true">&mdash;</p>'
      + '<p class="value-sm">No meal plan</p>'
      + '<p class="caption">The reference screenshots show a generated day of meals. Nothing in Trace produces '
      + 'one, so this is left as a marked placeholder rather than mocked up as though it existed.</p></div>');

    html += '<div class="callout signal"><p class="label signal">Cardio and food</p>'
      + '<p class="caption">Yesterday&rsquo;s ride does not appear on this screen as extra calories to eat, and it '
      + 'never will. The target already contains the training you normally do.</p></div>';

    return html;
  }

  function macroCell(name, m) {
    return '<div><p class="label sm">' + esc(name) + '</p>'
      + '<p class="stat-value">' + m.eaten + ' <span class="unit">g</span></p>'
      + '<div class="gauge" style="margin-top:4px"><i style="width:'
      + Math.min(100, Math.round((m.eaten / m.target) * 100)) + '%"></i></div>'
      + '<p class="caption">' + (m.target - m.eaten) + ' g left</p></div>';
  }

  // ---- 11 · PROGRESS ---------------------------------------------------

  function renderProgress() {
    const p = MOCK.progress;

    let html = screenHead('progress', 'Progress', 'Last eight weeks. ' + src(p.source));

    html += panel(headLeft('Sessions') + '<span class="tag ok">' + p.streakWeeks + '-week streak</span>',
      '<div class="panel-body tight">'
      + '<div style="display:flex;align-items:baseline;gap:8px"><p class="readout">' + p.sessionsThisWeek + '</p>'
      + '<p class="caption">of ' + p.sessionsTarget + ' planned this week</p></div>'
      + sparkbar(p.weeks, { labels: p.weekLabels, label: 'Sessions per week over eight weeks, sample data' })
      + '</div>');

    html += panel(headLeft('Programme adherence'),
      '<div class="panel-body tight">'
      + '<div class="gauge tall" role="img" aria-label="Adherence ' + MOCK.programme.adherencePct + ' percent"><i style="width:'
      + MOCK.programme.adherencePct + '%"></i></div>'
      + '<p class="caption">' + MOCK.programme.adherencePct + '% — ' + esc(MOCK.programme.adherenceNote) + '</p></div>');

    // Volume with four states
    html += panel(headLeft('Weekly sets by muscle')
      + '<div class="right">' + ['data', 'loading', 'empty', 'error'].map((s) =>
        '<button type="button" class="btn sm" data-volstate="' + s + '" aria-pressed="'
        + (state.volState === s) + '">' + s + '</button>').join('') + '</div>',
      '<div class="panel-body" id="vol-body">' + volumeBody() + '</div>');

    // e1RM trend with overlays
    const focus = MOCK.exercises[0];
    html += panel(headLeft('Estimated 1RM trend') + '<span class="tag muted">' + esc(focus.name) + '</span>',
      '<div class="panel-body tight">'
      + lineChart(focus.e1rm, {
        label: 'Estimated one-rep max with optional overlay, sample data',
        overlay: state.overlay === 'sleep' ? p.sleepOverlay : state.overlay === 'cardio' ? p.cardioOverlay : null,
        overlayColour: state.overlay === 'sleep' ? 'var(--s-sleep)' : 'var(--s-alert)',
      })
      + '<div class="seg" style="margin-top:8px" role="group" aria-label="Overlay a second series">'
      + [['none', 'No overlay'], ['sleep', 'Sleep'], ['cardio', 'Cardio']].map(([k, l]) =>
        '<button type="button" data-overlay="' + k + '" aria-pressed="' + (state.overlay === k) + '">' + l + '</button>').join('')
      + '</div>'
      + '<div class="legend" style="margin-top:8px"><span><i style="background:var(--s-strength)"></i>Estimated 1RM</span>'
      + (state.overlay !== 'none' ? '<span><i style="background:' + (state.overlay === 'sleep' ? 'var(--s-sleep)' : 'var(--s-alert)')
        + '"></i>' + (state.overlay === 'sleep' ? 'Hours asleep' : 'Cardio minutes') + '</span>' : '')
      + '</div>'
      + '<p class="caption">Both series are labelled, so which is which never depends on telling the colours apart. '
      + 'An overlay shows two things happening together. It is not evidence that one caused the other.</p></div>');

    // Week vs last
    html += panel(headLeft('This week vs last') + '<span class="tag demo">' + p.sessionsThisWeek + ' sessions</span>',
      '<div class="stats"><div><p class="label sm">Est. 1RM</p><p class="stat-value">22.4 <span class="unit">kg</span></p><p class="caption">+3.7%</p></div>'
      + '<div><p class="label sm">Volume</p><p class="stat-value">1,840 <span class="unit">kg</span></p><p class="caption">+9.2%</p></div>'
      + '<div><p class="label sm">Sets</p><p class="stat-value">16</p><p class="caption">+2</p></div></div>'
      + '<hr class="rule"><div class="stats">'
      + '<div><p class="label sm">Reps</p><p class="stat-value">148</p><p class="caption">+11</p></div>'
      + '<div><p class="label sm">Top set</p><p class="stat-value">16 <span class="unit">kg</span></p><p class="caption">0.0%</p></div>'
      + '<div><p class="label sm">Avg reps</p><p class="stat-value">9.3</p><p class="caption">+0.5</p></div></div>');

    html += panel(headLeft('Exercise progression'),
      '<div class="panel-body tight">'
      + p.lifts.map((l) => {
        const delta = l.to - l.from;
        const plateau = l.status === 'plateau';
        return '<div class="row"><div class="main">'
          + '<p class="heading">' + esc(l.name) + '</p>'
          + '<p class="caption">' + l.from + ' &rarr; ' + l.to + ' ' + esc(l.unit) + ' over 8 weeks</p></div>'
          + '<div class="trail">' + (plateau ? '<span class="tag watch">No change</span>'
            : '<span class="tag ok">+' + delta + ' ' + esc(l.unit) + '</span>') + '</div></div>';
      }).join('') + '</div>');

    html += panel(headLeft('Personal records') + '<span class="tag ok">' + p.records.length + '</span>',
      '<div class="panel-body tight">'
      + p.records.map((r) => '<div class="row"><div class="main"><p class="heading">' + esc(r.name) + '</p>'
        + '<p class="caption">' + esc(r.when) + '</p></div>'
        + '<div class="trail"><p class="value-sm">' + esc(r.detail) + '</p></div></div>').join('')
      + '<p class="caption">Best logged set, not a tested maximum.</p></div>');

    html += panel(headLeft('Fatigue trend', 'warn') + '<span class="tag watch">Rising</span>',
      '<div class="panel-body tight">'
      + lineChart(p.fatigue.map((f) => f.value), { colour: 'var(--s-energy)', label: 'Fatigue index over eight weeks, sample data' })
      + '<div class="spark-axis" aria-hidden="true">' + p.fatigue.map((f) => '<span>' + esc(f.week) + '</span>').join('') + '</div>'
      + '<p class="caption">A rough index built from volume, readiness answers and cardio load. Illustrative — '
      + 'the real app does not compute this, and no threshold here has been validated.</p></div>');

    html += panel(headLeft('Plateau notice · advisory', 'warn')
      + '<span class="tag watch" id="plateau-status">' + esc(MOCK.plateau.statusLabel) + '</span>',
      '<div class="panel-body" id="plateau-body">' + plateauBody() + '</div>');

    html += '<button class="btn block" data-action="goto" data-target="ai">Open the AI trainer review</button>';

    return html;
  }

  function volumeBody() {
    if (state.volState === 'loading') {
      return '<div class="sk-stack" role="status" aria-label="Loading weekly volume">'
        + '<div class="sk w60"></div><div class="sk"></div><div class="sk w80"></div>'
        + '<div class="sk"></div><div class="sk w40"></div></div>';
    }
    if (state.volState === 'empty') {
      return '<div class="state-box"><p class="glyph" aria-hidden="true">&mdash;</p>'
        + '<p class="value-sm">Nothing logged yet</p>'
        + '<p class="caption">Weekly sets appear here after your first session.</p></div>';
    }
    if (state.volState === 'error') {
      return '<div class="state-box"><p class="glyph" aria-hidden="true">&#9888;</p>'
        + '<p class="value-sm">Could not load your volume</p>'
        + '<p class="caption">Your sessions are safe — this panel could not be built. Try again.</p>'
        + '<button class="btn sm" data-volstate="data" style="margin-top:4px">Try again</button></div>';
    }
    return MOCK.progress.volume.map((v) => {
      const pct = Math.round((v.sets / v.target) * 100);
      const under = v.sets < v.target * 0.7;
      return '<div class="vol-row"><span class="name">' + esc(v.muscle) + '</span>'
        + '<span class="bar"><span class="gauge"><i class="' + (under ? 'warn' : '')
        + '" style="width:' + Math.min(100, pct) + '%"></i></span></span>'
        + '<span class="n">' + v.sets + '/' + v.target + '</span></div>';
    }).join('') + '<p class="caption">Sets per muscle this week against the sample target range.</p>';
  }

  function plateauBody() {
    const pl = MOCK.plateau;
    const d = state.plateau;

    if (d.decision) {
      const copy = {
        accepted: 'Recorded as your choice. In the real product this would create a new prescription for your '
          + 'next session — after you confirm it there too. Your programme and your logged history are unchanged.',
        postponed: 'Postponed. This will not come back on your next session. How long a postponement lasts is an '
          + 'open product question, not something this prototype decides.',
        dismissed: 'Dismissed. Your programme is unchanged and nothing was rewritten.',
      }[d.decision];
      const chosen = pl.options.filter((o) => o.id === d.chosen)[0];
      return '<div class="callout signal"><p class="label signal">' + esc(d.decision) + '</p>'
        + (d.decision === 'accepted' && chosen ? '<p class="value-sm">' + esc(chosen.title) + '</p>' : '')
        + '<p class="caption">' + copy + '</p></div>'
        + '<button class="btn ghost block" data-action="plateau-reset">Show the notice again</button>';
    }

    return '<div><p class="value-sm">' + esc(pl.exercise) + '</p>'
      + '<p class="caption" style="margin-top:6px">' + esc(pl.reason) + '</p></div>'
      + '<dl class="dl"><dt>Stalled</dt><dd>' + esc(pl.stalledMetric) + '</dd>'
      + '<dt>Baseline</dt><dd>' + esc(pl.baseline) + '</dd>'
      + '<dt>Current</dt><dd>' + esc(pl.current) + '</dd>'
      + '<dt>Window</dt><dd>' + pl.windowDays + ' days · ' + pl.evidence.length + ' qualifying sessions</dd>'
      + '<dt>Confidence</dt><dd>' + Math.round(pl.confidence * 100) + '%</dd></dl>'
      + '<div><p class="label sm" style="margin-bottom:6px">Sessions considered</p>'
      + '<div class="table-wrap"><table><caption class="sr-only">The sessions this assessment used</caption>'
      + '<thead><tr><th scope="col">Date</th><th scope="col">Load</th><th scope="col">Reps</th>'
      + '<th scope="col">RIR</th><th scope="col">e1RM</th></tr></thead><tbody>'
      + pl.evidence.map((e) => '<tr><td>' + esc(e.date) + (e.baseline ? ' ·' : '') + '</td><td>' + e.load
        + ' kg</td><td>' + e.reps + '</td><td>' + e.rir + '</td><td>' + e.e1rm.toFixed(1) + '</td></tr>').join('')
      + '</tbody></table></div></div>'
      + '<div><p class="label sm" style="margin-bottom:6px">Already ruled out</p>'
      + '<ul class="bullets">' + pl.checked.map((c) => '<li>' + esc(c) + '</li>').join('') + '</ul></div>'
      + '<div><p class="label sm" style="margin-bottom:6px">What you could do</p>'
      + '<div style="display:flex;flex-direction:column;gap:6px">'
      + pl.options.map((o) => '<button type="button" class="chip" style="text-align:left;width:100%" '
        + 'data-action="plateau-pick" data-id="' + o.id + '" aria-pressed="' + (state.plateau.chosen === o.id) + '">'
        + '<span class="value-sm" style="display:block">' + esc(o.title)
        + (o.recommended ? ' <span class="tag ok">Suggested first</span>' : '') + '</span>'
        + '<span class="caption" style="display:block;margin-top:3px">' + esc(o.tradeoff) + '</span></button>').join('')
      + '</div></div>'
      + '<div class="btn-row"><button class="btn primary" data-action="plateau-accept">Accept</button>'
      + '<button class="btn" data-action="plateau-postpone">Not now</button>'
      + '<button class="btn ghost" data-action="plateau-dismiss">Dismiss</button></div>'
      + '<p class="caption">Nothing changes until you choose. Declining leaves the programme exactly as it is.</p>';
  }

  // ---- 12 · AI REVIEW --------------------------------------------------

  function renderAI() {
    const items = state.ai.items;
    const bad = items.filter((i) => !i.valid);

    let html = screenHead('ai', 'A suggested session', 'Nothing here has been added to your plan.');

    html += '<div class="callout"><p class="label warn">Read this before accepting</p>'
      + '<p class="caption">This draft was written into the prototype by hand. No model was called, no service '
      + 'was contacted, and no key exists in this page. In the real product a generated session would need your '
      + 'review before it became a plan, and a session containing an exercise the catalogue does not recognise '
      + 'would be rejected whole rather than quietly patched.</p></div>';

    html += panel(headLeft('Request') + '<span class="tag mock">Mock</span>',
      '<div class="panel-body tight"><dl class="dl">'
      + '<dt>Asked for</dt><dd>' + esc(MOCK.aiDraft.generatedFor) + '</dd>'
      + '<dt>Source</dt><dd>' + esc(MOCK.aiDraft.model) + '</dd>'
      + '<dt>Validated</dt><dd>' + (bad.length ? bad.length + ' of ' + items.length + ' exercise ids not recognised'
        : 'All ' + items.length + ' exercise ids recognised') + '</dd>'
      + '</dl></div>'
      + '<hr class="rule"><div class="stats">'
      + '<div><p class="label sm">Confidence</p><p class="stat-value dash">&mdash;</p></div>'
      + '<div><p class="label sm">Data coverage</p><p class="stat-value dash">&mdash;</p></div>'
      + '<div><p class="label sm">Latency</p><p class="stat-value dash">&mdash;</p></div>'
      + '</div><div class="panel-body tight">'
      + '<p class="caption">Em dashes, not zeroes. No model ran, so there is no confidence to report — and a '
      + 'confident-looking 0% would be its own kind of wrong.</p></div>');

    html += '<div id="ai-list" style="display:flex;flex-direction:column;gap:8px">'
      + items.map((it, i) => '<div class="ex"' + (it.valid ? '' : ' style="border-color:rgba(217,83,79,0.5)"') + '>'
        + '<div class="ex-head" style="cursor:default">'
        + '<span class="ex-index" aria-hidden="true">' + (i + 1) + '</span>'
        + '<span class="ex-name"><span class="heading">' + esc(it.name) + '</span>'
        + '<span class="ex-prescription">' + it.sets + ' × ' + it.repLow + '–' + it.repHigh + ' · ' + it.rir
        + ' RIR · swap: ' + esc(it.sub) + '</span>'
        + '<span class="ex-prescription ghost-text">' + esc(it.id) + '</span></span>'
        + (it.valid ? '<span class="tag mock">Mock id</span>' : '<span class="tag bad">Unknown id</span>')
        + '</div></div>').join('')
      + '</div>';

    html += '<div id="ai-verdict">' + aiVerdict() + '</div>';

    if (state.ai.decision === null) {
      html += '<div class="btn-row" id="ai-actions">'
        + '<button class="btn primary" data-action="ai-confirm">Confirm</button>'
        + '<button class="btn" data-action="ai-edit">Edit</button>'
        + '<button class="btn danger" data-action="ai-reject">Reject</button></div>';
    }

    html += '<p class="caption">Confirm writes nothing. Edit and reject write nothing. This prototype holds all '
      + 'state in memory and forgets it when you reload the page.</p>';

    return html;
  }

  function aiVerdict() {
    const bad = state.ai.items.filter((i) => !i.valid);
    if (state.ai.decision === 'confirmed') {
      return '<div class="callout signal"><p class="label signal">Confirmed</p>'
        + '<p class="caption">In the real product this would become a planned session you could start. '
        + 'Here it writes nothing at all.</p></div>';
    }
    if (state.ai.decision === 'rejected') {
      return '<div class="callout"><p class="label warn">Rejected</p>'
        + '<p class="caption">The draft is discarded whole. The real product would fall back to the '
        + 'rule-generated session — the same one on the Train screen — and record that the draft was rejected, '
        + 'so a silent fallback is still something you can go and look at afterwards.</p></div>';
    }
    if (bad.length) {
      return '<div class="callout"><p class="label warn">Cannot be confirmed as written</p>'
        + '<p class="caption">' + esc(bad[0].name) + ' carries the id <code>' + esc(bad[0].id)
        + '</code>, which is not in the exercise catalogue. The rule is that this rejects the whole draft rather '
        + 'than dropping the one exercise: a five-exercise session minus its fourth is a different session, and '
        + 'nobody reviewed that one.</p>'
        + '<button class="btn sm" data-action="ai-swap" style="align-self:flex-start">Choose a replacement yourself</button></div>';
    }
    return '<div class="callout signal"><p class="label signal">Ready for your review</p>'
      + '<p class="caption">Every id resolves to the catalogue'
      + (state.ai.edited ? ', after the replacement you chose' : '')
      + '. Read it before you accept it — it is a draft, not advice.</p></div>';
  }

  // ---- 13 · SETUP ------------------------------------------------------

  function renderSetup() {
    const s = state.setup;
    const st = MOCK.setup;

    let html = screenHead('setup', 'Programme and goal',
      'Optional fields can be skipped. ' + src(SOURCE.DEMO));

    html += setupPick('Goal', 'goal', st.goals, s.goal);
    html += setupPick('Training phase', 'phase', st.phases, s.phase);

    html += panel(headLeft('Days per week') + '<span class="tag muted">' + s.days + '</span>',
      '<div class="panel-body tight"><div class="rir-row" role="group" aria-label="Days per week">'
      + [2, 3, 4, 5, 6].map((d) => '<button type="button" data-setup="days" data-value="' + d
        + '" aria-pressed="' + (s.days === d) + '">' + d + '</button>').join('')
      + '</div></div>');

    html += panel(headLeft('Available days') + '<span class="tag muted">' + s.available.length + ' picked</span>',
      '<div class="panel-body tight"><div class="chips" role="group" aria-label="Available days">'
      + st.days.map((d) => '<button type="button" class="chip" data-setup-multi="available" data-value="' + d
        + '" aria-pressed="' + (s.available.indexOf(d) !== -1) + '">' + d + '</button>').join('')
      + '</div></div>');

    html += panel(headLeft('Time per session') + '<span class="tag muted">' + s.minutes + ' min</span>',
      '<div class="panel-body tight"><div class="chips" role="group" aria-label="Time per session">'
      + st.sessionMinutes.map((m) => '<button type="button" class="chip" data-setup="minutes" data-value="' + m
        + '" aria-pressed="' + (s.minutes === m) + '">' + m + '</button>').join('')
      + '</div></div>');

    html += panel(headLeft('Equipment') + '<span class="tag muted">' + s.equipment.length + '</span>',
      '<div class="panel-body tight"><div class="chips" role="group" aria-label="Available equipment">'
      + st.equipment.map((e) => '<button type="button" class="chip" data-setup-multi="equipment" data-value="' + esc(e)
        + '" aria-pressed="' + (s.equipment.indexOf(e) !== -1) + '">' + esc(e) + '</button>').join('')
      + '</div><p class="caption">A prescription you cannot actually load is worse than no prescription.</p></div>');

    html += panel(headLeft('Exercises you like') + '<span class="tag muted">Optional</span>',
      '<div class="panel-body tight"><div class="chips" role="group" aria-label="Preferred exercises">'
      + st.exercisePreferences.map((e) => '<button type="button" class="chip" data-setup-multi="liked" data-value="' + esc(e)
        + '" aria-pressed="' + (s.liked.indexOf(e) !== -1) + '">' + esc(e) + '</button>').join('')
      + '</div></div>');

    html += panel(headLeft('Exercises to avoid') + '<span class="tag muted">Optional</span>',
      '<div class="panel-body tight"><div class="chips" role="group" aria-label="Disliked exercises">'
      + st.exercisePreferences.map((e) => '<button type="button" class="chip" data-setup-multi="disliked" data-value="' + esc(e)
        + '" aria-pressed="' + (s.disliked.indexOf(e) !== -1) + '">' + esc(e) + '</button>').join('')
      + '</div></div>');

    html += setupPick('Cardio each week', 'cardio', st.cardioFrequency, s.cardio);

    // Sensitive opt-ins — both skippable, both off by default.
    html += panel(headLeft('Optional · sleep and recovery') + '<span class="tag ' + (s.recoveryOptIn ? 'ok' : 'muted') + '">'
      + (s.recoveryOptIn ? 'On' : 'Off') + '</span>',
      '<div class="panel-body tight">'
      + '<p class="caption">Answer a short check-in about sleep, energy, soreness and stress. These are health '
      + 'questions, they are never required, and you can turn this off again at any time.</p>'
      + '<div class="btn-row" style="margin-top:4px">'
      + '<button class="btn ' + (s.recoveryOptIn ? 'primary' : '') + '" data-action="toggle-optin" data-key="recoveryOptIn">'
      + (s.recoveryOptIn ? 'On' : 'Turn on') + '</button>'
      + '<button class="btn ghost" data-action="skip-optin" data-key="recoveryOptIn">Skip this</button></div></div>');

    html += panel(headLeft('Optional · AI generation') + '<span class="tag ' + (s.aiOptIn ? 'ok' : 'muted') + '">'
      + (s.aiOptIn ? 'On' : 'Off') + '</span>',
      '<div class="panel-body tight">'
      + '<p class="caption">Let a model draft sessions for you to review. Turning this off costs you the model, '
      + 'not the feature — rule-generated programming keeps working exactly the same.</p>'
      + '<div class="btn-row" style="margin-top:4px">'
      + '<button class="btn ' + (s.aiOptIn ? 'primary' : '') + '" data-action="toggle-optin" data-key="aiOptIn">'
      + (s.aiOptIn ? 'On' : 'Turn on') + '</button>'
      + '<button class="btn ghost" data-action="skip-optin" data-key="aiOptIn">Skip this</button></div></div>');

    // Live preview
    html += panel(headLeft('Programme preview', 'signal') + '<span class="tag demo">Not saved</span>',
      '<div class="panel-body tight">'
      + '<p class="value-sm">' + esc(previewSplit(s)) + '</p>'
      + '<dl class="dl" style="margin-top:6px">'
      + '<dt>Goal</dt><dd>' + esc(s.goal) + ' · ' + esc(s.phase) + '</dd>'
      + '<dt>Schedule</dt><dd>' + s.days + ' days · ' + esc(s.available.join(', ') || 'no days picked') + '</dd>'
      + '<dt>Session</dt><dd>' + s.minutes + ' minutes</dd>'
      + '<dt>Equipment</dt><dd>' + esc(s.equipment.join(', ') || 'none picked') + '</dd>'
      + '<dt>Cardio</dt><dd>' + esc(s.cardio) + '</dd>'
      + '<dt>Recovery</dt><dd>' + (s.recoveryOptIn ? 'Check-in on' : 'Skipped') + '</dd>'
      + '<dt>AI</dt><dd>' + (s.aiOptIn ? 'Drafts on, review required' : 'Off — rules only') + '</dd>'
      + '</dl>'
      + '<p class="caption">Rebuilt live from your answers. Deterministic: the same answers always produce '
      + 'the same preview.</p></div>');

    if (s.confirmed) {
      html += '<div class="callout signal"><p class="label signal">Confirmed in this prototype</p>'
        + '<p class="caption">Nothing was written. In the real product this is where a programme and its days '
        + 'would be created in one transaction, archiving any previous active programme.</p></div>';
    }

    html += '<button class="btn primary block" data-action="confirm-programme"'
      + (s.available.length && s.equipment.length ? '' : ' disabled') + '>Confirm programme</button>';
    if (!s.available.length || !s.equipment.length) {
      html += '<p class="caption">Pick at least one day and one piece of equipment first.</p>';
    }

    return html;
  }

  function previewSplit(s) {
    if (s.days <= 2) return 'Full body · 2 days';
    if (s.days === 3) return 'Full body · 3 days';
    if (s.days === 4) return 'Upper / lower · 4 days';
    if (s.days === 5) return 'Upper / lower + full body · 5 days';
    return 'Push / pull / legs · 6 days';
  }

  function setupPick(title, key, options, current) {
    return panel(headLeft(title) + '<span class="tag muted">' + esc(current) + '</span>',
      '<div class="panel-body tight"><div class="chips" role="group" aria-label="' + esc(title) + '">'
      + options.map((o) => '<button type="button" class="chip" data-setup="' + key + '" data-value="' + esc(o)
        + '" aria-pressed="' + (current === o) + '">' + esc(o) + '</button>').join('')
      + '</div></div>');
  }

  // ---- 14 · PROFILE ----------------------------------------------------

  function renderProfile() {
    let html = screenHead('profile', 'Profile', src(SOURCE.DEMO));

    html += panel(headLeft('Account'),
      '<div class="panel-body tight"><p class="value-sm">' + esc(MOCK.user.name) + '</p>'
      + '<p class="caption">' + esc(MOCK.user.goal) + ' · ' + esc(MOCK.user.phase) + ' · '
      + MOCK.user.weightKg + ' kg · ' + MOCK.user.heightCm + ' cm</p>'
      + '<p class="caption ghost-text">An invented person. No account exists behind this screen.</p></div>');

    html += panel(headLeft('Connected sources') + '<span class="tag muted">0 of ' + MOCK.profile.connections.length + '</span>',
      '<div class="panel-body tight">'
      + MOCK.profile.connections.map((c) => '<div class="row"><div class="main">'
        + '<p class="heading">' + esc(c.name) + '</p><p class="caption">' + src(c.source) + '</p></div>'
        + '<div class="trail"><span class="tag muted">' + esc(c.state) + '</span></div></div>').join('')
      + '<p class="caption" style="margin-top:6px">Nothing is connected, and this prototype cannot connect '
      + 'anything. Every "imported" row elsewhere is illustrative.</p></div>');

    html += panel(headLeft('Motion') + '<span class="tag muted">' + esc(state.motion) + '</span>',
      '<div class="panel-body tight">'
      + '<div class="seg" role="group" aria-label="Motion preference">'
      + [['system', 'Follow system'], ['reduced', 'Reduce motion']].map(([k, l]) =>
        '<button type="button" data-motion="' + k + '" aria-pressed="' + (state.motion === k) + '">' + l + '</button>').join('')
      + '</div>'
      + '<p class="caption">The page already honours your operating system setting. This switch is here so the '
      + 'behaviour can be reviewed without changing an OS preference.</p></div>');

    html += panel(headLeft('Programme'),
      '<div class="panel-body"><button class="btn block" data-action="goto" data-target="setup">Edit programme and goal</button></div>');

    html += '<div class="callout"><p class="label warn">What this prototype stores</p>'
      + '<p class="caption">Nothing. No account, no database, no local storage, no network request. Reloading '
      + 'the page resets every screen to its starting state.</p></div>';

    return html;
  }

  // ---- sheets and dialogs ----------------------------------------------

  function openSheet(title, body) {
    $('#sheet-content').innerHTML =
      '<div class="panel-head"><p class="label" id="sheet-title">' + esc(title) + '</p>'
      + '<button class="btn sm ghost" data-action="close-sheet">Close</button></div><hr class="rule">' + body;
    $('#sheet-scrim').hidden = false;
    const first = $('#sheet button');
    if (first) first.focus();
  }
  const closeSheet = () => { $('#sheet-scrim').hidden = true; };

  function openDialog(title, body, confirmLabel, confirmAction) {
    $('#dialog-content').innerHTML =
      '<div class="panel-head"><p class="label warn" id="dialog-title">' + esc(title) + '</p></div><hr class="rule">'
      + '<div class="panel-body"><p class="caption" id="dialog-body">' + body + '</p>'
      + '<div class="btn-row"><button class="btn danger" data-action="' + confirmAction + '">' + esc(confirmLabel) + '</button>'
      + '<button class="btn ghost" data-action="close-dialog">Cancel</button></div></div>';
    $('#dialog-scrim').hidden = false;
    const first = $('#dialog button');
    if (first) first.focus();
  }
  const closeDialog = () => { $('#dialog-scrim').hidden = true; };

  // ---- routing ---------------------------------------------------------

  function renderTabs() {
    const active = SCREENS[state.screen].tab;
    $('#tabbar').innerHTML = TABS.map((t) =>
      '<button role="tab" data-screen="' + t.id + '" aria-selected="' + (t.id === active) + '"'
      + ' aria-label="' + esc(t.label) + '">'
      + '<span class="glyph" aria-hidden="true">' + t.glyph + '</span>' + esc(t.label) + '</button>').join('');
  }

  function go(screen, opts) {
    const o = opts || {};
    if (!SCREENS[screen]) return;
    if (!o.replace && screen !== state.screen) state.history.push(state.screen);
    stopRest();
    state.screen = screen;
    $$('.screen').forEach((s) => { s.hidden = s.id !== 'screen-' + screen; });
    paint();
    renderTabs();
    if (o.focus !== false) $('#screen-' + screen).focus({ preventScroll: true });
    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  function paint() {
    // Only the live screen holds markup. A hidden screen that keeps its DOM
    // leaves stale nodes in the document -- which is how an indoor session
    // ended up with an outdoor route still sitting in the page.
    $$('.screen').forEach((s) => {
      s.innerHTML = s.id === 'screen-' + state.screen ? SCREENS[state.screen].render() : '';
    });
  }

  function back() {
    const prev = state.history.pop() || SCREENS[state.screen].parent || 'home';
    state.screen = prev;
    $$('.screen').forEach((s) => { s.hidden = s.id !== 'screen-' + prev; });
    paint();
    renderTabs();
    $('#screen-' + prev).focus({ preventScroll: true });
  }

  // ---- rest timer ------------------------------------------------------

  function startRest(row) {
    stopRest();
    state.rest.forId = row.id;
    state.rest.remaining = row.source.restSec;
    state.rest.timer = window.setInterval(() => {
      if (state.session !== 'active') { stopRest(); return; }
      state.rest.remaining -= 1;
      if (state.rest.remaining <= 0) { stopRest(); toast('Rest done.'); }
      if (state.screen === 'train') paint();
    }, 1000);
  }

  function stopRest() {
    if (state.rest.timer) window.clearInterval(state.rest.timer);
    state.rest.timer = null;
    state.rest.remaining = 0;
    state.rest.forId = null;
  }

  // ---- session actions -------------------------------------------------

  const rowById = (id) => state.rows.filter((r) => r.id === id)[0];

  function startWorkout() {
    if (state.session === 'active' || state.session === 'paused') {
      go('train');
      toast('Session already open.');
      return;
    }
    const p = plan();
    const first = p.included.filter((r) => r.status === 'pending')[0];
    if (!first) { toast('Nothing left to start — every exercise is skipped or done.'); return; }
    state.session = 'active';
    first.status = 'active';
    state.openId = first.id;
    go('train');
    toast('Session started. Sample only — nothing is being recorded.');
  }

  function advance(row) {
    row.status = 'done';
    const next = plan().included.filter((r) => r.status === 'pending')[0];
    if (next) { next.status = 'active'; state.openId = next.id; }
    else {
      state.openId = null;
      state.session = 'done';
      toast('That is the whole session. Nothing was saved.');
      go('summary');
    }
  }

  // ---- events ----------------------------------------------------------

  document.addEventListener('click', (event) => {
    const target = event.target.closest('button');
    if (!target) return;
    const d = target.dataset;

    if (d.screen) { go(d.screen); return; }
    if (d.action === 'goto') { go(d.target); return; }
    if (d.action === 'back') { back(); return; }

    const row = d.id ? rowById(d.id) : null;

    switch (d.action) {
      case 'start-workout': startWorkout(); return;

      case 'pause-session':
        state.session = 'paused'; stopRest(); paint();
        toast('Paused. Nothing advances until you resume.'); return;

      case 'resume-session':
        state.session = 'active'; paint(); toast('Resumed.'); return;

      case 'finish-session':
        state.session = 'done'; stopRest(); go('summary'); return;

      case 'reset-session':
        state.rows = MOCK.exercises.map((ex, i) => makeRow(ex, i));
        state.session = 'idle'; state.openId = null; stopRest();
        go('train'); toast('Prototype session reset.'); return;

      case 'toggle':
        state.openId = state.openId === row.id ? null : row.id; paint(); return;

      case 'open-exercise':
        state.focusedId = row.id; go('exercise'); return;

      case 'open-replace': {
        const pool = MOCK.substitutionPool[row.id] || [];
        openSheet('Replace ' + row.source.name,
          '<div class="panel-body tight">'
          + '<p class="caption">Your history for ' + esc(row.source.name) + ' stays exactly as it is. '
          + 'A replacement applies to today only.</p>'
          + '<div class="chips" style="margin-top:6px">'
          + pool.map((name) => '<button type="button" class="chip" data-action="pick-sub" data-id="' + row.id
            + '" data-name="' + esc(name) + '" aria-pressed="' + (row.replacedWith === name) + '">'
            + esc(name) + '</button>').join('')
          + '</div>'
          + (row.replacedWith ? '<button class="btn block" data-action="undo-replace" data-id="' + row.id
            + '" style="margin-top:10px">Undo replacement</button>' : '')
          + '</div>');
        return;
      }

      case 'pick-sub':
        row.replacedWith = row.replacedWith === d.name ? null : d.name;
        closeSheet(); paint();
        toast(row.replacedWith ? 'Swapped to ' + row.replacedWith + '.' : 'Back to ' + row.source.name + '.');
        return;

      case 'undo-replace':
        row.replacedWith = null; closeSheet(); paint(); toast('Back to ' + row.source.name + '.'); return;

      case 'skip': {
        const wasActive = row.status === 'active';
        if (row.status === 'skipped') {
          row.status = 'pending';
          toast(displayName(row) + ' is back in the session.');
        } else {
          row.status = 'skipped'; row.logged = []; stopRest();
          toast(displayName(row) + ' skipped. It stays in your programme for next time.');
          if (wasActive && state.session === 'active') {
            const next = plan().included.filter((r) => r.status === 'pending')[0];
            if (next) { next.status = 'active'; state.openId = next.id; }
          }
        }
        paint(); return;
      }

      case 'open-add-exercise':
        openSheet('Add an exercise',
          '<div class="panel-body tight">'
          + '<p class="caption">Added to today only. Your programme is not rewritten.</p>'
          + MOCK.extraExercises.map((e) => '<div class="row"><div class="main">'
            + '<p class="heading">' + esc(e.name) + '</p>'
            + '<p class="caption">' + e.sets + ' × ' + e.repLow + '–' + e.repHigh + ' · ' + esc(e.equipment) + '</p></div>'
            + '<div class="trail"><button class="btn sm" data-action="add-exercise" data-id="' + e.id + '">Add</button></div>'
            + '</div>').join('')
          + '</div>');
        return;

      case 'add-exercise': {
        const ex = MOCK.extraExercises.filter((e) => e.id === d.id)[0];
        if (!ex || state.rows.some((r) => r.id === ex.id)) { closeSheet(); return; }
        const copy = Object.assign({}, ex, {
          secondary: [], pattern: 'Accessory', shape: 'core',
          beginner: 'Added to today only in this prototype.',
          cues: ['Control the weight.', 'Full range of motion.', 'Stop with reps in reserve.'],
          mistakes: ['Rushing.'], feel: 'The named muscle.',
          easier: 'Fewer reps.', harder: 'More reps.',
          substitute: '—', substituteWhy: 'Not offered for an added exercise.',
          e1rm: null, history: [], plateauStatus: 'insufficient_data',
        });
        state.rows.push(makeRow(copy, state.rows.length));
        closeSheet(); paint(); toast(ex.name + ' added to today.');
        return;
      }

      case 'draft':
        if (d.field === 'kg') row.draft.kg = Math.max(0, (row.draft.kg || 0) + Number(d.delta));
        else row.draft.reps = clamp(row.draft.reps + Number(d.delta), 1, 60);
        paint(); return;

      case 'rir':
        row.draft.rir = Number(d.rir); paint(); return;

      case 'log-set': {
        if (row.draft.rir === null) return;
        row.logged.push({
          kg: row.source.loadKg == null ? null : row.draft.kg,
          reps: row.draft.reps, rir: row.draft.rir,
        });
        row.draft.rir = null;
        if (row.logged.length >= row.source.sets) {
          toast(displayName(row) + ' complete. Sample only — nothing was saved.');
          advance(row);
        } else {
          startRest(row);
        }
        paint(); return;
      }

      case 'skip-rest': stopRest(); paint(); return;

      // --- independent
      case 'pick-muscle': {
        const i = state.independent.picked.indexOf(d.name);
        if (i === -1) state.independent.picked.push(d.name);
        else state.independent.picked.splice(i, 1);
        state.independent.generated = null;
        paint(); return;
      }

      case 'generate-independent': {
        const picked = state.independent.picked;
        const pool = MOCK.exercises.concat(MOCK.extraExercises);
        const chosen = pool.filter((e) => (e.primary || []).some((m) =>
          picked.some((p) => m.toLowerCase().indexOf(p.toLowerCase()) !== -1
            || p.toLowerCase().indexOf(m.toLowerCase()) !== -1)));
        state.independent.generated = (chosen.length ? chosen : pool.slice(0, 3)).slice(0, 5);
        paint();
        toast('Built from your current loads. Nothing was saved.');
        return;
      }

      // --- readiness
      case 'save-readiness':
        state.readiness.applied = true; state.readiness.skipped = false;
        toast('Noted for today. The plan has not been changed.'); return;

      case 'skip-readiness':
        state.readiness.skipped = true; state.readiness.applied = false;
        go('home'); toast('Skipped. Today is unchanged.'); return;

      // --- sleep
      case 'add-night': {
        const dr = state.sleepDraft;
        state.sleepNights.push({
          source: SOURCE.MANUAL, day: 'New', date: 'today',
          asleep: dr.hours, inBed: dr.hours + 0.4,
          bedtime: dr.bedtime, wake: dr.wake, awakenings: 1, quality: dr.quality,
        });
        paint(); toast('Night added, marked manually recorded. Nothing was stored.'); return;
      }

      case 'delete-night':
        state.sleepNights.splice(Number(d.index), 1);
        paint(); toast('Night removed from this prototype only.'); return;

      // --- cardio
      case 'toggle-cardio-empty':
        state.cardioEmpty = !state.cardioEmpty; paint(); return;

      case 'toggle-route':
        state.routeVisible = !state.routeVisible; paint();
        toast(state.routeVisible ? 'Route shown.' : 'Route hidden.'); return;

      case 'delete-ride':
        state.rides.splice(Number(d.index), 1);
        paint(); toast('Activity removed from this prototype only.'); return;

      case 'confirm-delete-activity':
        openDialog('Delete this activity?',
          'It disappears from your activity list and your weekly cardio load. Your calorie target does not '
          + 'change, because it never counted this ride in the first place.',
          'Delete', 'do-delete-activity');
        return;

      case 'do-delete-activity':
        closeDialog(); state.rides.shift(); go('cardio');
        toast('Deleted in this prototype only.'); return;

      // --- progress
      case 'plateau-pick':
        state.plateau.chosen = d.id; $('#plateau-body').innerHTML = plateauBody(); return;

      case 'plateau-accept':
        state.plateau.decision = 'accepted'; $('#plateau-body').innerHTML = plateauBody();
        toast('Choice recorded. Your programme is unchanged.'); return;

      case 'plateau-postpone':
        state.plateau.decision = 'postponed'; $('#plateau-body').innerHTML = plateauBody(); return;

      case 'plateau-dismiss':
        state.plateau.decision = 'dismissed'; $('#plateau-body').innerHTML = plateauBody(); return;

      case 'plateau-reset':
        state.plateau.decision = null; $('#plateau-body').innerHTML = plateauBody(); return;

      // --- nutrition
      case 'scan-note':
        toast('Entry point only. This prototype does not log food.'); return;

      // --- AI
      case 'ai-swap': {
        const badItem = state.ai.items.filter((i) => !i.valid)[0];
        if (!badItem) return;
        badItem.id = 'ex_mock_0176';
        badItem.name = 'Dumbbell Lateral Raise';
        badItem.sub = 'Cable Lateral Raise';
        badItem.rir = 2;
        badItem.valid = true;
        state.ai.edited = true;
        paint(); toast('Replaced by you, not by the app.'); return;
      }

      case 'ai-confirm':
        if (state.ai.items.some((i) => !i.valid)) {
          toast('Not confirmable while an exercise id is unrecognised.'); return;
        }
        state.ai.decision = 'confirmed'; paint(); return;

      case 'ai-edit':
        toast('Editing a draft is not built in this prototype. Use the replacement control above.'); return;

      case 'ai-reject':
        state.ai.decision = 'rejected'; paint(); return;

      // --- setup
      case 'toggle-optin':
        state.setup[d.key] = !state.setup[d.key]; paint();
        toast(state.setup[d.key] ? 'Turned on.' : 'Turned off.'); return;

      case 'skip-optin':
        state.setup[d.key] = false; paint(); toast('Skipped. Nothing is collected.'); return;

      case 'confirm-programme':
        state.setup.confirmed = true; paint(); toast('Confirmed in this prototype. Nothing was written.'); return;

      // --- overlays
      case 'close-sheet': closeSheet(); return;
      case 'close-dialog': closeDialog(); return;

      default: break;
    }

    // --- attribute-driven controls
    if (d.minutes) { state.minutes = Number(d.minutes); paint(); toast('Fitted to ' + state.minutes + ' minutes.'); return; }
    if (d.step) { state.readiness.sleepHours = clamp(state.readiness.sleepHours + Number(d.delta), 0, 14); paint(); return; }
    if (d.quality) { state.readiness.quality = d.quality; paint(); return; }
    if (d.scale) { state.readiness[d.scale] = Number(d.value); paint(); return; }
    if (d.sleepdraft) { state.sleepDraft.hours = clamp(state.sleepDraft.hours + Number(d.delta), 0, 14); paint(); return; }
    if (d.sleepquality) { state.sleepDraft.quality = d.sleepquality; paint(); return; }
    if (d.cardio) { state.cardio = d.cardio; state.routeVisible = true; paint(); return; }
    if (d.ridestate) { state.rideState = d.ridestate; paint(); return; }
    if (d.volstate) { state.volState = d.volstate; $('#vol-body').innerHTML = volumeBody(); return; }
    if (d.overlay) { state.overlay = d.overlay; paint(); return; }
    if (d.motion) {
      state.motion = d.motion;
      document.body.dataset.motion = d.motion === 'reduced' ? 'reduced' : '';
      paint(); return;
    }
    if (d.setup) {
      state.setup[d.setup] = isNaN(Number(d.value)) ? d.value : Number(d.value);
      state.setup.confirmed = false; paint(); return;
    }
    if (d.setupMulti) {
      const arr = state.setup[d.setupMulti];
      const i = arr.indexOf(d.value);
      if (i === -1) arr.push(d.value); else arr.splice(i, 1);
      state.setup.confirmed = false; paint(); return;
    }
  });

  // Escape closes whichever overlay is open.
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!$('#dialog-scrim').hidden) { closeDialog(); return; }
    if (!$('#sheet-scrim').hidden) closeSheet();
  });

  // Clicking the scrim itself dismisses; clicking the panel does not.
  $('#sheet-scrim').addEventListener('click', (e) => { if (e.target.id === 'sheet-scrim') closeSheet(); });
  $('#dialog-scrim').addEventListener('click', (e) => { if (e.target.id === 'dialog-scrim') closeDialog(); });

  // Arrow keys move across the tab bar, as a tablist should.
  $('#tabbar').addEventListener('keydown', (event) => {
    const keys = { ArrowLeft: -1, ArrowRight: 1 };
    if (!(event.key in keys)) return;
    const tabs = $$('#tabbar button');
    const i = tabs.indexOf(document.activeElement);
    if (i === -1) return;
    event.preventDefault();
    const next = tabs[(i + keys[event.key] + tabs.length) % tabs.length];
    go(next.dataset.screen, { focus: false });
    $$('#tabbar button')[(i + keys[event.key] + tabs.length) % tabs.length].focus();
  });

  go('home', { replace: true });
}());
