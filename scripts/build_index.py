"""
Build a curated index of free & open-source projects from GitHub.

How it works (each step prints progress so you can watch it):
  1. SEARCH   - runs GitHub search queries per category (Next.js, Bun, Python,
                frontend, backend, learning roadmaps).
  2. CHECK    - keeps only repos that pass upfront checks:
                  * has an OSI-style license (not missing / NOASSERTION)
                  * not archived, not a fork, not disabled
                  * pushed to within the last MAX_AGE_DAYS
                  * has a description and at least MIN_STARS stars
  3. CLASSIFY - assigns a level (beginner / intermediate / advanced) and a
                size (small / medium / large) using simple, documented rules.
  4. WRITE    - writes README.md, data/projects.json and data/projects.csv.

Nothing is copied: the index only links to the original projects and
credits their owners and licenses.

Requires the GitHub CLI (`gh`) to be installed and logged in, or a
GH_TOKEN / GITHUB_TOKEN env var (used automatically by `gh`).
Usage:  python scripts/build_index.py [--target 1000]
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_AGE_DAYS = 730
MIN_STARS = 20
BAD_LICENSES = {None, "", "NOASSERTION", "other"}

# category -> list of GitHub search queries.
# Queries mix "learning" style keywords with "real project" keywords so each
# category gets a spread across levels.
CATEGORIES: dict[str, list[str]] = {
    "Next.js": [
        "topic:nextjs topic:starter",
        "topic:nextjs topic:template",
        "topic:nextjs topic:tutorial",
        "topic:nextjs topic:saas",
        "topic:nextjs topic:ecommerce",
        "topic:nextjs topic:blog",
        "topic:nextjs topic:dashboard",
        "nextjs app router example",
    ],
    "Bun": [
        "topic:bun",
        "topic:bunjs",
        "topic:elysia",
        "topic:hono topic:bun",
        "bun runtime starter",
    ],
    "Python": [
        "topic:python topic:beginner-project",
        "topic:python-projects",
        "topic:python topic:automation",
        "topic:python topic:cli",
        "topic:python topic:machine-learning topic:tutorial",
        "python projects for beginners",
    ],
    "Frontend": [
        "topic:react topic:project",
        "topic:react topic:beginner",
        "topic:vue topic:project",
        "topic:svelte topic:app",
        "topic:frontend-projects",
        "topic:javascript-projects",
        "topic:tailwindcss topic:template",
        "topic:react topic:portfolio",
        "topic:nuxt topic:template",
        "topic:angular topic:example",
        "topic:frontend topic:ui",
        "topic:shadcn-ui",
        "topic:astro topic:template",
    ],
    "Backend": [
        "topic:fastapi",
        "topic:django topic:project",
        "topic:flask topic:project",
        "topic:express topic:rest-api",
        "topic:nestjs topic:boilerplate",
        "topic:backend topic:api",
        "topic:microservices topic:example",
    ],
    "Full-stack": [
        "topic:fullstack topic:nextjs",
        "topic:mern-stack",
        "topic:t3-stack",
        "topic:fullstack topic:fastapi",
        "topic:full-stack topic:project",
        "topic:fullstack topic:typescript",
        "topic:prisma topic:nextjs",
        "topic:supabase topic:nextjs",
        "topic:django topic:react",
        "topic:pern-stack",
        "topic:realworld",
    ],
    "Learning & Roadmaps": [
        "topic:roadmap topic:developer",
        "topic:learning-path",
        "topic:awesome-list topic:learning",
        "topic:coding-interview",
        "topic:project-based-learning",
        "topic:100-days-of-code",
        "topic:free-programming-books",
        "topic:tutorial topic:web-development",
        "topic:roadmap topic:learning",
        "topic:interview-questions",
        "topic:awesome topic:python",
        "topic:awesome topic:javascript",
        "topic:education topic:programming",
        "topic:cheatsheet",
        "topic:system-design",
    ],
}

BEGINNER_WORDS = ("beginner", "tutorial", "learn", "course", "100-days",
                  "exercise", "practice", "basics", "for-beginners", "simple")
ADVANCED_WORDS = ("microservice", "production", "enterprise", "saas",
                  "distributed", "kubernetes", "monorepo", "scalable", "framework")


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def gh_search(query: str, page: int) -> list[dict]:
    """Call the GitHub search API through the gh CLI, retrying on rate limits."""
    cmd = [
        "gh", "api", "-X", "GET", "search/repositories",
        "-f", f"q={query} fork:false archived:false stars:>={MIN_STARS}",
        "-f", "sort=stars", "-f", "order=desc",
        "-f", "per_page=100", "-f", f"page={page}",
    ]
    for attempt in range(5):
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if res.returncode == 0:
            return json.loads(res.stdout).get("items", [])
        err = res.stderr.lower()
        if "rate limit" in err or "403" in err or "secondary" in err:
            wait = 30 * (attempt + 1)
            log(f"   rate-limited, waiting {wait}s ...")
            time.sleep(wait)
            continue
        log(f"   search failed: {res.stderr.strip()[:200]}")
        return []
    return []


def passes_checks(r: dict, cutoff: datetime) -> tuple[bool, str]:
    lic = (r.get("license") or {}).get("spdx_id")
    if lic in BAD_LICENSES:
        return False, "no clear open-source license"
    if r.get("archived") or r.get("disabled") or r.get("fork"):
        return False, "archived/disabled/fork"
    if not r.get("description"):
        return False, "no description"
    pushed = datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00"))
    if pushed < cutoff:
        return False, "inactive"
    return True, ""


def classify_size(size_kb: int) -> str:
    if size_kb < 2_000:
        return "small"
    if size_kb < 30_000:
        return "medium"
    return "large"


def classify_level(r: dict, size: str) -> str:
    text = " ".join([r.get("name", ""), r.get("description") or "",
                     " ".join(r.get("topics") or [])]).lower()
    if any(w in text for w in BEGINNER_WORDS):
        return "beginner"
    if any(w in text for w in ADVANCED_WORDS) or size == "large":
        return "advanced"
    return "intermediate"


def collect(target: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    per_cat = max(1, -(-target // len(CATEGORIES)))  # round up
    seen: set[str] = set()
    out: list[dict] = []
    rejected: dict[str, int] = {}

    for cat, queries in CATEGORIES.items():
        log(f"== {cat}: aiming for ~{per_cat} projects")
        got = 0
        for q in queries:
            if got >= per_cat:
                break
            for page in (1, 2, 3):
                if got >= per_cat:
                    break
                log(f"   search '{q}' page {page}")
                items = gh_search(q, page)
                time.sleep(2.2)  # stay under 30 searches/minute
                if not items:
                    break
                for r in items:
                    if got >= per_cat:
                        break
                    if r["full_name"] in seen:
                        continue
                    ok, why = passes_checks(r, cutoff)
                    if not ok:
                        rejected[why] = rejected.get(why, 0) + 1
                        continue
                    seen.add(r["full_name"])
                    size = classify_size(r.get("size", 0))
                    out.append({
                        "category": cat,
                        "level": classify_level(r, size),
                        "size": size,
                        "name": r["full_name"],
                        "url": r["html_url"],
                        "description": (r.get("description") or "").strip(),
                        "language": r.get("language") or "",
                        "stars": r.get("stargazers_count", 0),
                        "license": r["license"]["spdx_id"],
                        "last_push": r["pushed_at"][:10],
                        "topics": r.get("topics") or [],
                    })
                    got += 1
        log(f"   kept {got} for {cat} (total {len(out)})")

    log(f"Rejected by checks: {rejected}")
    return out


def md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")[:160]


def write_outputs(projects: list[dict]) -> None:
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "projects.json").write_text(
        json.dumps(projects, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(ROOT / "data" / "projects.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[k for k in projects[0] if k != "topics"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(projects)

    levels = ("beginner", "intermediate", "advanced")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# Dev Projects Index",
        "",
        f"A curated, auto-generated index of **{len(projects)} free and open-source projects** "
        "for learning and building with Next.js, Bun, Python, frontend, backend and full-stack, "
        "plus learning roadmaps, organized by level and size.",
        "",
        f"_Last updated: {today}. Regenerated by `scripts/build_index.py`._",
        "",
        "> All projects belong to their original authors and are linked here with their "
        "licenses. To work on one, **fork it** (keeping its license and credit) or use it as "
        "inspiration for your own build.",
        "",
        "**Also see [CREATORS.md](CREATORS.md):** projects from YouTube coding creators "
        "with a live demo that was checked to be working.",
        "",
        "**Start learning with [LEARNING_PATH.md](LEARNING_PATH.md):** 120+ build-it-yourself "
        "projects across frontend, backend, databases, integrations, AI and DevOps.",
        "",
        "**Every learning project has its own repo:** see "
        "[dev-learning-hub](https://github.com/ArAryan1314/dev-learning-hub) for the repos, "
        "coding standards, action items and environment setup.",
        "",
        "Raw data for integrations: `data/projects.json`, `data/projects.csv`, "
        "`data/creators.json`, `data/creators.csv`.",
        "",
        "## How projects are selected",
        "",
        f"- Clear open-source license, not archived, not a fork",
        f"- Active: pushed within the last {MAX_AGE_DAYS // 365} years",
        f"- At least {MIN_STARS} stars and a description",
        "- **Size:** small < 2 MB, medium < 30 MB, large ≥ 30 MB (repo size)",
        "- **Level:** beginner if it mentions tutorial/learn/beginner; advanced if large "
        "or production/SaaS/microservices; otherwise intermediate (heuristic, not perfect)",
        "",
        "## Summary",
        "",
        "| Category | Beginner | Intermediate | Advanced | Total |",
        "|---|---|---|---|---|",
    ]
    cats = list(dict.fromkeys(p["category"] for p in projects))
    for c in cats:
        counts = [sum(1 for p in projects if p["category"] == c and p["level"] == l)
                  for l in levels]
        anchor = c.lower().replace(" & ", "--").replace(".", "").replace(" ", "-")
        lines.append(f"| [{c}](#{anchor}) | {' | '.join(map(str, counts))} | {sum(counts)} |")
    lines.append("")

    for c in cats:
        lines += [f"## {c}", ""]
        for l in levels:
            rows = sorted((p for p in projects if p["category"] == c and p["level"] == l),
                          key=lambda p: -p["stars"])
            if not rows:
                continue
            lines += [f"<details><summary><b>{l.title()}</b> ({len(rows)})</summary>", "",
                      "| Project | Description | Lang | Size | ⭐ | License |",
                      "|---|---|---|---|---|---|"]
            for p in rows:
                lines.append(f"| [{p['name']}]({p['url']}) | {md_escape(p['description'])} | "
                             f"{p['language']} | {p['size']} | {p['stars']:,} | {p['license']} |")
            lines += ["", "</details>", ""]

    (ROOT / "README.md").write_text("\n".join(lines), encoding="utf-8")
    log(f"Wrote README.md, data/projects.json, data/projects.csv ({len(projects)} projects)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=1000)
    args = ap.parse_args()
    log(f"Building index, target ~{args.target} projects")
    projects = collect(args.target)
    if not projects:
        sys.exit("No projects collected - is `gh` logged in?")
    write_outputs(projects)


if __name__ == "__main__":
    main()
