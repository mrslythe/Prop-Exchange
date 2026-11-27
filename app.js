// Clickjacking guard: the page stays hidden unless it is the top window; if another site
// frames it, the browser is sent to the real page instead.
if (window.self === window.top) {
  const g = document.getElementById("antiClickjack"); if (g) g.remove();
} else {
  try { window.top.location = window.self.location.href; } catch (e) { /* stays hidden */ }
}
const $ = id => document.getElementById(id);
let league = "ALL", show = "all", statF = "", q = "";
let run = null, games = [];
const openState = new Set();
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const f1 = n => (Math.round(n*10)/10).toString();
function lsGet(k){try{return localStorage.getItem(k)}catch(e){return null}}
function lsSet(k,v){try{localStorage.setItem(k,v)}catch(e){}}
const saved = lsGet("pex.league"); if (saved) league = saved;

document.querySelectorAll("[data-lg]").forEach(b => b.onclick = () => { league = b.dataset.lg; lsSet("pex.league", league); render(); });
$("show").onchange = () => { show = $("show").value; special = show === "special"; render(); };
$("stat").onchange = () => { statF = $("stat").value; render(); };
$("q").oninput = () => { q = $("q").value.trim().toLowerCase(); render(); };

function when(iso){
  if(!iso) return "Time TBD";
  const d = new Date(iso);
  return d.toLocaleString([], {weekday:"short", month:"short", day:"numeric", hour:"numeric", minute:"2-digit"});
}
let special = false;
// small line icons (replace emoji badges and flags)
const ICONS = {
  cake: '<path d="M4 20h16M6 20v-6h12v6M12 14v-4M12 6.5v.5"/>',
  target: '<circle cx="12" cy="12" r="7"/><path d="M12 2v5M12 17v5M2 12h5M17 12h5"/>',
  home: '<path d="M3 11l9-8 9 8M5 10v10h14V10"/>',
  pin: '<path d="M12 21s-7-6.5-7-12a7 7 0 0 1 14 0c0 5.5-7 12-7 12z"/><circle cx="12" cy="9" r="2.5"/>',
  moon: '<path d="M20 13.5A8 8 0 1 1 10.5 4a6.5 6.5 0 0 0 9.5 9.5z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  cross: '<path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z"/>',
  flame: '<path d="M12 3c1 3.5 5 5.5 5 10a5 5 0 0 1-10 0c0-2.5 1.5-4 2-6.5 1 1 2 2.2 2.5 3.8.5-2.5 0-5-.5-7.3z"/>',
  alert: '<path d="M12 4l9 16H3zM12 10v4M12 17v.5"/>'
};
const ic = n => `<svg class="ic" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[n] || ""}</svg>`;
const KIND_ICON = {birthday: "cake", revenge: "target", hometown: "home", homestate: "pin"};
const KIND_LABEL = {birthday: "Birthday", revenge: "Revenge", hometown: "Hometown", homestate: "Home state"};
const POSN = {QB: "QBs", RB: "RBs", WR: "WRs", TE: "TEs", G: "guards", F: "forwards", C: "centers"};
// ---- new signals: what nudged each projection, player flags, and the per-prop chart
const NUDGE_LABEL = {matchup: "matchup", venue: "home/away", minutes: "minutes", b2b: "back-to-back", teammate: "teammate out"};
const sgn = v => (v > 0 ? "+" : "−") + Math.abs(v);
const nudgeTxt = x => Object.entries(x.nudges || {}).map(([k, v]) => `${sgn(v)} ${NUDGE_LABEL[k] || k}`).join(" · ");
const propOpen = new Set(), propSample = {};
// v4 calls: play (green) / lean (yellow) / pass (red) on x.side, by x.edge over the price
const nvig = x => x.vegas != null && x.vegasU != null ? Math.round(100 * x.vegas / (x.vegas + x.vegasU)) : x.vegas;
const edgeTxt = e => e == null ? "" : `${e >= 0 ? "+" : "−"}${Math.abs(e).toFixed(1)}`;
const sideTxt = x => x.side === "under" ? "▼ UNDER" : "▲ OVER";
const isPlay = (x, side) => x.call === "play" && (!side || x.side === side);
function gameRows(p, x){
  return (p.gl || []).map((g, i) => ({d: g[0], opp: g[1], h: g[2], min: g[3], cur: g[4], v: (x.v || [])[i]})).filter(r => r.v != null);
}
function playerFlags(p){
  const out = [];
  const n = (p.props[0] || {}).nudges || {};
  if (n.b2b) out.push(`<span class="flag" title="Played yesterday: tired legs; projections lowered 2 points">${ic("moon")}Back-to-back</span>`);
  const mins = (p.gl || []).filter(g => g[4] && g[3]).map(g => g[3]);
  if (mins.length >= 5) {
    const l5 = mins.slice(0, 5).reduce((a, b) => a + b, 0) / 5, se = mins.reduce((a, b) => a + b, 0) / mins.length;
    if (Math.abs(l5 - se) >= 3) out.push(`<span class="flag ${l5 > se ? "u" : "d"}" title="Minutes per game, last 5 vs this season: a role change shows up here first">${ic("clock")}Minutes ${l5 > se ? "▲" : "▼"} ${l5.toFixed(0)} (season ${se.toFixed(0)})</span>`);
  }
  const t = p.props.find(x => x.tm)?.tm;
  if (t) out.push(`<span class="flag" title="${esc(t.name)} (${t.min} min/game) is out today. Tap a prop to see how this player did without him.">${ic("cross")}${esc(t.name)} out</span>`);
  return out.length ? `<span class="flags">${out.join("")}</span>` : "";
}
function altLines(line){
  const step = line < 3 ? 1 : line < 10 ? 1 : line < 20 ? 2 : line < 40 ? 3 : line < 100 ? 5 : 10;
  const out = [];
  for (let k = -2; k <= 3; k++) { const a = Math.round((line + k * step) * 2) / 2; if (a > 0 && !out.includes(a)) out.push(a); }
  return out;
}
function chartPanel(p, x, key){
  const S = propSample[key] || "10";
  const rows = gameRows(p, x);
  const pick = S === "season" ? rows.filter(r => r.cur) : rows.slice(0, +S);
  const n = pick.length, hit = pick.filter(r => r.v > x.line).length;
  const avg = n ? pick.reduce((a, r) => a + r.v, 0) / n : 0;
  const arr = [...pick].reverse();
  const max = Math.max(x.line * 1.3, ...arr.map(r => r.v), 1);
  const W = 26, H = 120, top = 14, base = top + H, width = Math.max(arr.length * W + 8, 120);
  const y = v => base - (v / max) * H;
  const bars = arr.map((r, i) => {
    const h = Math.max(2, base - y(r.v)), xx = 4 + i * W;
    return `<rect x="${xx}" y="${base - h}" width="${W - 6}" height="${h}" rx="2" class="${r.v > x.line ? "bh" : "bm"}"><title>${esc(r.d)} ${r.h ? "vs" : "@"} ${esc(r.opp)}: ${f1(r.v)}${r.min ? ` (${r.min} min)` : ""}</title></rect>
      <text x="${xx + (W - 6) / 2}" y="${base - h - 3}" class="bv">${f1(r.v)}</text>
      <text x="${xx + (W - 6) / 2}" y="${base + 11}" class="bo">${esc(r.opp)}</text>`;
  }).join("");
  const chart = n ? `<svg class="pchart" viewBox="0 0 ${width} ${base + 16}" width="${width}" height="${base + 16}" role="img" aria-label="${esc(x.stat)} in the last ${n} games vs the line ${x.line}">${bars}<line x1="0" x2="${width}" y1="${y(x.line)}" y2="${y(x.line)}" class="bl"/><text x="${width - 2}" y="${y(x.line) - 3}" class="blt">${x.line}</text></svg>` : `<p class="note">No games to chart yet.</p>`;
  const btn = (v, t) => `<button type="button" data-sample="${v}" aria-pressed="${S === v}">${t}</button>`;
  const alts = altLines(x.line).map(a => { const h = pick.filter(r => r.v > a).length; return `<span class="${a === x.line ? "cur" : ""}">o${a}: <b>${h}/${n}</b> ${n ? Math.round(100 * h / n) + "%" : ""}</span>`; }).join("");
  const se = rows.filter(r => r.cur), hm = se.filter(r => r.h), aw = se.filter(r => !r.h);
  const split = (list, t) => list.length ? `${t} <b>${list.filter(r => r.v > x.line).length}/${list.length}</b> (avg ${f1(list.reduce((a, r) => a + r.v, 0) / list.length)})` : "";
  const t = x.tm;
  const tmTxt = t ? `<p class="note">${ic("cross")} <b>Without ${esc(t.name)}</b> (out today, ${t.min} min/game): over in <b>${t.hits}/${t.n}</b> games, avg ${t.avg}${t.nW ? ` · with him: ${t.hitsW}/${t.nW}, avg ${t.avgW}` : ""}.${t.n < 3 ? " Small sample: not used in the projection." : ""}</p>` : "";
  const nt = nudgeTxt(x);
  return `<div class="pdet">
    <div class="pseg" role="group" aria-label="Sample">${btn("5", "L5")}${btn("10", "L10")}${btn("20", "L20")}${btn("season", "Season")}</div>
    <p class="note"><b>${esc(x.stat)} o${x.line}:</b> ${S === "season" ? "This season" : `Last ${n}`} over in <b>${hit}/${n}</b>${n ? ` (${Math.round(100 * hit / n)}%)` : ""} · avg ${f1(avg)}</p>
    <div class="pscroll">${chart}</div>
    <div class="alts"><span class="note">Alt lines (${S === "season" ? "season" : `last ${n}`}):</span>${alts}</div>
    <p class="note">This season: ${[split(hm, "Home"), split(aw, "Away")].filter(Boolean).join(" · ") || "—"}</p>
    ${tmTxt}
    ${x.form != null && !x.low ? `<p class="note"><b>How the ${x.proj}% over was built:</b> Vegas ${nvig(x) ?? "—"}% (over and under prices, bookmaker's cut removed) and Form ${x.form}% (base ${x.projBase}% = 60% season + 40% last 5${nt ? `, ${nt}` : ""}), each weighted by what the last 14 days of results say it is worth (refit every Monday). <b>Best side:</b> ${x.side} at ${x.chance}%${x.edge != null ? `, ${edgeTxt(x.edge)} points vs what its odds need to break even` : ""}.</p>` : ""}
  </div>`;
}
const TIER = {tough: "Tough", easy: "Easy", neutral: "Average"};
const ord = n => n + (["th","st","nd","rd"][(n % 100 - 20) % 10] || ["th","st","nd","rd"][n % 100] || "th");
function dvpLine(p){
  const m = p.matchup; if (!m) return "";
  const nick = (m.opp || "").split(" ").pop();
  return `<span class="dvp" title="Ranked 1 (allows the least) to ${m.of} (allows the most), over ${m.games} games this season. League average: ${m.avg}."><span class="tier ${esc(m.tier)}">${TIER[m.tier] || ""}</span>${esc(nick)} D vs ${POSN[m.pos] || m.pos}: <b>${m.allowed} ${esc(m.stat)}/game</b> allowed · ranks ${ord(m.rank)} of ${m.of}</span>`;
}
let parlays = [], rec = null;
const HARDROCK = "https://www.hardrock.bet/", PRIZEPICKS = "https://app.prizepicks.com/";
function showView(){
  const v = (location.hash === "#penny-blocks" || location.hash === "#penalty-stocks") ? "penalty" : location.hash === "#daily-sheet" ? "sheet" : location.hash === "#blue-chips" ? "blue" : "board";
  [["board", "viewBoard", "tabBoard"], ["penalty", "viewPenalty", "tabPenalty"], ["blue", "viewBlue", "tabBlue"], ["sheet", "viewSheet", "tabSheet"]].forEach(([k, view, tab]) => {
    $(view).hidden = v !== k; $(view).style.display = v === k ? "grid" : "none";
    $(tab).setAttribute("aria-current", v === k ? "page" : "false");
  });
}
window.addEventListener("hashchange", showView);
// game lines: total and spread calls for a game
function glChips(ln){
  if (!ln) return "";
  const cls = c => c === "play" ? "u" : c === "lean" ? "y" : "d";
  const word = c => c === "play" ? "PLAY" : c === "lean" ? "LEAN" : "PASS";
  const out = [];
  const t = ln.total;
  if (t && t.side) {
    const sd = t.side === "under" ? "▼ UNDER" : "▲ OVER";
    out.push(`<span class="gl" title="Our power ratings: ${t.score ? `${t.score[0]}-${t.score[1]}, ` : ""}total ${t.expected} (${t.model}% over) · Vegas ${t.market}% over (cut removed) · blend ${Math.round(t.w * 100)}% ours / ${Math.round(100 - t.w * 100)}% Vegas · edge ${edgeTxt(t.edge)}">Total <b>${t.line}</b><i class="${cls(t.call)}${t.strong ? " st" : ""}">${word(t.call)} ${sd} ${t.chance}%</i>${t.strong ? "STRONG" : ""}</span>`);
  }
  const sp = ln.spread;
  if (sp && sp.side) out.push(`<span class="gl" title="Our power ratings: ${sp.score ? `${sp.score[0]}-${sp.score[1]}` : ""} (our line: away ${sp.ourLine > 0 ? "+" : ""}${sp.ourLine}) · Vegas ${sp.market}% away covers (cut removed) · blend ${Math.round(sp.w * 100)}% ours · edge ${edgeTxt(sp.edge)}">Spread <i class="${cls(sp.call)}${sp.strong ? " st" : ""}">${word(sp.call)} ${esc(sp.pick)} ${sp.chance}%</i>${sp.strong ? "STRONG" : ""}</span>`);
  return out.join("");
}
function pickText(par){
  return `Prop Exchange: ${par.league} ${par.stat} parlay (${par.american})\n` +
    par.legs.map(l => `${l.name} ${l.side === "under" ? "under" : "over"} ${l.line} ${par.stat === "Anytime TD" ? "(anytime TD)" : par.stat}`).join("\n");
}
async function copyPicks(btn, text){
  try { await navigator.clipboard.writeText(text); btn.textContent = "Copied"; }
  catch (e) {
    const ta = document.createElement("textarea"); ta.value = text; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    let ok = false; try { ok = document.execCommand("copy"); } catch (_) {}
    ta.remove(); btn.textContent = ok ? "Copied" : "Copy failed: select the picks above";
  }
  setTimeout(() => { btn.textContent = "Copy picks"; }, 2500);
}
let sheetData = null;
function renderSheet(){
  const el = $("sheet"), d = sheetData;
  if (!d) return;
  const games = (d.games || []).filter(g => league === "ALL" || g.lg === league);
  const day = new Date(d.date + "T12:00:00").toLocaleDateString([], {weekday: "long", month: "long", day: "numeric"});
  const row = (r, under) => `<li><b>${esc(r.n)}</b> ${esc(r.s)} <span class="u">${under ? "u" : "o"}${r.line} ${under ? "▼" : "▲"} ${r.ch ?? r.proj}%${r.edge != null ? ` (${edgeTxt(r.edge)})` : ""}${r.strong ? " ★" : ""}</span></li>`;
  el.innerHTML = `<div class="shead"><h2>Daily Sheet · ${esc(day)}</h2><span class="rstat">Updated ${esc(new Date(d.updatedAt).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"}))} · games still to start · <button type="button" class="bbtn ghost noprint" id="sheetPrint">Print / save PDF</button></span></div>
    <p class="pnote">Each game's total and spread call and its green plays, over and under. Each % is our chance of that side; (+n) is how many points it beats what the odds need (★ = +6 or more). Emailed every day.</p>
    ${games.length ? games.map(g => `<div class="sgame"><h3>${esc(g.game)}<small>${esc(g.lg)} · ${esc(when(g.start))}</small></h3>
      ${g.lines && (g.lines.total || g.lines.spread) ? `<div class="glines">${glChips(g.lines)}</div>` : ""}
      ${g.overs.length ? `<div><span class="slabel">Green overs</span><ul class="slist">${g.overs.map(r => row(r, false)).join("")}</ul></div>` : ""}
      ${g.unders.length ? `<div><span class="slabel">Green unders</span><ul class="slist">${g.unders.map(r => row(r, true)).join("")}</ul></div>` : ""}
      ${!g.overs.length && !g.unders.length ? `<p class="rstat" style="margin:4px 0 0">No props in this game beat their price by 3+ points.</p>` : ""}
    </div>`).join("") : `<div class="empty"><b>No games left today</b>Tomorrow's sheet fills in once Vegas posts the lines.</div>`}
    ${d.parlays?.length ? `<div class="sgame"><h3>Penny Blocks</h3><ul class="slist">${d.parlays.filter(p => league === "ALL" || p.league === league).map(p => `<li><b>${esc(p.league)} ${esc(p.stat)}</b> ${esc(p.american || "")}: ${p.legs.map(esc).join(", ")}</li>`).join("")}</ul></div>` : ""}`;
  const pb = $("sheetPrint"); if (pb) pb.addEventListener("click", () => window.print());
}
fetch("data/sheet.json?t=" + Date.now(), {cache: "no-store"}).then(r => r.ok ? r.json() : null).then(d => { sheetData = d; renderSheet(); }).catch(() => {});
let blueChips = [];
function blueText(c){
  return `Prop Exchange Blue Chips: ${c.league} ${c.stat} (${c.legs.length} legs${c.american ? ", " + c.american : ""})\n` +
    c.legs.map(l => `${l.name} over ${l.line} ${c.stat} (last game ${f1(l.last.v)})`).join("\n");
}
function renderBlue(){
  const el = $("bgrid"); if (!el) return;
  const list = blueChips.filter(c => league === "ALL" || c.league === league);
  const bc = rec?.bluechips, L = bc?.legs, W = bc?.week, P = bc?.parlays;
  const pc = (h, n) => n ? Math.round(100 * h / n) + "%" : "—";
  $("brecord").innerHTML = L && L.n
    ? `<span>Players this week <b>${W?.hit ?? 0} of ${W?.n ?? 0}</b> went over${W?.n ? ` · ${money(W.P)}` : ""}</span><span>All-time <b>${L.hit} of ${L.n}</b> (${pc(L.hit, L.n)}) · ${money(L.P)} betting $10 on each</span>${P?.n ? `<span>Full parlays <b>${P.won} of ${P.n}</b> hit · ${money(P.profit)}</span>` : ""}`
    : `<span>No Blue Chips graded yet. Each qualifier is saved before his game and graded after it.</span>`;
  if (!list.length) { el.innerHTML = `<div class="empty"><b>No Blue Chips right now</b>They fill in once Vegas posts props.</div>`; return; }
  el.innerHTML = list.map((c, i) => {
    const head = `<header><h3><small>${esc(c.league)} · ${esc(c.stat)} ${c.min}+ · ${c.legs.length} player${c.legs.length === 1 ? "" : "s"}</small>${esc(c.stat)}</h3>${c.american ? `<div class="pay"><b>${esc(c.american)}</b><small>all ${c.legs.length}: $10 pays $${(10 * c.dec).toFixed(0)}</small></div>` : ""}</header>`;
    if (!c.legs.length) return `<article class="pcard">${head}<p class="pnote" style="padding:12px 14px">Nobody with a ${c.min}+ line went over both his last line and today's line in his last game.</p></article>`;
    const legs = c.legs.map(l => `<li><span class="ln">${esc(l.name)}<span>${esc(l.team || "")}</span></span>
        <span class="lg">Over ${l.line} · last game <b>${f1(l.last.v)}</b> ${l.last.home ? "vs" : "@"} ${esc(l.last.opp)} (line ${l.last.line}) · ${esc(when(l.start))}</span>
        <span class="lp"><b>+${l.margin}</b><small>${esc(l.odds)}</small></span></li>`).join("");
    return `<article class="pcard">${head}<ul class="legs">${legs}</ul>
      <div class="pmath"><span>+ = how far last game cleared today's line</span></div>
      <div class="pbtns">
        <a class="hr" href="${HARDROCK}" target="_blank" rel="noopener">Hard Rock</a>
        <a class="pp" href="${PRIZEPICKS}" target="_blank" rel="noopener">PrizePicks</a>
        <button type="button" data-bcopy="${i}">Copy picks</button>
      </div></article>`;
  }).join("");
  el.querySelectorAll("[data-bcopy]").forEach(b => b.addEventListener("click", () => copyPicks(b, blueText(list[Number(b.dataset.bcopy)]))));
}
function renderPenalty(){
  const list = parlays.filter(p => league === "ALL" || p.league === league);
  const pr = rec?.parlays;
  $("precord").innerHTML = pr && pr.n
    ? `<span>This week <b>${pr.week?.won ?? 0} of ${pr.week?.n ?? 0} hit</b>${pr.week?.n ? ` · ${money(pr.week.profit)}` : ""}</span><span>All-time <b>${pr.won} of ${pr.n}</b> (${Math.round(100*pr.won/pr.n)}%)${pr.profit != null ? ` · ${money(pr.profit)} betting $10 on each` : ""}</span>${pr.pending ? `<span>${pr.pending} waiting on games</span>` : ""}<span class="precent">${(pr.recent||[]).slice(0,10).map(p => `<span class="${p.res === "won" ? "w" : p.res === "lost" ? "l" : ""}" title="${esc(p.d)}">${esc(p.lg)} ${esc(p.s)} ${p.res === "won" ? "✓ " + esc(p.american||"") : p.res === "lost" ? "✗" : "void"}</span>`).join("")}</span>`
    : `<span>No parlays graded yet. ${pr?.pending ? `<b>${pr.pending}</b> saved and waiting on their games.` : "Each parlay is saved before its first leg starts and graded after the games."}</span>`;
  if (!list.length) { $("pgrid").innerHTML = `<div class="empty"><b>No parlays right now</b>The next update builds new ones once Vegas posts props.</div>`; return; }
  $("pgrid").innerHTML = list.map((par, i) => {
    if (!par.legs.length) return `<article class="pcard"><header><h3><small>${esc(par.league)}</small>${esc(par.stat)}</h3></header><p class="pnote" style="padding:12px 14px">${esc(par.note || "No parlay today.")}</p></article>`;
    const legs = par.legs.map(l => `<li><span class="ln">${esc(l.name)}<span>${esc(l.team||"")}</span></span>
        <span class="lg">${par.stat === "Anytime TD" ? "Scores a TD" : `${l.side === "under" ? "Under" : "Over"} ${l.line} ${esc(par.stat)}`}${l.strong ? " · strong" : ""} · ${esc(l.game)} · ${esc(when(l.start))}</span>
        <span class="lp"><b${l.side === "under" ? ' style="background:var(--down);color:#1d0405"' : ""}>${l.side === "under" ? "▼" : "▲"} ${l.proj}%</b><small>${esc(l.odds)}</small></span></li>`).join("");
    return `<article class="pcard">
      <header><h3><small>${esc(par.league)} · ${par.legs.length} legs</small>${esc(par.stat)}</h3><div class="pay"><b>${esc(par.american)}</b><small>$10 pays $${(10*par.dec).toFixed(2)}</small></div></header>
      <ul class="legs">${legs}</ul>
      <div class="pmath"><span>Combined chance <b>${par.proj}%</b></span><span>Sportsbook implies <b>${par.implied}%</b></span>${par.low ? `<span>Low confidence: priced from Vegas alone</span>` : ""}</div>
      <div class="pbtns">
        <a class="hr" href="${HARDROCK}" target="_blank" rel="noopener">Hard Rock</a>
        <a class="pp" href="${PRIZEPICKS}" target="_blank" rel="noopener">PrizePicks</a>
        <button type="button" data-copy="${i}">Copy picks</button>
      </div></article>`;
  }).join("");
  $("pgrid").querySelectorAll("[data-copy]").forEach(b => b.addEventListener("click", () => copyPicks(b, pickText(list[Number(b.dataset.copy)]))));
}
const OUT = new Set(["Out", "Injured Reserve", "Doubtful", "Suspension"]);
const isOut = p => OUT.has(p.injury?.status);
function injTag(p){
  const j = p.injury; if (!j) return "";
  const out = OUT.has(j.status);
  const tip = [j.status, j.type, j.note, j.returns ? "Expected back " + fmtD(j.returns.slice(0,10)) : ""].filter(Boolean).join(" · ");
  return `<span class="inj ${out ? "o" : "q"}" title="${esc(tip)}">${out ? "" : ic("alert")}${esc(j.status.toUpperCase())}${j.type ? " · " + esc(j.type) : ""}</span>`;
}
const vsOpen = new Set();
const fmtD = d => new Date(d + "T12:00:00").toLocaleDateString([], {month:"short", day:"numeric", year:"numeric"});
function vsPanel(p){
  const v = p.vs;
  if (!v) return `<div class="vs"><p class="note">Past matchups are not available for this player.</p></div>`;
  if (!v.n) return `<div class="vs"><h4>Career vs ${esc(v.opp)}</h4><p class="note">No regular-season or playoff games against the ${esc(v.opp)} yet.</p></div>`;
  const first = v.games[v.games.length-1].d.slice(0,4);
  const rows = p.props.map(x => {
    const s = x.vs || {};
    if (!s.n) return `<tr><td>${esc(x.stat)}</td><td>${x.line}</td><td colspan="4" style="text-align:left;color:var(--muted)">No ${esc(x.stat)} recorded in past games vs this team</td></tr>`;
    const chips = (s.v||[]).map((val,i) => val == null ? "" : `<i class="${val > x.line ? "h" : "m"}" title="${esc(fmtD(v.games[i].d))}">${f1(val)}</i>`).join("");
    return `<tr><td>${esc(x.stat)}${s.hot ? ` <span class="hot" title="Over in 60%+ of 3+ games vs this team">${ic("flame")}</span>` : ""}</td><td>${x.line}</td><td>${s.n}</td><td class="chg ${s.hits/s.n >= .5 ? "u" : "d"}">${s.hits}/${s.n} · ${Math.round(100*s.hits/s.n)}%</td><td>${s.avg}</td><td><span class="vals">${chips}</span></td></tr>`;
  }).join("");
  const glist = v.games.slice(0, 12).map(g => `<span><b>${esc(fmtD(g.d))}</b> ${esc(g.a)} ${esc(g.o)} ${esc(g.r)}${g.p ? " (playoffs)" : ""}</span>`).join("");
  return `<div class="vs"><h4>Career vs ${esc(v.opp)}<small>${v.n} game${v.n>1?"s":""} since ${first}</small></h4>
    <div class="tbl"><table><thead><tr><th>Stat</th><th>Today's line</th><th>Games</th><th>Over</th><th>Avg</th><th>Each game (newest first)</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="glist">${glist}${v.n > 12 ? `<span>+ ${v.n-12} earlier</span>` : ""}</div>
    ${v.n < 3 ? `<p class="note">Only ${v.n} game${v.n>1?"s":""} against this team, so read these numbers loosely.</p>` : ""}
    <p class="note">For reference only. Not part of the Projected %.</p></div>`;
}
function keep(p){
  if (show === "play" && !isPlay(p)) return false;
  if (show === "hit" && !isPlay(p, "over")) return false;
  if (show === "miss" && !isPlay(p, "under")) return false;
  if (show === "lean" && p.call !== "lean") return false;
  if (show === "5" && p.hits !== 5) return false;
  if (show === "strong" && !p.strong) return false;
  if (show === "moved" && !p.move) return false;
  if (statF && p.stat !== statF) return false;
  return true;
}
const proj = x => x.proj ?? x.pct;
// the call box: green PLAY / yellow LEAN / red PASS on the better side (calib.py). proj = chance of the over.
function callBox(x){
  const st = x.strong ? ` class="st"` : "", tag = x.strong ? `<b class="stg">STRONG</b>` : "";
  const e = x.edge != null ? ` ${edgeTxt(x.edge)}` : "";
  if (x.call === "play") return `<td class="hit u"><span${st} title="Our chance of the ${x.side} beats what its odds need by${e} points">${sideTxt(x)} ${x.chance}%${tag}</span>`;
  if (x.call === "lean") return `<td class="hit y"><span title="Lean: the ${x.side} beats its price by${e} points (under 3)">◆ LEAN ${x.side === "under" ? "U" : "O"} ${x.chance}%</span>`;
  return `<td class="hit d"><span title="Neither side beats its price${x.edge != null ? ` (best: ${x.side}${e})` : ""}">✕ PASS · o ${proj(x)}%</span>`;
}
function moveTxt(x){
  const o = x.open; if (!o) return "";
  const t = o.t ? new Date(o.t).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"}) : "open";
  if (x.move) return `<small class="sub mv ${x.move > 0 ? "u" : "d"}" title="Opened at ${o.line} (${esc(t)}). A rising line usually means money on the over; a falling line, on the under.">${x.move > 0 ? "▲" : "▼"} ${Math.abs(x.move)} since ${esc(t)}</small>`;
  if (o.over && x.over && o.over !== x.over.odds) return `<small class="sub" title="Same line, new price since ${esc(t)}">o was ${esc(o.over)}</small>`;
  return "";
}
function oddsTxt(o){ return o ? `${o.line} ${o.odds}` : "—"; }

function render(){
  document.querySelectorAll("[data-lg]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.lg === league)));
  renderPenalty(); renderBlue(); renderSheet();
  const list = games.filter(g => league === "ALL" || g.league === league).sort((a,b) => (a.start||"").localeCompare(b.start||""));

  // stat options
  const stats = [...new Set(list.flatMap(g => g.players.flatMap(p => p.props.map(x => x.stat))))].sort();
  const cur = $("stat").value;
  $("stat").innerHTML = `<option value="">Every stat</option>` + stats.map(s => `<option${s===cur?" selected":""}>${esc(s)}</option>`).join("");
  if (cur && !stats.includes(cur)) statF = "";

  // status
  let all = list.flatMap(g => g.players.flatMap(p => p.props));
  const ups = all.filter(x => isPlay(x, "over")).length;
  if (run) {
    const upd = new Date(run.createdAt);
    const errs = Object.entries(run.leagues||{}).filter(([,v]) => v.error).map(([k]) => k);
    $("status").innerHTML = `<span>Updated <b>${esc(upd.toLocaleString([], {weekday:"short", hour:"numeric", minute:"2-digit"}))}</b></span>
      <span><b>${list.length}</b> games</span><span><b>${all.length}</b> props</span>
      <span class="u">▲ ${ups} green over</span><span class="u">▼ ${all.filter(x => isPlay(x, "under")).length} green under</span><span class="y">◆ ${all.filter(x => x.call === "lean").length} lean</span><span class="d">✕ ${all.filter(x => x.call === "pass").length} pass</span><span>${all.filter(x => x.strong).length} strong</span><span>${all.filter(x => x.move).length} lines moved</span>${all.some(x => x.call === "out") ? `<span>${all.filter(x => x.call === "out").length} out (injured)</span>` : ""}
      ${errs.length ? `<span class="d">${errs.join(", ")} lines could not be loaded on the last update</span>` : ""}`;
  }

  // tape: strongest plays
  const top = list.flatMap(g => g.players.flatMap(p => p.props.map(x => ({p, x})))).filter(o => isPlay(o.x))
    .sort((a,b) => (b.x.edge || 0) - (a.x.edge || 0)).slice(0, 24);
  const tapeItems = top.length ? top.map(({p,x}) =>
      `<span><b>${esc(p.name.toUpperCase())}</b> ${esc(x.stat)} ${x.side === "under" ? "u" : "o"}${x.line} <span class="u">${sideTxt(x)} ${x.chance}% (${edgeTxt(x.edge)})</span> season avg ${x.season?.avg ?? f1(x.avg)}</span>`).join("")
    : `<span>No green plays right now.</span>`;
  $("tape").innerHTML = tapeItems + tapeItems;

  const board = $("board");
  if (!run) return;
  if (!list.length) {
    board.innerHTML = `<div class="empty"><b>No ${league === "ALL" ? "" : league + " "}games on the board</b>The next daily update will add games once Vegas posts player props for them.</div>`;
    return;
  }
  let firstOpen = openState.size === 0;
  board.innerHTML = list.map((g, gi) => {
    const a = g.teams?.away || {}, h = g.teams?.home || {};
    const players = g.players.map(p => ({...p, props: p.props.filter(keep)}))
      .filter(p => p.props.length && (!q || p.name.toLowerCase().includes(q)) && (!special || (p.badges||[]).length));
    const kinds = g.players.flatMap(p => (p.badges||[]).map(bd => bd.kind));
    const iconTxt = Object.keys(KIND_ICON).map(k => [k, kinds.filter(x => x === k).length]).filter(([,n]) => n)
      .map(([k,n]) => `<span class="pill s" title="${n} player${n>1?"s":""}: ${KIND_LABEL[k]}">${ic(KIND_ICON[k])} ${n}</span>`).join("");
    const props = g.players.flatMap(p => p.props);
    const gu = props.filter(x => isPlay(x, "over")).length, gd = props.filter(x => isPlay(x, "under")).length;
    if (special && !players.length) return "";
    const key = g.league + g.id;
    const open = openState.has(key) || (firstOpen && gi === 0) || (q && players.length);
    if (firstOpen && gi === 0) openState.add(key);
    const spread = a.spread?.v ? `${esc(a.abbr || a.name)} ${esc(a.spread.v)}` : "";
    const rows = players.map(p => {
      const pu = p.props.filter(x => isPlay(x)).length;
      const vkey = g.league + g.id + "|" + p.name, vopen = vsOpen.has(vkey);
      const hot = p.props.some(x => x.vs?.hot);
      const out = isOut(p);
      return `<tr class="player${out ? " isout" : ""}"><td colspan="8"><button type="button" class="pbtn" data-vs="${esc(vkey)}" aria-expanded="${vopen}" title="Show career stats vs today's opponent"><span class="car">▶</span><span class="pn">${esc(p.name)}</span>${hot ? `<span class="hot" title="Usually goes over vs this team">${ic("flame")}</span>` : ""}</button><span class="tm">${esc(p.team||"")}</span>${injTag(p)}<span class="ps">${out ? "Not expected to play: no call" : `${pu} play · ${p.props.filter(x => x.call === "lean").length} lean · ${p.props.filter(x => x.call === "pass").length} pass`}</span>${(p.badges||[]).map(bd => `<span class="badge ${esc(bd.kind)}" title="${esc(bd.text)}">${ic(KIND_ICON[bd.kind])} ${esc(bd.text)}</span>`).join("")}${playerFlags(p)}${dvpLine(p)}</td></tr>
      <tr class="vsrow"${vopen ? "" : " hidden"}><td colspan="8">${vopen ? vsPanel(p) : ""}</td></tr>` +
      p.props.map(x => {
        const se = x.season || {};
        const cells = [...x.last5].reverse().map((v, i, arr) =>
          `<i class="${v.v > x.line ? "h" : "m"}${i===arr.length-1 ? " new" : ""}" title="${esc(v.date)} ${esc(v.atVs)} ${esc(v.opp)}">${f1(v.v)}</i>`).join("");
        if (x.call === "out") return `<tr class="q isout"><td class="stat">${esc(x.stat)}</td><td>${x.line}</td><td colspan="4" style="text-align:left;color:var(--muted)">No call while ${esc(p.injury?.status || "out")}</td><td></td><td class="hit o"><span>OUT</span></td></tr>`;
        const pk = g.league + g.id + "|" + p.name + "|" + x.stat, popen = propOpen.has(pk);
        return `<tr class="q"><td class="stat"><button type="button" class="sbtn" data-prop="${esc(pk)}" aria-expanded="${popen}" title="Chart, alt lines and splits"><span class="car">▸</span>${esc(x.stat)}</button></td><td data-label="Line">${x.line}${moveTxt(x)}</td><td><span class="l5">${cells}</span></td>
          <td data-label="Last 5 avg">${f1(x.avg)}<small class="sub">${x.hits}/5 · ${x.pct}%</small></td>
          <td data-label="Season avg" class="chg ${se.avg > x.line ? "u" : "d"}">${se.avg ?? "—"}<small class="sub">${se.n ? `${se.hits}/${se.n} · ${se.pct}%` : "no games yet"}</small></td>
          <td data-label="Vegas" class="odds">${x.vegas != null ? x.vegas + "%" : "—"}<small class="sub">o ${esc(oddsTxt(x.over))}</small></td>
          ${callBox(x)}${x.low ? `<small class="sub" title="Anytime TD is priced from Vegas alone: the board's form numbers ran far too high on touchdowns.">Low confidence</small>`
            : x.form != null ? `<small class="sub" title="Chance of the over ${x.proj}% · Vegas ${nvig(x) ?? "—"}% (cut removed) · Form ${x.form}% (base ${x.projBase}%${nudgeTxt(x) ? ", nudged by: " + nudgeTxt(x) : ""}). Tap the stat for details.">${x.edge != null ? `Edge ${edgeTxt(x.edge)}${x[x.side]?.odds ? ` @ ${esc(x[x.side].odds)}` : ""} · ` : ""}Form ${x.form}%</small>` : ""}</td></tr>
          <tr class="prow"${popen ? "" : " hidden"}><td colspan="8">${popen ? chartPanel(p, x, pk) : ""}</td></tr>`;
      }).join("");
    }).join("");
    return `<details class="game" data-key="${esc(key)}"${open ? " open" : ""}>
      <summary>
        <span class="caret">▶</span>
        <span class="gname">${esc(a.name)}<em>@</em>${esc(h.name)}</span>
        <span class="gcount">${iconTxt}<span class="pill u" title="Green overs">▲ ${gu}</span><span class="pill u" title="Green unders">▼ ${gd}</span><span class="pill y" title="Leans">◆ ${props.filter(x => x.call === "lean").length}</span></span>
        <span class="gmeta"><span><b>${esc(g.league)}</b></span><span>${esc(when(g.start))}</span>
          ${spread ? `<span>Spread <b>${spread}</b></span>` : ""}
          ${a.total?.v ? `<span>Total <b>${esc(a.total.v.replace(/^o/,""))}</b></span>` : ""}
          ${a.ml?.v || a.ml?.odds ? `<span>ML <b>${esc(a.abbr||a.name)} ${esc(a.ml.v||a.ml.odds)} / ${esc(h.abbr||h.name)} ${esc(h.ml?.v||h.ml?.odds||"")}</b></span>` : ""}
        </span>
        ${g.lines ? `<span class="glines">${glChips(g.lines)}</span>` : ""}
      </summary>
      <div class="tbl">${rows ? `<table><thead><tr><th>Player / Stat</th><th>Line</th><th>Last 5 (old → new)</th><th>Last 5 avg</th><th>Season avg</th><th>Vegas %</th><th>Call</th></tr></thead><tbody>${rows}</tbody></table>`
        : `<div class="empty" style="margin:12px;border-color:var(--grid)">No props in this game match your filters.</div>`}</div>
    </details>`;
  }).join("");
  board.querySelectorAll(".pbtn").forEach(b => b.addEventListener("click", () => {
    const key = b.dataset.vs, row = b.closest("tr").nextElementSibling, open = !vsOpen.has(key);
    open ? vsOpen.add(key) : vsOpen.delete(key);
    b.setAttribute("aria-expanded", String(open));
    if (open) {
      const cut = key.indexOf("|"), gk = key.slice(0, cut), name = key.slice(cut + 1);
      const gm = games.find(x => x.league + x.id === gk), pl = gm?.players.find(x => x.name === name);
      row.firstElementChild.innerHTML = pl ? vsPanel(pl) : "";
    }
    row.hidden = !open;
  }));
  const findProp = k => {
    const [gk, name, stat] = k.split("|");
    const gm = games.find(x => x.league + x.id === gk), pl = gm?.players.find(x => x.name === name);
    return pl ? [pl, pl.props.find(x => x.stat === stat)] : [];
  };
  board.querySelectorAll(".sbtn").forEach(b => b.addEventListener("click", () => {
    const k = b.dataset.prop, row = b.closest("tr").nextElementSibling, open = !propOpen.has(k);
    open ? propOpen.add(k) : propOpen.delete(k);
    b.setAttribute("aria-expanded", String(open));
    if (open) { const [pl, x] = findProp(k); row.firstElementChild.innerHTML = pl && x ? chartPanel(pl, x, k) : ""; }
    row.hidden = !open;
  }));
  if (!board.dataset.sampleBound) board.dataset.sampleBound = "1", board.addEventListener("click", e => {
    const sb = e.target.closest("[data-sample]"); if (!sb) return;
    const row = sb.closest("tr.prow"), k = row?.previousElementSibling?.querySelector(".sbtn")?.dataset.prop; if (!k) return;
    propSample[k] = sb.dataset.sample;
    const [pl, x] = findProp(k); if (pl && x) row.firstElementChild.innerHTML = chartPanel(pl, x, k);
  });
  board.querySelectorAll("details.game").forEach(d => d.addEventListener("toggle", () => {
    d.open ? openState.add(d.dataset.key) : openState.delete(d.dataset.key);
  }));
}

const pctTxt = (h, n) => n ? Math.round(100 * h / n) + "%" : "—";
// profit on $10 bets: green, or red with a minus sign
const money = v => v == null ? "" : `<b class="${v >= 0 ? "u" : "d"}">${v >= 0 ? "+" : "−"}$${Math.abs(v).toFixed(2)}</b>`;
const pl = (b, k) => b && b[k + "B"] ? ` · ${money(b[k + "P"])}` : "";
const plT = (b, k) => b && b[k + "B"] ? `<div class="rstat">${money(b[k + "P"])}</div>` : "";  // in tables: own line
function introWeek(r){
  const el = $("introWeek"); if (!el || !r) return;
  const w = r.week || {}, pc = (h, n) => n ? Math.round(100 * h / n) + "%" : "—";
  el.innerHTML = (w.gN || w.lN) ? `This week: green plays <b>${pc(w.gHit, w.gN)}</b> right${w.gB ? ` (${money(w.gP)})` : ""} · leans <b>${pc(w.lHit, w.lN)}</b>${w.sN ? ` · strong <b>${pc(w.sHit, w.sN)}</b>` : ""}`
    : "This week's results show up after the first games are graded.";
}
{
  const lg = $("legend");
  if (lg) lg.innerHTML = Object.keys(KIND_ICON).map(k => `<span class="badge ${k}">${ic(KIND_ICON[k])} ${KIND_LABEL[k]}</span>`).join("") +
    `<span class="flag">${ic("moon")}Back-to-back</span><span class="flag">${ic("clock")}Minutes trend</span><span class="flag">${ic("cross")}Teammate out</span><span class="flag"><span class="hot">${ic("flame")}</span>Hot vs this team</span>`;
  const fb = $("filtBtn");
  if (fb) fb.addEventListener("click", () => { const t = document.querySelector("header.top"); const on = t.classList.toggle("showfilt"); fb.setAttribute("aria-expanded", String(on)); });
}
function renderRecord(r){
  introWeek(r);
  const sum = document.querySelector("#record .rstat"), body = $("recordBody");
  const t = r.total || {}, v1 = r.v1 || {}, v3 = r.v3 || {}, md = r.model;
  const v3P = (v3.gP || 0) + (v3.rP || 0);
  const old = `${v3.gN || v3.rN ? `<p class="rnote"><b>Previous version (Nov 12–26, form-based 58/46 cutoffs):</b> green overs hit ${pctTxt(v3.gHit, v3.gN)} (${v3.gHit}/${v3.gN}), yellow leans went over ${pctTxt(v3.lHit || 0, v3.lN || 0)}, red unders went under ${pctTxt(v3.rHit, v3.rN)} (${v3.rHit}/${v3.rN}). Betting $10 on every green and red call: ${money(v3P)}. Retired Nov 27: its percentages were far too confident (a 73% over went over about 52% of the time).</p>` : ""}${v1.gN || v1.rN ? `<p class="rnote"><b>Earlier versions (Nov 6–12):</b> green calls hit ${pctTxt(v1.gHit, v1.gN)} (${v1.gHit}/${v1.gN}), red calls went under ${pctTxt(v1.rHit, v1.rN)} (${v1.rHit}/${v1.rN}).</p>` : ""}`;
  const mt = md?.props_note?.test;
  const modelTxt = md ? `<p class="rnote"><b>The model:</b> refit ${md.fitted ? esc(fmtD(md.fitted)) : "—"} on ${(md.props_note?.n || 0).toLocaleString()} graded props from ${md.window ? `${esc(fmtD(md.window[0]))} to ${esc(fmtD(md.window[1]))}` : "the last 14 days"}. Weights now: ${["NBA", "NFL"].filter(k => md.props?.[k]).map(k => `${k} Vegas ×${md.props[k].vegas}, Form ×${md.props[k].form}`).join(" · ")}${["NBA", "NFL"].some(k => md.props?.[k]?.form === 0) ? " (a Form weight of 0 means form and the nudges have not added anything beyond the Vegas price lately, so they count for nothing until they do)" : ""}.${mt ? ` Honesty check on the newest 7 days (error score, lower is better): model ${mt.model}, Vegas alone ${mt.vegas}, coin flip ${mt.coinflip}.` : ""} Game lines blend our power ratings with Vegas at ${Object.entries(md.games || {}).map(([k, v]) => `${esc(k.replace("|", " "))} ${Math.round(v * 100)}%`).join(", ")}.</p>` : "";
  if (!t.gN && !t.lN) {
    sum.innerHTML = `New model (Nov 27): no graded games yet. ${r.pending ? `<b>${r.pending}</b> calls are waiting for their games to finish.` : ""}`;
    body.innerHTML = `<p class="rnote">Every call is saved just before its game starts and graded against the player's final stat once the game is over: a green or yellow call wins when its side (over or under) comes in. Pushes and players who did not play are left out.</p>${modelTxt}${old}`;
    return;
  }
  const w = r.week || {}, cls = (h, n) => n && h / n >= .524 ? "u" : "d";
  const wkLabel = d => "Week of " + new Date(d + "T12:00:00").toLocaleDateString([], {month: "short", day: "numeric"});
  const tot = b => ({n: (b.gN||0) + (b.lN||0), h: (b.gHit||0) + (b.lHit||0), P: (b.gP||0) + (b.lP||0), B: (b.gB||0) + (b.lB||0)});
  const chip = (label, b, k, N, H) => b[N] ? `<span>${label} <b class="${cls(b[H], b[N])}">${pctTxt(b[H], b[N])}</b> (${b[H]}/${b[N]})${pl(b, k)}</span>` : "";
  const at = tot(t);
  sum.innerHTML = `<span class="rtitle" style="font-size:13px">This week</span>
    ${w.gN || w.lN ? `${chip("Green", w, "g", "gN", "gHit")}${chip("Lean", w, "l", "lN", "lHit")}${chip("Strong", w, "s", "sN", "sHit")}`
      : `<span>No graded games yet this week (starts Monday).</span>`}
    <span style="opacity:.8">All-time green: ${pctTxt(t.gHit || 0, t.gN || 0)} (${t.gHit || 0}/${t.gN || 0})${t.gB ? ` · ${money(t.gP)}` : ""}</span>`;
  const cell = (b, k) => `${pctTxt(b[k + "Hit"] || 0, b[k + "N"] || 0)} <span class="rstat">(${b[k + "Hit"] || 0}/${b[k + "N"] || 0})</span>${plT(b, k)}`;
  const wkRow = b => { const x = tot(b); return `<tr><td>${esc(wkLabel(b.w))}${b.w === r.weekStart ? " <span class=\"rstat\">(now)</span>" : ""}</td><td>${cell(b, "g")}</td><td>${cell(b, "l")}</td><td>${cell(b, "s")}</td><td>${x.B ? money(x.P) : "—"}</td></tr>`; };
  const wk = (r.weeks || []).map(wkRow).join("");
  const allRow = `<tr><td><b>All-time</b></td><td>${cell(t, "g")}</td><td>${cell(t, "l")}</td><td>${cell(t, "s")}</td><td>${at.B ? money(at.P) : "—"}</td></tr>`;
  const lg = Object.entries(r.byLeague || {}).map(([k,v]) => `<tr><td>${esc(k)}</td><td>${cell(v, "g")}</td><td>${cell(v, "l")}</td></tr>`).join("");
  const bk = Object.entries(r.buckets || {}).filter(([,v]) => v.n).map(([k,v]) => {
    const pc = Math.round(100*v.over/v.n);
    return `<tr><td>${esc(k)}%</td><td>${v.n}</td><td>${pc}% <span class="rbar" style="width:${Math.max(2, pc*0.8)}px"></span></td></tr>`;
  }).join("");
  const st = Object.entries(r.byStat || {}).map(([k,v]) => [k, v.gN || 0, v.gHit || 0]).filter(([,n]) => n >= 5)
    .sort((a,b) => b[1] - a[1]).slice(0, 12).map(([k,n,h]) => `<tr><td>${esc(k)}</td><td>${n}</td><td class="chg ${h/n >= .524 ? "u" : "d"}">${pctTxt(h,n)}</td></tr>`).join("");
  const dy = (r.days || []).slice(-10).reverse().map(d => `<tr><td>${esc(fmtD(d.d))}</td><td>${cell(d, "g")}</td><td>${cell(d, "l")}</td></tr>`).join("");
  const gby = r.games?.by || {}, gold = r.games?.old || {};
  const gl = ["Total", "Spread"].flatMap(m => Object.entries(gby[m] || {}).map(([c, v]) =>
    `<tr><td>${m} · ${c === "play" ? "green" : c === "lean" ? "yellow" : "red (pass)"}</td><td>${v.hit}/${v.n} · ${pctTxt(v.hit, v.n)}</td><td>${v.B ? money(v.P) : "—"}</td></tr>`)).join("") +
    ["Total", "Spread"].filter(m => gold[m]).map(m => `<tr><td class="rstat">${m} · old version</td><td class="rstat">${gold[m].hit}/${gold[m].n} · ${pctTxt(gold[m].hit, gold[m].n)}</td><td class="rstat">${gold[m].B ? money(gold[m].P) : "—"}</td></tr>`).join("");
  const lt = r.latest ? r.latest.picks.slice(0, 40).map(p => {
    const right = p.r === p.side;
    return `<tr><td>${esc(p.n)} <span class="rstat">${esc(p.gl)}</span></td><td>${esc(p.s)} ${p.side === "under" ? "u" : "o"}${p.line}${p.strong ? " ★" : ""}</td><td>${p.ch ?? "—"}% (${edgeTxt(p.edge)})</td><td class="chg ${right ? "u" : "d"}">${p.a} ${right ? "✓" : "✗"}</td></tr>`;
  }).join("") : "";
  body.innerHTML = `<div class="rbody">
    <div class="wide"><h5>Week by week (Monday to Sunday)</h5><div class="tbl"><table><thead><tr><th>Week</th><th>Green plays</th><th>Yellow leans</th><th>Strong (+6)</th><th>Green + lean $</th></tr></thead><tbody>${wk}${allRow}</tbody></table></div></div>
    <div><h5>By league (all-time)</h5><table><thead><tr><th>League</th><th>Green plays</th><th>Leans</th></tr></thead><tbody>${lg}</tbody></table></div>
    <div><h5>Does the projection hold up?</h5><table><thead><tr><th>Chance of over</th><th>Props</th><th>Actually went over</th></tr></thead><tbody>${bk}</tbody></table><p class="rstat" style="margin:6px 0 0">If the projection is honest, each row's real rate lands inside its range.</p></div>
    <div><h5>By day</h5><table><thead><tr><th>Day</th><th>Green plays</th><th>Leans</th></tr></thead><tbody>${dy}</tbody></table></div>
    ${st ? `<div><h5>Green plays by stat (5+)</h5><table><thead><tr><th>Stat</th><th>Plays</th><th>Right</th></tr></thead><tbody>${st}</tbody></table></div>` : ""}
    ${gl ? `<div><h5>Game lines (all-time)</h5><table><thead><tr><th>Call</th><th>Right</th><th>$10 each</th></tr></thead><tbody>${gl}</tbody></table></div>` : ""}
    ${lt ? `<div class="wide"><h5>Latest results: green plays from ${esc(fmtD(r.latest.d))}</h5><div class="tbl"><table><thead><tr><th>Player</th><th>Call</th><th>Chance (edge)</th><th>Final</th></tr></thead><tbody>${lt}</tbody></table></div></div>` : ""}
  </div><p class="rnote">Calls are saved just before each game starts and graded against ESPN's final stats. A call is right when its side (over or under) comes in. Each week runs Monday to Sunday by the game's Eastern date and starts fresh; past weeks stay in the table and in the all-time totals. Pushes and players who did not play are not counted, and red passes are not bets. <b>Dollar amounts</b> are the profit or loss from betting $10 on every call at the best price when it was saved (a win pays the odds, a loss costs $10). At standard −110 odds you need to win 52.4% just to break even, so green below that loses money. ★ = strong (+6 or more). ${r.pending ? `${r.pending} calls still waiting on their games.` : ""}</p>${modelTxt}${old}`;
}
fetch("data/record.json?t=" + Date.now(), {cache: "no-store"}).then(r => r.ok ? r.json() : null).then(r => {
  if (r) { rec = r; renderRecord(r); renderPenalty(); renderBlue(); } else document.querySelector("#record .rstat").textContent = "Results will appear after the first games are graded.";
}).catch(() => { document.querySelector("#record .rstat").textContent = "Results could not be loaded."; });

showView();
(async () => {
  try {
    const res = await fetch("data/board.json?t=" + Date.now(), {cache: "no-store"});
    if (!res.ok) throw new Error(res.status);
    const b = await res.json();
    run = {run: b.run, createdAt: b.createdAt, leagues: b.leagues};
    games = b.games || [];
    parlays = b.parlays || [];
    blueChips = b.bluechips || [];
    render();
  } catch (e) {
    $("status").innerHTML = `<span class="d">The board data could not be loaded. Refresh the page to try again.</span>`;
    $("board").innerHTML = `<div class="empty"><b>No board yet</b>Today's data has not been published. Check back after the daily update.</div>`;
  }
})();
