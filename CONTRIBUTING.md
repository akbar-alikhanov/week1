# Contributing

## Before you start

Read [ARCHITECTURE.md](./ARCHITECTURE.md) first - it explains the Clean
Architecture layering, the dependency rule, and the reasoning behind every
non-obvious design decision. This document assumes that context.

## Coding conventions

- **TypeScript strict mode, no `any`.** `@typescript-eslint/no-explicit-any`
  is an error, not a warning.
- **Dependency rule is enforced by ESLint, not just convention.** Code under
  `src/entities/**` and `src/features/*/application/**` cannot import React,
  Next.js, `next-auth`, `@prisma/client`, or anything under
  `src/infrastructure/**` (see `eslint.config.mjs`'s `no-restricted-imports`
  rule). If you need a new piece of infrastructure from a use case, add it to
  the relevant `*Repository`/port interface in `entities/` and implement it
  in `infrastructure/`, then wire it in `infrastructure/container.ts`.
- **No business logic in components.** Components call a Server Action,
  which calls a use case from `getContainer()`. Grading, XP, unlock rules,
  etc. live in `entities/` (pure) or `features/*/application/` (orchestration
  against repository interfaces), never inline in a `.tsx` file.
- **Errors** are one of the `AppError` subclasses in
  `shared/errors/app-error.ts` (`ValidationError`, `NotFoundError`,
  `UnauthorizedError`, `ForbiddenError`, `ExerciseEvaluationError`, or the
  base `DomainError`). Server Actions wrap their body in `runAction()`
  (`shared/errors/action-result.ts`) rather than handling errors ad hoc.
- **Validate all external input with Zod** - form submissions, Server Action
  arguments, exercise answers. Never trust a client-supplied value, including
  ones that "should" already be validated client-side.
- Run `pnpm format` before committing; CI-equivalent checks are `pnpm lint`,
  `pnpm typecheck`, `pnpm test`, and `pnpm build` - all four should pass
  before you open a PR.

## Adding a new lesson (Excel/SQL content)

Lesson content is authored as data, not JSX, so it stays out of the
component tree (see ARCHITECTURE.md's "Content authoring & seeding"):

1. Add a `LessonSeed` entry (see `prisma/content-source/types.ts`) to the
   relevant module file, e.g. `prisma/content-source/excel/module-03.ts`.
   It needs `theory`, `example`, `commonMistakes`, one `exercise` (plus
   optional `additionalExercises`), and a `quiz` array.
2. Run `pnpm db:seed`. This writes the lesson's Markdown to
   `content/<course>/<module>/<lesson>.mdx` and upserts the
   Course/Module/Lesson/Exercise/Quiz rows in the database - it's safe to
   re-run repeatedly (idempotent upserts, not inserts).
3. Add a unit test if the lesson introduces a new exercise `type` or a new
   answer-checking edge case (see `entities/exercise/evaluator.test.ts`).
   Otherwise, existing exercise-type coverage already exercises the grading
   path.

## Adding a new project

1. Add a `ProjectSeed` entry (`prisma/content-source/types.ts`) to
   `prisma/content-source/projects.ts`, including `businessContext`,
   `datasetDescription`, `goal`, `deliverables`, `evaluationCriteria`,
   `hints`, and `tasks`. Point `courseSlug` at an existing course.
2. Run `pnpm db:seed`.

Projects have no automated grading (there's no single correct answer to a
business analysis) - `evaluationCriteria` is a self-review checklist shown
to the learner, and every submission is accepted. See
ARCHITECTURE.md § Projects for the reasoning.

## Adding a new use case

1. Define/extend the repository interface in `entities/<entity>/repository.ts`
   if the use case needs a new query - keep it narrow (return what the use
   case needs, not a generic "find everything").
2. Write the use case in `features/<feature>/application/<name>.use-case.ts`,
   depending only on repository interfaces (constructor-injected).
3. Implement any new repository methods in the matching
   `infrastructure/repositories/prisma-*.repository.ts`.
4. Wire the use case into `infrastructure/container.ts`.
5. Call it from a Server Action (`features/<feature>/actions.ts`), validating
   input with Zod and wrapping the body in `runAction()`.
6. Add a unit test against hand-written fakes of the repositories it depends
   on (see `features/projects/application/submit-project.use-case.test.ts`
   for the pattern) - no mocking library, just a small class implementing
   the interface in-memory.

## Testing

- **Domain** (`entities/**/*.test.ts`): pure functions/entities, no fakes
  needed.
- **Application** (`features/*/application/**/*.test.ts`): use cases against
  hand-written fakes.
- **Infrastructure** (`infrastructure/**/*.test.ts`): repository
  implementations against a real local PostgreSQL database
  (`DATABASE_URL`). Create uniquely-named fixtures and delete them in
  `afterAll` so the suite is safe to run against a database that also has
  seeded content.
- **E2E** (`e2e/**/*.spec.ts`, Playwright): golden-path user flows. Run
  `pnpm dev` in one terminal (or let Playwright start it) and
  `pnpm test:e2e` in another.

## Commit messages

Explain _why_, not just _what_ - the diff already shows what changed.
