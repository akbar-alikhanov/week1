# DALA — Data Analytics Learning Platform

A production-ready, self-paced platform for learning Data Analytics: Excel → SQL →
Power BI → Python → Statistics → Business Analytics → Portfolio → Junior Data
Analyst. Built with Next.js (App Router), TypeScript, Prisma/PostgreSQL and
Clean Architecture. See [ARCHITECTURE.md](./ARCHITECTURE.md) for the design.

## Features

- **Courses**: Excel and SQL fully built out (lessons with theory, worked
  examples, exercises, and quizzes); Power BI, Python, Statistics, and
  Business Analytics scaffolded with the same structure at a lighter content
  depth.
- **Exercise engine**: 8 exercise types (multiple choice, text/formula input,
  SQL query, true/false, matching, ordering, data analysis), graded
  server-side — the correct answer never reaches the client.
- **SQL Playground**: a Monaco-based SQL editor against an isolated,
  read-only sandbox database, both embedded in SQL lessons and as a
  standalone page.
- **Progress, XP, and achievements**: per-lesson/exercise/quiz/course
  progress, a simple XP/level system, and 9 achievements.
- **Roadmap**: a visual course roadmap where the next course unlocks once
  the previous one reaches 100% — enforced server-side, not just visually.
- **Projects**: 5 portfolio-style business-analysis projects (one per
  course), with a submission flow and XP reward.
- **Career Mode**: SQL/Excel interview question banks, business cases, and a
  resume builder.
- **Auth**: email/password registration and login (Auth.js), with the
  architecture left open for adding OAuth providers later.

## Stack

Next.js · TypeScript · Tailwind CSS · shadcn-style UI (Radix primitives) ·
PostgreSQL · Prisma ORM · Auth.js · Zod · React Hook Form · Recharts · Monaco
Editor · pnpm

## Prerequisites

- Node.js 22+
- pnpm 10+
- PostgreSQL 16+ (two databases: the app database and a sandbox database used
  only by the SQL Playground)

## Setup

```bash
pnpm install
cp .env.example .env
# edit .env with your DATABASE_URL / SANDBOX_DATABASE_URL / AUTH_SECRET
```

### Environment variables

See [.env.example](./.env.example) for the full list:

- `DATABASE_URL` — main application PostgreSQL connection string.
- `SANDBOX_DATABASE_URL` — owner connection to a **separate** PostgreSQL
  database used exclusively by the SQL Playground. Never point this at your
  production database. Only used by `pnpm db:seed:sandbox`.
- `SANDBOX_READONLY_DATABASE_URL` / `SANDBOX_READER_PASSWORD` — the
  read-only `sandbox_reader` role connection the app actually queries at
  request time; `pnpm db:seed:sandbox` creates the role with this password.
- `AUTH_SECRET` — secret used by Auth.js to sign session tokens. Generate
  with `openssl rand -base64 32`.
- `NEXTAUTH_URL` — public URL of the deployment.

### Database

```bash
pnpm db:migrate        # apply Prisma migrations to DATABASE_URL
pnpm db:seed           # seed demo user, courses, modules, lessons, exercises, projects
pnpm db:seed:sandbox   # provision the separate SQL Playground sandbox DB (schema, data, sandbox_reader role)
```

The seed creates a demo account: `demo@dala.dev` / `password123`.

The SQL Playground sandbox schema (its own tables: `customers`, `orders`,
`products`, `payments`) is provisioned separately, in its own database — see
[ARCHITECTURE.md § SQL Sandbox](./ARCHITECTURE.md#sql-sandbox). Both `pnpm
db:seed` and `pnpm db:seed:sandbox` are idempotent (upserts), safe to re-run.

## Development

```bash
pnpm dev            # start the dev server on http://localhost:3000
pnpm lint            # ESLint (flat config)
pnpm typecheck       # tsc --noEmit
pnpm format          # Prettier write
pnpm test            # Vitest unit tests (domain / application / infrastructure;
                     # the infrastructure tests need DATABASE_URL reachable)
pnpm test:e2e        # Playwright end-to-end tests
pnpm db:studio       # Prisma Studio
```

## Deployment

Designed for Vercel + a managed PostgreSQL provider (Neon, Supabase, RDS,
Prisma Postgres, ...).

1. **Provision two databases**: the main app database and a separate sandbox
   database for the SQL Playground (see § SQL Sandbox above) — a second
   small Postgres instance/branch is enough, it holds only four teaching
   tables. (The sandbox DB is only needed for the SQL Playground; the rest
   of the app works without it.)
2. **Set environment variables** in the Vercel project settings: at minimum
   `DATABASE_URL`, `AUTH_SECRET`, and `NEXTAUTH_URL` (the deployment's public
   URL) — that's enough for auth, courses, exercises, projects, etc. to
   work. Add `SANDBOX_DATABASE_URL`, `SANDBOX_READONLY_DATABASE_URL`, and
   `SANDBOX_READER_PASSWORD` too once you provision the sandbox DB, to also
   enable the SQL Playground.
3. **Build**: Vercel runs the `vercel-build` script (it takes precedence
   over `build` automatically), which chains
   `prisma migrate deploy && tsx prisma/seed.ts && next build` — so every
   deploy applies pending migrations and re-seeds content on its own, no
   manual migrate/seed step required. `prisma generate` runs first via the
   `postinstall` script (the generated Prisma Client under
   `src/generated/prisma` is git-ignored, so this has to happen on every
   install, including Vercel's). Both `migrate deploy` and the seed are
   idempotent, so re-running them on every build is safe and cheap once
   there's nothing new to apply.
4. If you add the sandbox DB later, run `pnpm db:seed:sandbox` once against
   it from a machine with network access to it (it's not part of the
   automatic Vercel build, since it needs its own separate credentials).

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — layers, dependency flow, folder
  structure, repositories, use cases, domain entities, and notable
  implementation decisions.
- [CONTRIBUTING.md](./CONTRIBUTING.md) — coding conventions and how to add new
  lessons/exercises/projects.
