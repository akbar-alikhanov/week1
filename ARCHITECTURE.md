# Architecture

DALA follows Clean Architecture with a feature-based organization on top. This
document explains the layers, the dependency rule, the folder structure, and
records the decisions made where the product spec was ambiguous.

## Layers

```
Presentation  (app/**            - pages, layouts, Server Actions, route handlers)
      ↓
Application   (features/*/application  - use cases)
      ↓
Domain        (entities/**       - entities, value objects, repository interfaces)
      ↑
Infrastructure(infrastructure/** - Prisma repositories, Auth.js, external services)
```

**Dependency Rule:** inner layers never import outer layers.

- `src/entities/**` and `src/features/*/application/**` (domain + application)
  must not import React, Next.js, `@prisma/client`, `next-auth`, or anything
  under `src/infrastructure/**`. This is not just a convention - it is
  enforced by an ESLint rule (`no-restricted-imports`, scoped to those
  globs) in `eslint.config.mjs`, so a violation fails `pnpm lint`.
- Repository **interfaces** live in the domain layer, next to the entity they
  serve (e.g. `src/entities/lesson/repository.ts`). Their **implementations**
  live in `src/infrastructure/repositories/prisma-*.repository.ts` and are
  wired to the interfaces only in the composition root.
- The composition root, `src/infrastructure/container.ts`, is the one place
  that imports both an interface and its concrete implementation. Server
  Actions and route handlers pull dependencies from `getContainer()`; nothing
  in `entities/` or `features/*/application/` ever imports it.

## Folder structure

```
src/
├── app/                    Next.js App Router: routes, layouts, Server Actions
│   ├── (auth)/             login / register (unauthenticated)
│   ├── (dashboard)/        authenticated app shell (sidebar, dashboard, courses, ...)
│   └── api/                route handlers for cases Server Actions don't fit
│
├── entities/               DOMAIN layer - one folder per business entity
│   └── <entity>/
│       ├── model.ts        entity class / value objects + invariants
│       ├── repository.ts   repository interface (port)
│       └── index.ts        public barrel export
│
├── features/                APPLICATION layer + feature-scoped UI
│   └── <feature>/
│       ├── application/     use cases (framework-free, depend only on entities)
│       └── components/      client/server components specific to this feature
│
├── infrastructure/          INFRASTRUCTURE layer
│   ├── database/            Prisma client singleton (driver adapter wiring)
│   ├── auth/                Auth.js configuration
│   ├── repositories/        Prisma implementations of domain repository interfaces
│   ├── services/            external services (e.g. SQL sandbox executor)
│   └── container.ts         composition root / DI
│
├── shared/                  Cross-cutting, framework-light utilities
│   ├── ui/                  shadcn-style UI primitives (Radix + CVA)
│   ├── components/          small shared components (theme provider, ...)
│   ├── errors/               AppError hierarchy + ActionResult helper
│   ├── constants/            gamification constants, etc.
│   ├── validation/            zod schemas shared by forms and Server Actions
│   └── lib/                  `cn()` and other tiny helpers
│
└── generated/prisma/         Prisma Client output (git-ignored, generated)

content/                      Lesson theory content (MDX), outside src/ and the DB
prisma/                       schema.prisma + migrations
```

`entities/` is intentionally not copied 1:1 from the spec's suggested tree:
`Module` is exported as `CourseModule` to avoid clashing with the built-in
`Module` type, and cross-cutting progress (`UserCourseProgress`,
`UserLessonProgress`, `UserExerciseProgress`) is grouped under a single
`entities/progress` folder rather than split three ways, since they share one
repository and one reporting concern.

## Domain entities

Each entity is a small class with a private constructor and a `static
create()` factory that enforces invariants (throwing `ValidationError` from
`shared/errors`). Entities that carry real behavior implement it as methods
that return a new instance (immutable-update style) rather than mutating in
place:

- **User** - owns XP/level/streak rules (`addXp`, `recordActivity`).
- **Exercise** - the public-safe shape (never carries `correctAnswer`).
  Grading logic is a pure function, `evaluateAnswer()`, that takes the
  server-side `CorrectAnswer` and the learner's `SubmittedAnswer` and returns
  `{ isCorrect }`. `SQL_QUERY` is the one exception: it cannot be graded by
  string comparison, so `evaluateAnswer()` throws for that type and the
  `ExecuteSqlExerciseUseCase` grades it by running the learner's query and a
  reference query against the sandbox and comparing result rows (see below).
- **Quiz** - `grade()` computes score/pass from answers + the answer key.
- **Achievement** - `evaluateNewAchievements()` is a pure policy function
  over a stats snapshot; it has no persistence or timing concerns.

Simpler entities (`Course`, `CourseModule`, `Lesson`, `Project`, ...) are
still classes for consistency, but their validation is intentionally light -
there is no behavior to justify a heavier model, per the "don't
over-engineer" guidance in the spec.

## Error handling

`src/shared/errors/app-error.ts` defines one hierarchy used everywhere:
`ValidationError`, `NotFoundError`, `UnauthorizedError`, `ForbiddenError`,
`ExerciseEvaluationError`, and a generic `DomainError`, all extending
`AppError`. Use cases and repositories throw these directly instead of
returning ad-hoc `{ error }` objects.

Server Actions wrap their body in `runAction()` (`shared/errors/action-result.ts`),
which catches `AppError` and returns a typed `ActionResult<T>`
(`{ success: true, data } | { success: false, error, fieldErrors? }`).
Components branch on `result.success` - there is no per-component
`try { } catch { }`, and unexpected (non-`AppError`) failures are logged
server-side and reported to the client as a generic message, never a raw
stack trace.

## Database & Prisma 7

Prisma 7 removed inline `datasource.url` from `schema.prisma` and requires an
explicit **driver adapter**. The app uses `@prisma/adapter-pg` against
PostgreSQL; the singleton lives in `src/infrastructure/database/prisma-client.ts`
and is only ever imported by infrastructure code. `prisma7.config.ts` (the
filename Prisma's own `init` generated) carries the `DATABASE_URL` used by
`prisma migrate`/`prisma generate`.

The Prisma Client is generated as TypeScript source (not a binary query
engine) into `src/generated/prisma`, which is git-ignored and regenerated by
`pnpm db:generate` / on install.

## SQL Sandbox

The SQL Playground (spec § 14) must never run arbitrary SQL against
production data. The chosen mechanism:

- A **separate PostgreSQL database** (`SANDBOX_DATABASE_URL`, `dala_sandbox`
  locally) holds only the teaching dataset (`customers`, `orders`,
  `products`, `payments`). It is provisioned and seeded independently of the
  main app database and the main Prisma schema does not touch it.
- Every learner query runs inside a **read-only transaction**
  (`SET TRANSACTION READ ONLY`) with a short `statement_timeout`, through a
  dedicated Postgres role that only has `SELECT` on the sandbox schema.
- Before execution, the query is checked against a **keyword denylist**
  (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `CREATE`, `TRUNCATE`, `GRANT`,
  `REVOKE`, and multi-statement `;`-separated payloads) as defense in depth on
  top of the read-only transaction and the restricted role.
- `ExecuteSqlExerciseUseCase` also uses this same mechanism to grade
  `SQL_QUERY` exercises: it runs the learner's query and the exercise's
  `referenceQuery`, and compares the resulting rows.

Full implementation lands in the SQL Playground phase; this section records
the decision so later phases don't re-litigate it.

## Content architecture

Lesson theory (title, objectives, theory, examples, common mistakes) is
authored as MDX under `content/<track>/module-XX/NN-slug.mdx`, not hardcoded
in React components. The database only stores structural metadata (`Course`,
`Module`, `Lesson.contentPath`, ordering) plus everything needed for
exercises, quizzes and progress. `Lesson.contentPath` points at the MDX file;
the lesson page reads and renders it at request time. This means new lessons
can be added by dropping a new MDX file + a DB row, without touching UI code.

## Authentication

Auth.js (`next-auth@5`) with a single `Credentials` provider and **JWT**
sessions (`src/infrastructure/auth/auth.ts`). Route protection is enforced in
two places:

- `src/proxy.ts` (Next.js 16 renamed `middleware.ts` to `proxy.ts`; the
  exported function must be named `proxy`) redirects unauthenticated
  visitors away from every protected route prefix to `/login?from=<path>`,
  and redirects already-authenticated visitors away from `/login`/`/register`
  to `/dashboard`.
- `app/(dashboard)/layout.tsx` re-checks the session server-side and
  redirects to `/login` if absent, so a protected page is never rendered
  even if the proxy layer is ever bypassed.

Passwords are hashed with `bcryptjs` (cost factor 12) behind a `PasswordHasher`
port defined in `features/authentication/application/ports.ts`, so
`RegisterUserUseCase`/`AuthenticateUserUseCase` stay framework-free and are
unit-tested against a fake hasher and a fake in-memory `UserRepository`.
`AuthenticateUserUseCase` deliberately returns `null` for both "no such user"
and "wrong password" so failed sign-ins don't leak which emails are
registered.

**No `@auth/prisma-adapter` yet.** The spec asks for architecture that
_allows_ adding OAuth later, not for OAuth now, and the schema already has
`Account`/`Session`/`VerificationToken` models ready for it. Wiring the
adapter today would add a dependency whose compatibility with Prisma 7's new
`prisma-client` generator output is unverified, for a capability nothing yet
uses - so it's deferred. Adding an OAuth provider later means installing
`@auth/prisma-adapter`, passing `adapter: PrismaAdapter(prisma)` into the
`NextAuth()` call, and keeping `session.strategy = "jwt"` (required whenever
a `Credentials` provider is present).

`registerAction`/`loginAction` (`features/authentication/actions.ts`) are
Server Actions that validate input with the same Zod schemas the client form
uses, call the use case, then call Auth.js's `signIn("credentials", { redirect:
false })` to establish the session before the client redirects - this keeps
"submit the form" and "you're signed in" a single request/response round
trip instead of a second client-side sign-in call.

## Testing strategy

- **Domain** (`entities/**/*.test.ts`): pure unit tests, no mocks needed
  since there are no framework dependencies to mock.
- **Application** (`features/*/application/**/*.test.ts`): use cases tested
  against hand-written in-memory fakes of the repository interfaces.
- **Infrastructure** (`infrastructure/repositories/**/*.test.ts`): repository
  implementations tested against a real (local) PostgreSQL database.
- **E2E** (`e2e/**/*.spec.ts`, Playwright): golden-path flows - register,
  login, browse a course, complete a lesson, submit an exercise, pass a quiz,
  see progress update, run a SQL exercise.

## Open decisions recorded here (spec was ambiguous)

- **Password hashing**: `bcryptjs` (pure JS) rather than native `bcrypt`, to
  avoid native build steps in constrained environments; cost factor 12.
- **Level formula**: `level = floor(xp / 100) + 1` - flat 100 XP per level,
  matching the spec's "simple XP system" instruction rather than a
  progressive curve.
- **UI kit**: `ui.shadcn.com` is unreachable from this environment's network
  policy, so the shadcn-style components under `src/shared/ui` are
  hand-written directly against the same Radix primitives + CVA pattern the
  shadcn CLI generates, rather than using the CLI.
