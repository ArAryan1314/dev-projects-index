"""
Index of projects from YouTube coding creators that have a WORKING live demo.

Steps (progress is printed for each):
  1. CREATORS - checks each GitHub account in CREATORS exists (unknown ones are skipped).
  2. FETCH    - lists each creator's public repos (core API, not the search API).
  3. FILTER   - keeps repos that are not forks/archived, were active within
                MAX_AGE_DAYS, and have a demo URL set (the repo "homepage").
  4. LIVE     - opens every demo URL; keeps only ones answering HTTP < 400.
  5. WRITE    - CREATORS.md + data/creators.json + data/creators.csv.

License note: many tutorial repos have no license. That means "all rights
reserved" - fine to study and learn from, but ask the author before reusing
the code in your own product. Those rows are flagged.

Usage: python scripts/build_creators.py
"""

from __future__ import annotations

import csv
import json
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_AGE_DAYS = 365 * 3
MIN_STARS = 5

# GitHub account -> channel name / focus. Accounts that don't exist are skipped.
CREATORS: dict[str, str] = {
    "adrianhajdin": "JavaScript Mastery (Next.js, React, full-stack)",
    "bradtraversy": "Traversy Media (web dev, full-stack)",
    "AntonioErdeljac": "Code With Antonio (Next.js SaaS clones)",
    "sonnysangha": "Sonny Sangha (Next.js, AI apps)",
    "joschan21": "Josh tried coding (Next.js)",
    "safak": "Lama Dev (React, Next.js, MERN)",
    "burakorkmez": "As a Programmer (MERN, Next.js)",
    "ed-roh": "EdRoh (full-stack dashboards)",
    "jherr": "Jack Herrington (React, Next.js)",
    "leerob": "Lee Robinson (Next.js)",
    "WebDevSimplified": "Web Dev Simplified (frontend)",
    "john-smilga": "Coding Addict (React projects)",
    "florinpop17": "Florin Pop (frontend projects)",
    "codewithsadee": "codewithsadee (HTML/CSS/JS sites)",
    "codebucks27": "CodeBucks (React, Next.js UI)",
    "kevin-powell": "Kevin Powell (CSS)",
    "iamshaunjp": "Net Ninja (frontend + backend)",
    "gitdagray": "Dave Gray (JS, React, Next.js)",
    "piyushgarg-dev": "Piyush Garg (Node, backend)",
    "hiteshchoudhary": "Hitesh Choudhary (JS, backend)",
    "CodeWithHarry": "CodeWithHarry (web, Python)",
    "fireship-io": "Fireship (web, quick builds)",
    "midudev": "midudev (JS, Next.js)",
    "FaztWeb": "Fazt (full-stack)",
    "CodingGarden": "Coding Garden (full-stack)",
    "freeCodeCamp": "freeCodeCamp (courses)",
    "techwithtim": "Tech With Tim (Python)",
    "patrickloeber": "Patrick Loeber / Python Engineer (Python, ML)",
    "KeithGalli": "Keith Galli (Python, data)",
    "CoreyMSchafer": "Corey Schafer (Python, Django, Flask)",
    "ArjanCodes": "ArjanCodes (Python design)",
    "amigoscode": "Amigoscode (backend)",
    "kentcdodds": "Kent C. Dodds (React)",
    "t3-oss": "Theo / t3.gg (Next.js T3 stack)",
}


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def gh_json(path: str):
    res = subprocess.run(["gh", "api", path], capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        return None
    return json.loads(res.stdout)


def is_live(url: str) -> tuple[str, bool]:
    if not url.startswith("http"):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (link-check)"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return url, r.status < 400
    except urllib.error.HTTPError as e:
        # 401/403 still means a live site that blocks bots
        return url, e.code in (401, 403)
    except Exception:
        return url, False


def main() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    candidates: list[dict] = []

    for handle, channel in CREATORS.items():
        user = gh_json(f"users/{handle}")
        if not user:
            log(f"skip {handle}: account not found")
            continue
        kind = "orgs" if user.get("type") == "Organization" else "users"
        repos = []
        for page in (1, 2, 3):
            batch = gh_json(f"{kind}/{handle}/repos?per_page=100&type=owner&sort=pushed&page={page}")
            if not batch:
                break
            repos += batch
        kept = 0
        for r in repos:
            if r.get("fork") or r.get("archived") or not (r.get("homepage") or "").strip():
                continue
            if r.get("stargazers_count", 0) < MIN_STARS:
                continue
            if datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) < cutoff:
                continue
            lic = (r.get("license") or {}).get("spdx_id")
            candidates.append({
                "creator": channel,
                "name": r["full_name"],
                "url": r["html_url"],
                "demo": r["homepage"].strip(),
                "description": (r.get("description") or "").strip(),
                "language": r.get("language") or "",
                "topics": r.get("topics") or [],
                "stars": r.get("stargazers_count", 0),
                "license": lic if lic and lic != "NOASSERTION" else "none (learn only)",
                "last_push": r["pushed_at"][:10],
            })
            kept += 1
        log(f"{handle}: {len(repos)} repos, {kept} with a demo link")

    log(f"Checking {len(candidates)} demo links (live test) ...")
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(lambda c: is_live(c["demo"]), candidates))
    live = []
    for c, (url, ok) in zip(candidates, results):
        if ok:
            c["demo"] = url
            live.append(c)
    log(f"{len(live)} of {len(candidates)} demos are live")

    live.sort(key=lambda p: (p["creator"], -p["stars"]))
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "creators.json").write_text(json.dumps(live, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(ROOT / "data" / "creators.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[k for k in live[0] if k != "topics"] + ["stack"], extrasaction="ignore")
        w.writeheader()
        for p in live:
            w.writerow({**p, "stack": ", ".join(p["topics"])})

    def esc(s: str) -> str:
        return s.replace("|", "\\|").replace("\n", " ")[:140]

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# Projects from YouTube Coding Creators: Live Demos",
        "",
        f"**{len(live)} projects** from popular coding YouTubers whose live demo answered a check on {today}.",
        "Each links to the original repo and its creator.",
        "",
        "> **License column:** `none (learn only)` means the author published no license. "
        "Study it freely, but ask the author before reusing the code in your own product.",
        "",
        "| Creator | Project | Live demo | Stack | ⭐ | License |",
        "|---|---|---|---|---|---|",
    ]
    for p in live:
        stack = ", ".join(([p["language"]] if p["language"] else []) + p["topics"][:4])
        lines.append(f"| {esc(p['creator'])} | [{p['name']}]({p['url']})<br><sub>{esc(p['description'])}</sub> | "
                     f"[demo]({p['demo']}) | {esc(stack)} | {p['stars']:,} | {p['license']} |")
    (ROOT / "CREATORS.md").write_text("\n".join(lines), encoding="utf-8")
    log("Wrote CREATORS.md, data/creators.json, data/creators.csv")


if __name__ == "__main__":
    main()
