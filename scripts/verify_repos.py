"""
Install, test and build every generated learning repo, and report what passed.

Detects each repo's starter type from its files and runs the same checks its
CI runs. Python framework repos share one virtualenv (<dir>/.venv-verify) so
packages are installed once. Go and Java use local toolchains when present,
otherwise Docker.

Usage:
  python scripts/verify_repos.py                      # ../learning-projects
  python scripts/verify_repos.py --dir PATH --only taskflow-api --jobs 4
Writes <dir>/VERIFY_REPORT.md and <dir>/verify_report.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NPM = "npm.cmd" if os.name == "nt" else "npm"
PY_PACKAGES = ["fastapi==0.165.0", "uvicorn==0.54.0", "httpx==0.28.1", "pytest==9.2.0",
               "flask==3.1.3", "django==6.1.3"]


def detect(repo: Path) -> str:
    has = lambda f: (repo / f).exists()  # noqa: E731
    if has("pom.xml"):
        return "java"
    if has("go.mod"):
        return "go"
    if has("manage.py"):
        return "django"
    if has("app/main.py"):
        return "fastapi"
    if has("app.py"):
        return "flask"
    if has("run_exercises.py"):
        return "sql"
    if has("scripts/check_links.py"):
        return "docs"
    if has("next.config.ts"):
        return "next"
    if has("vite.config.ts"):
        return "react"
    if has("Dockerfile") and has("src/app.ts"):
        return "devops"
    if has("src/app.ts"):
        return "node"
    if has("server.js"):
        return "web"
    if has("pyproject.toml"):
        return "python"
    return "unknown"


def docker_run(repo: Path, image: str, cmd: str) -> list[str]:
    return ["docker", "run", "--rm", "-v", f"{repo}:/src", "-w", "/src", image, "sh", "-c", cmd]


def steps(kind: str, repo: Path, venv_py: str) -> list[list[str]]:
    npm_i = [NPM, "install", "--no-audit", "--no-fund", "--loglevel=error"]
    py = sys.executable
    return {
        "web": [[NPM, "test"]],
        "node": [npm_i, [NPM, "run", "typecheck"], [NPM, "test"]],
        "devops": [npm_i, [NPM, "run", "typecheck"], [NPM, "test"], ["docker", "compose", "config", "-q"]],
        "react": [npm_i, [NPM, "run", "typecheck"], [NPM, "test"], [NPM, "run", "build"]],
        "next": [npm_i, [NPM, "test"], [NPM, "run", "build"], [NPM, "run", "typecheck"]],
        "python": [[py, "-m", "unittest", "discover", "-s", "tests", "-t", "."]],
        "sql": [[py, "-m", "unittest", "discover", "-s", "tests", "-t", "."], [py, "run_exercises.py"]],
        "docs": [[py, "scripts/check_links.py"]],
        "fastapi": [[venv_py, "-m", "pytest", "-q", "-p", "no:cacheprovider"]],
        "flask": [[venv_py, "-m", "pytest", "-q", "-p", "no:cacheprovider"]],
        "django": [[venv_py, "manage.py", "check"], [venv_py, "manage.py", "test"]],
        "go": ([["go", "vet", "./..."], ["go", "test", "./..."]] if shutil.which("go") else
               [docker_run(repo, "golang:1.23-alpine", "go vet ./... && go test ./...")]),
        "java": ([["mvn.cmd" if os.name == "nt" else "mvn", "-B", "-q", "test"]] if shutil.which("mvn") or shutil.which("mvn.cmd") else
                 [docker_run(repo, "maven:3.9-eclipse-temurin-21",
                             "mvn -B -q test && rm -rf target")]),
    }.get(kind, [])


def verify(repo: Path, venv_py: str) -> dict:
    kind = detect(repo)
    result = {"repo": repo.name, "kind": kind, "ok": True, "steps": [], "seconds": 0.0}
    start = time.time()
    plan = steps(kind, repo, venv_py)
    if not plan:
        result.update(ok=False, error="unknown project type")
    env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    for cmd in plan:
        r = subprocess.run(cmd, cwd=repo, capture_output=True, text=True, env=env,
                           encoding="utf-8", errors="replace")
        name = " ".join(Path(cmd[0]).stem if i == 0 else c for i, c in enumerate(cmd[:4]))
        step = {"cmd": name, "ok": r.returncode == 0}
        if r.returncode:
            step["output"] = (r.stdout + r.stderr)[-2500:]
        result["steps"].append(step)
        if r.returncode:
            result["ok"] = False
            break
    result["seconds"] = round(time.time() - start, 1)
    if result["ok"] and COMMIT_LOCKFILES and (repo / "package-lock.json").exists():
        commit_lockfile(repo)
    print(f"{'PASS' if result['ok'] else 'FAIL'}  {repo.name:<28} {kind:<8} {result['seconds']}s", flush=True)
    return result


COMMIT_LOCKFILES = False


def git_identity() -> list[str]:
    opts = []
    for key in ("user.name", "user.email"):
        val = subprocess.run(["git", "config", key], cwd=ROOT, capture_output=True,
                             text=True).stdout.strip()
        if val:
            opts += ["-c", f"{key}={val}"]
    return opts


def commit_lockfile(repo: Path) -> None:
    """Commit package-lock.json so installs are reproducible (CI uses the same versions)."""
    status = subprocess.run(["git", "status", "--porcelain", "package-lock.json"], cwd=repo,
                            capture_output=True, text=True).stdout.strip()
    if not status:
        return
    ident = git_identity()
    subprocess.run(["git", "add", "package-lock.json"], cwd=repo, check=True)
    subprocess.run(["git", *ident, "commit", "-q", "-m",
                    "Add package-lock.json from a verified install\n\n"
                    "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"], cwd=repo, check=True)


def shared_venv(base: Path) -> str:
    venv = base / ".venv-verify"
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not py.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        subprocess.run([str(py), "-m", "pip", "install", "-q", *PY_PACKAGES], check=True)
    return str(py)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT.parent / "learning-projects"))
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--commit-lockfiles", action="store_true",
                    help="commit package-lock.json in repos that passed")
    args = ap.parse_args()
    global COMMIT_LOCKFILES
    COMMIT_LOCKFILES = args.commit_lockfiles
    base = Path(args.dir).resolve()
    repos = sorted(p for p in base.iterdir() if (p / ".git").exists()
                   and (not args.only or p.name in args.only))
    needs_venv = any(detect(r) in ("fastapi", "flask", "django") for r in repos)
    venv_py = shared_venv(base) if needs_venv else sys.executable

    # Docker-based checks share caches badly in parallel; run them last, one at a time.
    docker_kinds = {"go", "java"} if not (shutil.which("go") and (shutil.which("mvn") or shutil.which("mvn.cmd"))) else set()
    local = [r for r in repos if detect(r) not in docker_kinds]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(lambda r: verify(r, venv_py), local))
    results += [verify(r, venv_py) for r in repos if detect(r) in docker_kinds]

    results.sort(key=lambda r: r["repo"])
    passed = sum(r["ok"] for r in results)
    (base / "verify_report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    lines = ["# Verify report", "", f"**{passed}/{len(results)} repos passed** "
             f"(install, typecheck, tests and build where applicable).", "",
             "| Repo | Type | Result | Checks | Time |", "|---|---|---|---|---|"]
    for r in results:
        checks = ", ".join(f"{'✅' if s['ok'] else '❌'} `{s['cmd']}`" for s in r["steps"])
        lines.append(f"| {r['repo']} | {r['kind']} | {'✅ pass' if r['ok'] else '❌ fail'} | "
                     f"{checks} | {r['seconds']}s |")
    fails = [r for r in results if not r["ok"]]
    for r in fails:
        out = next((s.get("output", "") for s in r["steps"] if not s["ok"]), r.get("error", ""))
        lines += ["", f"## ❌ {r['repo']}", "", "```", out.strip(), "```"]
    (base / "VERIFY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n{passed}/{len(results)} passed. Report: {base / 'VERIFY_REPORT.md'}")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
