"""Builds the Daily Sheet email from data/sheet.json: python3 tools/email_sheet.py sheet.json out.json
-> {subject, html, text}. Used by the daily email scheduled task."""
import json, html, datetime as dt, sys
from zoneinfo import ZoneInfo
ET = ZoneInfo("America/New_York")
d = json.load(open(sys.argv[1]))
e = html.escape
col = {"hit": ("OVER", "#16a34a"), "lean": ("LEAN", "#b45309"), "miss": ("UNDER", "#dc2626")}
day = dt.date.fromisoformat(d["date"])
subj = f"Prop Exchange Daily Sheet: {day.strftime('%A, %B')} {day.day}"
H, T = [], []
n = len(d["games"])
H.append(f'<div style="font-family:Arial,sans-serif;max-width:640px;color:#111"><h2 style="margin:0 0 4px">Prop Exchange Daily Sheet</h2><p style="margin:0 0 14px;color:#555">{n} games today · <a href="{e(d["site"])}">Open the Daily Sheet</a></p>')
T.append(f"Prop Exchange Daily Sheet - {n} games today\n{d['site']}\n")
for g in d["games"]:
    t = dt.datetime.fromisoformat(g["start"].replace("Z", "+00:00")).astimezone(ET).strftime("%a %-I:%M %p ET")
    H.append(f'<h3 style="margin:16px 0 4px;border-top:1px solid #ddd;padding-top:10px">{e(g["game"])} <span style="font-weight:normal;color:#666;font-size:13px">{e(g["lg"])} · {t}</span></h3>')
    T.append(f"\n{g['game']} ({g['lg']}, {t})")
    ln = g.get("lines") or {}
    parts, tparts = [], []
    if ln.get("total"):
        x = ln["total"]; w, c = col[x["call"]]
        st = " STRONG" if x.get("strong") else ""
        parts.append(f'Total {x["line"]:g}: <b style="color:{c}">{w} {x["proj"]}%{st}</b>')
        tparts.append(f"Total {x['line']:g}: {w} {x['proj']}%{st}")
    if ln.get("spread"):
        x = ln["spread"]; c = col[x["call"]][1]
        st = " STRONG" if x.get("strong") else ""
        parts.append(f'Spread: <b style="color:{c}">{e(x["pick"])} {x["chance"]}%{st}</b>')
        tparts.append(f"Spread: {x['pick']} {x['chance']}%{st}")
    if parts:
        H.append(f'<p style="margin:2px 0">{" &nbsp;·&nbsp; ".join(parts)}</p>'); T.append("  " + " | ".join(tparts))
    for key, label, pre, c, cap in (("overs", "Overs", "o", "#16a34a", 12), ("unders", "Strong unders", "u", "#dc2626", 8)):
        rows = g.get(key) or []
        if rows:
            items = ", ".join(f'{e(r["n"])} {e(r["s"])} <span style="color:{c}">{pre}{r["line"]:g} {r["proj"]}%{" ★" if r.get("strong") else ""}</span>' for r in rows[:cap])
            more = f" <span style='color:#888'>+{len(rows) - cap} more</span>" if len(rows) > cap else ""
            H.append(f'<p style="margin:4px 0;font-size:14px"><b>{label}:</b> {items}{more}</p>')
            T.append(f"  {label}: " + ", ".join(f"{r['n']} {r['s']} {pre}{r['line']:g} {r['proj']}%{' *' if r.get('strong') else ''}" for r in rows[:cap]))
if d.get("parlays"):
    H.append('<h3 style="margin:16px 0 4px;border-top:1px solid #ddd;padding-top:10px">Penny Blocks</h3>')
    T.append("\nPenny Blocks")
    for p in d["parlays"]:
        H.append(f'<p style="margin:2px 0;font-size:14px"><b>{e(p["league"])} {e(p["stat"])}</b> {e(p.get("american") or "")}: {e(", ".join(p["legs"]))}</p>')
        T.append(f"  {p['league']} {p['stat']} {p.get('american') or ''}: {', '.join(p['legs'])}")
foot = "Projected % is the chance of the over, from each player's season and last 5 games plus a little of the Vegas price. For entertainment; bet responsibly."
H.append(f'<p style="margin:18px 0 0;color:#777;font-size:12px">{foot}</p></div>'); T.append("\n" + foot)
json.dump({"subject": subj, "html": "".join(H), "text": "\n".join(T)}, open(sys.argv[2], "w"))
print(subj, len("".join(H)))
