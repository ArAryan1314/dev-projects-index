"""
Build a hands-on learning path of original project ideas.

Each idea is something to build yourself (your own code, your own repo). For
each one, the script looks up 1-2 permissively licensed reference projects in
data/projects.json, so you can study how others solved the same problem.

Outputs: LEARNING_PATH.md, data/learning_path.json, data/learning_path.csv
Usage:   python scripts/build_learning_path.py
(No network needed: it only reads data/projects.json.)
"""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PERMISSIVE = {"MIT", "Apache-2.0", "BSD-3-Clause", "BSD-2-Clause", "ISC",
              "CC0-1.0", "Unlicense", "MPL-2.0"}
LEVELS = {"B": "beginner", "I": "intermediate", "A": "advanced"}

# track -> [(repo name, level, stack, what you build, skills, keywords...)]
# The first keyword must appear in a reference repo and, when there are several
# keywords, at least one more must too. "lang:go" matches the repo's language.
TRACKS: dict[str, list[tuple]] = {
    "1. Web Foundations (HTML, CSS, JavaScript, TypeScript)": [
        ("html-css-landing", "B", "HTML, CSS", "Responsive product landing page", "Flexbox, grid, media queries", "landing", "tailwind", "responsive"),
        ("js-dom-games", "B", "JavaScript", "Tic-tac-toe, memory game and 2048 in vanilla JS", "DOM events, state, localStorage", "game", "javascript"),
        ("weather-widget", "B", "JavaScript, fetch", "Weather card using a free weather API", "fetch, async/await, error states", "weather", "api"),
        ("todo-vanilla", "B", "JavaScript", "Todo app with filters and persistence", "CRUD in the browser, localStorage", "todo", "javascript"),
        ("ts-fundamentals-lab", "B", "TypeScript, Vitest", "Typed exercises with unit tests", "Types, generics, narrowing, testing", "typescript", "learn"),
        ("css-animation-gallery", "B", "CSS", "Gallery of pure-CSS animations and transitions", "Keyframes, transforms, accessibility", "animation", "css"),
        ("form-validator", "B", "HTML, TypeScript", "Sign-up form with live validation", "Constraint API, regex, UX", "form", "validation"),
        ("markdown-previewer", "B", "TypeScript", "Live Markdown editor and preview", "Parsing, sanitizing HTML", "markdown", "editor"),
    ],
    "2. Frontend with React and Next.js": [
        ("react-starter-kit", "B", "React, Vite, TypeScript", "Your own reusable React starter", "Components, props, hooks, linting", "react", "starter", "vite"),
        ("movie-explorer", "B", "React, TMDB API", "Search and browse movies with details pages", "Routing, data fetching, pagination", "movie", "react"),
        ("crypto-screener", "I", "React, Tailwind", "Live crypto price table with charts", "Polling, charts, context", "crypto", "dashboard", "price", "react"),
        ("next-blog-mdx", "I", "Next.js, MDX", "Personal blog with tags and RSS", "SSG, MDX, SEO metadata", "blog", "nextjs", "mdx"),
        ("admin-dashboard-ui", "I", "Next.js, shadcn/ui", "Admin dashboard with tables, charts, dark mode", "Layouts, data tables, theming", "dashboard", "admin", "nextjs"),
        ("ecommerce-storefront", "I", "Next.js, Zustand", "Storefront with cart and checkout UI", "Global state, server components", "ecommerce", "store", "shop"),
        ("kanban-board", "I", "React, dnd-kit", "Drag-and-drop task board", "Drag and drop, optimistic UI", "kanban", "board", "drag"),
        ("component-library", "A", "React, Storybook, tsup", "Publishable UI component library", "Storybook, a11y, npm publishing", "component", "ui", "library"),
        ("i18n-portfolio", "I", "Next.js, next-intl", "Multilingual portfolio site", "i18n, routing, deployment", "portfolio", "nextjs"),
        ("pwa-notes", "I", "React, Workbox", "Offline-first notes PWA", "Service workers, IndexedDB", "pwa", "offline", "notes"),
        ("3d-product-viewer", "A", "React Three Fiber", "Interactive 3D product page", "Three.js, GSAP, performance", "three", "3d", "webgl"),
        ("vue-or-svelte-port", "I", "Vue or SvelteKit", "Rebuild movie-explorer in a second framework", "Compare frameworks", "svelte", "vue"),
    ],
    "3. Python": [
        ("py-automation-kit", "B", "Python", "CLI scripts: file renamer, CSV cleaner, backups", "argparse, pathlib, csv", "automation", "cli", "script"),
        ("web-scraper-jobs", "B", "Python, httpx, BeautifulSoup", "Job listing scraper to CSV", "HTTP, HTML parsing, rate limits", "scraper", "scraping", "crawler"),
        ("expense-cli", "B", "Python, SQLite, Typer", "Personal expense tracker in the terminal", "SQLite, CLI UX, tests", "cli", "sqlite", "expense"),
        ("python-oop-bank", "B", "Python, pytest", "Bank account simulator with tests", "OOP, exceptions, pytest", "pytest", "learn", "python"),
        ("telegram-bot", "I", "Python, python-telegram-bot", "Reminder bot for Telegram", "Bot APIs, scheduling", "bot", "telegram"),
        ("pdf-report-generator", "I", "Python, ReportLab", "Turn CSV data into PDF reports", "Templating, file generation", "pdf", "report"),
        ("data-analysis-notebooks", "I", "Pandas, Jupyter", "Exploratory analysis of an open dataset", "Pandas, plotting", "pandas", "data", "jupyter"),
        ("django-blog", "I", "Django", "Blog with admin, comments and auth", "Django ORM, admin, templates", "django", "blog"),
        ("flask-url-api", "B", "Flask", "Small REST API for bookmarks", "Routing, JSON, blueprints", "flask", "api"),
        ("async-downloader", "A", "Python asyncio, aiohttp", "Concurrent file downloader with progress", "asyncio, concurrency limits", "async", "asyncio"),
    ],
    "4. Backend with Node.js and Bun": [
        ("express-rest-api", "B", "Node, Express", "Notes REST API with validation", "Routing, middleware, Zod", "express", "api", "rest"),
        ("hono-bun-api", "I", "Bun, Hono", "Fast API on Bun with OpenAPI docs", "Bun runtime, OpenAPI", "hono", "bun"),
        ("nestjs-inventory", "A", "NestJS, PostgreSQL", "Inventory service with modules and DI", "NestJS, DI, TypeORM/Prisma", "nestjs", "nest"),
        ("graphql-bookstore", "I", "Apollo Server or GraphQL Yoga", "Bookstore GraphQL API", "Schemas, resolvers, DataLoader", "graphql", "api"),
        ("file-upload-service", "I", "Node, S3/R2", "Upload, resize and serve images", "Multipart, presigned URLs", "upload", "s3", "storage"),
        ("rate-limiter", "I", "Node, Redis", "Rate-limiting middleware package", "Token bucket, Redis", "rate", "redis", "limit"),
        ("email-service", "I", "Node, Resend/Nodemailer, React Email", "Transactional email microservice", "Templates, queues", "email", "mail"),
        ("cron-job-runner", "I", "Bun, node-cron", "Scheduled jobs with logs and retries", "Scheduling, idempotency", "cron", "schedule", "job"),
        ("api-gateway", "A", "Node, Fastify", "Gateway with routing, auth and caching", "Proxies, caching, observability", "gateway", "proxy"),
        ("bun-cli-tool", "B", "Bun, TypeScript", "Developer CLI published to npm", "CLI args, packaging", "cli", "bun"),
    ],
    "5. Databases and SQL": [
        ("sql-practice-50", "B", "PostgreSQL", "50 SQL exercises on a sample schema", "Joins, group by, window functions", "sql", "postgres", "learn"),
        ("prisma-blog-schema", "B", "Prisma, PostgreSQL", "Relational schema with migrations and seeds", "Relations, migrations", "prisma", "orm"),
        ("drizzle-saas-db", "I", "Drizzle, PostgreSQL", "Multi-tenant SaaS schema", "Tenancy, indexes", "drizzle", "postgres"),
        ("mongodb-reviews-api", "I", "MongoDB, Mongoose", "Product reviews API", "Document modeling, aggregation", "mongodb", "mongo"),
        ("redis-cache-demo", "I", "Redis", "Cache layer for a slow API", "TTL, cache invalidation", "redis", "cache"),
        ("full-text-search", "I", "PostgreSQL or Meilisearch", "Search over articles with ranking", "Full-text search, indexes", "search", "meilisearch", "full-text", "postgres"),
        ("db-backup-tool", "I", "Python or Bash", "Scheduled DB backups to cloud storage", "pg_dump, retention", "backup", "database"),
        ("supabase-realtime-app", "I", "Supabase", "App using Supabase auth, DB and RLS", "Row-level security", "supabase", "postgres"),
    ],
    "6. API and Third-Party Integrations": [
        ("stripe-payments-demo", "I", "Next.js, Stripe", "Checkout, subscriptions and webhooks", "Payments, webhook signatures", "stripe", "payment", "billing"),
        ("razorpay-integration", "I", "Node, Razorpay", "Indian payment gateway flow", "Orders, signature verification", "payment", "razorpay"),
        ("github-webhook-bot", "I", "Node, Octokit", "Bot that labels issues and PRs", "GitHub API, webhooks", "github", "bot", "webhook"),
        ("slack-notifier", "B", "Node, Slack API", "Post alerts to Slack from any app", "Incoming webhooks, Block Kit", "slack", "notification"),
        ("google-sheets-sync", "I", "Python, Google Sheets API", "Sync a database table to Google Sheets", "OAuth service accounts", "google", "sheets"),
        ("twilio-sms-otp", "I", "Node, Twilio", "Phone OTP verification", "SMS APIs, rate limits", "sms", "otp", "twilio"),
        ("maps-store-locator", "I", "React, Leaflet/Mapbox", "Store locator with geosearch", "Maps APIs, geocoding", "map", "leaflet", "mapbox"),
        ("calendar-booking", "A", "Next.js, Google Calendar API", "Appointment booking like a mini Calendly", "OAuth, timezones", "calendar", "booking", "schedul"),
        ("zapier-lite", "A", "Node, BullMQ", "Trigger-action automation engine", "Queues, connectors, retries", "workflow", "automation", "n8n"),
        ("openapi-client-gen", "I", "TypeScript, openapi-typescript", "Typed SDK generated from an OpenAPI spec", "OpenAPI, codegen", "openapi", "sdk"),
        ("cms-headless-site", "I", "Next.js, Strapi/Sanity/Payload", "Marketing site driven by a headless CMS", "CMS integration, ISR", "cms", "headless"),
        ("whatsapp-cloud-bot", "A", "Node, WhatsApp Cloud API", "Order-status bot over WhatsApp", "Meta APIs, webhooks", "whatsapp", "bot"),
    ],
    "7. Authentication and Security": [
        ("jwt-auth-api", "B", "Node or FastAPI", "Sign-up, login and refresh tokens", "Hashing, JWT, refresh rotation", "auth", "jwt"),
        ("oauth-social-login", "I", "Next.js, Auth.js/Better Auth", "Google and GitHub login", "OAuth 2.0, sessions", "auth", "oauth", "login"),
        ("rbac-admin", "I", "Next.js, Prisma", "Role-based access control panel", "Permissions, middleware", "rbac", "role", "permission"),
        ("2fa-totp", "I", "Node, otplib", "Two-factor auth with authenticator apps", "TOTP, QR codes, backup codes", "2fa", "totp", "auth"),
        ("passkeys-demo", "A", "SimpleWebAuthn", "Passwordless login with passkeys", "WebAuthn", "webauthn", "passkey"),
        ("api-key-manager", "I", "Hono, PostgreSQL", "Issue, hash and revoke API keys", "Key hashing, scopes", "api", "key"),
        ("owasp-top10-lab", "A", "Any", "Deliberately vulnerable app plus the fixes", "OWASP Top 10, secure coding", "security", "owasp"),
    ],
    "8. Full-Stack Applications": [
        ("taskflow-api", "I", "FastAPI, PostgreSQL, Docker", "Task manager backend", "REST, auth, Docker", "fastapi", "task"),
        ("taskflow-web", "I", "Next.js, TanStack Query", "Frontend for taskflow-api", "API client, caching, forms", "nextjs", "task", "todo"),
        ("expense-split", "I", "Next.js, Prisma", "Split expenses among friends", "Full-stack CRUD, server actions", "expense", "split"),
        ("url-shortener-saas", "I", "Next.js, Redis", "Short links with click analytics", "Redirects, analytics", "url", "shortener", "link"),
        ("job-board", "I", "MERN", "Job board with search and filters", "Search, filters, auth", "job", "board"),
        ("lms-mini", "A", "Next.js, Stripe, Supabase", "Course platform with paid enrollment", "Payments, video, access control", "lms", "course", "learning"),
        ("social-feed", "A", "Next.js, PostgreSQL", "Posts, likes, follows and infinite scroll", "Feeds, pagination", "social", "twitter", "feed"),
        ("invoice-generator", "I", "Next.js, react-pdf", "Create and email invoices as PDFs", "PDF generation, email", "invoice", "pdf"),
        ("event-ticketing", "A", "Next.js, Stripe, QR", "Sell tickets with QR check-in", "Payments, QR, concurrency", "event", "ticket"),
        ("saas-starter", "A", "Next.js, Better Auth, Stripe, Prisma", "Your own SaaS boilerplate", "Auth, billing, teams", "saas", "starter", "boilerplate"),
        ("restaurant-ordering", "I", "MERN", "Menu, cart and order tracking", "Order states, admin panel", "restaurant", "food", "order"),
        ("hotel-booking", "A", "Next.js, PostgreSQL", "Room search and booking with availability", "Date ranges, locking", "booking", "hotel"),
    ],
    "9. Real-Time and Messaging": [
        ("realtime-chat", "I", "Bun, WebSockets, Redis", "Chat rooms with typing indicators", "WebSockets, pub/sub", "chat", "websocket", "realtime"),
        ("socketio-whiteboard", "I", "Socket.IO, Canvas", "Shared drawing board", "Broadcasting, canvas", "whiteboard", "socket", "draw"),
        ("live-polls", "B", "Next.js, SSE", "Live voting with server-sent events", "SSE, live updates", "poll", "realtime"),
        ("notification-center", "I", "Node, Redis Streams", "In-app and push notifications", "Fan-out, web push", "notification", "push"),
        ("collab-editor", "A", "Yjs, WebSockets", "Google-Docs-style shared editor", "CRDTs, presence", "collaborative", "yjs", "editor"),
        ("video-call-webrtc", "A", "WebRTC", "1:1 video calling", "Signaling, STUN/TURN", "webrtc", "video"),
        ("kafka-order-pipeline", "A", "Kafka or RabbitMQ", "Event-driven order processing", "Event sourcing, consumers", "kafka", "rabbitmq", "event"),
    ],
    "10. AI and LLM Integration": [
        ("claude-chat-ui", "B", "Next.js, Claude API", "Streaming chat interface", "Streaming, prompt design", "chat", "ai", "llm"),
        ("doc-qa-bot", "I", "Python, Claude API, pgvector", "Ask questions about your PDFs (RAG)", "Embeddings, retrieval", "rag", "pdf", "document"),
        ("ai-resume-reviewer", "I", "Next.js, Claude API", "Upload a resume and get structured feedback", "Structured output, file parsing", "resume", "ai"),
        ("tool-use-agent", "A", "TypeScript, Claude API tool use", "Agent that calls your own APIs", "Tool calling, agent loops", "agent", "tool"),
        ("mcp-server-demo", "A", "TypeScript, MCP SDK", "MCP server exposing your app's data", "Model Context Protocol", "mcp", "model context"),
        ("ai-image-captioner", "I", "Python, vision model", "Caption and tag uploaded images", "Multimodal input", "image", "vision", "ai"),
        ("speech-to-notes", "I", "Python, Whisper", "Transcribe meetings into summaries", "Audio, transcription", "transcri", "whisper", "speech"),
        ("ai-code-reviewer", "A", "GitHub Actions, Claude API", "Bot that reviews pull requests", "CI integration, diffs", "review", "github", "ai"),
        ("support-ticket-classifier", "I", "FastAPI, Claude API", "Route support emails by topic and urgency", "Classification, evals", "classif", "ai"),
        ("llm-eval-harness", "A", "Python", "Test prompts against a dataset", "Evals, regression testing", "eval", "llm"),
    ],
    "11. DevOps, Cloud and CI/CD": [
        ("docker-compose-stack", "B", "Docker Compose", "App, database, cache and proxy in one file", "Containers, networks, volumes", "docker", "compose"),
        ("github-actions-ci", "B", "GitHub Actions", "Lint, test and build on every push", "CI pipelines, caching", "github-actions", "ci", "workflow"),
        ("nginx-reverse-proxy", "I", "Nginx, Let's Encrypt", "HTTPS reverse proxy for several apps", "TLS, proxying", "nginx", "proxy"),
        ("k8s-hello-cluster", "A", "Kubernetes, Helm", "Deploy taskflow to a local cluster", "Pods, services, Helm", "kubernetes", "k8s", "helm"),
        ("terraform-aws-basics", "A", "Terraform, AWS", "VPC, database and container service as code", "IaC, state", "terraform", "aws", "infrastructure"),
        ("monitoring-stack", "A", "Prometheus, Grafana", "Metrics and dashboards for your APIs", "Observability, alerts", "monitoring", "prometheus", "grafana"),
        ("serverless-functions", "I", "Vercel/Cloudflare Workers", "Edge functions for an API", "Serverless, edge", "serverless", "cloudflare", "edge"),
        ("vps-deploy-script", "I", "Bash, SSH", "One-command deploy to a VPS", "Shell scripting, systemd", "deploy", "vps", "self-host"),
    ],
    "12. Go and a Second Backend Language": [
        ("go-url-shortener", "B", "Go, PostgreSQL", "URL shortener with the standard library", "net/http, SQL", "lang:go", "url", "shortener"),
        ("go-rest-api", "I", "Go, chi/Gin", "CRUD API with middleware and tests", "Routing, testing", "lang:go", "api", "rest", "gin"),
        ("go-concurrency-lab", "I", "Go", "Worker pools, channels and pipelines", "Goroutines, channels", "lang:go", "concurren", "worker"),
        ("go-cli-tool", "B", "Go, Cobra", "Cross-platform CLI with releases", "CLI, GoReleaser", "lang:go", "cli"),
        ("grpc-microservices", "A", "Go, gRPC", "Two services talking over gRPC", "Protobuf, gRPC", "grpc", "microservice"),
        ("spring-boot-api", "I", "Java, Spring Boot", "REST API with JPA and tests", "Spring, JPA", "lang:java", "spring"),
    ],
    "13. Testing and Code Quality": [
        ("unit-testing-kata", "B", "Vitest or pytest", "TDD katas with full coverage", "TDD, mocking", "test", "tdd"),
        ("playwright-e2e", "I", "Playwright", "End-to-end tests for taskflow-web", "E2E, CI reports", "playwright", "e2e", "test"),
        ("api-contract-tests", "I", "Postman/Newman or Schemathesis", "Contract tests against the OpenAPI spec", "API testing", "api", "test"),
        ("load-testing-k6", "I", "k6", "Load test your APIs and find limits", "Performance testing", "load", "k6", "benchmark"),
        ("lint-format-setup", "B", "ESLint, Prettier, Ruff, Husky", "Shared lint and format config", "Code quality, pre-commit", "eslint", "lint", "prettier"),
    ],
    "14. Career and Interview Prep": [
        ("dsa-in-typescript", "B", "TypeScript", "Data structures and algorithms with tests", "DSA, complexity", "algorithm", "data structure"),
        ("leetcode-journal", "B", "Python or TypeScript", "Daily problem solutions with notes", "Problem solving", "leetcode", "interview"),
        ("system-design-notes", "I", "Markdown, diagrams", "Design write-ups: URL shortener, chat, feed", "System design", "system-design", "system design", "scalab", "interview"),
        ("frontend-interview-prep", "I", "React", "Machine-coding round practice apps", "Frontend interviews", "interview", "frontend"),
        ("portfolio-site", "B", "Next.js", "Portfolio linking every project above", "Personal brand, deployment", "portfolio", "nextjs"),
        ("open-source-contribs", "B", "Git", "Log of your PRs to other projects", "Git workflow, collaboration", "contribut", "first"),
    ],
}


def load_projects() -> list[dict]:
    path = ROOT / "data" / "projects.json"
    if not path.exists():
        return []
    return [p for p in json.loads(path.read_text(encoding="utf-8"))
            if p.get("license") in PERMISSIVE]


def haystack(p: dict) -> str:
    topics = p.get("topics") or []
    if isinstance(topics, str):
        topics = [topics]
    lang = f"lang:{p.get('language') or ''}"
    return " ".join([p.get("name", ""), p.get("description", ""), lang, *topics]).lower()


def find_refs(projects: list[dict], keywords: tuple[str, ...], used: dict[str, int]) -> list[dict]:
    def hit(kw: str, text: str) -> bool:
        # short keywords (go, ui, ci...) must match as whole words
        if len(kw) <= 3:
            return re.search(rf"\b{re.escape(kw)}\b", text) is not None
        return kw in text

    primary, *rest = [k.lower() for k in keywords]
    scored = []
    for p in projects:
        text = haystack(p)
        if not hit(primary, text):
            continue
        score = 1 + sum(hit(k, text) for k in rest)
        if score < min(2, len(keywords)):
            continue  # one loose word is not enough to call it a reference
        # spread references: penalise repos already suggested several times
        scored.append((score - 0.5 * used.get(p["name"], 0), p["stars"], p))
    scored.sort(key=lambda t: (-t[0], -t[1]))
    refs = [p for _, _, p in scored[:2]]
    for p in refs:
        used[p["name"]] = used.get(p["name"], 0) + 1
    return refs


def build() -> list[dict]:
    projects = load_projects()
    used: dict[str, int] = {}
    rows, n = [], 0
    for track, ideas in TRACKS.items():
        for name, lvl, stack, build_what, skills, *keywords in ideas:
            n += 1
            refs = find_refs(projects, tuple(keywords), used)
            rows.append({
                "id": n, "track": track, "repo": name, "level": LEVELS[lvl],
                "stack": stack, "build": build_what, "skills": skills,
                "references": [{"name": r["name"], "url": r["url"],
                                "license": r["license"], "stars": r["stars"]} for r in refs],
            })
    return rows


def write(rows: list[dict]) -> None:
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "data" / "learning_path.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(ROOT / "data" / "learning_path.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "track", "repo", "level", "stack", "build", "skills", "references"])
        for r in rows:
            w.writerow([r["id"], r["track"], r["repo"], r["level"], r["stack"], r["build"],
                        r["skills"], " ".join(x["url"] for x in r["references"])])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    counts = {l: sum(r["level"] == l for r in rows) for l in LEVELS.values()}
    lines = [
        "# Learning Path: Build-It-Yourself Projects",
        "",
        f"**{len(rows)} original projects** across {len(TRACKS)} tracks for learning frontend, "
        "backend, databases, integrations, AI, DevOps and more "
        f"({counts['beginner']} beginner, {counts['intermediate']} intermediate, "
        f"{counts['advanced']} advanced).",
        "",
        f"_Last updated: {today}. Regenerated by `scripts/build_learning_path.py`._",
        "",
        "## How to use this",
        "",
        "1. Go track by track. Inside a track, do beginner projects first.",
        "2. Create a **new repo of your own** for each project, using the suggested name, and write the code yourself.",
        "3. The **References** column links permissively licensed projects from this index that solve a similar problem. "
        "Read them to learn, and credit them in your README if you reuse any code (keep their license notice).",
        "4. Every repo should have: a README with screenshots and setup steps, tests, a `.env.example`, "
        "and a GitHub Actions CI workflow. Deploy it where possible and link the live demo.",
        "5. Tick it off here and link your repo when it's done.",
        "",
        "**Recommended languages:** TypeScript (frontend + Node/Bun backend), Python (APIs, automation, AI), "
        "SQL (every project), then Go or Java as a second backend language. Bash, Git and Docker throughout.",
        "",
        "## Tracks",
        "",
        "| Track | Projects |",
        "|---|---|",
    ]
    for track in TRACKS:
        anchor = re.sub(r"[^a-z0-9 -]", "", track.lower()).replace(" ", "-")
        lines.append(f"| [{track}](#{anchor}) | {sum(r['track'] == track for r in rows)} |")
    lines.append("")

    for track in TRACKS:
        lines += [f"## {track}", "",
                  "| # | Done | Repo to create | Level | Stack | What you build | Skills | References |",
                  "|---|---|---|---|---|---|---|---|"]
        for r in (r for r in rows if r["track"] == track):
            refs = "<br>".join(f"[{x['name']}]({x['url']}) ({x['license']})"
                               for x in r["references"]) or "-"
            lines.append(f"| {r['id']} | ☐ | `{r['repo']}` | {r['level']} | {r['stack']} | "
                         f"{r['build']} | {r['skills']} | {refs} |")
        lines.append("")

    (ROOT / "LEARNING_PATH.md").write_text("\n".join(lines), encoding="utf-8")
    with_refs = sum(bool(r["references"]) for r in rows)
    print(f"Wrote LEARNING_PATH.md and data/learning_path.* "
          f"({len(rows)} projects, {with_refs} with references)")


if __name__ == "__main__":
    write(build())
