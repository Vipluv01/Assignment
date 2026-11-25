/* Growth Center front end. No build step, no dependencies.
   The browser owns the team's saved changes (localStorage). Every view is rendered from
   /api/dashboard, which recomputes all analytics from source data + those changes. */
(() => {
'use strict';
const KEY = 'growth_center_state_v1';
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = n => n == null ? '–' : Math.round(n).toLocaleString('en-IN');
const inr = n => n == null ? '–' : '₹' + Math.round(n).toLocaleString('en-IN');
const pct = (n, d = 1) => n == null ? '–' : (n * 100).toFixed(d) + '%';
const addDays = (day, n) => { const d = new Date(day + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };
const nice = day => day ? new Date(day + 'T00:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' }) : '–';

const TEAM = ['Meera Iyer', 'Arjun Verma', 'Nisha Rao', 'Dev Malhotra'];
const SEED_TASKS = [
  { title: 'Send T-7 and T-1 reminder to confirmed registrants', description: 'Simulated starter task. Reminder sequence aimed at the confirmed-to-attended gap.', owner_name: 'Dev Malhotra', due_date: '2025-04-05', status: 'todo', priority: 'high', campaign_id: null },
  { title: 'Weekly paid social creative refresh', description: 'Simulated starter task.', owner_name: 'Arjun Verma', due_date: '2025-03-18', status: 'in_progress', priority: 'medium', campaign_id: 'C02' },
  { title: 'Confirm group bookings with 10 partner clubs', description: 'Simulated starter task.', owner_name: 'Meera Iyer', due_date: '2025-03-25', status: 'todo', priority: 'high', campaign_id: 'C04' },
  { title: 'Brief creators on registration link and tracking', description: 'Simulated starter task.', owner_name: 'Nisha Rao', due_date: '2025-03-10', status: 'blocked', priority: 'medium', campaign_id: 'C03' },
  { title: 'Launch referral leaderboard', description: 'Simulated starter task.', owner_name: 'Dev Malhotra', due_date: '2025-03-01', status: 'done', priority: 'medium', campaign_id: 'C05' },
].map((t, i) => ({ task_id: 'T-' + (i + 1), source: 'manual', created_at: '2025-02-20', evidence: '', ...t }));

const fresh = () => ({ as_of: '2025-03-20', seq: 10, tab: 'measure', team: TEAM.slice(),
  overlay: { campaign_edits: {}, new_campaigns: [], daily: [], outcomes: [], targets: [], tasks: SEED_TASKS.map(t => ({ ...t })), settings: {} },
  chat: { provider: null, messages: [], log: [], events: [] } });

let S;
try { S = JSON.parse(localStorage.getItem(KEY)) || fresh(); } catch { S = fresh(); }
if (!S.overlay || !S.chat) S = fresh();
let D = null;            // last dashboard payload
let ui = { metric: 'cost_per_registration', taskFilter: { status: '', owner: '', campaign: '' }, busy: false };

function save() {
  try { localStorage.setItem(KEY, JSON.stringify(S)); }
  catch (e) { toast('Could not save to browser storage: ' + e.message); }
}
const nextId = p => p + '-' + (++S.seq);
function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => t.hidden = true, 3200); }

async function api(path, body) {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({ error: 'Server returned ' + r.status }));
  if (!r.ok || j.error && !j.provider) throw new Error(j.error || ('HTTP ' + r.status));
  return j;
}

async function refresh() {
  try {
    D = await api('/api/dashboard', { overlay: S.overlay, as_of: S.as_of });
    S.as_of = D.as_of; save();
    renderChrome(); render();
  } catch (e) {
    $('#view').innerHTML = `<div class="card"><h2>Could not load analytics</h2><p class="muted">${esc(e.message)}</p><p class="muted">Is the server running? Start it with <code>python3 server.py</code>.</p></div>`;
  }
}

function renderChrome() {
  $('#eventName').textContent = `${D.event.event_name} · ${nice(D.bounds.event_start)}–${nice(D.bounds.event_end)} 2025 · ${D.overview.phase}` + (D.overview.days_to_event > 0 ? ` · ${D.overview.days_to_event} days to go` : '');
  const a = $('#asOf'); a.min = D.bounds.min; a.max = D.bounds.max; a.value = D.as_of;
  const presets = [['15 Feb', '2025-02-15'], ['20 Mar', '2025-03-20'], ['Event eve', addDays(D.bounds.event_start, -1)], ['Final', D.bounds.max]];
  $('#presets').innerHTML = presets.map(([l, d]) => `<button data-act="asof" data-day="${d}" class="${d === D.as_of ? 'on' : ''}">${l}</button>`).join('');
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === S.tab));
  const mode = { claude: 'Claude', gemini: 'Gemini', offline: 'rule-based (no AI key)' }[D.ai_provider] || D.ai_provider;
  $('#aiMode').textContent = mode;
  const b = $('#banner');
  if (D.warnings.length) { b.hidden = false; b.textContent = D.warnings.join(' · '); } else b.hidden = true;
}

function render() {
  const v = $('#view');
  v.innerHTML = ({ measure: viewMeasure, diagnose: viewDiagnose, decide: viewDecide, execute: viewExecute, data: viewData }[S.tab] || viewMeasure)();
  renderSuggest();
}

/* ---------------------------------------------------------------- charts */
function lineChart(rows, key, goalKey, opts = {}) {
  const W = 640, H = 220, L = 46, R = 14, T = 10, B = 24;
  const max = Math.max(1, ...rows.map(r => Math.max(r[key] || 0, r[goalKey] || 0))) * 1.08;
  const x = i => L + (W - L - R) * (rows.length > 1 ? i / (rows.length - 1) : 0);
  const y = v => T + (H - T - B) * (1 - v / max);
  const path = k => rows.map((r, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r[k] || 0).toFixed(1)).join('');
  const ticks = [0, .25, .5, .75, 1].map(f => max / 1.08 * f);
  const step = Math.max(1, Math.round(rows.length / 6));
  let s = `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${esc(opts.label || '')}" data-chart="line" data-key="${key}" data-goal="${goalKey || ''}" data-unit="${opts.unit || ''}">`;
  ticks.forEach(t => { s += `<line class="gridl" x1="${L}" x2="${W - R}" y1="${y(t)}" y2="${y(t)}"/><text x="${L - 6}" y="${y(t) + 4}" text-anchor="end">${opts.unit === 'inr' ? '₹' + (t >= 1000 ? Math.round(t / 1000) + 'k' : Math.round(t)) : fmt(t)}</text>`; });
  rows.forEach((r, i) => { if (i % step === 0) s += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${nice(r.date)}</text>`; });
  if (goalKey) s += `<path d="${rows.map((r, i) => (i ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(r[goalKey] || 0).toFixed(1)).join('')}" fill="none" stroke="var(--ink-3)" stroke-width="1.5" stroke-dasharray="5 4"/>`;
  s += `<path d="${path(key)}" fill="none" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/>`;
  s += `<line class="cross" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="var(--ink-3)" stroke-width="1" visibility="hidden"/><rect class="hit" x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent"/></svg>`;
  return s;
}

function barChart(rows, valueKey, f, opts = {}) {
  const vals = rows.map(r => r[valueKey]).filter(v => v != null);
  const max = Math.max(1e-9, ...vals);
  return `<div>` + rows.map(r => {
    const v = r[valueKey];
    return `<div class="funnel-row" data-tip="${esc(r.campaign_name)}: ${esc(f(v))}">
      <div>${esc(r.campaign_name)}</div>
      <div class="bar"><i style="width:${v == null ? 0 : Math.max(0, v / max * 100).toFixed(1)}%;${r.campaign_id == null ? 'background:var(--neutral-mark)' : ''}"></i></div>
      <div class="num">${f(v)}${opts.ref != null && v != null && r.campaign_id != null ? ` <span class="conv">(${(v / opts.ref).toFixed(2)}x)</span>` : ''}</div></div>`;
  }).join('') + `</div>`;
}

/* ---------------------------------------------------------------- Measure */
function kpi(label, x, f, note) {
  const p = x.pct_of_goal;
  const isSpend = label.startsWith('Spend');
  return `<div class="card kpi"><div class="label">${label}</div><div class="value num">${f(x.actual)}</div>
    <div class="of">${x.goal != null ? `of ${f(x.goal)} ${isSpend ? 'budget' : 'goal'} · <span class="num">${pct(p, 0)}</span>` : 'no goal set'}</div>
    <div class="meter"><i class="${isSpend && p > 1 ? 'over' : ''}" style="width:${Math.min(100, (p || 0) * 100)}%"></i></div>
    <div class="small muted">${note}</div></div>`;
}

function viewMeasure() {
  const o = D.overview, m = o.metrics, v = o.vs_target, f = o.forecast;
  const gapTxt = x => x.goal == null ? '' : (x.gap > 0 ? `${fmt(x.gap)} short` : `${fmt(-x.gap)} above goal`);
  const pre = f.basis === 'projection';
  const fcBadge = f.visitor_goal == null ? '' : (f.visitor_gap_vs_goal >= 0 ? `<span class="badge good">${pre ? 'On track' : 'Goal met'}</span>` : `<span class="badge bad">${fmt(-f.visitor_gap_vs_goal)} ${pre ? 'short at this pace' : 'short of goal'}</span>`);
  const anon = [['Impressions', m.impressions, null], ['Clicks', m.clicks, m.ctr], ['Landing sessions', m.landing_page_sessions, m.click_to_session], ['Registration starts', m.registration_starts, m.session_to_start]];
  const ppl = [['Identified people', m.identified_external_people, null], ['Registered', m.registered_external_people, m.identified_external_people ? m.registered_external_people / m.identified_external_people : null],
    ['Confirmed', m.confirmed, m.confirm_rate], ['Verified visitors', m.unique_external_visitors, o.phase === 'pre-event' ? null : (m.confirmed ? m.unique_external_visitors / m.confirmed : null)]];
  const funnel = (rows) => { const mx = Math.max(1, rows[0][1]); return rows.map(([l, n, c]) => `<div class="funnel-row" data-tip="${esc(l)}: ${fmt(n)}"><div>${l}</div><div class="bar"><i style="width:${(n / mx * 100).toFixed(1)}%"></i></div><div class="num">${fmt(n)} <span class="conv">${c == null ? '' : pct(c) + ' of prev.'}</span></div></div>`).join(''); };
  return `
  <div class="grid g4">
    ${kpi('Verified external visitors', v.unique_external_visitors, fmt, o.phase === 'pre-event' ? 'Attendance exists only from event day' : gapTxt(v.unique_external_visitors) + ` · ${fmt(m.walk_in_visitors)} walk-ins`)}
    ${kpi('Registered external people', v.registered_external_people, fmt, gapTxt(v.registered_external_people) + ` · ${fmt(m.confirmed)} confirmed`)}
    ${kpi('Identified external people', v.identified_external_people, fmt, gapTxt(v.identified_external_people))}
    ${kpi('Spend vs approved budget', v.spend_inr, inr, o.budget_remaining_inr != null ? inr(o.budget_remaining_inr) + ' remaining' : '')}
  </div>
  <div class="card">
    <div class="card-head"><h2>${pre ? 'Projected outcome at current pace' : 'Outcome'}</h2><span>${fcBadge} <span class="pill">targets: ${esc(o.target_version || 'none')}</span></span></div>
    <div class="grid g4">
      <div><div class="sub">${pre ? 'Projected' : 'Actual'} verified visitors</div><div class="kpi"><span class="value num">${fmt(f.projected_visitors)}</span> <span class="of">goal ${fmt(f.visitor_goal)}</span></div></div>
      <div><div class="sub">${pre ? 'Projected' : 'Actual'} registrations</div><div class="kpi"><span class="value num">${fmt(f.projected_registrations)}</span> <span class="of">${pre ? `at ${f.registrations_per_day_recent}/day` : ''}</span></div></div>
      <div><div class="sub">${pre ? 'Registrations/day needed for visitor goal' : 'Show rate (confirmed who attended)'}</div><div class="kpi"><span class="value num">${pre ? (f.registrations_per_day_needed_for_visitor_goal ?? '–') : pct(m.show_rate_confirmed)}</span> <span class="of">${pre ? `over ${f.days_left_to_event_eve} days` : ''}</span></div></div>
      <div><div class="sub">${pre ? 'Projected spend' : 'Cost per verified visitor'}</div><div class="kpi"><span class="value num">${pre ? inr(f.projected_spend_inr) : inr(m.cost_per_visitor)}</span> <span class="of">${pre ? (f.projected_budget_overrun_inr > 0 ? `<span class="badge bad">${inr(f.projected_budget_overrun_inr)} over budget</span>` : 'within budget') : 'blended, incl. walk-ins'}</span></div></div>
    </div>
    <p class="sub" style="margin-top:8px">${esc(f.note)}</p>
  </div>
  <div class="grid g2">
    <div class="card"><div class="card-head"><h2>Cumulative registrations vs goal</h2><div class="legend"><span><i></i>Registered external people</span><span><i class="goal"></i>Registration goal in force</span></div></div>
      ${lineChart(D.series, 'cum_registrations', 'registration_goal', { label: 'Cumulative registrations versus goal' })}</div>
    <div class="card"><div class="card-head"><h2>Cumulative spend vs budget</h2><div class="legend"><span><i></i>Net spend</span><span><i class="goal"></i>Approved budget</span></div></div>
      ${lineChart(D.series, 'cum_spend_inr', 'budget_inr', { unit: 'inr', label: 'Cumulative spend versus budget' })}</div>
  </div>
  <div class="grid g2">
    <div class="card"><h2>Awareness funnel</h2><p class="sub">Anonymous event counts, not people. Summed platform reach (${fmt(m.reported_reach_sum)}) is not unique reach and is left out.</p>${funnel(anon)}</div>
    <div class="card"><h2>People funnel</h2><p class="sub">Distinct external people. Internal, staff and test identities are excluded.</p>${funnel(ppl)}
      <p class="sub" style="margin-top:8px">${fmt(m.cancelled)} cancelled · ${fmt(m.waitlisted)} waitlisted · ${fmt(m.interested)} still unconfirmed · ${fmt(m.opted_out_people)} opted out of contact</p></div>
  </div>
  <div class="card"><div class="card-head"><h2>Campaign KPIs as of ${nice(D.as_of)}</h2><span class="sub">Attribution: the campaign recorded on the registration</span></div>${campaignTable(D.campaigns, m)}</div>`;
}

function campaignTable(rows, total) {
  const cols = [['Spend', r => inr(r.spend_inr)], ['Budget', r => r.budget_inr != null ? inr(r.budget_inr) : '–'], ['Sessions', r => fmt(r.landing_page_sessions)], ['Identified', r => fmt(r.identified_external_people)],
    ['Registered', r => fmt(r.registered_external_people)], ['Confirmed', r => fmt(r.confirmed)], ['Visitors', r => fmt(r.unique_external_visitors)], ['Visitor goal', r => r.visitor_goal != null ? fmt(r.visitor_goal) : '–'],
    ['Cost / reg.', r => inr(r.cost_per_registration)], ['Cost / visitor', r => inr(r.cost_per_visitor)], ['Show rate', r => pct(r.show_rate_confirmed)]];
  return `<div class="tablewrap"><table><thead><tr><th>Campaign</th><th>Owner</th><th>Status</th>${cols.map(c => `<th class="n">${c[0]}</th>`).join('')}</tr></thead><tbody>` +
    rows.map(r => `<tr><td>${esc(r.campaign_name)}</td><td>${esc(r.owner_name || '–')}</td><td>${r.status ? statusBadge(r.status) : ''}</td>${cols.map(c => `<td class="n">${c[1](r)}</td>`).join('')}</tr>`).join('') +
    `<tr class="total"><td>All campaigns</td><td></td><td></td>${cols.map(c => `<td class="n">${c[0] === 'Budget' || c[0] === 'Visitor goal' ? '' : c[1](total)}</td>`).join('')}</tr></tbody></table></div>`;
}
const statusBadge = s => `<span class="badge ${({ active: '', scaled: 'good', paused: 'warn', stopped: 'bad', planned: '' })[s] || ''}">${esc(s)}</span>`;

/* ---------------------------------------------------------------- Diagnose */
const METRICS = {
  cost_per_registration: ['Cost per registration', inr, 'lower is better'], cost_per_visitor: ['Cost per verified visitor', inr, 'lower is better; from event day'],
  registered_external_people: ['Registered people', fmt, ''], unique_external_visitors: ['Verified visitors', fmt, ''],
  show_rate_confirmed: ['Show rate (confirmed who attended)', pct, 'from event day'], registrations_per_session: ['Registrations per landing session', pct, 'comparison index: people over anonymous sessions'],
  cancel_rate: ['Cancellation rate', pct, 'lower is better'], optout_rate: ['Opt-out rate', pct, 'lower is better'], spend_inr: ['Spend', inr, ''],
};
function viewDiagnose() {
  const tot = D.overview.metrics, [label, f, hint] = METRICS[ui.metric];
  const rows = D.campaigns.slice().sort((a, b) => (b[ui.metric] ?? -1) - (a[ui.metric] ?? -1));
  const ratio = ['cost_per_registration', 'cost_per_visitor', 'show_rate_confirmed', 'registrations_per_session', 'cancel_rate', 'optout_rate'].includes(ui.metric) ? tot[ui.metric] : null;
  const steps = [['ctr', 'Click-through', true], ['click_to_session', 'Click → session', true], ['session_to_start', 'Session → form start', true], ['registrations_per_session', 'Registrations / session', true],
    ['confirm_rate', 'Registered → confirmed', true], ['cancel_rate', 'Cancelled', false], ['show_rate_confirmed', 'Confirmed → attended', true]];
  const camp = D.campaigns.filter(r => r.campaign_id);
  const cell = (r, [k, , hiGood]) => { const a = r[k], b = tot[k]; if (a == null || !b) return `<td class="n">–</td>`; const rel = a / b; const bad = hiGood ? rel < 0.8 : rel > 1.25, good = hiGood ? rel > 1.2 : rel < 0.8;
    return `<td class="n ${bad ? 'lo' : good ? 'hi' : ''}" data-tip="${(rel).toFixed(2)}x the all-campaign rate${bad ? ' · weak step' : ''}">${pct(a)}${bad ? ' ▼' : good ? ' ▲' : ''}</td>`; };
  const prev = Object.fromEntries((D.previous.rows || []).map(r => [r.campaign_id, r]));
  const delta = (a, b, lowerGood) => { if (a == null || b == null || !b) return '<span class="muted">–</span>'; const d = (a - b) / b; const good = lowerGood ? d < -0.05 : d > 0.05, bad = lowerGood ? d > 0.05 : d < -0.05;
    return `<span class="badge ${good ? 'good' : bad ? 'bad' : ''}">${d > 0 ? '+' : ''}${(d * 100).toFixed(0)}%</span>`; };
  const worst = steps.filter(s => tot[s[0]] != null).map(s => s);
  return `
  <div class="card"><div class="card-head"><h2>Compare campaigns</h2>
      <label class="small muted">Metric <select data-act="metric">${Object.entries(METRICS).map(([k, v]) => `<option value="${k}" ${k === ui.metric ? 'selected' : ''}>${v[0]}</option>`).join('')}</select></label></div>
    <p class="sub">${label} as of ${nice(D.as_of)}${hint ? ' · ' + hint : ''}${ratio != null ? ` · all campaigns: ${f(ratio)} (multiple shown in brackets)` : ''}</p>
    ${barChart(rows, ui.metric, f, { ref: ratio })}</div>
  <div class="card"><h2>Where each campaign leaks</h2>
    <p class="sub">Step rates per campaign against the all-campaign rate. ▼ marks a step at least 20% worse than the whole event (25% for cancellations); ▲ at least 20% better. The first four columns use anonymous event counts.</p>
    <div class="tablewrap"><table><thead><tr><th>Campaign</th>${worst.map(s => `<th class="n">${s[1]}</th>`).join('')}</tr></thead><tbody>
    ${camp.map(r => `<tr><td>${esc(r.campaign_name)}</td>${worst.map(s => cell(r, s)).join('')}</tr>`).join('')}
    <tr class="total"><td>All campaigns</td>${worst.map(s => `<td class="n">${pct(tot[s[0]])}</td>`).join('')}</tr></tbody></table></div></div>
  <div class="card"><h2>What changed: last ${D.settings.window_days} days vs the ${D.settings.window_days} days before</h2>
    <p class="sub">${nice(D.recent.since)}–${nice(D.recent.to)} against ${nice(D.previous.since)}–${nice(D.previous.to)}. New registrations and spend in each window.</p>
    <div class="tablewrap"><table><thead><tr><th>Campaign</th><th class="n">Registrations</th><th class="n">before</th><th>change</th><th class="n">Spend</th><th class="n">before</th><th>change</th><th class="n">Cost / reg.</th><th class="n">before</th><th>change</th></tr></thead><tbody>
    ${D.recent.rows.filter(r => r.campaign_id).map(r => { const p = prev[r.campaign_id] || {};
      return `<tr><td>${esc(r.campaign_name)}</td><td class="n">${fmt(r.registered_external_people)}</td><td class="n">${fmt(p.registered_external_people)}</td><td>${delta(r.registered_external_people, p.registered_external_people)}</td>
        <td class="n">${inr(r.spend_inr)}</td><td class="n">${inr(p.spend_inr)}</td><td>${delta(r.spend_inr, p.spend_inr, true)}</td>
        <td class="n">${inr(r.cost_per_registration)}</td><td class="n">${inr(p.cost_per_registration)}</td><td>${delta(r.cost_per_registration, p.cost_per_registration, true)}</td></tr>`; }).join('')}
    ${D.previous.total ? `<tr class="total"><td>All campaigns</td><td class="n">${fmt(D.recent.total.registered_external_people)}</td><td class="n">${fmt(D.previous.total.registered_external_people)}</td><td>${delta(D.recent.total.registered_external_people, D.previous.total.registered_external_people)}</td>
      <td class="n">${inr(D.recent.total.spend_inr)}</td><td class="n">${inr(D.previous.total.spend_inr)}</td><td>${delta(D.recent.total.spend_inr, D.previous.total.spend_inr, true)}</td>
      <td class="n">${inr(D.recent.total.cost_per_registration)}</td><td class="n">${inr(D.previous.total.cost_per_registration)}</td><td>${delta(D.recent.total.cost_per_registration, D.previous.total.cost_per_registration, true)}</td></tr>` : ''}
    </tbody></table></div></div>`;
}

/* ---------------------------------------------------------------- Decide */
const VERDICT_CLASS = { 'SCALE': 'good', 'SCALE + FIX': 'good', 'FIX': 'warn', 'STOP': 'bad', 'HOLD': '', 'INSUFFICIENT DATA': '' };
function viewDecide() {
  const d = D.decisions, s = D.settings, ra = d.reallocation;
  const openFor = cid => D.tasks.filter(t => t.campaign_id === cid && t.status !== 'done').length;
  const lab = { window_days: 'Window (days)', assumed_show_rate: 'Assumed show rate (pre-event)', scale_cost_ratio: 'SCALE if cost ≤ × blended', stop_cost_ratio: 'STOP if cost ≥ × blended',
    fix_conversion_ratio: 'FIX if reg./session < × blended', fix_show_ratio: 'FIX if show rate < × blended', fix_cancel_ratio: 'FIX if cancellations > × blended', fix_optout_ratio: 'FIX if opt-outs > × blended', min_sample_registrations: 'Minimum registrations to judge' };
  return `
  <div class="card"><div class="card-head"><h2>Scale, fix or stop</h2><span class="sub">Judged on ${esc(d.cost_metric)} over the ${esc(d.basis)} · blended ${inr(d.blended_cost)} · budget remaining ${inr(d.budget_remaining_inr)}</span></div>
    ${d.campaigns.map(c => `<div class="verdict">
      <div><strong>${esc(c.campaign_name)}</strong><div class="small muted">${esc(c.owner_name || '')} · ${statusBadge(c.status)}</div></div>
      <div><span class="badge ${VERDICT_CLASS[c.verdict]}">${c.verdict}</span> ${esc(c.action)}
        <ul>${c.evidence.map(e => `<li>${esc(e)}</li>`).join('') || '<li>Within thresholds on every check.</li>'}</ul></div>
      <div class="row-actions">${openFor(c.campaign_id) ? `<span class="small muted">${openFor(c.campaign_id)} open task(s)</span><br>` : ''}
        <button class="small" data-act="task-from-verdict" data-cid="${c.campaign_id}">Create task</button>
        ${c.verdict === 'STOP' && c.status !== 'stopped' && c.status !== 'paused' ? `<button class="small" data-act="set-status" data-cid="${c.campaign_id}" data-status="paused">Mark paused</button>` : ''}
        ${c.verdict === 'SCALE' && c.status !== 'scaled' ? `<button class="small" data-act="set-status" data-cid="${c.campaign_id}" data-status="scaled">Mark scaled</button>` : ''}</div></div>`).join('')}
  </div>
  ${ra ? `<div class="card"><h2>Budget reallocation estimate</h2>
    <p>Moving the ${inr(ra.amount_inr_per_window)} that <strong>${esc(ra.from.join(', '))}</strong> spent in the window to <strong>${esc(ra.to.join(', '))}</strong> gives up about ${fmt(ra.registrations_lost)} registrations and gains about ${fmt(ra.registrations_gained_est)}: net <strong>${ra.net_registrations_est >= 0 ? '+' : ''}${fmt(ra.net_registrations_est)}</strong> per ${s.window_days} days.</p>
    <p class="sub"><span class="badge warn">Assumption</span> ${esc(ra.assumption)}</p></div>` : ''}
  <div class="card"><div class="card-head"><h2>Decision thresholds</h2><button class="small ghost" data-act="reset-settings">Reset to defaults</button></div>
    <p class="sub">These are the rules behind the verdicts above. Change one and the verdicts, forecast and copilot answers update.</p>
    <form class="inline" data-form="settings">${Object.keys(lab).map(k => `<label>${lab[k]}<input type="number" step="${k === 'window_days' || k === 'min_sample_registrations' ? 1 : 0.05}" min="0" name="${k}" value="${s[k]}"></label>`).join('')}
      <button class="primary">Apply</button></form></div>`;
}

/* ---------------------------------------------------------------- Execute */
function viewExecute() {
  const f = ui.taskFilter;
  const tasks = D.tasks.filter(t => (!f.status || (f.status === 'overdue' ? t.overdue : t.status === f.status)) && (!f.owner || t.owner_name === f.owner) && (!f.campaign || t.campaign_id === f.campaign))
    .sort((a, b) => (a.status === 'done') - (b.status === 'done') || String(a.due_date || '9').localeCompare(String(b.due_date || '9')));
  const cname = id => (D.campaign_meta.find(c => c.campaign_id === id) || {}).campaign_name || '–';
  const openN = D.tasks.filter(t => t.status !== 'done').length, od = D.tasks.filter(t => t.overdue).length;
  const sel = (name, val, opts) => `<select data-act="task-field" data-field="${name}">${opts.map(o => `<option ${o === val ? 'selected' : ''}>${o}</option>`).join('')}</select>`;
  const perf = Object.fromEntries(D.campaigns.map(r => [r.campaign_id, r]));
  return `
  <div class="card"><div class="card-head"><h2>Campaigns</h2><button class="small primary" data-act="new-campaign">Add campaign</button></div>
    <p class="sub">Status, owner, budget and goal are saved in this browser and feed the Measure table and the copilot. Spend and results come from the data.</p>
    <div class="tablewrap"><table><thead><tr><th>Campaign</th><th>Channel</th><th>Owner</th><th>Status</th><th class="n">Budget (₹)</th><th class="n">Spent</th><th class="n">Visitor goal</th><th class="n">Visitors</th><th>Open tasks</th><th></th></tr></thead><tbody>
    ${D.campaign_meta.map(c => { const p = perf[c.campaign_id] || {}; const over = c.budget_inr != null && p.spend_inr > c.budget_inr;
      return `<tr data-cid="${c.campaign_id}"><td><strong>${esc(c.campaign_name)}</strong><div class="small muted">${c.campaign_id}${c.source === 'team' ? ' · added by team' : ''}</div></td><td>${esc(c.channel || '')}</td>
      <td><select data-act="camp-field" data-field="owner_name">${S.team.map(o => `<option ${o === c.owner_name ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select></td>
      <td><select data-act="camp-field" data-field="status">${['active', 'scaled', 'paused', 'stopped', 'planned'].map(o => `<option ${o === c.status ? 'selected' : ''}>${o}</option>`).join('')}</select></td>
      <td class="n"><input type="number" min="0" step="1000" style="width:100px" data-act="camp-field" data-field="budget_inr" value="${c.budget_inr ?? ''}" placeholder="none"></td>
      <td class="n">${inr(p.spend_inr)}${over ? ' <span class="badge bad">over</span>' : ''}</td>
      <td class="n"><input type="number" min="0" step="10" style="width:80px" data-act="camp-field" data-field="visitor_goal" value="${c.visitor_goal ?? ''}" placeholder="none"></td>
      <td class="n">${fmt(p.unique_external_visitors)}</td><td>${D.tasks.filter(t => t.campaign_id === c.campaign_id && t.status !== 'done').length}</td>
      <td class="row-actions">${c.source === 'team' ? `<button class="small danger" data-act="del-campaign">Delete</button>` : ''}</td></tr>`; }).join('')}
    </tbody></table></div></div>
  <div class="card"><div class="card-head"><h2>Tasks and action items</h2><span><span class="pill">${openN} open</span> ${od ? `<span class="badge bad">${od} overdue</span>` : ''} <button class="small primary" data-act="new-task">Add task</button></span></div>
    <div class="filters small"><span class="muted">Filter</span>
      <select data-act="task-filter" data-field="status"><option value="">Any status</option>${['todo', 'in_progress', 'blocked', 'done', 'overdue'].map(o => `<option ${f.status === o ? 'selected' : ''}>${o}</option>`).join('')}</select>
      <select data-act="task-filter" data-field="owner"><option value="">Any owner</option>${S.team.map(o => `<option ${f.owner === o ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select>
      <select data-act="task-filter" data-field="campaign"><option value="">Any campaign</option>${D.campaign_meta.map(c => `<option value="${c.campaign_id}" ${f.campaign === c.campaign_id ? 'selected' : ''}>${esc(c.campaign_name)}</option>`).join('')}</select>
      <span class="muted">Overdue is measured against the dashboard date (${nice(D.as_of)}).</span></div>
    <div class="tablewrap"><table><thead><tr><th>Task</th><th>Campaign</th><th>Owner</th><th>Due</th><th>Status</th><th>Priority</th><th>Source</th><th></th></tr></thead><tbody>
    ${tasks.map(t => `<tr data-tid="${esc(t.task_id)}"><td><strong>${esc(t.title)}</strong>${t.description ? `<div class="small muted">${esc(t.description)}</div>` : ''}${t.evidence ? `<div class="small muted">Evidence: ${esc(t.evidence)}</div>` : ''}</td>
      <td>${esc(t.campaign_id ? cname(t.campaign_id) : 'All')}</td><td>${sel('owner_name', t.owner_name, S.team)}</td>
      <td><input type="date" data-act="task-field" data-field="due_date" value="${esc(t.due_date || '')}">${t.overdue ? ' <span class="badge bad">overdue</span>' : ''}</td>
      <td>${sel('status', t.status, ['todo', 'in_progress', 'blocked', 'done'])}</td><td>${sel('priority', t.priority, ['high', 'medium', 'low'])}</td>
      <td><span class="pill">${esc(t.source || 'manual')}</span></td><td class="row-actions"><button class="small" data-act="edit-task">Edit</button> <button class="small danger" data-act="del-task">Delete</button></td></tr>`).join('') || `<tr><td colspan="8" class="muted">No tasks match this filter.</td></tr>`}
    </tbody></table></div></div>`;
}

/* ---------------------------------------------------------------- Data */
function viewData() {
  const o = S.overlay, camps = D.campaign_meta;
  const copt = (blank) => (blank ? `<option value="">Unattributed (walk-ins)</option>` : '') + camps.map(c => `<option value="${c.campaign_id}">${esc(c.campaign_name)}</option>`).join('');
  const cname = id => (camps.find(c => c.campaign_id === id) || {}).campaign_name || 'Unattributed';
  const dq = D.duplicates_removed;
  return `
  <div class="card"><h2>Log campaign activity and spend</h2><p class="sub">Adds a daily row for a campaign. Use a negative spend to record a vendor credit. Every chart, verdict and copilot answer recomputes from it.</p>
    <form class="inline" data-form="daily"><label>Campaign<select name="campaign_id" required>${copt()}</select></label><label>Date<input type="date" name="activity_date" value="${D.as_of}" min="${D.bounds.min}" required></label>
      <label>Spend (₹)<input type="number" name="marketing_spend_inr" step="1" value="0"></label><label>Impressions<input type="number" name="impressions" min="0" value="0"></label><label>Clicks<input type="number" name="clicks" min="0" value="0"></label>
      <label>Landing sessions<input type="number" name="landing_page_sessions" min="0" value="0"></label><label>Form starts<input type="number" name="registration_starts" min="0" value="0"></label><button class="primary">Add entry</button></form></div>
  <div class="card"><h2>Log results</h2><p class="sub">Adds people-level results as simulated records (IDs starting with U), counted exactly like source records. Check-ins against a campaign admit that campaign's confirmed registrants who have not attended yet; with no campaign they are walk-ins.</p>
    <form class="inline" data-form="outcome"><label>Campaign<select name="campaign_id">${copt(true)}</select></label><label>Date<input type="date" name="date" value="${D.as_of}" min="${D.bounds.min}" required></label>
      <label>New identified leads<input type="number" name="new_leads" min="0" value="0"></label><label>New confirmed registrations<input type="number" name="new_registrations" min="0" value="0"></label><label>Verified check-ins<input type="number" name="verified_checkins" min="0" value="0"></label><button class="primary">Add results</button></form></div>
  <div class="card"><h2>Targets and budget</h2><p class="sub">A target version applies from its effective date until the next one. Add a version to change goals or the approved budget.</p>
    <div class="tablewrap"><table><thead><tr><th>Effective</th><th>Version</th><th class="n">Identified goal</th><th class="n">Registration goal</th><th class="n">Visitor goal</th><th class="n">Budget</th><th></th></tr></thead><tbody>
    ${D.targets.map(t => { const mine = o.targets.find(x => x.effective_at === t.effective_at && x.target_version === t.target_version);
      return `<tr><td>${esc(t.effective_at.slice(0, 10))}</td><td>${esc(t.target_version)}</td><td class="n">${fmt(t.identified_external_people_goal)}</td><td class="n">${fmt(t.registration_goal)}</td><td class="n">${fmt(t.unique_external_visitors_goal)}</td><td class="n">${inr(t.marketing_budget_inr)}</td>
      <td>${mine ? `<button class="small danger" data-act="del-target" data-id="${esc(mine.id)}">Delete</button>` : '<span class="pill">source</span>'}</td></tr>`; }).join('')}</tbody></table></div>
    <form class="inline" data-form="target" style="margin-top:10px"><label>Effective date<input type="date" name="effective" value="${D.as_of}" required></label><label>Version name<input name="target_version" value="Team revision" required></label>
      <label>Identified goal<input type="number" name="identified_external_people_goal" min="0" value="${D.overview.vs_target.identified_external_people.goal ?? 0}"></label><label>Registration goal<input type="number" name="registration_goal" min="0" value="${D.overview.vs_target.registered_external_people.goal ?? 0}"></label>
      <label>Visitor goal<input type="number" name="unique_external_visitors_goal" min="0" value="${D.overview.vs_target.unique_external_visitors.goal ?? 0}"></label><label>Budget (₹)<input type="number" name="marketing_budget_inr" min="0" value="${D.overview.vs_target.spend_inr.goal ?? 0}"></label><button class="primary">Add version</button></form></div>
  <div class="card"><h2>Team-entered records</h2>
    ${o.daily.length + o.outcomes.length === 0 ? '<p class="muted">Nothing logged yet. The app is showing source data only.</p>' : `<div class="tablewrap"><table><thead><tr><th>Type</th><th>Date</th><th>Campaign</th><th>Detail</th><th></th></tr></thead><tbody>
      ${o.daily.map(r => `<tr><td>Activity</td><td>${esc(r.activity_date)}</td><td>${esc(cname(r.campaign_id))}</td><td>spend ${inr(r.marketing_spend_inr)} · ${fmt(r.impressions)} impressions · ${fmt(r.clicks)} clicks · ${fmt(r.landing_page_sessions)} sessions · ${fmt(r.registration_starts)} starts</td><td><button class="small danger" data-act="del-daily" data-id="${esc(r.activity_id)}">Delete</button></td></tr>`).join('')}
      ${o.outcomes.map(r => `<tr><td>Results</td><td>${esc(r.date)}</td><td>${esc(cname(r.campaign_id))}</td><td>${fmt(r.new_leads)} leads · ${fmt(r.new_registrations)} registrations · ${fmt(r.verified_checkins)} check-ins</td><td><button class="small danger" data-act="del-outcome" data-id="${esc(r.id)}">Delete</button></td></tr>`).join('')}</tbody></table></div>`}</div>
  <div class="card"><h2>Source data and saved state</h2>
    <p class="sub">Source: the provided Attendee Dataset (CampusFest 2025, synthetic), ${D.bounds.min} to ${D.event.history_end.slice(0, 10)}. Import-retry duplicates removed on load: ${dq.daily} daily rows, ${dq.registration_history} status versions, ${dq.checkins} check-ins. Your changes are stored in this browser.</p>
    <p><button data-act="export">Export saved changes (JSON)</button> <button data-act="import">Import saved changes</button> <button class="danger" data-act="reset">Reset to original data</button> <input type="file" id="importFile" accept="application/json" hidden></p></div>`;
}

/* ---------------------------------------------------------------- dialogs */
function dialog(html, onSubmit) {
  const d = $('#dlg'); d.innerHTML = html; d.showModal();
  d.querySelector('form').onsubmit = e => { e.preventDefault(); if (e.submitter && e.submitter.value === 'cancel') return d.close(); onSubmit(Object.fromEntries(new FormData(e.target))); d.close(); };
}
function taskDialog(t = {}) {
  const isNew = !t.task_id;
  dialog(`<form><h2>${isNew ? 'New task' : 'Edit task'}</h2>
    <label>Title<input name="title" required value="${esc(t.title || '')}"></label>
    <label>Description<textarea name="description" rows="2">${esc(t.description || '')}</textarea></label>
    <label>Campaign<select name="campaign_id"><option value="">All campaigns</option>${D.campaign_meta.map(c => `<option value="${c.campaign_id}" ${t.campaign_id === c.campaign_id ? 'selected' : ''}>${esc(c.campaign_name)}</option>`).join('')}</select></label>
    <label>Owner<select name="owner_name">${S.team.map(o => `<option ${o === t.owner_name ? 'selected' : ''}>${esc(o)}</option>`).join('')}</select></label>
    <label>Due date<input type="date" name="due_date" value="${esc(t.due_date || addDays(D.as_of, 3))}"></label>
    <label>Priority<select name="priority">${['high', 'medium', 'low'].map(o => `<option ${o === (t.priority || 'medium') ? 'selected' : ''}>${o}</option>`).join('')}</select></label>
    <label>Evidence<textarea name="evidence" rows="2">${esc(t.evidence || '')}</textarea></label>
    <div class="btns"><button value="cancel" formnovalidate>Cancel</button><button class="primary" value="ok">Save</button></div></form>`, v => {
    v.campaign_id = v.campaign_id || null;
    if (isNew) addTask({ ...v, source: t.source || 'manual' }); else Object.assign(S.overlay.tasks.find(x => x.task_id === t.task_id), v);
    save(); refresh(); toast(isNew ? 'Task created' : 'Task updated');
  });
}
function addTask(t) {
  const task = { task_id: nextId('T'), status: 'todo', priority: 'medium', source: 'manual', created_at: D.as_of, description: '', evidence: '', campaign_id: null, owner_name: S.team[0], due_date: addDays(D.as_of, 3), ...t };
  if (!S.team.includes(task.owner_name)) task.owner_name = S.team[0];
  S.overlay.tasks.push(task); return task;
}
function campaignDialog() {
  dialog(`<form><h2>New campaign</h2>
    <label>Name<input name="campaign_name" required></label><label>Channel<input name="channel" required placeholder="e.g. whatsapp_groups"></label>
    <label>Target audience<input name="target_audience"></label><label>Objective<input name="objective"></label>
    <label>Owner<select name="owner_name">${S.team.map(o => `<option>${esc(o)}</option>`).join('')}</select></label>
    <label>Budget (₹)<input type="number" name="budget_inr" min="0"></label><label>Visitor goal<input type="number" name="visitor_goal" min="0"></label>
    <div class="btns"><button value="cancel" formnovalidate>Cancel</button><button class="primary" value="ok">Create</button></div></form>`, v => {
    const id = 'U' + String(++S.seq).padStart(2, '0');
    S.overlay.new_campaigns.push({ campaign_id: id, campaign_name: v.campaign_name, channel: v.channel, target_audience: v.target_audience, objective: v.objective, owner_name: v.owner_name,
      created_at: D.as_of + 'T09:00:00', planned_start_at: D.as_of + 'T09:00:00', planned_end_at: D.bounds.event_end + 'T20:00:00', status: 'planned',
      budget_inr: v.budget_inr === '' ? null : +v.budget_inr, visitor_goal: v.visitor_goal === '' ? null : +v.visitor_goal });
    save(); refresh(); toast('Campaign created. Log its activity and results in the Data tab.');
  });
}

/* ---------------------------------------------------------------- events */
document.addEventListener('click', e => {
  const b = e.target.closest('[data-act], [data-tab]'); if (!b) return;
  if (b.dataset.tab) { S.tab = b.dataset.tab; save(); renderChrome(); render(); window.scrollTo(0, 0); return; }
  const a = b.dataset.act, row = b.closest('tr'), o = S.overlay;
  if (a === 'asof') { S.as_of = b.dataset.day; refresh(); }
  else if (a === 'new-task') taskDialog();
  else if (a === 'edit-task') taskDialog(o.tasks.find(t => t.task_id === row.dataset.tid));
  else if (a === 'del-task') { if (confirm('Delete this task?')) { o.tasks = o.tasks.filter(t => t.task_id !== row.dataset.tid); save(); refresh(); } }
  else if (a === 'new-campaign') campaignDialog();
  else if (a === 'del-campaign') { const cid = row.dataset.cid; if (confirm('Delete this campaign and the activity and results logged for it?')) { o.new_campaigns = o.new_campaigns.filter(c => c.campaign_id !== cid); o.daily = o.daily.filter(r => r.campaign_id !== cid); o.outcomes = o.outcomes.filter(r => r.campaign_id !== cid); delete o.campaign_edits[cid]; save(); refresh(); } }
  else if (a === 'task-from-verdict') {
    const c = D.decisions.campaigns.find(x => x.campaign_id === b.dataset.cid);
    taskDialog({ title: `${c.verdict}: ${c.campaign_name}`, description: c.action, campaign_id: c.campaign_id, owner_name: c.owner_name, priority: c.verdict === 'STOP' || c.verdict === 'FIX' ? 'high' : 'medium',
      evidence: `As of ${D.as_of}: ` + (c.evidence.join('; ') || 'within thresholds'), source: 'decision rule' });
  }
  else if (a === 'set-status') { (o.campaign_edits[b.dataset.cid] ||= {}).status = b.dataset.status; save(); refresh(); toast('Campaign marked ' + b.dataset.status); }
  else if (a === 'reset-settings') { o.settings = {}; save(); refresh(); }
  else if (a === 'del-daily') { o.daily = o.daily.filter(r => r.activity_id !== b.dataset.id); save(); refresh(); }
  else if (a === 'del-outcome') { o.outcomes = o.outcomes.filter(r => r.id !== b.dataset.id); save(); refresh(); }
  else if (a === 'del-target') { o.targets = o.targets.filter(r => r.id !== b.dataset.id); save(); refresh(); }
  else if (a === 'export') { const u = URL.createObjectURL(new Blob([JSON.stringify(S, null, 2)], { type: 'application/json' })); const l = document.createElement('a'); l.href = u; l.download = 'growth-center-state.json'; l.click(); URL.revokeObjectURL(u); }
  else if (a === 'import') $('#importFile').click();
  else if (a === 'reset') { if (confirm('Discard every saved change (tasks, campaign edits, logged data, targets, chat) and return to the original dataset?')) { S = fresh(); save(); refresh(); renderChat(); } }
  else if (a === 'suggest') { $('#chatInput').value = b.textContent; sendChat(); }
  else if (a === 'confirm-proposal' || a === 'dismiss-proposal') resolveProposal(b.dataset.pid, a === 'confirm-proposal');
});

document.addEventListener('change', e => {
  const el = e.target, a = el.dataset.act, o = S.overlay;
  if (el.id === 'asOf' && el.value) { S.as_of = el.value; refresh(); }
  else if (el.id === 'importFile' && el.files[0]) { el.files[0].text().then(t => { const j = JSON.parse(t); if (!j.overlay) throw new Error('not a Growth Center export'); S = { ...fresh(), ...j }; save(); refresh(); renderChat(); toast('Imported'); }).catch(err => toast('Import failed: ' + err.message)); el.value = ''; }
  else if (a === 'metric') { ui.metric = el.value; render(); }
  else if (a === 'task-filter') { ui.taskFilter[el.dataset.field] = el.value; render(); }
  else if (a === 'task-field') { const t = o.tasks.find(t => t.task_id === el.closest('tr').dataset.tid); t[el.dataset.field] = el.value; save(); refresh(); }
  else if (a === 'camp-field') { const cid = el.closest('tr').dataset.cid, f = el.dataset.field; (o.campaign_edits[cid] ||= {})[f] = (f === 'budget_inr' || f === 'visitor_goal') ? (el.value === '' ? null : +el.value) : el.value; save(); refresh(); }
});

document.addEventListener('submit', e => {
  const form = e.target.closest('[data-form]'); if (!form) return;
  e.preventDefault();
  const v = Object.fromEntries(new FormData(form)), o = S.overlay, kind = form.dataset.form;
  const num = k => +v[k] || 0;
  if (kind === 'daily') { o.daily.push({ activity_id: nextId('USR'), campaign_id: v.campaign_id, activity_date: v.activity_date, marketing_spend_inr: num('marketing_spend_inr'), impressions: num('impressions'), clicks: num('clicks'), reported_reach: 0, landing_page_sessions: num('landing_page_sessions'), registration_starts: num('registration_starts') }); toast('Activity logged'); }
  else if (kind === 'outcome') { if (!(num('new_leads') + num('new_registrations') + num('verified_checkins'))) return toast('Enter at least one count'); o.outcomes.push({ id: 'O' + (++S.seq), campaign_id: v.campaign_id || null, date: v.date, new_leads: num('new_leads'), new_registrations: num('new_registrations'), verified_checkins: num('verified_checkins') }); toast('Results logged'); }
  else if (kind === 'target') { o.targets.push({ id: nextId('TV'), effective_at: v.effective + 'T09:00:00', target_version: v.target_version, identified_external_people_goal: num('identified_external_people_goal'), registration_goal: num('registration_goal'), unique_external_visitors_goal: num('unique_external_visitors_goal'), marketing_budget_inr: num('marketing_budget_inr') }); toast('Target version added'); }
  else if (kind === 'settings') { o.settings = v; toast('Thresholds applied'); }
  if ((kind === 'daily' || kind === 'outcome') && (v.activity_date || v.date) > S.as_of) S.as_of = v.activity_date || v.date;
  save(); refresh();
});

/* tooltips */
const tip = $('#tip');
document.addEventListener('mousemove', e => {
  const svg = e.target.closest('svg[data-chart="line"]');
  if (svg && D) {
    const r = svg.getBoundingClientRect(), W = 640, L = 46, R = 14, rows = D.series;
    const px = (e.clientX - r.left) / r.width * W;
    const i = Math.max(0, Math.min(rows.length - 1, Math.round((px - L) / (W - L - R) * (rows.length - 1))));
    const row = rows[i], f = svg.dataset.unit === 'inr' ? inr : fmt, cx = L + (W - L - R) * (rows.length > 1 ? i / (rows.length - 1) : 0);
    const c = svg.querySelector('.cross'); c.setAttribute('x1', cx); c.setAttribute('x2', cx); c.setAttribute('visibility', 'visible');
    tip.innerHTML = `<strong>${nice(row.date)}</strong><br>Actual: ${f(row[svg.dataset.key])}` + (svg.dataset.goal && row[svg.dataset.goal] != null ? `<br>${svg.dataset.unit === 'inr' ? 'Budget' : 'Goal'}: ${f(row[svg.dataset.goal])}` : '');
    return showTip(e);
  }
  document.querySelectorAll('svg .cross').forEach(c => c.setAttribute('visibility', 'hidden'));
  const t = e.target.closest('[data-tip]');
  if (t) { tip.textContent = t.dataset.tip; return showTip(e); }
  tip.hidden = true;
});
function showTip(e) { tip.hidden = false; const w = tip.offsetWidth; tip.style.left = Math.min(window.innerWidth - w - 8, e.clientX + 12) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; }

/* ---------------------------------------------------------------- copilot */
function md(src) {
  const inline = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>');
  const lines = String(src || '').split('\n'); let out = '', i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (/^\s*\|.*\|\s*$/.test(l)) {
      const rows = []; while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(lines[i++]);
      const cells = r => r.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim());
      const body = rows.filter(r => !/^\s*\|[\s:|-]+\|\s*$/.test(r));
      out += '<div class="tablewrap"><table>' + body.map((r, k) => '<tr>' + cells(r).map(c => k === 0 ? `<th>${inline(c)}</th>` : `<td>${inline(c)}</td>`).join('') + '</tr>').join('') + '</table></div>';
    } else if (/^\s*([-*•]|\d+[.)])\s+/.test(l)) {
      const ord = /^\s*\d/.test(l); let items = '';
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) items += '<li>' + inline(lines[i++].replace(/^\s*([-*•]|\d+[.)])\s+/, '')) + '</li>';
      out += ord ? `<ol>${items}</ol>` : `<ul>${items}</ul>`;
    } else if (/^#{1,4}\s/.test(l)) { out += `<p><strong>${inline(l.replace(/^#+\s/, ''))}</strong></p>`; i++; }
    else if (l.trim() === '') i++;
    else { let p = l; i++; while (i < lines.length && lines[i].trim() && !/^\s*([-*•]|\d+[.)]|\||#)/.test(lines[i])) p += ' ' + lines[i++]; out += `<p>${inline(p)}</p>`; }
  }
  return out;
}
function describeAction(p) {
  const cname = id => (D.campaign_meta.find(c => c.campaign_id === id) || {}).campaign_name || id;
  if (p.type === 'create_task') return `<strong>New task:</strong> ${esc(p.title || 'Untitled')}<div class="small muted">${esc(p.owner_name || 'unassigned')} · due ${esc(p.due_date || addDays(D.as_of, 3))} · ${esc(p.priority || 'medium')}${p.campaign_id ? ' · ' + esc(cname(p.campaign_id)) : ''}</div>${p.description ? `<div class="small">${esc(p.description)}</div>` : ''}${p.evidence ? `<div class="small muted">Evidence: ${esc(p.evidence)}</div>` : ''}`;
  if (p.type === 'update_task') return `<strong>Update task ${esc(p.task_id)}:</strong> ${['status', 'owner_name', 'due_date', 'priority', 'title'].filter(k => p[k]).map(k => `${k.replace('_', ' ')} → ${esc(p[k])}`).join(', ')}`;
  if (p.type === 'update_campaign') return `<strong>Update ${esc(cname(p.campaign_id))}:</strong> ${['status', 'budget_inr', 'owner_name'].filter(k => p[k] != null).map(k => `${k.replace('_inr', '').replace('_', ' ')} → ${esc(k === 'budget_inr' ? inr(p[k]) : p[k])}`).join(', ')}${p.evidence ? `<div class="small muted">Evidence: ${esc(p.evidence)}</div>` : ''}`;
  return esc(JSON.stringify(p));
}
function renderChat() {
  const log = $('#chatLog');
  if (!S.chat.log.length) {
    log.innerHTML = `<div class="msg note">I answer from this app's current data: the same numbers as the dashboard, including anything your team has logged or changed. I show the queries I ran, and I'll say so when the data can't answer.</div>`;
  } else log.innerHTML = S.chat.log.map(m => {
    if (m.role === 'user') return `<div class="msg user">${esc(m.text)}</div>`;
    if (m.role === 'error') return `<div class="msg err">${esc(m.text)}</div>`;
    if (m.role === 'note') return `<div class="msg note">${esc(m.text)}</div>`;
    return `<div class="msg bot">${md(m.text)}${(m.proposals || []).map(p => `<div class="proposal ${p.state || ''}">${describeAction(p)}
        ${p.state ? `<div class="small muted">${p.state === 'done' ? 'Confirmed and saved' + (p.result ? ' · ' + esc(p.result) : '') : 'Dismissed'}</div>` : `<div class="btns"><button class="small primary" data-act="confirm-proposal" data-pid="${esc(p.proposal_id)}">Confirm</button><button class="small" data-act="dismiss-proposal" data-pid="${esc(p.proposal_id)}">Dismiss</button></div>`}</div>`).join('')}
      ${(m.trace || []).length ? `<details class="trace"><summary>Data used: ${m.trace.length} quer${m.trace.length === 1 ? 'y' : 'ies'}</summary><ul>${m.trace.map(t => `<li><strong>${esc(t.tool)}</strong> <code>${esc(JSON.stringify(t.input))}</code> → ${esc(t.summary)}</li>`).join('')}</ul></details>` : ''}</div>`;
  }).join('') + (ui.busy ? `<div class="msg note">Working on it…</div>` : '');
  log.scrollTop = log.scrollHeight;
  $('#chatSend').disabled = ui.busy;
}
function renderSuggest() {
  const pre = D && D.overview.phase === 'pre-event';
  const qs = pre ? ['Are we on track for the visitor goal?', 'Which campaign should we scale and which should we stop?', 'Where is the biggest funnel bottleneck?', 'What changed in the last 14 days?']
    : ['Why did we miss the visitor goal?', 'Which campaigns had the worst no-show rate?', 'Rank campaigns by cost per verified visitor', 'What should we do differently next time?'];
  $('#chatSuggest').innerHTML = S.chat.log.length ? '' : qs.map(q => `<button data-act="suggest">${q}</button>`).join('');
}
async function sendChat() {
  const input = $('#chatInput'), text = input.value.trim();
  if (!text || ui.busy) return;
  input.value = ''; S.chat.log.push({ role: 'user', text }); ui.busy = true; renderChat(); renderSuggest();
  const events = S.chat.events.splice(0);
  let userText = text, trace = [], proposals = [];
  try {
    for (let round = 0; round < 6; round++) {
      const r = await api('/api/chat', { overlay: S.overlay, as_of: S.as_of, team: S.team, provider: S.chat.provider, messages: S.chat.messages, user_text: userText, events: round === 0 ? events : [] });
      S.chat.provider = r.provider; S.chat.messages = r.messages || [];
      trace = trace.concat(r.trace || []); proposals = proposals.concat(r.proposals || []);
      if (r.error) { S.chat.log.push({ role: 'error', text: r.error }); break; }
      if (r.done) { if (r.notice && !S.chat.log.some(m => m.role === 'note')) S.chat.log.push({ role: 'note', text: r.notice }); S.chat.log.push({ role: 'bot', text: r.reply || '(no answer)', trace, proposals }); break; }
      userText = '';
      if (round === 5) S.chat.log.push({ role: 'error', text: 'The analysis took too many steps. Try a narrower question.' });
    }
  } catch (e) { S.chat.log.push({ role: 'error', text: 'Copilot request failed: ' + e.message }); }
  ui.busy = false; trimChat(); save(); renderChat();
}
function trimChat() { // keep browser storage bounded; old turns drop from the model's memory, not from the data
  if (JSON.stringify(S.chat.messages).length > 600000) { S.chat.messages = []; S.chat.log.push({ role: 'note', text: 'Conversation memory was reset because it grew too large. Earlier answers stay visible above.' }); }
  if (S.chat.log.length > 80) S.chat.log = S.chat.log.slice(-80);
}
function resolveProposal(pid, ok) {
  let p; S.chat.log.forEach(m => (m.proposals || []).forEach(x => { if (x.proposal_id === pid) p = x; }));
  if (!p || p.state) return;
  if (!ok) { p.state = 'dismissed'; S.chat.events.push(`User dismissed proposal ${pid} (${p.type}).`); save(); return renderChat(); }
  const o = S.overlay;
  if (p.type === 'create_task') { const t = addTask({ title: p.title || 'Untitled', description: p.description || '', owner_name: p.owner_name, due_date: p.due_date || addDays(D.as_of, 3), priority: p.priority || 'medium', campaign_id: p.campaign_id || null, evidence: p.evidence || '', source: 'copilot' }); p.result = t.task_id; S.chat.events.push(`User confirmed proposal ${pid}: task ${t.task_id} "${t.title}" created, owner ${t.owner_name}, due ${t.due_date}.`); }
  else if (p.type === 'update_task') { const t = o.tasks.find(t => t.task_id === p.task_id); if (!t) { toast('That task no longer exists'); return; } ['status', 'owner_name', 'due_date', 'priority', 'title', 'description'].forEach(k => { if (p[k]) t[k] = p[k]; }); p.result = t.task_id; S.chat.events.push(`User confirmed proposal ${pid}: task ${t.task_id} updated.`); }
  else if (p.type === 'update_campaign') { const e = (o.campaign_edits[p.campaign_id] ||= {}); ['status', 'budget_inr', 'owner_name'].forEach(k => { if (p[k] != null) e[k] = p[k]; }); p.result = p.campaign_id; S.chat.events.push(`User confirmed proposal ${pid}: campaign ${p.campaign_id} updated.`); }
  p.state = 'done'; save(); renderChat(); refresh(); toast('Saved to the management tool');
}
$('#chatForm').addEventListener('submit', e => { e.preventDefault(); sendChat(); });
$('#chatInput').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } });
$('#chatClear').addEventListener('click', () => { S.chat = { provider: null, messages: [], log: [], events: [] }; save(); renderChat(); renderSuggest(); });
$('#chatToggle').addEventListener('click', () => { document.body.classList.toggle(window.innerWidth <= 1100 ? 'chatopen' : 'nochat'); });

// deep links: /#decide opens a tab, ?date=2025-03-01 sets the dashboard date, ?ask=... asks the copilot
const qp = new URLSearchParams(location.search);
if (['measure', 'diagnose', 'decide', 'execute', 'data'].includes(location.hash.slice(1))) S.tab = location.hash.slice(1);
if (/^\d{4}-\d\d-\d\d$/.test(qp.get('date') || '')) S.as_of = qp.get('date');
renderChat();
refresh().then(() => { if (qp.get('ask')) { $('#chatInput').value = qp.get('ask'); sendChat(); } });
})();
