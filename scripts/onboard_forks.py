"""
Fork open-source projects into your account and bring each one up to a
current repo standard, keeping the original author's history and credit.

For each project in data/pilot.json (or the file given with --list):
  1. FORK     gh repo fork  -> <you>/<name>  ("forked from ..." stays visible)
  2. CLONE    fresh shallow clone of the ORIGINAL project into ../projects/<name>
              (line-ending conversion off, so upstream files stay byte-identical)
  3. DETECT   finds every Node (npm/pnpm/yarn/bun) and Python (uv/pip) project
              in the repo root and first-level folders, plus the scripts each has
  4. ADD      only files that are MISSING (nothing upstream is overwritten):
                .github/workflows/standard-ci.yml   install, lint, typecheck, build, test
                .github/workflows/codeql.yml        security code scanning
                .github/dependabot.yml              dependency updates
                SECURITY.md, .editorconfig, issue + PR templates
              and a short "About this fork" credit block at the top of README.md
              plus any project fix in data/fixes/<name>.patch
  5. PUSH     the fork branch becomes: original latest commit + ONE standards
              commit (re-running re-syncs the fork with the original project)
  6. ACTIONS  enables Actions on the fork, disables the upstream workflows
              (they often deploy or need the author's secrets), and adds topics
  7. RECORD   writes data/forks.json for the status dashboard

Rules for CI: checks the project already defines (lint/test/...) are BLOCKING.
Checks this script introduces (audit, extra linters) are REPORT-ONLY, so a
fork is not marked red for problems the upstream project never claimed to fix.

Usage: python scripts/onboard_forks.py [--list data/pilot.json] [--only name]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT.parent / "projects"
SKIP_DIRS = {"node_modules", ".git", "docs", "doc", "examples", "example", ".github", "test", "tests"}
FORK_PACING = 90  # seconds between new forks, to stay under GitHub's anti-spam limits
CO_AUTHOR ="Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"


def log(msg: str) -> None:
    print(msg, flush=True)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8")
    if check and res.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)}\n{res.stderr.strip()[:500]}")
    return res


def gh_json(*args: str):
    return json.loads(run(["gh", *args]).stdout)


# ---------------------------------------------------------------- detection

def expand_script(d: Path, name: str, depth: int = 0) -> str:
    """Script text plus every script it calls (`bun run x`, `run-s x:*`, `--filter dir x`)."""
    pkg_file = d / "package.json"
    if depth > 5 or not pkg_file.exists():
        return ""
    scripts = json.loads(pkg_file.read_text(encoding="utf-8")).get("scripts", {})
    text = scripts.get(name, "")
    out = [text]
    for ref in re.findall(r"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?([\w:.-]+)", text):
        if ref in scripts and ref != name:
            out.append(expand_script(d, ref, depth + 1))
    for pat in re.findall(r"run-[sp]\s+([\w:*.-]+)", text):
        rx = re.compile("^" + re.escape(pat).replace(r"\*", ".*") + "$")
        out += [expand_script(d, s, depth + 1) for s in scripts if rx.match(s) and s != name]
    for sub, ref in re.findall(r"--filter\s+['\"]?\.?/?([\w./-]+?)['\"]?\s+(?:run\s+)?([\w:.-]+)", text):
        out.append(expand_script(d / sub, ref, depth + 1))
    return " ".join(out)


def detect_node(d: Path) -> dict | None:
    pkg_file = d / "package.json"
    if not pkg_file.exists():
        return None
    pkg = json.loads(pkg_file.read_text(encoding="utf-8"))
    scripts = pkg.get("scripts", {})
    pm_field = pkg.get("packageManager", "")
    if (d / "bun.lock").exists() or (d / "bun.lockb").exists() or pm_field.startswith("bun"):
        pm = "bun"
    elif (d / "pnpm-lock.yaml").exists() or pm_field.startswith("pnpm"):
        pm = "pnpm"
    elif (d / "yarn.lock").exists() or pm_field.startswith("yarn"):
        pm = "yarn"
    else:
        pm = "npm"
    typecheck = next((s for s in ("typecheck", "type-check", "check-types", "types", "check") if s in scripts), None)
    test = "test" if "test" in scripts and "no test specified" not in scripts["test"] else None
    # A watch-mode test script never exits in CI: prefer a one-shot variant.
    if test and "--watch" in scripts["test"]:
        test = next((s for s in ("test:ci", "test-ci", "test:run", "test:unit", "test-coverage",
                                 "test:coverage", "coverage") if s in scripts), None)
    fmt = next((s for s in ("format:check", "check-format", "check-code", "prettier:check",
                            "format-check", "lint:format") if s in scripts), None)
    build = "build" if "build" in scripts else None
    notes = []
    # A "build" that deploys (wrangler/vercel/...) needs the author's cloud account: skip it.
    if build and re.search(r"\b(deploy|wrangler|vercel|netlify)\b", expand_script(d, "build")):
        build = None
        notes.append("build script deploys to a cloud account, so CI runs checks + tests instead")
    # End-to-end browser tests need the whole app stack running: report only.
    e2e = bool(test and re.search(r"playwright|cypress", expand_script(d, test)))
    if e2e:
        notes.append("tests are end-to-end (need the full app running), so they are report-only")
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    schema = next((p for p in (d / "prisma" / "schema.prisma", d / "schema.prisma") if p.exists()), None)
    prisma_pg = bool(schema and "prisma" in deps and 'provider = "postgresql"' in schema.read_text(encoding="utf-8"))
    drizzle_pg = "drizzle-kit" in deps and any(k in deps for k in ("pg", "postgres", "@neondatabase/serverless"))
    # Only add a database when a script that CI runs actually touches it.
    ci_text = " ".join(expand_script(d, s) for s in (build, test, "postinstall") if s)
    postgres = prisma_pg or (drizzle_pg and re.search(r"migrate|drizzle", ci_text) is not None)
    browsers = any(k == "playwright" or k.startswith(("@playwright/", "@vitest/browser")) for k in deps)
    pnpm_pinned = pm == "pnpm" and pm_field.startswith("pnpm")
    lock = {"npm": "package-lock.json", "pnpm": "pnpm-lock.yaml", "yarn": "yarn.lock", "bun": None}[pm]
    return {
        "kind": "node", "pm": pm, "lock": bool(lock and (d / lock).exists()),
        "pnpm_pinned": pnpm_pinned,
        "lint": "lint" if "lint" in scripts else None, "format": fmt,
        "typecheck": typecheck, "build": build, "test": test, "e2e": e2e,
        "nvmrc": next((f for f in (".nvmrc", ".node-version") if (d / f).exists()), None),
        "env_example": (d / ".env.example").exists(), "postgres": postgres, "notes": notes,
        "browsers": browsers,
    }


def min_python(spec: str) -> str:
    m = re.search(r">=\s*3\.(\d+)", spec or "")
    return f"3.{max(int(m.group(1)), 10)}" if m and int(m.group(1)) > 12 else "3.12"


def toml_section(text: str, header: str) -> str:
    m = re.search(rf"^\[{re.escape(header)}\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
    return m.group(1) if m else ""


def detect_python(d: Path, repo: Path) -> dict | None:
    has_py = (d / "pyproject.toml").exists() or (d / "setup.py").exists() or (d / "requirements.txt").exists()
    if not has_py:
        return None
    pyproject = (d / "pyproject.toml").read_text(encoding="utf-8") if (d / "pyproject.toml").exists() else ""
    extras_sec = toml_section(pyproject, "project.optional-dependencies")
    names = re.findall(r"^\s*([A-Za-z0-9_-]+)\s*=", extras_sec, re.M)
    extras = ["all"] if "all" in names else []
    extras += [e for e in ("dev", "test", "tests", "testing") if e in names]
    groups_sec = toml_section(pyproject, "dependency-groups")
    groups = [g for g in re.findall(r"^\s*([A-Za-z0-9_-]+)\s*=", groups_sec, re.M) if g in ("dev", "test", "tests", "testing")]
    req_files = [p for p in ("requirements-dev.txt", "requirements-test.txt", "requirements_dev.txt",
                             "dev-requirements.txt", "test-requirements.txt", "requirements/dev.txt",
                             "requirements/test.txt", "tests/requirements.txt", "_requirements/test.txt")
                 if (d / p).exists()]
    tests_dir = (d / "tests").is_dir() or (d / "test").is_dir()
    # Tests marked "browser" need real browsers installed: skip them in standard CI.
    cfg = pyproject + "".join((d / f).read_text(encoding="utf-8", errors="ignore")
                              for f in ("pytest.ini", "tox.ini", "setup.cfg") if (d / f).exists())
    req = re.search(r'requires-python\s*=\s*"([^"]+)"', pyproject)
    return {
        "kind": "python", "uv": (d / "uv.lock").exists() or (repo / "uv.lock").exists(),
        "pyproject": bool(pyproject) or (d / "setup.py").exists(),
        "requirements": (d / "requirements.txt").exists(),
        "extras": extras, "groups": groups, "req_files": req_files,
        "tests": tests_dir, "tests_dir": next((t for t in ("tests", "test") if (d / t).is_dir()), None),
        "skip_browser": bool(re.search(r"^\s*browser\s*:", cfg, re.M) or '-m "browser"' in cfg),
        "python": min_python(req.group(1) if req else ""),
        "ruff_configured": "[tool.ruff" in pyproject or (d / "ruff.toml").exists() or (d / ".ruff.toml").exists(),
        "env_example": (d / ".env.example").exists(), "postgres": False, "notes": [],
    }


def detect(repo: Path, overrides: dict) -> list[tuple[str, dict]]:
    found = []
    dirs = [repo] + sorted(p for p in repo.iterdir() if p.is_dir() and p.name not in SKIP_DIRS and not p.name.startswith("."))
    for d in dirs:
        for info in (detect_node(d), detect_python(d, repo)):
            if info:
                rel = "." if d == repo else d.name
                info.update(overrides.get(f"{info['kind']}@{rel}", {}))
                found.append((rel, info))
    # In a JS workspace monorepo the root package covers sub-packages already.
    if any(r == "." and i["kind"] == "node" for r, i in found):
        found = [(r, i) for r, i in found if r == "." or i["kind"] != "node"]
    return found


# ---------------------------------------------------------------- generation

# Generated YAML deliberately uses NO quotes: projects lint YAML with opposite
# quote rules (eslint-yaml wants single, Prettier wants double), and plain
# scalars satisfy both.

def step(name: str, cmd: str, soft: bool = False) -> str:
    body = f"      - name: {name}\n"
    if soft:
        body += "        continue-on-error: true\n"
    if "\n" in cmd:
        return body + "        run: |\n" + "\n".join(f"          {c}" for c in cmd.splitlines())
    return body + f"        run: {cmd}"


def services_block(i: dict) -> str:
    pg = i.get("postgres")
    if not pg:
        return ""
    pg = pg if isinstance(pg, dict) else {}
    user, pw, db = pg.get("user", "postgres"), pg.get("password", "postgres"), pg.get("db", "postgres")
    return (f"    services:\n      postgres:\n        image: postgres:17\n"
            f"        env:\n          POSTGRES_USER: {user}\n          POSTGRES_PASSWORD: {pw}\n          POSTGRES_DB: {db}\n"
            f"        ports:\n          - 5432:5432\n"
            f"        options: >-\n          --health-cmd pg_isready --health-interval 5s --health-timeout 5s --health-retries 10\n")


def job_env(i: dict) -> str:
    env = dict(i.get("env", {}))
    pg = i.get("postgres")
    if pg:
        pg = pg if isinstance(pg, dict) else {}
        user, pw, db = pg.get("user", "postgres"), pg.get("password", "postgres"), pg.get("db", "postgres")
        url = f"postgresql://{user}:{pw}@localhost:5432/{db}"
        for k in ("DATABASE_URL", "DIRECT_URL", "POSTGRES_PRISMA_URL", "POSTGRES_URL_NON_POOLING", "POSTGRES_URL"):
            env.setdefault(k, url)
        env.update({k: v for k, v in pg.get("extra_env", {}).items()})
    if not env:
        return ""
    return "    env:\n" + "".join(f"      {k}: {v}\n" for k, v in env.items())


def job_header(jid: str, title: str, rel: str, i: dict) -> str:
    return (f"  {jid}:\n    name: {title}\n    runs-on: ubuntu-latest\n    timeout-minutes: 20\n"
            + services_block(i) + job_env(i)
            + f"    defaults:\n      run:\n        working-directory: {rel}\n    steps:\n")


def node_job(rel: str, i: dict) -> str:
    jid = "node-" + (re.sub(r"[^a-z0-9]+", "-", rel.lower()).strip("-") or "root")
    pm = i["pm"]
    run_cmd = {"npm": "npm run", "pnpm": "pnpm run", "yarn": "yarn run", "bun": "bun run"}[pm]
    install = i.get("install") or {
        # An out-of-date lockfile makes `npm ci` refuse; fall back so CI still validates the code.
        "npm": "npm ci || npm install" if i["lock"] else "npm install",
        "pnpm": "pnpm install" if i["lock"] else "pnpm install --no-frozen-lockfile",
        "yarn": "yarn install", "bun": "bun install"}[pm]
    audit = {"npm": "npm audit --audit-level=high", "pnpm": "pnpm audit --audit-level high",
             "yarn": "yarn npm audit || yarn audit", "bun": "bun audit"}[pm]
    steps = ["      - uses: actions/checkout@v5"]
    if pm == "pnpm":
        steps.append("      - uses: pnpm/action-setup@v4")
        if not i["pnpm_pinned"]:
            steps.append("        with:\n          version: 10")
    if pm == "bun":
        steps.append("      - uses: oven-sh/setup-bun@v2")
    node_ver = f"node-version-file: {rel}/{i['nvmrc']}" if i["nvmrc"] else "node-version: 22"
    # package-manager-cache off: auto-caching fails on repos without a lockfile.
    steps += ["      - uses: actions/setup-node@v5", "        with:", f"          {node_ver}",
              "          package-manager-cache: false"]
    if pm == "yarn":
        steps.append("      - run: corepack enable")
    # Copy the example env BEFORE install: some projects run migrations in postinstall.
    if i["env_example"]:
        steps.append(step("Use example env", "cp .env.example .env"))
    steps.append(step("Install", install))
    if i.get("browsers") and i["test"]:
        exec_cmd = {"npm": "npx", "pnpm": "pnpm exec", "yarn": "yarn exec", "bun": "bunx"}[pm]
        steps.append(step("Install test browser (Playwright Chromium)", f"{exec_cmd} playwright install --with-deps chromium"))
    lint_soft = bool(i.get("lint_soft"))
    for label, script, soft in (("Lint (report only)" if lint_soft else "Lint", i["lint"], lint_soft),
                                ("Format check (report only)", i["format"], True),
                                ("Type-check", i["typecheck"], False), ("Build", i["build"], False),
                                ("Test" + (" (e2e, report only)" if i["e2e"] else ""), i["test"], i["e2e"])):
        if script:
            steps.append(step(label, f"{run_cmd} {script}", soft))
    if not any((i["build"], i["test"], i["typecheck"])):
        steps.append(step("Smoke test (package manifest valid)", "npm pkg get name"))
    steps.append(step("Dependency audit (report only)", audit, soft=True))
    return job_header(jid, f"Node ({rel})", rel, i) + "\n".join(steps)


def python_job(rel: str, i: dict) -> str:
    jid = "python-" + (re.sub(r"[^a-z0-9]+", "-", rel.lower()).strip("-") or "root")
    steps = ["      - uses: actions/checkout@v5"]
    if i["env_example"]:
        steps.append(step("Use example env", "cp .env.example .env"))
    if i["uv"]:
        steps.append("      - uses: astral-sh/setup-uv@v6")
        steps.append(step("Install", i.get("install") or "uv sync --all-extras --all-groups"))
        py = "uv run"
    else:
        steps += ["      - uses: actions/setup-python@v6", "        with:", f"          python-version: {i['python']}"]
        cmds = ["python -m pip install --upgrade pip"]
        if i["requirements"]:
            cmds.append("pip install -r requirements.txt")
        if i["pyproject"]:
            extras = f"[{','.join(i['extras'])}]" if i["extras"] else ""
            cmds.append(f"pip install -e .{extras}")
        cmds += [f"pip install --group {g}" for g in i["groups"]]
        cmds += [f"pip install -r {f}" for f in i["req_files"]]
        cmds.append("pip install pytest ruff pip-audit")
        steps.append(step("Install", i.get("install") or "\n".join(cmds)))
        py = "python -m"
    ruff_run = "uvx ruff" if i["uv"] else "ruff"
    steps.append(step("Lint (ruff)" if i["ruff_configured"] else "Lint (ruff, report only)",
                      f"{ruff_run} check .", soft=not i["ruff_configured"]))
    if i.get("test_cmd"):
        steps.append(step("Test", f"{py.replace('python -m', '').strip()} {i['test_cmd']}".strip()))
    elif i["tests"]:
        marker = " -m 'not browser'" if i["skip_browser"] else ""
        # pytest exit code 5 = "no tests collected": treat as a pass (nothing to fail).
        # Point pytest at the tests folder so stray root scripts (benchmarks.py, ...) aren't collected.
        target = f" {i['tests_dir']}" if i.get("tests_dir") else ""
        steps.append(step("Test" + (" (non-browser)" if marker else ""),
                          f"{py} pytest{target} -q{marker} || [ $? -eq 5 ]"))
    else:
        steps.append(step("Smoke test (all files compile)", i.get("smoke_cmd") or "python -m compileall -q ."))
    audit = "uvx pip-audit" if i["uv"] else "pip-audit"
    steps.append(step("Dependency audit (report only)", audit, soft=True))
    return job_header(jid, f"Python ({rel})", rel, i) + "\n".join(steps)


def docs_job() -> str:
    return """  docs:
    name: Docs (markdown + links)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - name: Markdown lint (report only)
        continue-on-error: true
        uses: DavidAnson/markdownlint-cli2-action@v20
      - name: Link check (report only)
        continue-on-error: true
        uses: lycheeverse/lychee-action@v2
        with:
          args: --no-progress --max-concurrency 8 ./**/*.md
          fail: false"""


def ci_workflow(stacks: list[tuple[str, dict]]) -> str:
    jobs = [node_job(r, i) if i["kind"] == "node" else python_job(r, i) for r, i in stacks] or [docs_job()]
    return ("name: Standard CI\n\non:\n  push:\n  pull_request:\n  workflow_dispatch:\n\n"
            "permissions:\n  contents: read\n\n"
            "concurrency:\n  group: ci-${{ github.ref }}\n  cancel-in-progress: true\n\n"
            "env:\n  CI: true\n  SKIP_ENV_VALIDATION: 1\n  NEXT_TELEMETRY_DISABLED: 1\n\n"
            "jobs:\n" + "\n\n".join(jobs) + "\n")


def codeql_workflow(stacks) -> str:
    langs = sorted({"javascript-typescript" if i["kind"] == "node" else "python" for _, i in stacks})
    if not langs:
        return ""
    return f"""name: CodeQL

on:
  push:
  pull_request:
  schedule:
    - cron: 30 4 * * 0

permissions:
  security-events: write
  contents: read

jobs:
  analyze:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        language: [{", ".join(langs)}]
    steps:
      - uses: actions/checkout@v5
      - uses: github/codeql-action/init@v4
        with:
          languages: ${{{{ matrix.language }}}}
          build-mode: none
      - uses: github/codeql-action/analyze@v4
"""


def dependabot(stacks) -> str:
    entries = ["  - package-ecosystem: github-actions\n    directory: /\n    schedule:\n      interval: weekly"]
    for rel, i in stacks:
        eco = "npm" if i["kind"] == "node" else ("uv" if i.get("uv") else "pip")
        if i["kind"] == "node" and i["pm"] == "bun":
            eco = "bun"
        d = "/" if rel == "." else f"/{rel}"
        entries.append(f"  - package-ecosystem: {eco}\n    directory: {d}\n    schedule:\n      interval: weekly\n    open-pull-requests-limit: 5")
    return "version: 2\nupdates:\n" + "\n".join(entries) + "\n"


SECURITY = """# Security Policy

This repository is a fork of [{up}](https://github.com/{up}).

- Vulnerabilities in the **original project**: please report them upstream, following the policy at <https://github.com/{up}/security>.
- Issues specific to **this fork** (CI, configuration, changes made here): open a private advisory via the **Security** tab of this repository.
"""

EDITORCONFIG = """root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 2

[*.py]
indent_size = 4

[*.md]
trim_trailing_whitespace = false

[Makefile]
indent_style = tab
"""

BUG = """---
name: Bug report
about: Something isn't working
labels: bug
---

**What happened**

**Steps to reproduce**

**Expected behaviour**

**Environment** (OS, Node/Python version, browser)
"""

FEATURE = """---
name: Feature request
about: Suggest an improvement
labels: enhancement
---

**Problem this would solve**

**Proposed solution**
"""

PR = """## What changed

## Why

## Checks

- [ ] CI passes
- [ ] Tested locally
"""


def readme_block(owner: str, name: str, up: str, lic: str, demo: str) -> str:
    # Blank lines around comments and between quote paragraphs keep Prettier/oxfmt happy.
    demo_line = f">\n> **Live demo (upstream):** <{demo}>\n" if demo else ""
    return (f"<!-- fork-notice:start -->\n\n"
            f"> **About this fork:** maintained copy of [{up}](https://github.com/{up}), "
            f"used for learning and integration. All credit for the original work goes to its authors. "
            f"License: {lic} (see `LICENSE`).\n{demo_line}>\n"
            f"> [![Standard CI](https://github.com/{owner}/{name}/actions/workflows/standard-ci.yml/badge.svg)]"
            f"(https://github.com/{owner}/{name}/actions/workflows/standard-ci.yml)\n\n"
            f"<!-- fork-notice:end -->\n\n")


def write_if_missing(path: Path, content: str, added: list[str], repo: Path) -> None:
    if content and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")
        added.append(path.relative_to(repo).as_posix())


# ---------------------------------------------------------------- main flow

def onboard(entry: dict, owner: str) -> dict:
    up = entry["upstream"]
    name = up.split("/")[1]
    log(f"\n=== {up}")
    meta = gh_json("api", f"repos/{up}")
    lic = (meta.get("license") or {}).get("spdx_id") or "see LICENSE"
    branch = meta["default_branch"]

    # 1. fork (idempotent: gh reuses an existing fork)
    fork = f"{owner}/{name}"
    if run(["gh", "api", f"repos/{fork}"], check=False).returncode != 0:
        # GitHub throttles fork creation ("submitted too quickly"): back off and retry.
        for wait in (0, 120, 240, 480, 900):
            if wait:
                log(f"  GitHub fork limit hit, waiting {wait // 60} min ...")
                time.sleep(wait)
            res = run(["gh", "repo", "fork", up, "--clone=false", "--default-branch-only"], check=False)
            if res.returncode == 0 or "already exists" in res.stderr:
                break
            if "too quickly" not in res.stderr and "403" not in res.stderr:
                raise RuntimeError(f"fork failed: {res.stderr.strip()[:300]}")
        else:
            raise RuntimeError("fork failed: GitHub rate limit did not clear")
        time.sleep(FORK_PACING)
    for _ in range(20):
        if run(["gh", "api", f"repos/{fork}"], check=False).returncode == 0:
            break
        time.sleep(3)
    else:
        raise RuntimeError("fork did not appear on GitHub")
    log(f"  forked  -> https://github.com/{fork}")

    # 2. clone
    repo = WORK / name
    # Always rebuild from a fresh clone of the ORIGINAL project, with line-ending
    # conversion off from the start, so upstream files are byte-for-byte untouched.
    WORK.mkdir(parents=True, exist_ok=True)
    if repo.exists():
        def _force(func, path, *_):
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(repo, onexc=_force) if sys.version_info >= (3, 12) else shutil.rmtree(repo, onerror=_force)
    run(["git", "-c", "core.autocrlf=false", "clone", "-q", "--depth", "1", "--branch", branch,
         "--config", "core.autocrlf=false", f"https://github.com/{up}.git", str(repo)])
    run(["git", "remote", "rename", "origin", "upstream"], cwd=repo)
    run(["git", "remote", "add", "origin", f"https://github.com/{fork}.git"], cwd=repo)
    run(["git", "config", "user.name", owner], cwd=repo)
    run(["git", "config", "user.email", entry["email"]], cwd=repo)

    # 3. detect
    ov_file = ROOT / "data" / "overrides.json"
    overrides = json.loads(ov_file.read_text(encoding="utf-8")).get(name, {}) if ov_file.exists() else {}
    stacks = detect(repo, overrides)
    desc = ", ".join(f"{i['kind']}:{i.get('pm', 'uv' if i.get('uv') else 'pip')}@{r}" for r, i in stacks) or "docs only"
    log(f"  detected {desc}")

    # 4. add standard files
    added: list[str] = []
    gh_dir = repo / ".github"
    # Our own CI files are regenerated on every run so fixes to this script apply.
    for fname, content, marker in (("standard-ci.yml", ci_workflow(stacks), "name: Standard CI"),
                                   ("codeql.yml", codeql_workflow(stacks), "build-mode: none")):
        p = gh_dir / "workflows" / fname
        if p.exists() and marker in p.read_text(encoding="utf-8") and content and p.read_text(encoding="utf-8") != content:
            p.write_text(content, encoding="utf-8", newline="\n")
            added.append(f".github/workflows/{fname} (updated)")
        else:
            write_if_missing(p, content, added, repo)
    if not (gh_dir / "dependabot.yml").exists() and not (gh_dir / "dependabot.yaml").exists() and not (repo / "renovate.json").exists():
        write_if_missing(gh_dir / "dependabot.yml", dependabot(stacks), added, repo)
    if not any((repo / p).exists() for p in ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md")):
        write_if_missing(repo / "SECURITY.md", SECURITY.format(up=up), added, repo)
    write_if_missing(repo / ".editorconfig", EDITORCONFIG, added, repo)
    if not (gh_dir / "ISSUE_TEMPLATE").exists():
        write_if_missing(gh_dir / "ISSUE_TEMPLATE" / "bug_report.md", BUG, added, repo)
        write_if_missing(gh_dir / "ISSUE_TEMPLATE" / "feature_request.md", FEATURE, added, repo)
    if not any((repo / p).exists() for p in (".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md")):
        write_if_missing(gh_dir / "pull_request_template.md", PR, added, repo)

    readme = next((repo / f for f in ("README.md", "readme.md", "Readme.md") if (repo / f).exists()), repo / "README.md")
    # newline="" keeps the README's original line endings exactly as they are
    text = readme.open(encoding="utf-8", newline="").read() if readme.exists() else f"# {name}\n"
    if "fork-notice:start" not in text:
        block = readme_block(owner, name, up, lic, meta.get("homepage") or "")
        if "\r\n" in text:
            block = block.replace("\n", "\r\n")
        with readme.open("w", encoding="utf-8", newline="") as fh:
            fh.write(block + text)
        added.append(f"{readme.name} (fork notice)")
    # Project-specific fixes found while validating (data/fixes/<name>.patch)
    # Stage ONLY the files written above. Never `git add -A`: a repo with
    # `* text eol=crlf` in .gitattributes would have every untouched file
    # (images included) re-normalized and silently rewritten.
    paths = [a.split(" (")[0] for a in added]
    if paths:
        run(["git", "add", "--", *paths], cwd=repo)
    # Project-specific fixes found while validating (data/fixes/<name>.patch);
    # --index applies the patch straight to the index, staging exactly its files.
    patch = ROOT / "data" / "fixes" / f"{name}.patch"
    if patch.exists():
        run(["git", "apply", "--index", "--whitespace=nowarn", str(patch)], cwd=repo)
        added.append(f"fixes from {patch.name}")
    log(f"  added   {', '.join(added) or 'nothing (already standard)'}")

    # 5. commit + push
    if run(["git", "diff", "--cached", "--quiet"], cwd=repo, check=False).returncode != 0:
        msg = ("chore: add CI, security scanning and repo standards\n\n"
               "Adds standard CI (install, lint, type-check, build, test), CodeQL,\n"
               "Dependabot, SECURITY.md, .editorconfig, issue/PR templates and a\n"
               f"credit notice for the upstream project {up}.\n\n{CO_AUTHOR}")
        run(["git", "commit", "-q", "-m", msg], cwd=repo)

    # 6. actions: enable, disable upstream workflows, then push to trigger ours
    run(["gh", "api", "-X", "PUT", f"repos/{fork}/actions/permissions", "-F", "enabled=true", "-f", "allowed_actions=all"], check=False)
    # The fork branch becomes: upstream HEAD + our single standards commit.
    for attempt in range(4):  # a just-created fork can briefly reject pushes
        res = run(["git", "push", "-q", "--force", "origin", f"HEAD:{branch}"], cwd=repo, check=attempt == 3)
        if res.returncode == 0:
            break
        time.sleep(20 * (attempt + 1))
    wfs = gh_json("api", f"repos/{fork}/actions/workflows", "--paginate")["workflows"]
    disabled = []
    for wf in wfs:
        if not wf["path"].endswith(("standard-ci.yml", "codeql.yml")) and wf["state"] == "active":
            run(["gh", "api", "-X", "PUT", f"repos/{fork}/actions/workflows/{wf['id']}/disable"], check=False)
            disabled.append(Path(wf["path"]).name)
    if disabled:
        log(f"  disabled upstream workflows: {', '.join(disabled)}")
    topics = ["forked-project", entry["category"].lower().replace(" & ", "-").replace(".", "").replace(" ", "-"), entry["level"]]
    run(["gh", "repo", "edit", fork, "--enable-issues", *sum((["--add-topic", t] for t in topics), [])], check=False)
    log("  pushed, CI started")

    return {**entry, "name": name, "fork": fork, "url": f"https://github.com/{fork}",
            "branch": branch, "license": lic, "stack": desc, "added": added,
            "note": "; ".join(n for _, i in stacks for n in i.get("notes", []))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", default=str(ROOT / "data" / "pilot.json"))
    ap.add_argument("--only")
    args = ap.parse_args()
    owner = gh_json("api", "user")["login"]
    uid = gh_json("api", "user")["id"]
    email = f"{uid}+{owner}@users.noreply.github.com"
    entries = json.loads(Path(args.list).read_text(encoding="utf-8"))
    if args.only:
        entries = [e for e in entries if e["upstream"].endswith("/" + args.only)]

    out_file = ROOT / "data" / "forks.json"
    records = {r["upstream"]: r for r in json.loads(out_file.read_text(encoding="utf-8"))} if out_file.exists() else {}
    for e in entries:
        try:
            records[e["upstream"]] = onboard({**e, "email": email}, owner)
        except Exception as exc:  # keep going; report at the end
            log(f"  FAILED: {exc}")
            records.setdefault(e["upstream"], {**e, "error": str(exc)[:300]})
        out_file.write_text(json.dumps([{k: v for k, v in r.items() if k != "email"} for r in records.values()],
                                       indent=2), encoding="utf-8")
    log(f"\nDone. {len(records)} records in data/forks.json")


if __name__ == "__main__":
    main()
