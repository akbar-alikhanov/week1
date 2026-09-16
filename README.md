# DALA — Data Analytics Learning Platform

A production-ready, self-paced platform for learning Data Analytics: Excel → SQL →
Power BI → Python → Statistics → Business Analytics → Portfolio → Junior Data
Analyst. Built with Next.js (App Router), TypeScript, Prisma/PostgreSQL and
Clean Architecture. See [ARCHITECTURE.md](./ARCHITECTURE.md) for the design.

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
- `SANDBOX_DATABASE_URL` — separate PostgreSQL database used exclusively by the
  SQL Playground. Never point this at your production database.
- `AUTH_SECRET` — secret used by Auth.js to sign session tokens.
- `NEXTAUTH_URL` — public URL of the deployment.

### Database

```bash
pnpm db:migrate   # apply Prisma migrations to DATABASE_URL
pnpm db:seed      # seed demo user, courses, modules, lessons, exercises, projects
```

The SQL Playground sandbox schema (its own tables: `customers`, `orders`,
`products`, `payments`) is provisioned separately — see
[ARCHITECTURE.md § SQL Sandbox](./ARCHITECTURE.md#sql-sandbox).

## Development

```bash
pnpm dev            # start the dev server on http://localhost:3000
pnpm lint            # ESLint (flat config)
pnpm typecheck       # tsc --noEmit
pnpm format          # Prettier write
pnpm test            # Vitest unit tests (domain / application / infrastructure)
pnpm test:e2e        # Playwright end-to-end tests
pnpm db:studio       # Prisma Studio
```

## Deployment

Designed for Vercel + a managed PostgreSQL provider (Neon, Supabase, RDS,
Prisma Postgres, ...). Set the same environment variables in the Vercel
project settings, then run `pnpm db:migrate` against the production database
as part of your release process (e.g. `prisma migrate deploy`).

## Documentation

- [ARCHITECTURE.md](./ARCHITECTURE.md) — layers, dependency flow, folder
  structure, repositories, use cases, domain entities, and notable
  implementation decisions.
- [CONTRIBUTING.md](./CONTRIBUTING.md) — coding conventions and how to add new
  lessons/exercises.
