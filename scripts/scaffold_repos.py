"""
Create one separate git repository per project in data/learning_path.json.

Each repo gets a small starter that runs and passes its tests without extra
setup where possible, plus:
  README.md     what to build, how to run it, references
  PENDING.md    checklist of everything still to do in that project
  LICENSE       MIT, in your name
  .github/workflows/ci.yml, .gitignore, .env.example
and an initial git commit.

Also writes:
  <out>/README.md         overview of all generated repos
  <out>/publish_all.sh    creates every repo on GitHub with `gh` and pushes it
  PROJECTS_STATUS.md      (in this index repo) status + pending count per repo

Existing repo folders are never overwritten (your work stays safe) unless you
pass --force.

Usage:
  python scripts/scaffold_repos.py                    # all projects
  python scripts/scaffold_repos.py --only taskflow-api go-rest-api
  python scripts/scaffold_repos.py --out ../learning-projects --owner YourGitHubName
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

V = {  # pinned dependency versions (checked on npm / PyPI when generated)
    "next": "16.4.6", "react": "19.3.1", "react-dom": "19.3.1",
    "@types/react": "19.3.0", "@types/react-dom": "19.3.0", "@types/node": "24.19.2",
    "typescript": "5.9.3", "vite": "8.3.8", "@vitejs/plugin-react": "6.3.0",
    "fastapi": "0.165.0", "uvicorn": "0.54.0", "httpx": "0.28.1", "pytest": "9.2.0",
    "flask": "3.1.3", "django": "6.1.3", "spring-boot": "3.5.6",
}

ACRONYMS = {"api", "ui", "ai", "ci", "sql", "css", "html", "js", "ts", "jwt", "url", "pdf",
            "2fa", "k8s", "mcp", "pwa", "rbac", "cms", "sms", "otp", "llm", "rest", "grpc",
            "e2e", "owasp", "aws", "dom", "oop", "cli", "vps", "saas", "i18n", "qa", "dsa",
            "3d", "mdx", "mern", "k6", "totp", "dnd", "db"}

# Which parts of a "stack" string each template already provides.
BASELINE = {
    "node": ["node", "typescript", "bun", "any"],
    "next": ["next.js", "react", "typescript"],
    "react": ["react", "vite", "typescript"],
    "web": ["html", "css", "javascript"],
    "python": ["python"],
    "fastapi": ["fastapi", "python"],
    "flask": ["flask", "python"],
    "django": ["django", "python"],
    "go": ["go"],
    "java": ["java", "spring boot"],
    "devops": ["docker compose", "docker"],
    "sql": [],
    "docs": ["markdown", "git"],
}

RUN = {  # quick-start commands shown in README
    "node": "npm install        # only needed for type checking\nnpm test           # run tests\nnpm start          # http://localhost:3000/health",
    "next": "npm install\nnpm test           # unit tests\nnpm run dev        # http://localhost:3000\nnpm run build      # production build",
    "react": "npm install\nnpm test           # unit tests\nnpm run dev        # http://localhost:5173\nnpm run build      # production build",
    "web": "npm test           # unit tests (no install needed)\nnpm start          # http://localhost:3000",
    "python": "python -m unittest discover -s tests -t .   # run tests\npython -m __PKG__ add \"first note\"\npython -m __PKG__ list",
    "fastapi": "python -m venv .venv && . .venv/bin/activate   # Windows: .venv\\Scripts\\activate\npip install -r requirements.txt\npytest\nuvicorn app.main:app --reload                   # http://localhost:8000/docs",
    "flask": "python -m venv .venv && . .venv/bin/activate   # Windows: .venv\\Scripts\\activate\npip install -r requirements.txt\npytest\nflask --app app run --debug                     # http://localhost:5000/health",
    "django": "python -m venv .venv && . .venv/bin/activate   # Windows: .venv\\Scripts\\activate\npip install -r requirements.txt\npython manage.py test\npython manage.py runserver                      # http://localhost:8000/health",
    "go": "go test ./...\ngo run .           # http://localhost:8080/health",
    "java": "mvn test\nmvn spring-boot:run   # http://localhost:8080/health",
    "devops": "npm test                     # app tests\ndocker compose up --build    # app on http://localhost:3000/health",
    "sql": "python run_exercises.py      # runs every exercise against SQLite\npython -m unittest discover -s tests -t .",
    "docs": "python scripts/check_links.py   # checks every relative link in the notes",
}

# --------------------------------------------------------------------------- templates
# Placeholders: __NAME__ repo name, __TITLE__ title, __BUILD__ one-line goal,
# __PKG__ python package name, __OWNER__ GitHub owner, __YEAR__ year.

NODE_APP = '''import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";

export interface Item {
  id: number;
  title: string;
  createdAt: string;
}

/** In-memory store. Replace with a real database as part of the pending work. */
export function createStore() {
  const items: Item[] = [];
  let nextId = 1;
  return {
    list: (): Item[] => [...items],
    add(title: string): Item {
      const clean = String(title ?? "").trim();
      if (!clean) throw new Error("title is required");
      const item = { id: nextId++, title: clean, createdAt: new Date().toISOString() };
      items.push(item);
      return item;
    },
  };
}

function send(res: ServerResponse, status: number, body: unknown): void {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

async function readJson(req: IncomingMessage): Promise<Record<string, unknown>> {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  if (!raw) return {};
  return JSON.parse(raw) as Record<string, unknown>;
}

export function createApp(): Server {
  const store = createStore();
  return createServer(async (req, res) => {
    const url = new URL(req.url ?? "/", "http://localhost");
    try {
      if (req.method === "GET" && url.pathname === "/health") {
        return send(res, 200, { status: "ok", service: "__NAME__" });
      }
      if (url.pathname === "/api/items") {
        if (req.method === "GET") return send(res, 200, store.list());
        if (req.method === "POST") {
          const body = await readJson(req);
          return send(res, 201, store.add(String(body.title ?? "")));
        }
        return send(res, 405, { error: "method not allowed" });
      }
      return send(res, 404, { error: "not found" });
    } catch (err) {
      return send(res, 400, { error: err instanceof Error ? err.message : "bad request" });
    }
  });
}
'''

NODE_SERVER = '''import { createApp } from "./app.ts";

const port = Number(process.env.PORT ?? 3000);
createApp().listen(port, () => {
  console.log(`__NAME__ running on http://localhost:${port}/health`);
});
'''

NODE_TEST = '''import assert from "node:assert/strict";
import { after, before, test } from "node:test";
import type { AddressInfo } from "node:net";
import { createApp, createStore } from "./app.ts";

const server = createApp();
let base = "";

before(async () => {
  await new Promise<void>((resolve) => server.listen(0, resolve));
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});
after(() => new Promise<void>((resolve) => server.close(() => resolve())));

test("GET /health returns ok", async () => {
  const res = await fetch(`${base}/health`);
  assert.equal(res.status, 200);
  assert.equal((await res.json()).status, "ok");
});

test("POST then GET /api/items", async () => {
  const created = await fetch(`${base}/api/items`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ title: "first" }),
  });
  assert.equal(created.status, 201);
  const list = await (await fetch(`${base}/api/items`)).json();
  assert.equal(list.length, 1);
  assert.equal(list[0].title, "first");
});

test("rejects an empty title", async () => {
  const res = await fetch(`${base}/api/items`, { method: "POST", body: JSON.stringify({ title: " " }) });
  assert.equal(res.status, 400);
});

test("store assigns increasing ids", () => {
  const store = createStore();
  assert.equal(store.add("a").id, 1);
  assert.equal(store.add("b").id, 2);
});
'''

NODE_TSCONFIG = '''{
  "compilerOptions": {
    "target": "ES2023",
    "module": "NodeNext",
    "moduleResolution": "NodeNext",
    "strict": true,
    "noEmit": true,
    "allowImportingTsExtensions": true,
    "erasableSyntaxOnly": true,
    "verbatimModuleSyntax": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["src"]
}
'''

LIB_ITEMS = '''export interface Item {
  id: number;
  title: string;
  done: boolean;
}

/** Pure helpers: easy to unit test, reused by the UI. */
export function addItem(items: Item[], title: string): Item[] {
  const clean = title.trim();
  if (!clean) return items;
  const id = items.reduce((max, i) => Math.max(max, i.id), 0) + 1;
  return [...items, { id, title: clean, done: false }];
}

export function toggleItem(items: Item[], id: number): Item[] {
  return items.map((i) => (i.id === id ? { ...i, done: !i.done } : i));
}

export function remaining(items: Item[]): number {
  return items.filter((i) => !i.done).length;
}
'''

LIB_ITEMS_TEST = '''import assert from "node:assert/strict";
import { test } from "node:test";
import { addItem, remaining, toggleItem, type Item } from "./items.ts";

test("addItem ignores blank titles", () => {
  assert.deepEqual(addItem([], "   "), []);
});

test("addItem assigns ids and toggleItem flips done", () => {
  let items: Item[] = addItem([], "learn");
  items = addItem(items, "build");
  assert.deepEqual(items.map((i) => i.id), [1, 2]);
  items = toggleItem(items, 1);
  assert.equal(remaining(items), 1);
});
'''

NEXT_FILES = {
    "package.json": None,  # built in code
    "next.config.ts": '''import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default nextConfig;
''',
    "tsconfig.json": '''{
  "compilerOptions": {
    "target": "ES2022",
    "lib": [
      "dom",
      "dom.iterable",
      "esnext"
    ],
    "allowJs": false,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "allowImportingTsExtensions": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ]
  },
  "include": [
    "next-env.d.ts",
    "**/*.ts",
    "**/*.tsx",
    ".next/types/**/*.ts",
    ".next/dev/types/**/*.ts"
  ],
  "exclude": [
    "node_modules"
  ]
}
''',
    "app/layout.tsx": '''import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "__TITLE__",
  description: "__BUILD__",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
''',
    "app/page.tsx": '''import ItemList from "./item-list";

export default function Home() {
  return (
    <main>
      <h1>__TITLE__</h1>
      <p className="lead">__BUILD__</p>
      <ItemList />
      <p className="muted">
        Starter page. See <code>PENDING.md</code> for what to build next. Health check:{" "}
        <a href="/api/health">/api/health</a>
      </p>
    </main>
  );
}
''',
    "app/item-list.tsx": '''"use client";

import { useState } from "react";
import { addItem, remaining, toggleItem, type Item } from "../lib/items";

export default function ItemList() {
  const [items, setItems] = useState<Item[]>([]);
  const [title, setTitle] = useState("");

  return (
    <section>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setItems((prev) => addItem(prev, title));
          setTitle("");
        }}
      >
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add an item" aria-label="New item" />
        <button type="submit">Add</button>
      </form>
      <ul>
        {items.map((i) => (
          <li key={i.id}>
            <label>
              <input type="checkbox" checked={i.done} onChange={() => setItems((prev) => toggleItem(prev, i.id))} />{" "}
              {i.done ? <s>{i.title}</s> : i.title}
            </label>
          </li>
        ))}
      </ul>
      <p className="muted">{remaining(items)} remaining</p>
    </section>
  );
}
''',
    "app/api/health/route.ts": '''export function GET() {
  return Response.json({ status: "ok", service: "__NAME__" });
}
''',
    "app/globals.css": None,  # shared CSS
    "lib/items.ts": LIB_ITEMS,
    "lib/items.test.ts": LIB_ITEMS_TEST,
}

APP_CSS = ''':root {
  color-scheme: light dark;
  --bg: #fafafa;
  --fg: #1a1a1a;
  --muted: #666;
  --accent: #2563eb;
  font-family: system-ui, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #111; --fg: #eee; --muted: #999; --accent: #60a5fa; }
}
body { margin: 0; background: var(--bg); color: var(--fg); }
main { max-width: 640px; margin: 0 auto; padding: 48px 16px; }
.lead { font-size: 1.1rem; }
.muted { color: var(--muted); }
a { color: var(--accent); }
form { display: flex; gap: 8px; margin: 24px 0 8px; }
input[type="text"], input:not([type]) { flex: 1; padding: 8px 10px; font: inherit; }
button { padding: 8px 14px; font: inherit; cursor: pointer; }
ul { padding-left: 0; list-style: none; }
li { padding: 6px 0; }
'''

REACT_FILES = {
    "index.html": '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>__TITLE__</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
''',
    "vite.config.ts": '''import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
});
''',
    "tsconfig.json": '''{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "isolatedModules": true,
    "allowImportingTsExtensions": true,
    "skipLibCheck": true,
    "types": ["vite/client", "node"]
  },
  "include": ["src", "vite.config.ts"]
}
''',
    "src/main.tsx": '''import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
''',
    "src/App.tsx": '''import { useState } from "react";
import { addItem, remaining, toggleItem, type Item } from "./lib/items";

export default function App() {
  const [items, setItems] = useState<Item[]>([]);
  const [title, setTitle] = useState("");

  return (
    <main>
      <h1>__TITLE__</h1>
      <p className="lead">__BUILD__</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setItems((prev) => addItem(prev, title));
          setTitle("");
        }}
      >
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add an item" aria-label="New item" />
        <button type="submit">Add</button>
      </form>
      <ul>
        {items.map((i) => (
          <li key={i.id}>
            <label>
              <input type="checkbox" checked={i.done} onChange={() => setItems((prev) => toggleItem(prev, i.id))} />{" "}
              {i.done ? <s>{i.title}</s> : i.title}
            </label>
          </li>
        ))}
      </ul>
      <p className="muted">{remaining(items)} remaining · see PENDING.md for what to build next</p>
    </main>
  );
}
''',
    "src/index.css": None,
    "src/lib/items.ts": LIB_ITEMS,
    "src/lib/items.test.ts": LIB_ITEMS_TEST,
}

WEB_FILES = {
    "package.json": '''{
  "name": "__NAME__",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "start": "node server.js",
    "test": "node --test \\"src/**/*.test.js\\""
  }
}
''',
    "index.html": '''<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>__TITLE__</title>
    <link rel="stylesheet" href="styles.css" />
  </head>
  <body>
    <main>
      <h1>__TITLE__</h1>
      <p class="lead">__BUILD__</p>
      <form id="add-form">
        <input id="title" placeholder="Add an item" aria-label="New item" />
        <button type="submit">Add</button>
      </form>
      <ul id="list"></ul>
      <p class="muted" id="count"></p>
    </main>
    <script type="module" src="src/app.js"></script>
  </body>
</html>
''',
    "styles.css": None,
    "src/logic.js": '''/** Pure functions: no DOM, so they are easy to test. */
export function addItem(items, title) {
  const clean = String(title ?? "").trim();
  if (!clean) return items;
  const id = items.reduce((max, i) => Math.max(max, i.id), 0) + 1;
  return [...items, { id, title: clean, done: false }];
}

export function toggleItem(items, id) {
  return items.map((i) => (i.id === id ? { ...i, done: !i.done } : i));
}

export function remaining(items) {
  return items.filter((i) => !i.done).length;
}
''',
    "src/app.js": '''import { addItem, remaining, toggleItem } from "./logic.js";

const KEY = "__NAME__:items";
let items = load();

function load() {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "[]");
  } catch {
    return [];
  }
}

function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(items));
  } catch {
    /* storage unavailable: keep working in memory */
  }
}

function render() {
  const list = document.getElementById("list");
  list.replaceChildren(
    ...items.map((i) => {
      const li = document.createElement("li");
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = i.done;
      box.addEventListener("change", () => {
        items = toggleItem(items, i.id);
        save();
        render();
      });
      label.append(box, " ", i.title);
      li.append(label);
      return li;
    }),
  );
  document.getElementById("count").textContent = `${remaining(items)} remaining`;
}

document.getElementById("add-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const input = document.getElementById("title");
  items = addItem(items, input.value);
  input.value = "";
  save();
  render();
});

render();
''',
    "src/logic.test.js": '''import assert from "node:assert/strict";
import { test } from "node:test";
import { addItem, remaining, toggleItem } from "./logic.js";

test("addItem ignores blank titles", () => {
  assert.deepEqual(addItem([], "  "), []);
});

test("toggleItem flips done and remaining counts", () => {
  let items = addItem(addItem([], "a"), "b");
  items = toggleItem(items, 2);
  assert.equal(remaining(items), 1);
});
''',
    "server.js": '''// Tiny static file server so the page works over http:// (ES modules need it).
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";

const root = process.cwd();
const types = { ".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png" };
const port = Number(process.env.PORT ?? 3000);

createServer(async (req, res) => {
  const path = new URL(req.url ?? "/", "http://localhost").pathname;
  const file = normalize(join(root, path === "/" ? "index.html" : path));
  if (!file.startsWith(root)) return res.writeHead(403).end();
  try {
    const body = await readFile(file);
    res.writeHead(200, { "content-type": types[extname(file)] ?? "application/octet-stream" }).end(body);
  } catch {
    res.writeHead(404).end("not found");
  }
}).listen(port, () => console.log(`Serving on http://localhost:${port}`));
''',
}

PY_FILES = {
    "pyproject.toml": '''[project]
name = "__NAME__"
version = "0.1.0"
description = "__BUILD__"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
__NAME__ = "__PKG__.__main__:main"
''',
    "__PKG__/__init__.py": '"""__TITLE__: __BUILD__"""\n\n__version__ = "0.1.0"\n',
    "__PKG__/core.py": '''"""Core logic. Kept free of I/O details so it is easy to test."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Note:
    id: int
    text: str
    created_at: str


class NoteStore:
    """Stores notes in a JSON file. Replace or extend as part of the pending work."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def list(self) -> list[Note]:
        if not self.path.exists():
            return []
        return [Note(**n) for n in json.loads(self.path.read_text(encoding="utf-8"))]

    def add(self, text: str) -> Note:
        text = text.strip()
        if not text:
            raise ValueError("text is required")
        notes = self.list()
        note = Note(
            id=max((n.id for n in notes), default=0) + 1,
            text=text,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        notes.append(note)
        self.path.write_text(json.dumps([asdict(n) for n in notes], indent=2), encoding="utf-8")
        return note
''',
    "__PKG__/__main__.py": '''"""Command-line entry point: python -m __PKG__ --help"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .core import NoteStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="__NAME__", description="__BUILD__")
    parser.add_argument("--data", default="data.json", help="where to store data")
    sub = parser.add_subparsers(dest="cmd", required=True)
    add = sub.add_parser("add", help="add a note")
    add.add_argument("text")
    sub.add_parser("list", help="list notes")
    args = parser.parse_args(argv)

    store = NoteStore(Path(args.data))
    if args.cmd == "add":
        note = store.add(args.text)
        print(f"added #{note.id}: {note.text}")
    else:
        for n in store.list():
            print(f"#{n.id}  {n.created_at}  {n.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
''',
    "tests/__init__.py": "",
    "tests/test_core.py": '''import tempfile
import unittest
from pathlib import Path

from __PKG__.__main__ import main
from __PKG__.core import NoteStore


class NoteStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "data.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_add_and_list(self) -> None:
        store = NoteStore(self.path)
        store.add("first")
        store.add("second")
        self.assertEqual([n.id for n in store.list()], [1, 2])

    def test_rejects_blank(self) -> None:
        with self.assertRaises(ValueError):
            NoteStore(self.path).add("   ")

    def test_cli(self) -> None:
        self.assertEqual(main(["--data", str(self.path), "add", "hello"]), 0)
        self.assertEqual(NoteStore(self.path).list()[0].text, "hello")


if __name__ == "__main__":
    unittest.main()
''',
}

FASTAPI_FILES = {
    "requirements.txt": f"fastapi=={V['fastapi']}\nuvicorn=={V['uvicorn']}\nhttpx=={V['httpx']}\npytest=={V['pytest']}\n",
    "pytest.ini": "[pytest]\npythonpath = .\ntestpaths = tests\n",
    "app/__init__.py": "",
    "app/main.py": '''"""__TITLE__: __BUILD__"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="__TITLE__", version="0.1.0")


class ItemIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class Item(ItemIn):
    id: int


# In-memory storage. Replace with a real database as part of the pending work.
_items: dict[int, Item] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "__NAME__"}


@app.get("/api/items")
def list_items() -> list[Item]:
    return list(_items.values())


@app.post("/api/items", status_code=201)
def create_item(data: ItemIn) -> Item:
    item = Item(id=max(_items, default=0) + 1, title=data.title.strip())
    _items[item.id] = item
    return item


@app.get("/api/items/{item_id}")
def get_item(item_id: int) -> Item:
    if item_id not in _items:
        raise HTTPException(status_code=404, detail="item not found")
    return _items[item_id]


@app.delete("/api/items/{item_id}", status_code=204)
def delete_item(item_id: int) -> None:
    if _items.pop(item_id, None) is None:
        raise HTTPException(status_code=404, detail="item not found")
''',
    "tests/__init__.py": "",
    "tests/test_main.py": '''from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    assert client.get("/health").json()["status"] == "ok"


def test_item_crud() -> None:
    created = client.post("/api/items", json={"title": "first"})
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert client.get(f"/api/items/{item_id}").json()["title"] == "first"
    assert client.delete(f"/api/items/{item_id}").status_code == 204
    assert client.get(f"/api/items/{item_id}").status_code == 404


def test_validation() -> None:
    assert client.post("/api/items", json={"title": ""}).status_code == 422
''',
}

FLASK_FILES = {
    "requirements.txt": f"flask=={V['flask']}\npytest=={V['pytest']}\n",
    "pytest.ini": "[pytest]\npythonpath = .\ntestpaths = tests\n",
    "app.py": '''"""__TITLE__: __BUILD__"""

from flask import Flask, jsonify, request


def create_app() -> Flask:
    app = Flask(__name__)
    items: dict[int, dict] = {}  # in-memory; replace with a database later

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "__NAME__"}

    @app.get("/api/items")
    def list_items():
        return jsonify(list(items.values()))

    @app.post("/api/items")
    def create_item():
        title = str((request.get_json(silent=True) or {}).get("title", "")).strip()
        if not title:
            return {"error": "title is required"}, 400
        item = {"id": max(items, default=0) + 1, "title": title}
        items[item["id"]] = item
        return item, 201

    return app


app = create_app()
''',
    "tests/__init__.py": "",
    "tests/test_app.py": '''from app import create_app


def test_health() -> None:
    client = create_app().test_client()
    assert client.get("/health").get_json()["status"] == "ok"


def test_create_and_list() -> None:
    client = create_app().test_client()
    assert client.post("/api/items", json={"title": "first"}).status_code == 201
    assert client.post("/api/items", json={"title": ""}).status_code == 400
    assert [i["title"] for i in client.get("/api/items").get_json()] == ["first"]
''',
}

DJANGO_FILES = {
    "requirements.txt": f"django=={V['django']}\n",
    "manage.py": '''#!/usr/bin/env python
import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
''',
    "config/__init__.py": "",
    "config/settings.py": '''import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
''',
    "config/urls.py": '''from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health", views.health),
    path("", views.home),
]
''',
    "config/wsgi.py": '''import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
application = get_wsgi_application()
''',
    "core/__init__.py": "",
    "core/apps.py": '''from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
''',
    "core/views.py": '''from django.http import HttpResponse, JsonResponse


def health(request):
    return JsonResponse({"status": "ok", "service": "__NAME__"})


def home(request):
    return HttpResponse("<h1>__TITLE__</h1><p>__BUILD__</p><p>See PENDING.md for next steps.</p>")
''',
    "core/tests.py": '''from django.test import TestCase


class SmokeTest(TestCase):
    def test_health(self):
        self.assertEqual(self.client.get("/health").json()["status"], "ok")

    def test_home(self):
        self.assertContains(self.client.get("/"), "__TITLE__")
''',
}

GO_FILES = {
    "go.mod": "module github.com/__OWNER__/__NAME__\n\ngo 1.22\n",
    "store.go": '''package main

import (
	"errors"
	"strings"
	"sync"
)

// Item is a sample resource. Replace it with your project's real model.
type Item struct {
	ID    int    `json:"id"`
	Title string `json:"title"`
}

// Store keeps items in memory and is safe for concurrent use.
type Store struct {
	mu     sync.Mutex
	items  []Item
	nextID int
}

func NewStore() *Store { return &Store{nextID: 1} }

func (s *Store) Add(title string) (Item, error) {
	title = strings.TrimSpace(title)
	if title == "" {
		return Item{}, errors.New("title is required")
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	item := Item{ID: s.nextID, Title: title}
	s.nextID++
	s.items = append(s.items, item)
	return item, nil
}

func (s *Store) List() []Item {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]Item(nil), s.items...)
}
''',
    "main.go": '''package main

import (
	"encoding/json"
	"log"
	"net/http"
	"os"
)

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// NewRouter wires the HTTP routes (Go 1.22+ method patterns).
func NewRouter(store *Store) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "service": "__NAME__"})
	})
	mux.HandleFunc("GET /api/items", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, store.List())
	})
	mux.HandleFunc("POST /api/items", func(w http.ResponseWriter, r *http.Request) {
		var body struct {
			Title string `json:"title"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON"})
			return
		}
		item, err := store.Add(body.Title)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, http.StatusCreated, item)
	})
	return mux
}

func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	log.Printf("__NAME__ listening on http://localhost:%s/health", port)
	log.Fatal(http.ListenAndServe(":"+port, NewRouter(NewStore())))
}
''',
    "main_test.go": '''package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHealth(t *testing.T) {
	rec := httptest.NewRecorder()
	NewRouter(NewStore()).ServeHTTP(rec, httptest.NewRequest(http.MethodGet, "/health", nil))
	if rec.Code != http.StatusOK || !strings.Contains(rec.Body.String(), "ok") {
		t.Fatalf("unexpected response: %d %s", rec.Code, rec.Body.String())
	}
}

func TestCreateItem(t *testing.T) {
	router := NewRouter(NewStore())
	rec := httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/api/items", strings.NewReader(`{"title":"first"}`)))
	if rec.Code != http.StatusCreated {
		t.Fatalf("want 201, got %d", rec.Code)
	}
	rec = httptest.NewRecorder()
	router.ServeHTTP(rec, httptest.NewRequest(http.MethodPost, "/api/items", strings.NewReader(`{"title":" "}`)))
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("want 400, got %d", rec.Code)
	}
}
''',
}

JAVA_PKG = "com/example/app"
JAVA_FILES = {
    "pom.xml": f'''<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>{V['spring-boot']}</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>__NAME__</artifactId>
  <version>0.1.0</version>
  <name>__TITLE__</name>
  <description>__BUILD__</description>
  <properties>
    <java.version>21</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
''',
    f"src/main/java/{JAVA_PKG}/Application.java": '''package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
''',
    f"src/main/java/{JAVA_PKG}/ItemController.java": '''package com.example.app;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
public class ItemController {
    public record Item(int id, String title) {}
    public record ItemRequest(String title) {}

    // In-memory storage. Replace with Spring Data JPA as part of the pending work.
    private final List<Item> items = new CopyOnWriteArrayList<>();
    private final AtomicInteger nextId = new AtomicInteger(1);

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok", "service", "__NAME__");
    }

    @GetMapping("/api/items")
    public List<Item> list() {
        return items;
    }

    @PostMapping("/api/items")
    public ResponseEntity<?> create(@RequestBody ItemRequest body) {
        if (body.title() == null || body.title().isBlank()) {
            return ResponseEntity.badRequest().body(Map.of("error", "title is required"));
        }
        Item item = new Item(nextId.getAndIncrement(), body.title().trim());
        items.add(item);
        return ResponseEntity.status(HttpStatus.CREATED).body(item);
    }
}
''',
    f"src/test/java/{JAVA_PKG}/ItemControllerTest.java": '''package com.example.app;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ItemControllerTest {
    @Autowired MockMvc mvc;

    @Test
    void health() throws Exception {
        mvc.perform(get("/health")).andExpect(status().isOk()).andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void createRejectsBlank() throws Exception {
        mvc.perform(post("/api/items").contentType(MediaType.APPLICATION_JSON).content("{\\"title\\":\\" \\"}"))
            .andExpect(status().isBadRequest());
        mvc.perform(post("/api/items").contentType(MediaType.APPLICATION_JSON).content("{\\"title\\":\\"first\\"}"))
            .andExpect(status().isCreated());
    }
}
''',
}

DEVOPS_EXTRA = {
    "Dockerfile": '''FROM node:24-alpine
WORKDIR /app
COPY package.json ./
COPY src ./src
ENV NODE_ENV=production PORT=3000
EXPOSE 3000
USER node
CMD ["node", "src/server.ts"]
''',
    ".dockerignore": "node_modules\n.git\n.env\n",
    "docker-compose.yml": '''services:
  app:
    build: .
    ports:
      - "3000:3000"
    environment:
      PORT: "3000"
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:3000/health"]
      interval: 10s
      timeout: 3s
      retries: 3
''',
    "infra/README.md": '''# Infrastructure

Put the infrastructure for this project here (see `PENDING.md` for the list):
for example Kubernetes manifests, Helm charts, Terraform, Nginx config,
monitoring config or deploy scripts. The sample app in `src/` is the thing
being deployed.
''',
}

SQL_FILES = {
    "schema.sql": '''-- Sample shop schema. Works in SQLite and PostgreSQL.
CREATE TABLE customers (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  city TEXT NOT NULL
);
CREATE TABLE products (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  price NUMERIC NOT NULL
);
CREATE TABLE orders (
  id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(id),
  ordered_on DATE NOT NULL
);
CREATE TABLE order_items (
  order_id INTEGER NOT NULL REFERENCES orders(id),
  product_id INTEGER NOT NULL REFERENCES products(id),
  quantity INTEGER NOT NULL
);
''',
    "seed.sql": '''INSERT INTO customers VALUES (1,'Asha','Hyderabad'),(2,'Ravi','Pune'),(3,'Meera','Hyderabad');
INSERT INTO products VALUES (1,'Keyboard',1500),(2,'Mouse',600),(3,'Monitor',9000);
INSERT INTO orders VALUES (1,1,'2026-01-05'),(2,2,'2026-01-09'),(3,1,'2026-02-11');
INSERT INTO order_items VALUES (1,1,1),(1,2,2),(2,3,1),(3,2,1);
''',
    "exercises/01_select.sql": "-- 1. List all customers from Hyderabad, ordered by name.\nSELECT name FROM customers WHERE city = 'Hyderabad' ORDER BY name;\n",
    "exercises/02_join.sql": "-- 2. Total amount spent per customer (join + group by).\nSELECT c.name, SUM(p.price * oi.quantity) AS total\nFROM customers c\nJOIN orders o ON o.customer_id = c.id\nJOIN order_items oi ON oi.order_id = o.id\nJOIN products p ON p.id = oi.product_id\nGROUP BY c.name\nORDER BY total DESC;\n",
    "exercises/03_window.sql": "-- 3. Rank products by price (window function).\nSELECT name, price, RANK() OVER (ORDER BY price DESC) AS price_rank FROM products;\n",
    "run_exercises.py": '''"""Run every exercise in exercises/ against an in-memory SQLite database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.executescript((ROOT / "schema.sql").read_text(encoding="utf-8"))
    db.executescript((ROOT / "seed.sql").read_text(encoding="utf-8"))
    return db


def run(path: Path, db: sqlite3.Connection) -> list[tuple]:
    return db.execute(path.read_text(encoding="utf-8")).fetchall()


def main() -> None:
    db = connect()
    for path in sorted((ROOT / "exercises").glob("*.sql")):
        print(f"== {path.name}")
        for row in run(path, db):
            print("  ", row)


if __name__ == "__main__":
    main()
''',
    "tests/__init__.py": "",
    "tests/test_exercises.py": '''import unittest
from pathlib import Path

from run_exercises import ROOT, connect, run


class ExerciseTest(unittest.TestCase):
    def test_every_exercise_runs(self) -> None:
        db = connect()
        for path in sorted((ROOT / "exercises").glob("*.sql")):
            with self.subTest(path.name):
                self.assertTrue(run(path, db), f"{path.name} returned no rows")

    def test_totals(self) -> None:
        rows = run(Path(ROOT / "exercises" / "02_join.sql"), connect())
        self.assertEqual(rows[0], ("Ravi", 9000))


if __name__ == "__main__":
    unittest.main()
''',
}

DOCS_FILES = {
    "notes/README.md": '''# Notes

Index of write-ups. Add one file per topic and link it here.

- [Template](template.md)
''',
    "notes/template.md": '''# Topic title

## Problem
What are we solving? Requirements and constraints.

## Approach
Main idea, diagram, data model.

## Trade-offs
What you chose, what you gave up, alternatives.

## References
Links you learned from.
''',
    "scripts/check_links.py": '''"""Fail if any relative Markdown link points to a file that does not exist."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\\[[^\\]]*\\]\\(([^)#\\s]+)")


def broken_links() -> list[str]:
    bad = []
    for md in ROOT.rglob("*.md"):
        if ".git" in md.parts:
            continue
        for target in LINK.findall(md.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("mailto:"):
                continue
            if not (md.parent / target).exists():
                bad.append(f"{md.relative_to(ROOT)} -> {target}")
    return bad


if __name__ == "__main__":
    problems = broken_links()
    for p in problems:
        print("broken:", p)
    print("ok" if not problems else f"{len(problems)} broken link(s)")
    sys.exit(1 if problems else 0)
''',
}

CI = {
    "node": '''      - uses: actions/setup-node@v4
        with:
          node-version: 24
      - run: npm install --no-audit --no-fund
      - run: npm run typecheck
      - run: npm test
''',
    "next": '''      - uses: actions/setup-node@v4
        with:
          node-version: 24
      - run: npm install --no-audit --no-fund
      - run: npm test
      - run: npm run build
''',
    "react": '''      - uses: actions/setup-node@v4
        with:
          node-version: 24
      - run: npm install --no-audit --no-fund
      - run: npm run typecheck
      - run: npm test
      - run: npm run build
''',
    "web": '''      - uses: actions/setup-node@v4
        with:
          node-version: 24
      - run: npm test
''',
    "python": '''      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m unittest discover -s tests -t .
''',
    "fastapi": '''      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest
''',
    "flask": '''      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: pytest
''',
    "django": '''      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python manage.py check
      - run: python manage.py test
''',
    "go": '''      - uses: actions/setup-go@v5
        with:
          go-version: "1.23"
      - run: go vet ./...
      - run: go test ./...
''',
    "java": '''      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "21"
          cache: maven
      - run: mvn -B test
''',
    "devops": '''      - uses: actions/setup-node@v4
        with:
          node-version: 24
      - run: npm install --no-audit --no-fund
      - run: npm run typecheck
      - run: npm test
      - run: docker compose config -q
      - run: docker build -t __NAME__ .
''',
    "sql": '''      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m unittest discover -s tests -t .
''',
    "docs": '''      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python scripts/check_links.py
''',
}

GITIGNORE = """node_modules/
.next/
dist/
build/
coverage/
next-env.d.ts
*.tsbuildinfo
__pycache__/
*.pyc
.venv/
.pytest_cache/
db.sqlite3
data.json
target/
.env
.env.*
!.env.example
*.log
.DS_Store
"""

TEMPLATE_FILES = {
    "web": WEB_FILES, "next": NEXT_FILES, "react": REACT_FILES, "python": PY_FILES,
    "fastapi": FASTAPI_FILES, "flask": FLASK_FILES, "django": DJANGO_FILES,
    "go": GO_FILES, "java": JAVA_FILES, "sql": SQL_FILES, "docs": DOCS_FILES,
}

TEMPLATE_LABEL = {
    "node": "TypeScript on Node.js (no framework yet, runs with zero dependencies)",
    "next": "Next.js + React + TypeScript", "react": "React + Vite + TypeScript",
    "web": "Plain HTML, CSS and JavaScript", "python": "Python standard library CLI",
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django", "go": "Go standard library",
    "java": "Spring Boot (Java 21)", "devops": "Node.js app + Docker + Docker Compose",
    "sql": "SQL exercises run on SQLite", "docs": "Markdown notes with a link checker",
}


# --------------------------------------------------------------------------- logic

def pick_template(p: dict) -> str:
    stack, track, name = p["stack"], p["track"], p["repo"]
    s = stack.lower()
    if re.search(r"java", s) or "spring" in s:
        return "java"
    if s.startswith("go"):
        return "go"
    if "django" in s:
        return "django"
    if "flask" in s:
        return "flask"
    if "fastapi" in s:
        return "fastapi"
    if name == "sql-practice-50":
        return "sql"
    if stack in ("Markdown, diagrams", "Git"):
        return "docs"
    if "next.js" in s or "mern" in s:
        return "next"
    if "react" in s or "vue" in s or "svelte" in s:
        return "react"
    if track.startswith("1.") and name != "ts-fundamentals-lab":
        return "web"
    if track.startswith("11."):
        return "devops"
    if "python" in s or "pandas" in s or track.startswith("3."):
        return "python"
    return "node"


def title_of(name: str) -> str:
    return " ".join(w.upper() if w in ACRONYMS else w.capitalize() for w in name.split("-"))


def pending_items(p: dict, template: str) -> list[tuple[str, list[str]]]:
    """Grouped checklist of what is still to do in this project."""
    base = BASELINE[template]
    integrate = []
    for part in [x.strip() for x in p["stack"].split(",") if x.strip()]:
        low = part.lower()
        if any(b == low or b in low.split(" or ") for b in base):
            continue
        if " or " in low or "/" in part:
            integrate.append(f"Choose one and integrate it: **{part}**")
        else:
            integrate.append(f"Integrate **{part}**")
    if template == "node" and any(k in p["stack"].lower() for k in ("express", "hono", "nest", "fastify")):
        integrate.append("Replace the built-in `node:http` server in `src/app.ts` with the framework above")
    if template in ("node", "fastapi", "flask", "go", "java") and p["track"].split(".")[0] in {"4", "5", "6", "7", "8"}:
        integrate.append("Replace the in-memory store with a real database (and add migrations)")

    skills = [f"Practise: {s.strip()}" for s in p["skills"].split(",") if s.strip()]
    refs = [f"Study [{r['name']}]({r['url']}) ({r['license']}). Note what you'd reuse and credit it if you do"
            for r in p["references"]]

    groups = [
        ("Setup (done by the generator)", [
            "~~Starter app that runs~~ ✅", "~~Sample tests passing~~ ✅",
            "~~CI workflow (`.github/workflows/ci.yml`)~~ ✅", "~~README, LICENSE, .gitignore, .env.example~~ ✅",
        ]),
        ("Research", refs or ["Find 1-2 open-source projects that solve a similar problem and read their code"]),
        ("Integrations to add", integrate or ["Nothing extra: the starter already uses this stack"]),
        ("Build the project", [
            f"Core goal: **{p['build']}**",
            "Write down the features (user stories) in this file before coding",
            "Replace the sample `items` code with the real domain model",
            "Handle errors and empty/loading states",
        ]),
        ("Skills to practise", skills),
        ("Quality", [
            "Tests for every new feature (aim for the main flows, not 100%)",
            "Keep CI green on every push",
            "Put every secret in `.env` and document it in `.env.example`",
        ]),
        ("Ship it", [
            "Create the GitHub repo and push (`publish_all.sh` does this for every project)",
            "Deploy it (Vercel, Render, Railway, Fly.io or similar) and add the live link to the README",
            "Add screenshots or a short GIF to the README",
            "Tick this project off in `LEARNING_PATH.md` in dev-projects-index",
        ]),
    ]
    return groups


def fill(text: str, ctx: dict) -> str:
    for k, v in ctx.items():
        text = text.replace(f"__{k}__", v)
    return text


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def files_for(template: str, ctx: dict) -> dict[str, str]:
    files: dict[str, str] = {}
    if template in ("node", "devops"):
        files["src/app.ts"] = NODE_APP
        files["src/server.ts"] = NODE_SERVER
        files["src/app.test.ts"] = NODE_TEST
        files["tsconfig.json"] = NODE_TSCONFIG
        files["package.json"] = json.dumps({
            "name": ctx["NAME"], "version": "0.1.0", "private": True, "type": "module",
            "description": ctx["BUILD"], "engines": {"node": ">=22.18"},
            "scripts": {"start": "node src/server.ts", "dev": "node --watch src/server.ts",
                        "test": 'node --test "src/**/*.test.ts"', "typecheck": "tsc"},
            "devDependencies": {"@types/node": V["@types/node"], "typescript": V["typescript"]},
        }, indent=2) + "\n"
        if template == "devops":
            files.update(DEVOPS_EXTRA)
    else:
        for rel, body in TEMPLATE_FILES[template].items():
            if body is None:
                continue
            files[rel.replace("__PKG__", ctx["PKG"])] = body
    if template == "next":
        files["app/globals.css"] = APP_CSS
        files["package.json"] = json.dumps({
            "name": ctx["NAME"], "version": "0.1.0", "private": True, "type": "module",
            "scripts": {"dev": "next dev", "build": "next build", "start": "next start",
                        "test": 'node --test "lib/**/*.test.ts"', "typecheck": "tsc --noEmit"},
            "dependencies": {"next": V["next"], "react": V["react"], "react-dom": V["react-dom"]},
            "devDependencies": {k: V[k] for k in ("@types/node", "@types/react", "@types/react-dom", "typescript")},
        }, indent=2) + "\n"
    if template == "react":
        files["src/index.css"] = APP_CSS
        files["package.json"] = json.dumps({
            "name": ctx["NAME"], "version": "0.1.0", "private": True, "type": "module",
            "scripts": {"dev": "vite", "build": "vite build", "preview": "vite preview",
                        "test": 'node --test "src/**/*.test.ts"', "typecheck": "tsc --noEmit"},
            "dependencies": {"react": V["react"], "react-dom": V["react-dom"]},
            "devDependencies": {k: V[k] for k in ("@types/node", "@types/react", "@types/react-dom",
                                                  "@vitejs/plugin-react", "typescript", "vite")},
        }, indent=2) + "\n"
    if template == "web":
        files["styles.css"] = APP_CSS
    return {k: fill(v, ctx) for k, v in files.items()}


def readme(p: dict, template: str, ctx: dict, n_pending: int) -> str:
    run = fill(RUN[template], ctx)
    refs = "\n".join(f"- [{r['name']}]({r['url']}) ({r['license']}, ⭐ {r['stars']:,})"
                     for r in p["references"]) or "- None picked yet. Find one and add it here."
    return f"""# {ctx['TITLE']}

[![CI](https://github.com/{ctx['OWNER']}/{ctx['NAME']}/actions/workflows/ci.yml/badge.svg)](https://github.com/{ctx['OWNER']}/{ctx['NAME']}/actions/workflows/ci.yml)

{p['build']}.

| | |
|---|---|
| **Track** | {p['track']} |
| **Level** | {p['level']} |
| **Target stack** | {p['stack']} |
| **Skills** | {p['skills']} |
| **Starter** | {TEMPLATE_LABEL[template]} |
| **Status** | 🚧 Starter ready, {n_pending} tasks pending ([PENDING.md](PENDING.md)) |

Project #{p['id']} of the learning path in
[dev-projects-index](https://github.com/{ctx['OWNER']}/dev-projects-index/blob/main/LEARNING_PATH.md).

## Quick start

```bash
{run}
```

The starter is intentionally small: a working, tested skeleton so you can
start integrating straight away. Everything still to build is listed in
[PENDING.md](PENDING.md).

## References to learn from

{refs}

These belong to their authors. Read them to learn; if you copy any code, keep
its license notice and credit it here.

## License

MIT © {ctx['YEAR']} {ctx['OWNER']}
"""


def pending_md(p: dict, ctx: dict, groups: list[tuple[str, list[str]]]) -> str:
    lines = [f"# Pending work: {ctx['TITLE']}", "",
             "Tick items off (`[x]`) as you finish them.", ""]
    for heading, items in groups:
        lines += [f"## {heading}", ""]
        done = heading.startswith("Setup")
        lines += [f"- [{'x' if done else ' '}] {i.replace('~~', '').replace(' ✅', '')}" for i in items]
        lines.append("")
    return "\n".join(lines)


def license_text(owner: str, year: str) -> str:
    return f"""MIT License

Copyright (c) {year} {owner}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""


def env_example(template: str) -> str:
    lines = ["# Copy to .env and fill in. Never commit .env.", ""]
    port = {"next": 3000, "react": 5173, "fastapi": 8000, "flask": 5000, "django": 8000,
            "go": 8080, "java": 8080}.get(template, 3000)
    if template not in ("sql", "docs", "python"):
        lines.append(f"PORT={port}")
    lines += ["# DATABASE_URL=postgres://user:password@localhost:5432/app",
              "# API keys for the integrations listed in PENDING.md go here"]
    return "\n".join(lines) + "\n"


def git_identity() -> list[str]:
    """Reuse this index repo's git identity (it may be set only locally here)."""
    opts = []
    for key in ("user.name", "user.email"):
        val = subprocess.run(["git", "config", key], cwd=ROOT, capture_output=True,
                             text=True).stdout.strip()
        if val:
            opts += ["-c", f"{key}={val}"]
    return opts


IDENTITY: list[str] = []


def git(repo: Path, *args: str) -> None:
    r = subprocess.run(["git", *IDENTITY, *args], cwd=repo, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"git {args[0]} failed in {repo}: {r.stderr.strip()}")


def scaffold(p: dict, out: Path, owner: str, force: bool) -> tuple[str, int, bool]:
    template = pick_template(p)
    repo = out / p["repo"]
    groups = pending_items(p, template)
    n_pending = sum(len(items) for h, items in groups if not h.startswith("Setup"))
    if repo.exists():
        if not force:
            return template, n_pending, False
        def _writable(func, path, _exc):  # git marks objects read-only on Windows
            Path(path).chmod(0o700)
            func(path)
        shutil.rmtree(repo, onexc=_writable)
    year = str(datetime.now(timezone.utc).year)
    ctx = {"NAME": p["repo"], "TITLE": title_of(p["repo"]), "BUILD": p["build"],
           "PKG": p["repo"].replace("-", "_").lstrip("0123456789_") or "app",
           "OWNER": owner, "YEAR": year}
    files = files_for(template, ctx)
    files["README.md"] = readme(p, template, ctx, n_pending)
    files["PENDING.md"] = pending_md(p, ctx, groups)
    files["LICENSE"] = license_text(owner, year)
    files[".gitignore"] = GITIGNORE
    files[".env.example"] = env_example(template)
    files[".github/workflows/ci.yml"] = (
        "name: CI\n\non:\n  push:\n  pull_request:\n\njobs:\n  test:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - uses: actions/checkout@v4\n" + fill(CI[template], ctx))
    for rel, body in files.items():
        write(repo / rel, body)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", f"Initial scaffold: {ctx['TITLE']}\n\n{p['build']}. "
        f"Starter: {TEMPLATE_LABEL[template]}. See PENDING.md for remaining work.\n\n"
        "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    return template, n_pending, True


def write_overview(out: Path, owner: str, rows: list[dict]) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = ["# Learning Projects Workspace", "",
             f"{len(rows)} separate git repositories, one per project in "
             "`dev-projects-index/LEARNING_PATH.md`. Each folder is its own repo with a working "
             "starter, tests, CI and a `PENDING.md` checklist.", "",
             f"_Generated {today} by `dev-projects-index/scripts/scaffold_repos.py`._", "",
             "- Publish all to GitHub: install the GitHub CLI, run `gh auth login`, then `bash publish_all.sh`",
             "- Status of every repo: `dev-projects-index/PROJECTS_STATUS.md`", "",
             "| # | Repo | Starter | Level | Pending |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['id']} | [{r['repo']}]({r['repo']}/README.md) | {r['template']} | "
                     f"{r['level']} | [{r['pending']} tasks]({r['repo']}/PENDING.md) |")
    write(out / "README.md", "\n".join(lines) + "\n")

    sh = ["#!/usr/bin/env bash",
          "# Create every learning repo on GitHub and push it. Safe to re-run: repos that",
          "# already exist on GitHub are skipped. Needs: gh auth login",
          "set -euo pipefail",
          f'OWNER="${{OWNER:-{owner}}}"',
          'VISIBILITY="${VISIBILITY:---public}"   # set VISIBILITY=--private to keep them private',
          'cd "$(dirname "$0")"', ""]
    for r in rows:
        desc = r["build"].replace('"', "'")
        sh.append(f'if gh repo view "$OWNER/{r["repo"]}" >/dev/null 2>&1; then echo "skip {r["repo"]} (exists)"; '
                  f'else gh repo create "$OWNER/{r["repo"]}" $VISIBILITY --source "{r["repo"]}" --push '
                  f'--description "{desc}" && echo "created {r["repo"]}"; sleep 2; fi')
    write(out / "publish_all.sh", "\n".join(sh) + "\n")


def write_status(owner: str, rows: list[dict]) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total = sum(r["pending"] for r in rows)
    lines = ["# Projects Status", "",
             f"Every project in [LEARNING_PATH.md](LEARNING_PATH.md) has its own repository with a "
             f"working starter. **{len(rows)} repos, {total} pending tasks in total.**", "",
             f"_Generated {today} by `scripts/scaffold_repos.py`. GitHub links work once "
             "`publish_all.sh` has been run._", "",
             "Legend: ✅ starter, tests and CI done · 🚧 project work pending (see each repo's PENDING.md)", ""]
    for track in dict.fromkeys(r["track"] for r in rows):
        lines += [f"## {track}", "", "| # | Repo | Starter | Level | Status | Pending tasks |",
                  "|---|---|---|---|---|---|"]
        for r in (r for r in rows if r["track"] == track):
            url = f"https://github.com/{owner}/{r['repo']}"
            lines.append(f"| {r['id']} | [{r['repo']}]({url}) | {r['template']} | {r['level']} | "
                         f"✅ 🚧 | [{r['pending']}]({url}/blob/main/PENDING.md) |")
        lines.append("")
    write(ROOT / "PROJECTS_STATUS.md", "\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT.parent / "learning-projects"))
    ap.add_argument("--owner", default=None, help="GitHub user name (default: git config user.name)")
    ap.add_argument("--only", nargs="*", help="only these repo names")
    ap.add_argument("--force", action="store_true", help="delete and regenerate existing repo folders")
    args = ap.parse_args()

    IDENTITY[:] = git_identity()
    owner = args.owner or subprocess.run(["git", "config", "user.name"], cwd=ROOT, capture_output=True,
                                         text=True).stdout.strip() or "your-github-user"
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    projects = json.loads((ROOT / "data" / "learning_path.json").read_text(encoding="utf-8"))

    rows, created = [], 0
    for p in projects:
        if args.only and p["repo"] not in args.only:
            template = pick_template(p)
            groups = pending_items(p, template)
            pending = sum(len(i) for h, i in groups if not h.startswith("Setup"))
        else:
            template, pending, made = scaffold(p, out, owner, args.force)
            created += made
            print(f"{'created' if made else 'exists '}  {p['repo']:<28} {template}")
        rows.append({**p, "template": template, "pending": pending})

    write_overview(out, owner, rows)
    write_status(owner, rows)
    print(f"\n{created} repos created in {out}; overview, publish_all.sh and PROJECTS_STATUS.md written")


if __name__ == "__main__":
    main()
