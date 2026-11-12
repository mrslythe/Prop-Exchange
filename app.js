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
const POSN = {QB: "QBs", RB: "RBs", WR: "WRs", TE: "TEs"};
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
  const v = (location.hash === "#penny-blocks" || location.hash === "#penalty-stocks") ? "penalty" : location.hash === "#daily-sheet" ? "sheet" : "board";
  [["board", "viewBoard", "tabBoard"], ["penalty", "viewPenalty", "tabPenalty"], ["sheet", "viewSheet", "tabSheet"]].forEach(([k, view, tab]) => {
    $(view).hidden = v !== k; $(view).style.display = v === k ? "grid" : "none";
    $(tab).setAttribute("aria-current", v === k ? "page" : "false");
  });
}
window.addEventListener("hashchange", showView);
// game lines: total and spread calls for a game
function glChips(ln){
  if (!ln) return "";
  const cls = c => c === "hit" ? "u" : c === "lean" ? "y" : "d";
  const out = [];
  const t = ln.total;
  if (t) {
    const word = t.call === "hit" ? "▲ OVER" : t.call === "lean" ? "◆ LEAN" : "▼ UNDER";
    out.push(`<span class="gl" title="Form ${t.form}% · Vegas ${t.vegas ?? "—"}% · season game totals avg ${t.awayAvg} / ${t.homeAvg} · expected ${t.expected}">Total <b>${t.line}</b><i class="${cls(t.call)}${t.strong ? " st" : ""}">${word} ${t.proj}%</i>${t.strong ? "STRONG" : ""}</span>`);
  }
  const sp = ln.spread;
  if (sp) out.push(`<span class="gl" title="Form ${sp.form}% (away covers ${sp.awayCover}% · home fails ${sp.homeFail}%) · Vegas ${sp.vegas ?? "—"}%">Spread <b>${esc(sp.pick)}</b><i class="${cls(sp.call)}${sp.strong ? " st" : ""}">${sp.call === "hit" ? "▲" : "◆"} ${sp.chance}%</i>${sp.strong ? "STRONG" : ""}</span>`);
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
  const row = (r, under) => `<li><b>${esc(r.n)}</b> ${esc(r.s)} <span class="${under ? "d" : "u"}">${under ? "u" : "o"}${r.line} ${under ? "▼" : "▲"} ${r.proj}%${r.strong ? " ★" : ""}</span></li>`;
  el.innerHTML = `<div class="shead"><h2>Daily Sheet · ${esc(day)}</h2><span class="rstat">Updated ${esc(new Date(d.updatedAt).toLocaleTimeString([], {hour: "numeric", minute: "2-digit"}))} · games still to start · <button type="button" class="bbtn ghost noprint" id="sheetPrint">Print / save PDF</button></span></div>
    <p class="pnote">Each game's total and spread call, its green OVER calls, and its strong UNDER calls (★ = strong). Projected % is the chance of the over. Emailed every day.</p>
    ${games.length ? games.map(g => `<div class="sgame"><h3>${esc(g.game)}<small>${esc(g.lg)} · ${esc(when(g.start))}</small></h3>
      ${g.lines && (g.lines.total || g.lines.spread) ? `<div class="glines">${glChips(g.lines)}</div>` : ""}
      ${g.overs.length ? `<div><span class="slabel">Overs (green)</span><ul class="slist">${g.overs.map(r => row(r, false)).join("")}</ul></div>` : ""}
      ${g.unders.length ? `<div><span class="slabel">Strong unders</span><ul class="slist">${g.unders.map(r => row(r, true)).join("")}</ul></div>` : ""}
    </div>`).join("") : `<div class="empty"><b>No games left today</b>Tomorrow's sheet fills in once Vegas posts the lines.</div>`}
    ${d.parlays?.length ? `<div class="sgame"><h3>Penny Blocks</h3><ul class="slist">${d.parlays.filter(p => league === "ALL" || p.league === league).map(p => `<li><b>${esc(p.league)} ${esc(p.stat)}</b> ${esc(p.american || "")}: ${p.legs.map(esc).join(", ")}</li>`).join("")}</ul></div>` : ""}`;
  const pb = $("sheetPrint"); if (pb) pb.addEventListener("click", () => window.print());
}
fetch("data/sheet.json?t=" + Date.now(), {cache: "no-store"}).then(r => r.ok ? r.json() : null).then(d => { sheetData = d; renderSheet(); }).catch(() => {});
function renderPenalty(){
  const list = parlays.filter(p => league === "ALL" || p.league === league);
  const pr = rec?.parlays;
  $("precord").innerHTML = pr && pr.n
    ? `<span>Parlay record <b>${pr.won} of ${pr.n} hit</b> (${Math.round(100*pr.won/pr.n)}%)${pr.profit != null ? ` · ${money(pr.profit)} betting $10 on each` : ""}</span>${pr.pending ? `<span>${pr.pending} waiting on games</span>` : ""}<span class="precent">${(pr.recent||[]).slice(0,10).map(p => `<span class="${p.res === "won" ? "w" : p.res === "lost" ? "l" : ""}" title="${esc(p.d)}">${esc(p.lg)} ${esc(p.s)} ${p.res === "won" ? "✓ " + esc(p.american||"") : p.res === "lost" ? "✗" : "void"}</span>`).join("")}</span>`
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
  return `<span class="inj ${out ? "o" : "q"}" title="${esc(tip)}">${out ? "" : "⚠️ "}${esc(j.status.toUpperCase())}${j.type ? " · " + esc(j.type) : ""}</span>`;
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
    return `<tr><td>${esc(x.stat)}${s.hot ? " 🔥" : ""}</td><td>${x.line}</td><td>${s.n}</td><td class="chg ${s.hits/s.n >= .5 ? "u" : "d"}">${s.hits}/${s.n} · ${Math.round(100*s.hits/s.n)}%</td><td>${s.avg}</td><td><span class="vals">${chips}</span></td></tr>`;
  }).join("");
  const glist = v.games.slice(0, 12).map(g => `<span><b>${esc(fmtD(g.d))}</b> ${esc(g.a)} ${esc(g.o)} ${esc(g.r)}${g.p ? " (playoffs)" : ""}</span>`).join("");
  return `<div class="vs"><h4>Career vs ${esc(v.opp)}<small>${v.n} game${v.n>1?"s":""} since ${first}</small></h4>
    <div class="tbl"><table><thead><tr><th>Stat</th><th>Today's line</th><th>Games</th><th>Over</th><th>Avg</th><th>Each game (newest first)</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="glist">${glist}${v.n > 12 ? `<span>+ ${v.n-12} earlier</span>` : ""}</div>
    ${v.n < 3 ? `<p class="note">Only ${v.n} game${v.n>1?"s":""} against this team, so read these numbers loosely.</p>` : ""}
    <p class="note">For reference only. Not part of the Projected %.</p></div>`;
}
function keep(p){
  if (show === "hit" && p.call !== "hit") return false;
  if (show === "miss" && p.call !== "miss") return false;
  if (show === "lean" && p.call !== "lean") return false;
  if (show === "5" && p.hits !== 5) return false;
  if (show === "strong" && !p.strong) return false;
  if (show === "moved" && !p.move) return false;
  if (statF && p.stat !== statF) return false;
  return true;
}
const proj = x => x.proj ?? x.pct;
// the call box: green OVER, yellow LEAN, red UNDER (thresholds in calib.py). proj = Projected % (the over).
function callBox(x){
  const st = x.strong ? ` class="st"` : "", tag = x.strong ? `<b class="stg">STRONG</b>` : "";
  if (x.call === "hit") return `<td class="hit u"><span${st}>▲ OVER ${proj(x)}%${tag}</span>`;
  if (x.call === "lean") return `<td class="hit y"><span title="Lean: 46-57%">◆ LEAN ${proj(x)}%</span>`;
  return `<td class="hit d"><span${st}>▼ UNDER ${proj(x)}%${tag}</span>`;
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
  renderPenalty(); renderSheet();
  const list = games.filter(g => league === "ALL" || g.league === league).sort((a,b) => (a.start||"").localeCompare(b.start||""));

  // stat options
  const stats = [...new Set(list.flatMap(g => g.players.flatMap(p => p.props.map(x => x.stat))))].sort();
  const cur = $("stat").value;
  $("stat").innerHTML = `<option value="">Every stat</option>` + stats.map(s => `<option${s===cur?" selected":""}>${esc(s)}</option>`).join("");
  if (cur && !stats.includes(cur)) statF = "";

  // status
  let all = list.flatMap(g => g.players.flatMap(p => p.props));
  const ups = all.filter(x => x.call === "hit").length;
  if (run) {
    const upd = new Date(run.createdAt);
    const errs = Object.entries(run.leagues||{}).filter(([,v]) => v.error).map(([k]) => k);
    $("status").innerHTML = `<span>Updated <b>${esc(upd.toLocaleString([], {weekday:"short", hour:"numeric", minute:"2-digit"}))}</b></span>
      <span><b>${list.length}</b> games</span><span><b>${all.length}</b> props</span>
      <span class="u">▲ ${ups} over</span><span class="d">▼ ${all.filter(x => x.call === "miss").length} under</span><span class="y">◆ ${all.filter(x => x.call === "lean").length} lean</span><span>${all.filter(x => x.strong).length} strong</span><span>${all.filter(x => x.move).length} lines moved</span>${all.some(x => x.call === "out") ? `<span>${all.filter(x => x.call === "out").length} out (injured)</span>` : ""}
      ${errs.length ? `<span class="d">${errs.join(", ")} lines could not be loaded on the last update</span>` : ""}`;
  }

  // tape: strongest plays
  const top = list.flatMap(g => g.players.flatMap(p => p.props.map(x => ({p, x})))).filter(o => o.x.strong)
    .sort((a,b) => (b.x.call === "hit") - (a.x.call === "hit") || Math.abs(proj(b.x) - 50) - Math.abs(proj(a.x) - 50)).slice(0, 24);
  const tapeItems = top.length ? top.map(({p,x}) => x.call === "hit"
      ? `<span><b>${esc(p.name.toUpperCase())}</b> ${esc(x.stat)} o${x.line} <span class="u">▲ OVER ${proj(x)}%</span> season avg ${x.season?.avg ?? f1(x.avg)}</span>`
      : `<span><b>${esc(p.name.toUpperCase())}</b> ${esc(x.stat)} u${x.line} <span class="d">▼ UNDER ${proj(x)}%</span> season avg ${x.season?.avg ?? f1(x.avg)}</span>`).join("")
    : `<span>No strong calls right now.</span>`;
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
    const icons = g.players.flatMap(p => (p.badges||[]).map(bd => bd.icon));
    const iconTxt = ["🎂","😤","🏠","📍"].map(i => [i, icons.filter(x => x === i).length]).filter(([,n]) => n)
      .map(([i,n]) => `<span class="pill s" title="${n} player${n>1?"s":""}">${i} ${n}</span>`).join("");
    const props = g.players.flatMap(p => p.props);
    const gu = props.filter(x => x.call === "hit").length;
    if (special && !players.length) return "";
    const key = g.league + g.id;
    const open = openState.has(key) || (firstOpen && gi === 0) || (q && players.length);
    if (firstOpen && gi === 0) openState.add(key);
    const spread = a.spread?.v ? `${esc(a.abbr || a.name)} ${esc(a.spread.v)}` : "";
    const rows = players.map(p => {
      const pu = p.props.filter(x => x.call === "hit").length;
      const vkey = g.league + g.id + "|" + p.name, vopen = vsOpen.has(vkey);
      const hot = p.props.some(x => x.vs?.hot);
      const out = isOut(p);
      return `<tr class="player${out ? " isout" : ""}"><td colspan="8"><button type="button" class="pbtn" data-vs="${esc(vkey)}" aria-expanded="${vopen}" title="Show career stats vs today's opponent"><span class="car">▶</span><span class="pn">${esc(p.name)}</span>${hot ? `<span title="Usually goes over vs this team">🔥</span>` : ""}</button><span class="tm">${esc(p.team||"")}</span>${injTag(p)}<span class="ps">${out ? "Not expected to play: no call" : `${pu} over · ${p.props.filter(x => x.call === "lean").length} lean · ${p.props.filter(x => x.call === "miss").length} under`}</span>${(p.badges||[]).map(bd => `<span class="badge ${esc(bd.kind)}" title="${esc(bd.text)}"><span aria-hidden="true">${bd.icon}</span> ${esc(bd.text)}</span>`).join("")}${dvpLine(p)}</td></tr>
      <tr class="vsrow"${vopen ? "" : " hidden"}><td colspan="8">${vopen ? vsPanel(p) : ""}</td></tr>` +
      p.props.map(x => {
        const se = x.season || {};
        const cells = [...x.last5].reverse().map((v, i, arr) =>
          `<i class="${v.v > x.line ? "h" : "m"}${i===arr.length-1 ? " new" : ""}" title="${esc(v.date)} ${esc(v.atVs)} ${esc(v.opp)}">${f1(v.v)}</i>`).join("");
        if (x.call === "out") return `<tr class="q isout"><td class="stat">${esc(x.stat)}</td><td>${x.line}</td><td colspan="4" style="text-align:left;color:var(--muted)">No call while ${esc(p.injury?.status || "out")}</td><td></td><td class="hit o"><span>OUT</span></td></tr>`;
        return `<tr class="q"><td class="stat">${esc(x.stat)}</td><td>${x.line}${moveTxt(x)}</td><td><span class="l5">${cells}</span></td>
          <td>${f1(x.avg)}<small class="sub">${x.hits}/5 · ${x.pct}%</small></td>
          <td class="chg ${se.avg > x.line ? "u" : "d"}">${se.avg ?? "—"}<small class="sub">${se.n ? `${se.hits}/${se.n} · ${se.pct}%` : "no games yet"}</small></td>
          <td class="odds">${x.vegas != null ? x.vegas + "%" : "—"}<small class="sub">o ${esc(oddsTxt(x.over))}</small></td>
          ${callBox(x)}${x.low ? `<small class="sub" title="Anytime TD is priced from Vegas alone: the board's form numbers ran far too high on touchdowns.">Low confidence</small>`
            : x.form != null ? `<small class="sub" title="Form = 60% season + 40% last-5 hit rate${x.matchup ? `, with the matchup nudge (${x.projBase}% before it; opponent ranks ${ord(x.matchup.rank)} toughest, ${x.matchup.allowed}/game vs ${x.matchup.avg} average)` : ""}.">Form ${x.form}%${x.matchup?.nudge ? ` (${x.matchup.nudge > 0 ? "+" : ""}${x.matchup.nudge} matchup)` : ""}</small>` : ""}</td></tr>`;
      }).join("");
    }).join("");
    return `<details class="game" data-key="${esc(key)}"${open ? " open" : ""}>
      <summary>
        <span class="caret">▶</span>
        <span class="gname">${esc(a.name)}<em>@</em>${esc(h.name)}</span>
        <span class="gcount">${iconTxt}<span class="pill u">▲ ${gu}</span><span class="pill y">◆ ${props.filter(x => x.call === "lean").length}</span><span class="pill d">▼ ${props.filter(x => x.call === "miss").length}</span></span>
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
  board.querySelectorAll("details.game").forEach(d => d.addEventListener("toggle", () => {
    d.open ? openState.add(d.dataset.key) : openState.delete(d.dataset.key);
  }));
}

const pctTxt = (h, n) => n ? Math.round(100 * h / n) + "%" : "—";
// profit on $10 bets: green, or red with a minus sign
const money = v => v == null ? "" : `<b class="${v >= 0 ? "u" : "d"}">${v >= 0 ? "+" : "−"}$${Math.abs(v).toFixed(2)}</b>`;
const pl = (b, k) => b && b[k + "B"] ? ` · ${money(b[k + "P"])}` : "";
const plT = (b, k) => b && b[k + "B"] ? `<div class="rstat">${money(b[k + "P"])}</div>` : "";  // in tables: own line
function renderRecord(r){
  const sum = document.querySelector("#record .rstat"), body = $("recordBody");
  const t = r.total || {}, v1 = r.v1 || {};
  const old = v1.gN || v1.rN ? `<p class="rnote"><b>Earlier versions (Nov 6–12):</b> green calls hit ${pctTxt(v1.gHit, v1.gN)} (${v1.gHit}/${v1.gN}), red calls went under ${pctTxt(v1.rHit, v1.rN)} (${v1.rHit}/${v1.rN}). The track record above counts the current version (green 58%+, yellow 46–57%, red 45% or less) from Nov 12 on.</p>` : "";
  if (!t.gN && !t.rN) {
    sum.innerHTML = `Current version: no graded games yet. ${r.pending ? `<b>${r.pending}</b> calls are waiting for their games to finish.` : ""}`;
    body.innerHTML = `<p class="rnote">Every call is saved just before its game starts and graded against the player's final stat once the game is over. Pushes and players who did not play are left out. Results show up here after the first games finish.</p>${old}`;
    return;
  }
  const w = r.week || {}, cls = (h, n) => n && h / n >= .5 ? "u" : "d";
  const wp = (w.gP || 0) + (w.rP || 0), wb = (w.gB || 0) + (w.rB || 0);
  sum.innerHTML = `<span>Over calls hit <b class="${cls(t.gHit, t.gN)}">${pctTxt(t.gHit, t.gN)}</b> (${t.gHit}/${t.gN})${pl(t, "g")}</span>
    ${t.lN ? `<span>Leans went over <b class="${cls(t.lHit, t.lN)}">${pctTxt(t.lHit, t.lN)}</b> (${t.lHit}/${t.lN})${pl(t, "l")}</span>` : ""}
    <span>Under calls hit <b class="${cls(t.rHit, t.rN)}">${pctTxt(t.rHit, t.rN)}</b> (${t.rHit}/${t.rN})${pl(t, "r")}</span>
    ${t.sN ? `<span>Strong calls <b class="${cls(t.sHit, t.sN)}">${pctTxt(t.sHit, t.sN)}</b> (${t.sHit}/${t.sN})${pl(t, "s")}</span>` : ""}
    <span>Last 7 days <b>${pctTxt((w.gHit||0) + (w.rHit||0), (w.gN||0) + (w.rN||0))}</b>${wb ? ` · ${money(wp)}` : ""}</span>`;
  const lg = Object.entries(r.byLeague || {}).map(([k,v]) => `<tr><td>${esc(k)}</td><td>${pctTxt(v.gHit,v.gN)} <span class="rstat">(${v.gHit}/${v.gN})</span>${plT(v, "g")}</td><td>${pctTxt(v.rHit,v.rN)} <span class="rstat">(${v.rHit}/${v.rN})</span>${plT(v, "r")}</td></tr>`).join("");
  const bk = Object.entries(r.buckets || {}).filter(([,v]) => v.n).map(([k,v]) => {
    const pc = Math.round(100*v.over/v.n);
    return `<tr><td>${esc(k)}%</td><td>${v.n}</td><td>${pc}% <span class="rbar" style="width:${Math.max(2, pc*0.8)}px"></span></td></tr>`;
  }).join("");
  const st = Object.entries(r.byStat || {}).map(([k,v]) => [k, v.gN + v.rN, v.gHit + v.rHit]).filter(([,n]) => n >= 5)
    .sort((a,b) => b[1] - a[1]).slice(0, 12).map(([k,n,h]) => `<tr><td>${esc(k)}</td><td>${n}</td><td class="chg ${h/n >= .55 ? "u" : "d"}">${pctTxt(h,n)}</td></tr>`).join("");
  const dy = (r.days || []).slice(-10).reverse().map(d => `<tr><td>${esc(fmtD(d.d))}</td><td>${pctTxt(d.gHit,d.gN)} <span class="rstat">(${d.gHit}/${d.gN})</span>${plT(d, "g")}</td><td>${pctTxt(d.rHit,d.rN)} <span class="rstat">(${d.rHit}/${d.rN})</span>${plT(d, "r")}</td></tr>`).join("");
  const gby = r.games?.by || {};
  const gl = ["Total", "Spread"].flatMap(m => Object.entries(gby[m] || {}).map(([c, v]) =>
    `<tr><td>${m} · ${c === "hit" ? "green" : c === "lean" ? "yellow" : "red"}</td><td>${v.hit}/${v.n} · ${pctTxt(v.hit, v.n)}</td><td>${v.B ? money(v.P) : "—"}</td></tr>`)).join("");
  const lt = r.latest ? r.latest.picks.slice(0, 40).map(p => {
    const ov = p.call !== "miss", right = p.r === (ov ? "over" : "under");
    return `<tr><td>${esc(p.n)} <span class="rstat">${esc(p.gl)}</span></td><td>${esc(p.s)} ${ov ? "o" : "u"}${p.line}${p.strong ? " ★" : ""}</td><td>${p.proj}%</td><td class="chg ${right ? "u" : "d"}">${p.a} ${right ? "✓" : "✗"}</td></tr>`;
  }).join("") : "";
  body.innerHTML = `<div class="rbody">
    <div><h5>By league</h5><table><thead><tr><th>League</th><th>Over calls</th><th>Under calls</th></tr></thead><tbody>${lg}</tbody></table></div>
    <div><h5>Does the projection hold up?</h5><table><thead><tr><th>Projected</th><th>Props</th><th>Actually went over</th></tr></thead><tbody>${bk}</tbody></table><p class="rstat" style="margin:6px 0 0">If the projection is honest, each row's real rate lands inside its range.</p></div>
    <div><h5>By day</h5><table><thead><tr><th>Day</th><th>Over calls</th><th>Under calls</th></tr></thead><tbody>${dy}</tbody></table></div>
    ${st ? `<div><h5>Calls by stat (5+ calls)</h5><table><thead><tr><th>Stat</th><th>Calls</th><th>Right</th></tr></thead><tbody>${st}</tbody></table></div>` : ""}
    ${gl ? `<div><h5>Game lines (totals and spreads)</h5><table><thead><tr><th>Call</th><th>Right</th><th>$10 each</th></tr></thead><tbody>${gl}</tbody></table></div>` : ""}
    ${lt ? `<div class="wide"><h5>Latest results: calls from ${esc(fmtD(r.latest.d))}</h5><div class="tbl"><table><thead><tr><th>Player</th><th>Call</th><th>Projected</th><th>Final</th></tr></thead><tbody>${lt}</tbody></table></div></div>` : ""}
  </div><p class="rnote">Calls are saved just before each game starts and graded against ESPN's final stats. Pushes and players who did not play are not counted. Over and Under counts are green and red calls; yellow leans are counted separately. <b>Dollar amounts</b> are the profit or loss from betting $10 on every call at the best price when it was saved (a win pays the odds, a loss costs $10). At standard −110 odds you need to win 52.4% just to break even. Red anytime-TD calls are left out: there is no "no TD" bet on the board. ★ = strong call. ${r.pending ? `${r.pending} calls still waiting on their games.` : ""}</p>${old}`;
}
fetch("data/record.json?t=" + Date.now(), {cache: "no-store"}).then(r => r.ok ? r.json() : null).then(r => {
  if (r) { rec = r; renderRecord(r); renderPenalty(); } else document.querySelector("#record .rstat").textContent = "Results will appear after the first games are graded.";
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
    render();
  } catch (e) {
    $("status").innerHTML = `<span class="d">The board data could not be loaded. Refresh the page to try again.</span>`;
    $("board").innerHTML = `<div class="empty"><b>No board yet</b>Today's data has not been published. Check back after the daily update.</div>`;
  }
})();
