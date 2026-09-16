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

`PostgresSqlSandboxService` (`src/infrastructure/services/postgres-sql-sandbox.service.ts`)
implements all four layers: it rejects anything but a single `SELECT`/`WITH`
statement, checks the forbidden-keyword regex, wraps the query as
`SELECT * FROM (<query>) AS sandboxed_query LIMIT 500` inside a
`BEGIN TRANSACTION READ ONLY` block with a 5s `statement_timeout`, and always
connects as the `sandbox_reader` role (`SANDBOX_READONLY_DATABASE_URL`),
provisioned by `pnpm db:seed:sandbox` with `SELECT`-only grants. `SubmitExerciseUseCase`
grades `SQL_QUERY` exercises by running both the learner's query and the
exercise's `referenceQuery` through this same service and comparing the
result rows (order-insensitive: rows are normalized and sorted before
comparison, since an ungrouped `SELECT` doesn't guarantee row order without
an explicit `ORDER BY`). `ExecuteSqlExerciseUseCase` runs a query with no
grading - used for the "Run" preview both on lesson `SQL_QUERY` exercises
and the standalone SQL Playground (a later phase, reusing this same
service and sandbox dataset). Both entry points share an in-memory
sliding-window rate limiter (`src/infrastructure/services/in-memory-rate-limiter.ts`,
20 requests/minute per user) as required by spec §29; a multi-instance
production deployment should swap it for a shared store (Redis/Upstash)
behind the same interface.

`/playground` (the standalone SQL Playground page, spec §14) is a thin
client shell (`SqlPlayground`) over the same `SqlEditor`, `QueryResultTable`
and `runSqlQueryAction` already built for lesson `SQL_QUERY` exercises - it
just runs a query for live preview with no grading, and shows a static
sidebar of the sandbox's four tables/columns. It is intentionally not
gated by the roadmap unlock policy (unlike course/lesson pages): it is a
practice tool under "Practice" in the nav, not a course step, so trying
SQL there ahead of finishing Excel is allowed.

The Monaco editor used for `SQL_QUERY` answers is bundled through Next.js
(`loader.config({ monaco })` from a direct `monaco-editor` import) rather
than fetched from `@monaco-editor/react`'s default CDN loader, and loaded
via `next/dynamic(..., { ssr: false })` since `monaco-editor` touches
`window` at import time and cannot be evaluated during SSR. This also makes
the editor work in network-restricted environments and removes a runtime
dependency on a third-party CDN being reachable.

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

## Content authoring & seeding

Lesson content is authored once as structured TypeScript data
(`prisma/content-source/**`, one file per module: `theory`, `example`,
`commonMistakes`, one or more `exercise`(s) with the answer key, and `quiz`
questions) rather than as hand-written `.mdx` files. `prisma/seed.ts` then:

1. Writes each lesson's theory as a real `.mdx` file under `content/<course
slug>/<module slug>/<lesson slug>.mdx` (frontmatter `objectives`, body
   sections `## Theory` / `## Example` / `## Common mistakes`).
2. Upserts `Course` → `Module` → `Lesson` (with `contentPath` pointing at the
   file just written) → `Exercise` (server-side `correctAnswer` included) →
   `Quiz`/`QuizQuestion`.

This keeps the "content lives in files, DB holds metadata" rule from spec §23
while letting content be authored as reviewable, type-checked data instead of
~90 separate hand-edited files. The generated `.mdx` files are real,
independently readable/editable content - the TS source is just how they get
produced and kept in sync with their DB rows; editing either the source data
or a generated `.mdx` file directly both work, but only the source is
re-seedable.

**Content depth tiering.** Spec §35 asks to fully implement Excel first
(all 8 modules / 54 lessons); §36 asks for full depth on SQL's first modules
with real datasets (≥2 theory examples, ≥3 exercises, ≥3 quiz questions per
lesson) and §34 allows the remaining courses (Power BI, Python, Statistics,
Business Analytics) to ship with "basic structure" only. Applied here as:

- **Excel** - all 54 lessons implemented with real theory, a worked example,
  one graded exercise and a 1-2 question quiz each.
- **SQL modules 1-2** (SELECT/WHERE fundamentals, filtering & sorting) - the
  heavier tier: 2+ worked examples, 3 graded exercises, 3 quiz questions per
  lesson, against a shared 4-table dataset (`customers`, `products`,
  `orders`, `payments`) that doubles as the SQL Playground's sandbox dataset.
- **SQL modules 3-6** (aggregation, JOINs, subqueries/CTEs, window
  functions) - one real exercise and 1-2 quiz questions per lesson; still
  real, runnable SQL against the same dataset, just less repetition per
  concept.
- **Power BI / Python / Statistics / Business Analytics** - `Course` and
  `Module` rows only (topics grouped from the spec's flat lists), no lessons
  yet. The course detail page renders these modules with a "Content coming
  soon" state instead of an empty/broken list.

## Gamification wiring

`EvaluateAchievementsUseCase` runs the pure `evaluateNewAchievements()`
policy (Phase 2) against a stats snapshot (`AchievementRepository.getStats()`)
and persists any newly-crossed thresholds. Rather than bury this inside
`CompleteLessonUseCase`/`SubmitExerciseUseCase`/`SubmitQuizUseCase`, each of
those three Server Actions calls it once, after its own use case succeeds,
and folds the result into the action's response as `newAchievements` - so
the client can toast "Achievement unlocked" without the completion use
cases needing to know achievements exist. XP awarding stays inside each
completion use case itself (not a separate step) since it is intrinsic to
"this lesson/exercise/quiz was just completed," not a cross-cutting policy
evaluated against a stats snapshot the way achievements are.

`GetDashboardUseCase` aggregates: level/XP (via `levelForXp`/`xpIntoCurrentLevel`
from the `User` entity), streaks, per-course progress
(`ProgressRepository.getAllCourseProgress`), the 3 most recent unlocked
achievements, and a "continue learning" pointer - the first incomplete
lesson found by walking courses → modules → lessons in order. That walk is
O(courses × modules × lessons) with one query per level; acceptable at
today's content volume (~90 lessons) and revisited if the course catalog
grows enough to matter.

## Roadmap gating

Spec §19 asks that "the next stage unlocks once its requirements are met,
but the user can still see the whole roadmap." Read literally, that's an
access-control rule, not just a visual one, so it's enforced at the use-case
level, not only drawn differently on one page:

- `computeUnlockedCourseIds()` (pure, `entities/progress/model.ts`) is the
  single source of truth: the first course is always unlocked; each
  following course unlocks once the previous one's `percentComplete` is 100. It takes an ordered list of `{courseId, percentComplete}` and has no
  persistence or framework dependency, so it's unit-tested directly.
- `assertCourseUnlocked()` (`features/progress/application/course-lock.ts`)
  wraps that policy with the repository calls needed to evaluate it for a
  given user, and throws `ForbiddenError` if the requested course isn't
  unlocked yet. Both `GetCourseUseCase` and `GetLessonUseCase` call it
  before returning any content, so a learner can't reach SQL (or any later
  course) by guessing/typing a URL before finishing Excel - not just by not
  seeing a link to it.
- `ListCoursesUseCase` (used by both `/courses` and `/roadmap`) computes the
  same `isUnlocked` flag per course so those pages can render a locked
  state (dimmed card / lock icon, non-clickable) instead of a link, without
  duplicating the unlock rule.
- The `(dashboard)` course and lesson pages catch `ForbiddenError` and
  render `LockedCourseNotice` (a small "complete the previous course"
  card with a link back to `/roadmap`) instead of a raw error.

A `userId` of `null` (no session) never triggers the check - every route
that reaches these use cases already requires authentication via
`proxy.ts`, so this is purely defensive.

## Projects

`Project`/`ProjectTask`/`ProjectSubmission` (entities, repositories) existed
from Phase 2; Phase 9 wires them up end to end:

- `ListProjectsUseCase`, `GetProjectUseCase`, `SubmitProjectUseCase`
  (`features/projects/application/`) follow the same shape as the exercise
  and quiz use cases, and a `PrismaProjectRepository` /
  `PrismaProjectSubmissionRepository` implement the entity-layer interfaces.
- Access is gated the same way as courses and lessons: both `GetProjectUseCase`
  and `SubmitProjectUseCase` call the existing `assertCourseUnlocked()`
  against the project's `courseId`, so a project can't be viewed or
  submitted before its course is unlocked on the roadmap - one policy, no
  duplicated rule.
- **Evaluation is unlike exercises/quizzes**: those grade against a stored
  `correctAnswer`; a business-analysis project has no single correct answer
  to check server-side. The spec's "Evaluation" section is therefore treated
  as a self-review checklist shown to the learner (`Project.evaluationCriteria`),
  not an automated grader. `SubmitProjectUseCase` accepts every submission
  (`ProjectSubmission.status = "ACCEPTED"`) and awards the project's XP once,
  on the learner's first submission for that project; resubmitting (e.g. to
  fix a mistake) is recorded but doesn't re-award XP - mirroring how
  `SubmitQuizUseCase` only awards XP on a learner's first pass. Manual
  reviewer feedback remains possible later via the existing `feedback`/
  `status` columns without a schema change.
- `Project` gained two fields beyond the Phase 2 schema -
  `deliverables: Json` and `evaluationCriteria: Json` (both `string[]`) - to
  hold the "Expected Deliverables" and "Evaluation" sections the spec asks
  each project to have; `hints` already existed. This was a small additive
  migration (`add_project_evaluation_fields`), safe since the app has no
  production data yet.
- Content: 5 projects seeded from `prisma/content-source/projects.ts`, one
  per course track. Following the same depth-tiering already used for
  lessons, Excel's "Sales Analysis" and SQL's "E-commerce Analytics" are
  fully detailed (business context, dataset, 4 tasks, deliverables, hints,
  evaluation criteria); the Power BI/Python/Business Analytics projects have
  the same structure filled in at a lighter level of detail, consistent with
  those courses' stub-module status.

## Career Mode

Unlike courses/exercises/projects, Career Mode (§ "basic structure ok" per
spec) has no progress tracking, grading, or XP - it's reference content plus
a personal tool. That changes what "don't hardcode content in components"
means here:

- Interview questions and business cases (`features/career/content/interview-content.ts`)
  are plain TS data, not routed through Prisma/MDX like lesson content -
  there's nothing to seed, migrate, or query per-user, so a database round
  trip would add infrastructure without adding value. Content still lives
  outside the JSX (`QuestionCard`, `/career/page.tsx`) so it can be edited or
  extended without touching rendering code.
- The **resume builder** (`/career/resume`) is a client-only tool: form
  state persists to the browser's `localStorage` (never sent to the server),
  since a resume draft is a personal scratchpad, not shared or graded data
  that needs a `User`-owned DB row. "Export" is a print-friendly view opened
  via `window.print()`, avoiding a PDF-generation dependency for an MVP
  feature the spec marks as "basic structure ok."

## Testing strategy

- **Domain** (`entities/**/*.test.ts`): pure unit tests, no mocks needed
  since there are no framework dependencies to mock - e.g. `Quiz.grade()`,
  `evaluateAnswer()`, `evaluateNewAchievements()`, `computeUnlockedCourseIds()`.
- **Application** (`features/*/application/**/*.test.ts`): use cases tested
  against hand-written in-memory fakes of the repository interfaces (no
  mocking library) - e.g. `SubmitExerciseUseCase`, `SubmitQuizUseCase`,
  `SubmitProjectUseCase`, `CompleteLessonUseCase`.
- **Infrastructure** (`infrastructure/repositories/**/*.test.ts`,
  `infrastructure/services/**/*.test.ts`): two sub-categories, both run by
  `pnpm test` alongside the domain/application suites:
  - Repository implementations against a real (local) PostgreSQL database via
    the shared `prisma` client, e.g. `PrismaUserRepository.test.ts` (create /
    find / XP-save round trip) and `PrismaProjectRepository.test.ts` (the
    `Json` string-array columns - `deliverables`/`evaluationCriteria`/`hints`
    - round-trip correctly, and ordered tasks come back in order). Each test
      creates its own uniquely-named fixture rows and deletes them in
      `afterAll`, so the suite is safe to run against the same database used
      for `pnpm dev`/seeding. `vitest.config.mts` loads `.env` (`dotenv/config`)
      so `DATABASE_URL` is available the same way `playwright.config.ts`
      already loads it for e2e.
  - Services tested in isolation where hitting the real dependency isn't the
    point, e.g. `PostgresSqlSandboxService`'s keyword-denylist/statement-shape
    rejection tests mock the `pg` driver, since what's under test is the
    pure validation logic that runs before any query reaches Postgres.
- **E2E** (`e2e/**/*.spec.ts`, Playwright): golden-path flows - register,
  login, browse a course, complete a lesson, submit an exercise, pass a quiz,
  see progress update, run a SQL exercise, run a query in the standalone
  playground, submit a project, browse Career Mode's interview prep and
  resume builder.

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
- **Migrating/seeding on Vercel**: rather than requiring a manual
  `prisma migrate deploy`/seed step run from a separate machine against the
  production database (the more conventional setup), the `vercel-build`
  script runs `prisma migrate deploy && tsx prisma/seed.ts` before
  `next build` on every deploy. This trades a small amount of build time for
  removing an entire manual step from the deploy process; it's safe because
  both operations are idempotent (migrate deploy no-ops once applied, and
  the seed only upserts), and appropriate for this app's content-as-code
  model where "deploy" and "the content is up to date" should be the same
  event. A team with a stricter migration-review process would instead gate
  `prisma migrate deploy` behind a manual or CI-approved step - see
  `vercel-build` in `package.json` if you need to split it back out.
