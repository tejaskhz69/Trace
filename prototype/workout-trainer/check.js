/* Prototype checks. Run from the repository root:
 *
 *     node prototype/workout-trainer/check.js
 *
 * It drives the prototype through jsdom -- clicking real buttons, reading the
 * DOM back -- so the claims in README.md are verified rather than asserted.
 *
 * jsdom is NOT a new dependency: it is already in apps/mobile/node_modules
 * because Jest brings it. Nothing is installed, and the checks touch no
 * database, no server and no production file.
 */

'use strict';

const path = require('path');
const fs = require('fs');
const REPO = path.resolve(__dirname, '..', '..');
const { JSDOM } = require(path.join(REPO, 'apps', 'mobile', 'node_modules', 'jsdom'));

const DIR = __dirname;
const html = fs.readFileSync(path.join(DIR, 'index.html'), 'utf8');

const errors = [];
const network = [];

const dom = new JSDOM(html, {
  runScripts: 'dangerously',
  url: 'http://localhost/',
  beforeParse(w) {
    w.addEventListener('error', (e) => errors.push('window error: ' + e.message));
    w.scrollTo = () => {};
    // Any attempt to reach the network is recorded, not permitted.
    w.fetch = (...a) => { network.push('fetch ' + a[0]); return Promise.reject(new Error('blocked')); };
    w.XMLHttpRequest = function () { network.push('xhr'); };
    w.WebSocket = function () { network.push('websocket'); };
    w.navigator.sendBeacon = () => { network.push('beacon'); return false; };
  },
});
const { window } = dom;
const { document } = window;

for (const f of ['data.js', 'app.js']) {
  const el = document.createElement('script');
  el.textContent = fs.readFileSync(path.join(DIR, f), 'utf8');
  document.body.appendChild(el);
}

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const click = (el) => { if (!el) throw new Error('no element to click'); el.click(); };
const text = (s) => ($(s) ? $(s).textContent.trim() : '<<missing ' + s + '>>');
const screenText = () => $('.screen:not([hidden])').textContent;
const visible = () => $$('.screen').filter((p) => !p.hidden);

/** The visible screen. Every scoped assertion goes through this, because a
 *  query against the whole document can pick up a screen the user is not on. */
const scr = () => $('.screen:not([hidden])');
const sq = (sel) => scr().querySelector(sel);
const sqa = (sel) => Array.from(scr().querySelectorAll(sel));

/** Navigate the way a person would: by tab where one exists, otherwise by
 *  walking the real path to the sub-screen. */
const ROUTES = {
  exercise() {
    // The expanded row persists across navigation, so a blind toggle would
    // sometimes collapse it instead of opening it.
    goto('train');
    for (let i = 0; i < 2 && !sq('[data-action="open-exercise"]'); i++) {
      click(sq('[data-action="toggle"]'));
    }
    click(sq('[data-action="open-exercise"]'));
  },
  summary() { goto('train'); click(sq('[data-action="goto"][data-target="summary"]')); },
  ride() { goto('cardio'); click(sq('[data-action="goto"][data-target="ride"]')); },
  ai() { goto('progress'); click(sq('[data-action="goto"][data-target="ai"]')); },
  setup() { goto('home'); click(sq('[data-action="goto"][data-target="setup"]')); },
  independent() { goto('home'); click(sq('[data-action="goto"][data-target="independent"]')); },
  sleep() { goto('recover'); click(sq('[data-action="goto"][data-target="sleep"]')); },
  profile() { click($('.avatar')); },
};

function goto(id) {
  const tab = $('#tabbar [data-screen="' + id + '"]');
  if (tab) { click(tab); return; }
  if (ROUTES[id]) { ROUTES[id](); return; }
  throw new Error('no route to ' + id);
}

let pass = 0, fail = 0;
function check(name, fn) {
  try { fn(); console.log('  ok   ' + name); pass++; }
  catch (e) { console.log('  FAIL ' + name + ' -- ' + e.message); fail++; }
}
const assert = (cond, msg) => { if (!cond) throw new Error(msg); };

const ALL_SCREENS = ['home', 'train', 'exercise', 'summary', 'independent', 'recover', 'sleep',
  'cardio', 'ride', 'eat', 'progress', 'ai', 'setup', 'profile'];

console.log('\n-- boot --');
check('home is the landing screen', () => {
  assert(!$('#screen-home').hidden, 'home hidden');
  assert(visible().length === 1, 'more than one screen visible');
});
check('the disclosure banner is present and not dismissible', () => {
  const b = $('.banner');
  assert(/Prototype/.test(b.textContent) && /sample data only/.test(b.textContent), 'banner wrong');
  assert(!$('.banner button'), 'banner has a dismiss control');
});
check('six bottom tabs render', () => {
  assert($$('#tabbar button').length === 6, 'expected 6 tabs, got ' + $$('#tabbar button').length);
});
check('every tab targets a screen that exists', () => {
  $$('#tabbar button').forEach((t) => assert($('#screen-' + t.dataset.screen), 'dangling ' + t.dataset.screen));
});

console.log('\n-- every screen renders --');
for (const id of ALL_SCREENS) {
  check('renders: ' + id, () => {
    goto(id);
    assert(!$('#screen-' + id).hidden, 'hidden after nav');
    assert($('#screen-' + id).textContent.trim().length > 200, 'looks empty');
    assert(visible().length === 1, 'more than one screen visible');
  });
}

console.log('\n-- navigation --');
check('every screen carries a kind badge', () => {
  for (const id of ALL_SCREENS) {
    goto(id);
    assert($('#screen-' + id + ' .kind'), id + ' has no kind badge');
  }
});
check('the six screen categories are all represented', () => {
  const kinds = new Set();
  for (const id of ALL_SCREENS) { goto(id); kinds.add($('#screen-' + id + ' .kind').textContent.trim()); }
  for (const want of ['Programming', 'Performed log', 'Sleep & recovery', 'Cardio', 'Nutrition', 'Progress']) {
    assert(kinds.has(want), 'missing category: ' + want);
  }
});
check('sub-screens offer a back control that returns', () => {
  goto('home'); goto('cardio');
  click($('[data-action="goto"][data-target="ride"]'));
  assert(!$('#screen-ride').hidden, 'did not reach ride');
  click($('#screen-ride [data-action="back"]'));
  assert(!$('#screen-cardio').hidden, 'back did not return to cardio');
});
check('quick actions reach every hub', () => {
  goto('home');
  for (const t of ['independent', 'sleep', 'cardio', 'recover', 'eat', 'progress', 'setup']) {
    goto('home');
    const b = $('#screen-home [data-action="goto"][data-target="' + t + '"]');
    assert(b, 'no quick action for ' + t);
  }
});
check('the tab bar tracks which section a sub-screen belongs to', () => {
  goto('home'); goto('recover');
  click($('#screen-recover [data-action="goto"][data-target="sleep"]'));
  assert($('#tabbar [data-screen="recover"]').getAttribute('aria-selected') === 'true',
    'recover tab not selected while on sleep');
});

console.log('\n-- sample and source labelling --');
check('every screen discloses that it is sample data', () => {
  for (const id of ALL_SCREENS) {
    goto(id);
    const t = $('#screen-' + id).textContent.toLowerCase();
    assert(/sample|mock|demo|prototype|not recorded|writes nothing|read-only/.test(t), id + ' has no disclosure');
  }
});
check('every screen head carries a Sample tag', () => {
  for (const id of ALL_SCREENS) {
    goto(id);
    assert($('#screen-' + id + ' .screen-head .tag.demo'), id + ' head has no Sample tag');
  }
});
check('source labels come from the fixed vocabulary', () => {
  const allowed = ['demo', 'manually recorded', 'imported', 'estimated', 'unavailable'];
  for (const id of ALL_SCREENS) {
    goto(id);
    $$('#screen-' + id + ' .src').forEach((s) => {
      assert(allowed.indexOf(s.textContent.trim().toLowerCase()) !== -1,
        id + ': unexpected source label "' + s.textContent.trim() + '"');
    });
  }
});
check('every mock record in data.js declares a source', () => {
  const src = fs.readFileSync(path.join(DIR, 'data.js'), 'utf8');
  const objects = (src.match(/\{\s*source:/g) || []).length;
  assert(objects > 40, 'expected many source-tagged records, found ' + objects);
});

console.log('\n-- today\'s workout --');
check('session header shows exercises done over total, and a time budget', () => {
  goto('train');
  assert(/\d+ \/ \d+/.test(screenText()), 'no n/m counter');
  assert(/\/ \d+ min/.test(screenText()), 'no time budget');
});
check('warm-up rows are marked as not working sets', () => {
  assert(/Not working sets/i.test(screenText()), 'warm-up not marked');
});
check('a 15-minute budget drops accessories and names them', () => {
  click($('[data-minutes="15"]'));
  assert(/Left out to fit 15 minutes/.test(screenText()), 'no omission notice');
  assert(/Goblet Squat/.test(screenText()), 'lost a compound');
});
check('restoring the budget restores the accessories', () => {
  click($('[data-minutes="60"]'));
  assert(!/Left out to fit/.test(screenText()), 'still omitting');
});
check('starting the session activates the first exercise', () => {
  click($('[data-action="start-workout"]'));
  assert($('.ex.active'), 'nothing active');
  assert(/In progress/.test(screenText()), 'state not shown');
});
check('log set is disabled until reps-in-reserve is answered', () => {
  assert($('[data-action="log-set"]').disabled, 'log enabled with no RIR');
});
check('choosing reps-in-reserve enables logging', () => {
  click($('[data-action="rir"][data-rir="2"]'));
  assert(!$('[data-action="log-set"]').disabled, 'still disabled');
});
check('the load stepper moves in 2.5 kg increments', () => {
  const before = Number($('.setbox output').textContent);
  click($('[data-action="draft"][data-field="kg"][data-delta="2.5"]'));
  assert(Number($('.setbox output').textContent) === before + 2.5, 'increment wrong');
});
check('logging a set starts a rest countdown', () => {
  click($('[data-action="log-set"]'));
  assert(/Rest ·/.test(screenText()), 'no rest timer shown');
  click($('[data-action="skip-rest"]'));
  assert(!/Rest ·/.test(screenText()), 'rest did not clear');
});
check('pausing stops the session advancing', () => {
  click($('[data-action="pause-session"]'));
  assert(/Paused/.test(screenText()), 'not paused');
  assert(!$('[data-action="log-set"]'), 'set logger still available while paused');
});
check('resuming restores the logger', () => {
  click($('[data-action="resume-session"]'));
  assert($('[data-action="log-set"]'), 'logger did not come back');
});
check('completing every set advances to the next exercise', () => {
  for (let i = 0; i < 8; i++) {
    const rir = $('[data-action="rir"][data-rir="2"]');
    if (rir) click(rir);
    const log = $('[data-action="log-set"]');
    if (log && !log.disabled) click(log);
    const sk = $('[data-action="skip-rest"]');
    if (sk) click(sk);
  }
  assert($$('.ex')[0].className.indexOf('active') === -1, 'first exercise still active');
});
check('an exercise can be added to today only', () => {
  goto('train');
  const before = $$('#ov-list .ex').length;
  click($('[data-action="open-add-exercise"]'));
  assert(!$('#sheet-scrim').hidden, 'sheet did not open');
  click($('[data-action="add-exercise"]'));
  assert($$('#ov-list .ex').length === before + 1, 'exercise not added');
  assert($('#sheet-scrim').hidden, 'sheet did not close');
});
check('replace opens a sheet and names the original', () => {
  const head = $$('[data-action="toggle"]')[2];
  click(head);
  click($('[data-action="open-replace"]'));
  assert(/stays exactly as it is/.test($('#sheet').textContent), 'no history reassurance');
  click($('#sheet [data-action="pick-sub"]'));
  assert(/Replaced/.test($('#ov-list').textContent), 'replacement not shown');
});
check('skipping marks the row and keeps it listed', () => {
  const before = $$('#ov-list .ex').length;
  click($('[data-action="skip"]'));
  assert($('.ex.skipped'), 'nothing skipped');
  assert($$('#ov-list .ex').length === before, 'row disappeared instead of being marked');
});
check('finishing produces a summary with totals', () => {
  click($('[data-action="finish-session"]'));
  assert(!$('#screen-summary').hidden, 'did not reach summary');
  assert(/Sets/.test(screenText()) && /Volume/.test(screenText()), 'no totals');
  assert(/Unchanged/.test(screenText()), 'summary does not state the calorie target is unchanged');
});
check('the prototype session can be reset', () => {
  click($('[data-action="reset-session"]'));
  assert(/Start workout/.test(screenText()), 'not back to an unstarted session');
});

console.log('\n-- exercise detail --');
check('detail carries an original movement diagram, marked as such', () => {
  goto('train');
  click($$('[data-action="toggle"]')[0]);
  click($('[data-action="open-exercise"]'));
  assert($('#screen-exercise .movement svg'), 'no diagram');
  assert(/not a demonstration/i.test(screenText()), 'diagram not qualified');
});
check('detail covers muscles, pattern, cues, mistakes and feel', () => {
  for (const want of ['Primary', 'Secondary', 'Pattern', 'Equipment', 'Form cues', 'Common mistakes', 'What you should feel']) {
    assert(screenText().indexOf(want) !== -1, 'missing section: ' + want);
  }
});
check('cues are numbered steps, not a bulleted list', () => {
  assert($$('#screen-exercise .cues li').length >= 3, 'fewer than three numbered cues');
});
check('detail offers an easier and a harder variation', () => {
  assert(/Easier/.test(screenText()) && /Harder/.test(screenText()), 'variations missing');
});
check('detail shows progression history and recent performance', () => {
  assert(/Estimated 1RM/.test(screenText()), 'no e1RM panel');
  assert($$('#screen-exercise table tbody tr').length >= 3, 'no recent-performance rows');
});
check('e1RM is labelled an estimate, never a tested maximum', () => {
  assert(/[Nn]ot a tested maximum/.test(screenText()), 'e1RM not qualified');
});
check('detail shows a plateau status', () => {
  assert(/Plateau status/.test(screenText()), 'no plateau status');
});

console.log('\n-- independent workout --');
check('independent logging is labelled as logging, not programming', () => {
  goto('home');
  click($('[data-action="goto"][data-target="independent"]'));
  assert($('#screen-independent .kind').textContent.trim() === 'Performed log', 'wrong kind badge');
  assert(/does not change your programme/i.test(screenText()), 'boundary not stated');
});
check('build is disabled until a muscle group is picked', () => {
  assert($('[data-action="generate-independent"]').disabled, 'enabled with nothing picked');
});
check('picking groups builds a session', () => {
  click($('[data-action="pick-muscle"][data-name="Chest"]'));
  click($('[data-action="pick-muscle"][data-name="Core"]'));
  click($('[data-action="generate-independent"]'));
  assert(/Built for you/.test(screenText()), 'nothing generated');
});

console.log('\n-- recovery --');
check('readiness recomputes from the answers', () => {
  goto('recover');
  const before = Number($('#screen-recover .readout').textContent);
  click($('[data-scale="energy"][data-value="5"]'));
  click($('[data-quality="Good"]'));
  const after = Number($('#screen-recover .readout').textContent);
  assert(after > before, before + ' -> ' + after);
});
check('a worse answer lowers the score', () => {
  const before = Number($('#screen-recover .readout').textContent);
  click($('[data-scale="stress"][data-value="5"]'));
  click($('[data-scale="soreness"][data-value="5"]'));
  assert(Number($('#screen-recover .readout').textContent) < before, 'score did not fall');
});
check('the score is bounded to 0-100 at both extremes', () => {
  ['energy', 'soreness', 'stress'].forEach((k) => click($('[data-scale="' + k + '"][data-value="1"]')));
  for (let i = 0; i < 30; i++) { const b = $('[data-step="sleepHours"][data-delta="-0.5"]'); if (b) click(b); }
  const low = Number($('#screen-recover .readout').textContent);
  assert(low >= 0 && low <= 100, 'out of range low: ' + low);
  ['energy'].forEach((k) => click($('[data-scale="' + k + '"][data-value="5"]')));
  for (let i = 0; i < 30; i++) { const b = $('[data-step="sleepHours"][data-delta="0.5"]'); if (b) click(b); }
  const high = Number($('#screen-recover .readout').textContent);
  assert(high >= 0 && high <= 100, 'out of range high: ' + high);
});
check('the recommendation shows its working, factor by factor', () => {
  assert(/Why this number/.test(screenText()), 'no breakdown');
  assert($$('#screen-recover .vol-row').length >= 5, 'fewer than five factors');
});
check('a recommended training intensity is stated and marked unapplied', () => {
  assert(/Train as planned|Reduced volume|Technique focus/.test(screenText()), 'no intensity guidance');
  assert(/nothing has been applied/i.test(screenText()), 'not marked unapplied');
});
check('recovery carries a recovery trend', () => {
  assert(/Recovery trend/.test(screenText()), 'no trend panel');
});
check('the check-in is skippable and leaves the plan alone', () => {
  goto('train');
  const before = $('#screen-train').textContent;
  goto('recover');
  click($('[data-action="skip-readiness"]'));
  goto('train');
  assert($('#screen-train').textContent === before, 'plan changed on skip');
});
check('skipping is surfaced on home rather than assumed', () => {
  goto('home');
  assert(/Check-in skipped/.test(screenText()), 'skip state not shown');
});

console.log('\n-- sleep --');
check('sleep states plainly that nothing was measured', () => {
  goto('recover');
  click($('#screen-recover [data-action="goto"][data-target="sleep"]'));
  assert(/[Nn]othing here was measured/.test(screenText()), 'no measurement disclaimer');
  assert(/no sleep permission/i.test(screenText()), 'permission status not stated');
});
check('external sleep sources are shown as not connected', () => {
  assert(/Not connected/.test(screenText()), 'connection state missing');
});
check('every night row carries a source label', () => {
  const rows = $$('#screen-sleep .row');
  const withSrc = rows.filter((r) => r.querySelector('.src'));
  assert(withSrc.length >= 7, 'only ' + withSrc.length + ' rows carry a source');
});
check('a missing night is marked unavailable, not zero', () => {
  assert(/unavailable/i.test(screenText()), 'no unavailable label');
  assert(/No record/.test(screenText()), 'missing night not stated');
});
check('a night can be added by hand and is marked manually recorded', () => {
  const before = $$('#screen-sleep .row').length;
  click($('[data-action="add-night"]'));
  assert($$('#screen-sleep .row').length === before + 1, 'night not added');
  assert(/manually recorded/i.test(screenText()), 'not marked manual');
});
check('a night can be deleted', () => {
  const before = $$('#screen-sleep .row').length;
  click($('[data-action="delete-night"]'));
  assert($$('#screen-sleep .row').length === before - 1, 'night not deleted');
});
check('sleep carries a privacy explanation', () => {
  assert(/Privacy/.test(screenText()), 'no privacy section');
  assert(/open questions/i.test(screenText()), 'retention not flagged as unresolved');
});

console.log('\n-- cardio --');
check('outdoor shows a route placeholder, labelled not recorded', () => {
  goto('cardio');
  click($('[data-cardio="outdoor"]'));
  assert(sq('.route'), 'no route figure outdoors');
  assert(/not recorded/i.test(sq('.route').textContent), 'route not qualified');
});
check('INDOOR SHOWS NO GEOGRAPHIC ROUTE', () => {
  click($('[data-cardio="indoor"]'));
  assert(!sq('.route'), 'a route was drawn for an indoor session');
  assert(sqa('svg path[stroke="#3DDC84"]').length === 0, 'a route path survived indoors');
  assert(!$('.route'), 'a route survived anywhere in the document while indoors');
  assert(/no route/i.test(screenText()), 'absence not explained');
});
check('indoor and outdoor are genuinely different activities', () => {
  const indoor = screenText();
  click($('[data-cardio="outdoor"]'));
  assert(indoor !== screenText(), 'identical content for both');
});
check('the route can be hidden and shown again', () => {
  click($('[data-action="toggle-route"]'));
  assert(!sq('.route'), 'route still drawn after hiding');
  assert(/Route hidden/.test(screenText()), 'hidden state not explained');
  click($('[data-action="toggle-route"]'));
  assert(sq('.route'), 'route did not come back');
});
check('cardio states the calorie target is unchanged', () => {
  assert(/Unchanged/.test(screenText()), 'no unchanged row');
  assert(/does not/i.test(screenText()) && /kcal to eat/.test(screenText()), 'anti-double-count sentence missing');
});
check('weekly cardio load is shown', () => {
  assert(/Weekly cardio load/.test(screenText()), 'no weekly load');
});
check('recent rides list carries per-row sources', () => {
  assert($$('#screen-cardio .row .src').length >= 3, 'rides missing source labels');
  assert(/Illustrative only/.test(screenText()), 'imported row not qualified');
});
check('an activity can be deleted from the list', () => {
  const before = $$('#screen-cardio .row').length;
  click($('[data-action="delete-ride"]'));
  assert($$('#screen-cardio .row').length === before - 1, 'ride not deleted');
});
check('the empty state is reachable and reversible', () => {
  click($('[data-action="toggle-cardio-empty"]'));
  assert(/No cardio recorded/.test(screenText()), 'empty state not shown');
  click($('[data-action="toggle-cardio-empty"]'));
  assert(/Weekly cardio load/.test(screenText()), 'did not return');
});

console.log('\n-- cycling detail --');
check('ride detail exposes start, pause, resume and finish states', () => {
  click($('[data-action="goto"][data-target="ride"]'));
  for (const s of ['idle', 'active', 'paused', 'finished']) {
    assert($('[data-ridestate="' + s + '"]'), 'missing state: ' + s);
  }
  click($('[data-ridestate="active"]'));
  assert($('[data-ridestate="active"]').getAttribute('aria-pressed') === 'true', 'state not selected');
});
check('ride detail hides the route for an indoor session too', () => {
  goto('cardio');
  click($('[data-cardio="indoor"]'));
  click(sq('[data-action="goto"][data-target="ride"]'));
  assert(!sq('.route'), 'ride detail drew a route for an indoor session');
  goto('cardio');
  click($('[data-cardio="outdoor"]'));
  click(sq('[data-action="goto"][data-target="ride"]'));
  assert(sq('.route'), 'ride detail lost the route outdoors');
});
check('ride detail says no tracking is happening', () => {
  assert(/does not record anything/i.test(screenText()), 'recording disclaimer missing');
  assert(/No location permission/i.test(screenText()), 'location disclaimer missing');
});
check('deleting an activity asks first', () => {
  click($('[data-action="confirm-delete-activity"]'));
  assert(!$('#dialog-scrim').hidden, 'no confirmation dialog');
  assert($('#dialog').getAttribute('role') === 'alertdialog', 'dialog not an alertdialog');
  click($('[data-action="close-dialog"]'));
  assert($('#dialog-scrim').hidden, 'dialog did not close');
});

console.log('\n-- nutrition --');
check('nutrition is marked read-only', () => {
  goto('eat');
  assert(/Read-only/.test(screenText()), 'not marked read-only');
});
check('verified and estimated values are distinguished', () => {
  assert($$('#screen-eat .tag.ok').some((t) => /Verified/.test(t.textContent)), 'no Verified tag');
  assert($$('#screen-eat .tag.watch').some((t) => /Estimated/.test(t.textContent)), 'no Estimated tag');
});
check('AI estimates carry a plus-or-minus band', () => {
  assert(/±/.test(screenText()), 'no uncertainty band shown');
});
check('food rows carry source attribution', () => {
  assert(/USDA|Open Food Facts|Curated by Trace|Photo estimate/.test(screenText()), 'no attribution');
});
check('the three kinds of number are explained', () => {
  assert(/three different kinds of number/i.test(screenText()), 'distinction not explained');
});
check('cardio calories are not offered as food', () => {
  assert(/never will/.test(screenText()) || /already contains/.test(screenText()), 'invariant not stated');
});
check('the meal plan is a marked placeholder, not a mock-up', () => {
  assert(/No meal plan/.test(screenText()), 'meal plan not marked absent');
  assert(/rather than mocked up/.test(screenText()), 'placeholder not explained');
});

console.log('\n-- progress --');
check('all four panel states render', () => {
  goto('progress');
  for (const st of ['loading', 'empty', 'error', 'data']) {
    click($('[data-volstate="' + st + '"]'));
    assert($('#vol-body').innerHTML.trim().length > 0, st + ' rendered nothing');
  }
});
check('progress carries consistency, volume, progression and records', () => {
  for (const want of ['Sessions', 'Weekly sets by muscle', 'Exercise progression', 'Personal records',
    'Estimated 1RM trend', 'This week vs last', 'Fatigue trend', 'Programme adherence']) {
    assert(screenText().indexOf(want) !== -1, 'missing: ' + want);
  }
});
check('sleep and cardio overlays can be switched on', () => {
  click($('[data-overlay="sleep"]'));
  assert(/Hours asleep/.test(screenText()), 'sleep overlay not labelled');
  click($('[data-overlay="cardio"]'));
  assert(/Cardio minutes/.test(screenText()), 'cardio overlay not labelled');
  click($('[data-overlay="none"]'));
});
check('an overlay is not presented as causation', () => {
  click($('[data-overlay="sleep"]'));
  assert(/not evidence that one caused the other/i.test(screenText()), 'causation caveat missing');
  click($('[data-overlay="none"]'));
});
check('the plateau card shows exercise, evidence, baseline and current', () => {
  const t = screenText();
  for (const want of ['Dumbbell Bench Press', 'Sessions considered', 'Baseline', 'Current', 'Already ruled out']) {
    assert(t.indexOf(want) !== -1, 'missing: ' + want);
  }
  assert($$('#plateau-body tbody tr').length === 4, 'expected 4 evidence rows');
});
check('the plateau card offers accept, postpone and dismiss', () => {
  assert($('[data-action="plateau-accept"]'), 'no accept');
  assert($('[data-action="plateau-postpone"]'), 'no postpone');
  assert($('[data-action="plateau-dismiss"]'), 'no dismiss');
});
check('accepting does not change the session', () => {
  goto('train');
  const before = $('#screen-train').textContent;
  goto('progress');
  click($('[data-action="plateau-accept"]'));
  assert(/unchanged/i.test($('#plateau-body').textContent), 'no unchanged statement');
  goto('train');
  assert($('#screen-train').textContent === before, 'the session changed after accepting');
});
check('postponing is offered without a fabricated cooldown', () => {
  goto('progress');
  click($('[data-action="plateau-reset"]'));
  click($('[data-action="plateau-postpone"]'));
  assert(/postponed/i.test($('#plateau-body').textContent), 'not postponed');
  assert(/open product question/i.test($('#plateau-body').textContent), 'cooldown invented');
});
check('dismissing is reversible', () => {
  click($('[data-action="plateau-reset"]'));
  click($('[data-action="plateau-dismiss"]'));
  assert(/dismissed/i.test($('#plateau-body').textContent), 'not dismissed');
  click($('[data-action="plateau-reset"]'));
  assert($('[data-action="plateau-accept"]'), 'notice did not come back');
});

console.log('\n-- AI review --');
check('an unrecognised exercise id blocks confirmation', () => {
  goto('progress');
  click($('[data-action="goto"][data-target="ai"]'));
  assert(/Cannot be confirmed/.test(screenText()), 'no rejection notice');
  click($('[data-action="ai-confirm"]'));
  assert(!/^Confirmed/m.test($('#ai-verdict').textContent), 'confirmed with a bad id');
});
check('the whole draft is refused, not silently patched', () => {
  assert(/rejects the whole draft/.test(screenText()), 'whole-draft rule not stated');
  assert($$('#ai-list .ex').length === 5, 'an item was dropped');
});
check('confidence is an em dash, not a fabricated percentage', () => {
  assert($$('#screen-ai .stat-value.dash').length >= 2, 'confidence reported as a number');
});
check('the user chooses the replacement, and it is attributed to them', () => {
  click($('[data-action="ai-swap"]'));
  assert(/Ready for your review/.test($('#ai-verdict').textContent), 'still blocked');
  assert(/after the replacement you chose/.test($('#ai-verdict').textContent), 'not attributed to the user');
});
check('confirming then works, and writes nothing', () => {
  click($('[data-action="ai-confirm"]'));
  assert(/Confirmed/.test($('#ai-verdict').textContent), 'not confirmed');
  assert(/writes nothing/.test(screenText()), 'no writes-nothing statement');
  assert(!$('#ai-actions'), 'actions still shown after a decision');
});

console.log('\n-- programme setup --');
check('setup covers every field the brief asks for', () => {
  goto('home');
  click($('[data-action="goto"][data-target="setup"]'));
  const t = screenText();
  for (const want of ['Goal', 'Training phase', 'Days per week', 'Available days', 'Time per session',
    'Equipment', 'Exercises you like', 'Exercises to avoid', 'Cardio each week',
    'sleep and recovery', 'AI generation', 'Programme preview']) {
    assert(t.indexOf(want) !== -1, 'missing: ' + want);
  }
});
check('the preview updates from the answers', () => {
  const before = screenText();
  click($('[data-setup="days"][data-value="5"]'));
  assert(screenText() !== before, 'preview did not change');
  assert(/Upper \/ lower/.test(screenText()), 'split did not follow day count');
});
check('sensitive opt-ins are off by default and skippable', () => {
  const t = screenText();
  assert(/Optional · sleep and recovery/.test(t), 'recovery opt-in missing');
  assert($('[data-action="skip-optin"][data-key="recoveryOptIn"]'), 'no skip for recovery');
  assert($('[data-action="skip-optin"][data-key="aiOptIn"]'), 'no skip for AI');
});
check('turning AI off does not remove programming', () => {
  assert(/rule-generated programming keeps working/i.test(screenText()), 'opt-in framed as a threat');
});
check('confirming states that nothing was written', () => {
  click($('[data-action="confirm-programme"]'));
  assert(/Nothing was written/.test(screenText()), 'confirmation overclaims');
});

console.log('\n-- profile --');
check('every external source is shown as not connected', () => {
  goto('home');
  click($('.avatar'));
  assert(!$('#screen-profile').hidden, 'avatar did not open profile');
  assert($$('#screen-profile .tag.muted').filter((t) => /Not connected/.test(t.textContent)).length >= 4,
    'a source claims to be connected');
});
check('profile states that nothing is stored', () => {
  assert(/No account, no database, no local storage/.test(screenText()), 'storage claim missing');
});

console.log('\n-- motion and accessibility --');
check('reduced motion can be switched on in-page', () => {
  click($('[data-motion="reduced"]'));
  assert(document.body.dataset.motion === 'reduced', 'body flag not set');
});
check('the stylesheet honours the OS setting too', () => {
  const css = fs.readFileSync(path.join(DIR, 'styles.css'), 'utf8');
  assert(/@media \(prefers-reduced-motion: reduce\)/.test(css), 'no media query');
  assert(/body\[data-motion="reduced"\]/.test(css), 'no in-page override');
  assert(/\.mv-anim \{ animation: none/.test(css), 'movement diagram keeps animating');
});
check('switching back restores system behaviour', () => {
  click($('[data-motion="system"]'));
  assert(document.body.dataset.motion !== 'reduced', 'flag stuck');
});
check('every interactive control has an accessible name', () => {
  const seen = new Set();
  for (const id of ALL_SCREENS) {
    goto(id);
    $$('button').forEach((b) => {
      if (!b.textContent.trim() && !b.getAttribute('aria-label')) seen.add(b.outerHTML.slice(0, 70));
    });
  }
  assert(seen.size === 0, Array.from(seen).join(' | '));
});
check('every chart carries a text alternative', () => {
  for (const id of ALL_SCREENS) {
    goto(id);
    $$('#screen-' + id + ' svg').forEach((s) => {
      const named = s.getAttribute('aria-label') || s.querySelector('title');
      assert(named, id + ': an svg has no accessible name');
    });
    $$('#screen-' + id + ' .spark, #screen-' + id + ' .gauge[role="img"], #screen-' + id + ' .split').forEach((n) => {
      assert(n.getAttribute('aria-label'), id + ': a chart div has no aria-label');
    });
  }
});
check('tables carry captions', () => {
  for (const id of ALL_SCREENS) {
    goto(id);
    $$('#screen-' + id + ' table').forEach((t) => assert(t.querySelector('caption'), id + ': table without a caption'));
  }
});
check('grouped controls are labelled', () => {
  for (const id of ALL_SCREENS) {
    goto(id);
    $$('#screen-' + id + ' [role="group"]').forEach((g) => {
      assert(g.getAttribute('aria-label') || g.getAttribute('aria-labelledby'),
        id + ': an unlabelled control group');
    });
  }
});
check('overlays are modal and dismissible by Escape', () => {
  goto('train');
  click($('[data-action="open-add-exercise"]'));
  assert($('#sheet').getAttribute('aria-modal') === 'true', 'sheet not modal');
  const ev = new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true });
  document.dispatchEvent(ev);
  assert($('#sheet-scrim').hidden, 'Escape did not close the sheet');
});

console.log('\n-- claims audit --');
check('clinical vocabulary appears only inside a disclaimer', () => {
  const words = ['diagnos', 'cure', 'treatment', 'disease', 'medical', 'clinical'];
  for (const id of ALL_SCREENS) {
    goto(id);
    const all = $('#screen-' + id).textContent.toLowerCase().replace(/\s+/g, ' ');
    for (const w of words) {
      let from = 0;
      for (;;) {
        const at = all.indexOf(w, from);
        if (at === -1) break;
        const lead = all.slice(Math.max(0, at - 50), at);
        assert(/(^|[^a-z])(not|no|never|cannot)([^a-z][^.]*)?$/.test(lead),
          id + ': unnegated "' + w + '" in ...' + lead + all.slice(at, at + 25));
        from = at + w.length;
      }
    }
  }
});
check('the app never claims to know why something hurts', () => {
  goto('exercise');
  assert(/cannot tell you what is wrong/i.test(screenText()), 'limit not stated');
});
check('no screen claims data was really collected', () => {
  for (const id of ALL_SCREENS) {
    goto(id);
    const t = $('#screen-' + id).textContent;
    assert(!/we recorded your/i.test(t), id + ' claims a recording');
    assert(!/synced from your/i.test(t), id + ' claims a sync');
    assert(!/imported from your/i.test(t), id + ' claims an import');
  }
});
check('no production API path is referenced as though it were called', () => {
  const js = fs.readFileSync(path.join(DIR, 'app.js'), 'utf8')
    + fs.readFileSync(path.join(DIR, 'data.js'), 'utf8');
  assert(!/\/api\/workouts/.test(js), 'a production route appears in prototype code');
  assert(!/localhost:8000|127\.0\.0\.1/.test(js), 'an API host appears in prototype code');
});

console.log('\n-- isolation --');
check('no network call was attempted', () => {
  assert(network.length === 0, network.join(', '));
});
check('no external host appears in any prototype file', () => {
  for (const f of ['index.html', 'app.js', 'data.js', 'styles.css']) {
    const s = fs.readFileSync(path.join(DIR, f), 'utf8');
    assert(!/https?:\/\//.test(s), f + ' contains an external URL');
  }
});
check('nothing is persisted', () => {
  const js = fs.readFileSync(path.join(DIR, 'app.js'), 'utf8');
  assert(!/localStorage\.|sessionStorage\.|indexedDB\./.test(js), 'prototype writes to storage');
  assert(window.localStorage.length === 0, 'localStorage was written');
});
check('the page loads only its own two scripts', () => {
  const tags = html.match(/<script[^>]*>/g) || [];
  assert(tags.length === 2, 'expected 2 script tags, got ' + tags.length);
  assert(tags.every((t) => /src="(data|app)\.js"/.test(t)), 'unexpected script source');
});

console.log('\n-- runtime errors --');
check('no uncaught errors during the whole run', () => {
  assert(errors.length === 0, errors.join(' | '));
});

console.log('\n' + pass + ' passed, ' + fail + ' failed');
process.exit(fail ? 1 : 0);
