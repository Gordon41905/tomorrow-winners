#!/usr/bin/env python3
"""Archive completed NFL weeks from ESPN (never overwrite existing week files).
Usage: archive_nfl_weeks.py nfl <outdir> <first_week> <last_week>
Example: archive_nfl_weeks.py nfl archive/nfl 1 18
Also supports: archive_nfl_weeks.py nba <outdir> <YYYY-MM-DD first> <YYYY-MM-DD last>
Existing files are never overwritten (history is append-only)."""
import json, sys, os, subprocess, datetime
def get(u):
    return json.loads(subprocess.run(["curl","-s","--max-time","30",u],capture_output=True,text=True).stdout)
def trim(e, odds=None):
    c=e["competitions"][0]; st=e["status"]
    ev={"id":e["id"],"date":e["date"],"shortName":e.get("shortName",""),
        "status":{"period":st.get("period"),"displayClock":st.get("displayClock",""),
                  "type":{k:st["type"].get(k) for k in ("state","completed","shortDetail","detail","name")}},
        "competitions":[{"neutralSite":c.get("neutralSite",False),"venue":{"fullName":(c.get("venue") or {}).get("fullName","")},
            "competitors":[{"homeAway":x["homeAway"],"score":x.get("score"),"winner":x.get("winner",False),
                "team":{k:x["team"].get(k) for k in ("id","displayName","shortDisplayName","abbreviation")}} for x in c.get("competitors",[])]}]}
    if odds: ev["odds"]=odds
    return ev
def nfl_odds(eid, home, away):
    try:
        d=get(f"https://sports.core.api.espn.com/v2/sports/football/leagues/nfl/events/{eid}/competitions/{eid}/odds")
        it=[x for x in d.get("items",[]) if x.get("details") or x.get("overUnder") is not None]
        x=next((x for x in it if str(x["provider"]["id"])=="100"), it[0] if it else None)
        if not x: return None
        o={"src":x["provider"].get("name","ESPN"),"close":{"d":x.get("details") or "","ou":x.get("overUnder")}}
        try:
            hs=float(x["homeTeamOdds"]["open"]["pointSpread"]["american"])
            sp="Even" if hs==0 else (f"{home} {hs:g}" if hs<0 else f"{away} -{hs:g}")
        except Exception: sp=""
        try: ot=float(x["open"]["total"]["american"])
        except Exception: ot=None
        if sp or ot is not None: o["open"]={"d":sp,"ou":ot}
        return o
    except Exception: return None
def write(path, obj):
    if os.path.exists(path): print("keep", path); return False
    json.dump(obj, open(path,"w"), separators=(",",":")); print("wrote", path); return True
def index(outdir):
    files=sorted(f for f in os.listdir(outdir) if f.endswith(".json") and f!="index.json")
    out=[]
    for f in files:
        j=json.load(open(os.path.join(outdir,f)))
        out.append({k:j.get(k) for k in ("file","week","label","detail","date","games")})
    json.dump({"updated":datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p PT"),"items":out}, open(os.path.join(outdir,"index.json"),"w"), indent=1)
mode,outdir,a,b=sys.argv[1:5]; os.makedirs(outdir,exist_ok=True)
if mode=="nfl":
    cal={}
    sb0=get("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard")
    for blk in sb0["leagues"][0].get("calendar",[]):
        if str(blk.get("value"))=="2":
            for en in blk.get("entries",[]): cal[int(en["value"])]=en
    for w in range(int(a),int(b)+1):
        fn=f"2026-wk{w:02d}.json"; p=os.path.join(outdir,fn)
        if os.path.exists(p): print("keep",p); continue
        sb=get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard?seasontype=2&week={w}&dates=2026")
        evs=sb.get("events",[])
        if not evs or not all(e["status"]["type"].get("completed") for e in evs): print("week",w,"not complete; skip"); continue
        out=[]
        for e in evs:
            c=e["competitions"][0]["competitors"]; h=next(x for x in c if x["homeAway"]=="home"); aw=next(x for x in c if x["homeAway"]=="away")
            out.append(trim(e, nfl_odds(e["id"], h["team"]["abbreviation"], aw["team"]["abbreviation"])))
        en=cal.get(w,{})
        write(p,{"file":fn,"league":"NFL","season":2026,"week":w,"label":en.get("label",f"Week {w}"),"detail":en.get("detail",""),"games":len(out),
                 "source":"ESPN scoreboard seasontype=2&week=%d&dates=2026; lines DraftKings via ESPN core odds"%w,"events":out})
    index(outdir)
elif mode=="nba":
    d=datetime.date.fromisoformat(a); last=datetime.date.fromisoformat(b)
    while d<=last:
        fn=f"{d.isoformat()}.json"; p=os.path.join(outdir,fn)
        if not os.path.exists(p):
            sb=get(f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={d.strftime('%Y%m%d')}")
            evs=sb.get("events",[])
            if all(e["status"]["type"].get("completed") or "POSTPONED" in (e["status"]["type"].get("name") or "") for e in evs):
                write(p,{"file":fn,"league":"NBA","season":"2026-27","date":d.isoformat(),"label":d.strftime("%a %b ")+str(d.day),"games":len(evs),
                         "source":"ESPN scoreboard dates=%s"%d.strftime('%Y%m%d'),"events":[trim(e) for e in evs]})
            else: print(d,"not complete; skip")
        else: print("keep",p)
        d+=datetime.timedelta(days=1)
    index(outdir)
