"""
Build PROJECTS.md: a status dashboard of every forked project in data/forks.json.

For each fork it reads the latest "Standard CI" run and, if it failed, which
step failed. Usage: python scripts/build_dashboard.py
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def gh_json(*args: str):
    res = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    return json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else None


def ci_status(fork: str) -> tuple[str, str]:
    runs = gh_json("run", "list", "-R", fork, "-w", "Standard CI", "-L", "1",
                   "--json", "databaseId,status,conclusion")
    if not runs:
        return "no run", ""
    r = runs[0]
    if r["status"] != "completed":
        return "running", ""
    if r["conclusion"] == "success":
        return "passing", ""
    view = gh_json("run", "view", str(r["databaseId"]), "-R", fork, "--json", "jobs") or {"jobs": []}
    failed = [f"{j['name']}: {s['name']}" for j in view["jobs"] for s in j.get("steps", [])
              if s.get("conclusion") == "failure"]
    return "failing", "; ".join(failed)


def main() -> None:
    forks = json.loads((ROOT / "data" / "forks.json").read_text(encoding="utf-8"))
    ov_file = ROOT / "data" / "overrides.json"
    overrides = json.loads(ov_file.read_text(encoding="utf-8")) if ov_file.exists() else {}
    rows, counts = [], {}
    for f in forks:
        if "fork" not in f:
            status, why = "onboarding failed", f.get("error", "")[:120]
        else:
            status, why = ci_status(f["fork"])
            for extra in (f.get("note"), overrides.get(f["name"], {}).get("fix_note")):
                if extra:
                    why = (why + "; " if why else "") + extra
        f["ci"] = status
        f["ci_detail"] = why
        counts[status] = counts.get(status, 0) + 1
        rows.append(f)
        print(f"{f['upstream']}: {status} {why}", flush=True)

    (ROOT / "data" / "forks.json").write_text(json.dumps(forks, indent=2), encoding="utf-8")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    icon = {"passing": "✅", "failing": "❌", "running": "⏳"}
    lines = [
        "# Forked Projects: Status",
        "",
        f"{len(rows)} projects forked into this account with standard CI, CodeQL security scanning, "
        "Dependabot, SECURITY.md, issue/PR templates and a credit notice for the original authors.",
        "",
        "**Summary:** " + " · ".join(f"{icon.get(k, '⚠️')} {k}: {v}" for k, v in sorted(counts.items())),
        "",
        f"_Updated {today} by `scripts/build_dashboard.py`. Report-only checks (format, dependency audit) "
        "never mark a project as failing._",
        "",
        "| Project | Original | Category | Level | Stack | CI | Notes |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in sorted(rows, key=lambda r: (r["category"], ["beginner", "intermediate", "advanced"].index(r["level"]))):
        if "fork" in f:
            badge = (f"[![CI](https://github.com/{f['fork']}/actions/workflows/standard-ci.yml/badge.svg)]"
                     f"(https://github.com/{f['fork']}/actions/workflows/standard-ci.yml)")
            proj = f"[{f['name']}]({f['url']})"
        else:
            badge, proj = "—", f["upstream"].split("/")[1]
        lines.append(f"| {proj} | [{f['upstream']}](https://github.com/{f['upstream']}) | {f['category']} | "
                     f"{f['level']} | {f.get('stack', '')} | {badge} | {f['ci_detail'].replace('|', '/')} |")
    (ROOT / "PROJECTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote PROJECTS.md: {counts}")


if __name__ == "__main__":
    main()
