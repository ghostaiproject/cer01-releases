# Live data for the CER-01 app + site: Ghostskills skills/log + unit cards (units.json) with each repo's
# current version and status. Runs in sync.yml (every 30 min, on dispatch). Writes data.json only when it changed.
# Private repos (Grocerierun...) need the GHOST_SYNC_TOKEN secret; without it their last known values are kept.
import json, os, re, urllib.request, datetime
from pathlib import Path

R = Path(__file__).resolve().parent.parent
TOKEN = os.environ.get("GH_TOKEN", "")
API = "https://api.github.com/"
GS = "https://raw.githubusercontent.com/ghostaiproject/Ghostskills/main/site/data.json"


def get(url, raw=False):
    req = urllib.request.Request(url if url.startswith("http") else API + url,
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "cer01-sync",
                                          **({"Authorization": "Bearer " + TOKEN} if TOKEN and not raw else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print("skip", url, type(e).__name__, getattr(e, "code", ""))
        return None


def versions(repo):
    out, seen = [], set()
    for page in (1, 2, 3):
        rows = get(f"repos/{repo}/commits?per_page=100&page={page}") or []
        for c in rows:
            m = re.search(r"\b(\d+\.\d+\.\d+)\b", c["commit"]["message"].split("\n")[0])
            if m and m.group(1) not in seen:
                seen.add(m.group(1)); out.append(["v" + m.group(1), c["commit"]["committer"]["date"][:10]])
        if len(rows) < 100:
            break
    out.sort(key=lambda v: [int(n) for n in v[0][1:].split(".")], reverse=True)
    return out[:60]


def main():
    old = json.loads((R / "data.json").read_text(encoding="utf-8")) if (R / "data.json").exists() else {}
    cards = json.loads((R / "units.json").read_text(encoding="utf-8"))["units"]
    oldu = {u["id"]: u for u in old.get("units", [])}
    data = dict(old)
    gs = get(GS, raw=True)
    if gs:
        for k in ("branch", "sha", "dirty", "skills", "log", "rev"):
            if k in gs:
                data[k] = gs[k]
    uver = dict(old.get("uver", {}))
    units = []
    for c in cards:
        u = dict(c); repo = u.get("repo"); auto = u.pop("auto", {}) or {}
        prev = oldu.get(u["id"], {})
        for k in ("ver", "st", "ok", "upd"):     # last known live values stay when a repo can't be read
            if k in prev and prev.get("live"):
                u[k] = prev[k]
        if repo:
            last = get(f"repos/{repo}/commits?per_page=1")
            if last:
                u["upd"] = last[0]["commit"]["committer"]["date"][:10]; u["live"] = True
                if auto.get("ver") == "sha":
                    u["ver"] = "main · " + last[0]["sha"][:7]
            if auto.get("ver") == "release":
                rel = get(f"repos/{repo}/releases/latest")
                if rel and rel.get("tag_name"):
                    u["ver"] = rel["tag_name"]; uver[u["id"]] = rel["tag_name"]
            if auto.get("ver") == "versions":
                vs = versions(repo)
                if vs:
                    data["versions"] = vs; u["ver"] = vs[0][0]; uver[u["id"]] = vs[0][0]
            if auto.get("run"):
                runs = (get(f"repos/{repo}/actions/runs?per_page=10") or {}).get("workflow_runs", [])
                runs = [r for r in runs if auto["run"] == "*" or r["name"] == auto["run"]]
                if runs:
                    r = runs[0]
                    if r["status"] == "waiting":
                        u["st"], u["ok"] = "needs approval", False
                    elif r["status"] == "completed" and r["conclusion"] == "failure":
                        u["st"], u["ok"] = "build failed", False
                    elif r["status"] == "completed" and r["conclusion"] == "success":
                        u["st"], u["ok"] = c.get("st", "build ok"), True
                    u["live"] = True
        units.append(u)
    data["units"] = units
    data["uver"] = uver
    same = {k: v for k, v in data.items() if k != "at"} == {k: v for k, v in old.items() if k != "at"}
    if same:
        print("no change"); return
    data["at"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (R / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    print("data.json:", len(units), "units,", len(data.get("skills", [])), "skills, uver", uver)


if __name__ == "__main__":
    main()
