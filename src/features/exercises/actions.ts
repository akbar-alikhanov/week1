"use server";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { sqlQueryRateLimiter } from "@/infrastructure/services/in-memory-rate-limiter";
import {
  ForbiddenError,
  UnauthorizedError,
  ValidationError,
} from "@/shared/errors/app-error";
import { runAction, type ActionResult } from "@/shared/errors/action-result";
import { submittedAnswerSchema } from "@/shared/validation/exercise";
import type { SubmitExerciseResult } from "@/features/exercises/application/submit-exercise.use-case";
import type { SqlQueryResult } from "@/features/exercises/application/ports";

export async function submitExerciseAction(
  exerciseId: string,
  answer: unknown,
): Promise<ActionResult<SubmitExerciseResult>> {
  return runAction(async () => {
    const session = await auth();
    if (!session?.user) {
      throw new UnauthorizedError();
    }

    const parsed = submittedAnswerSchema.safeParse(answer);
    if (!parsed.success) {
      throw new ValidationError("Invalid answer submitted.");
    }

    if (parsed.data.type === "SQL_QUERY" && !sqlQueryRateLimiter.check(session.user.id)) {
      throw new ForbiddenError(
        "Too many SQL queries. Please wait a moment and try again.",
      );
    }

    return getContainer().submitExerciseUseCase.execute(
      session.user.id,
      exerciseId,
      parsed.data,
    );
  });
}

export async function runSqlQueryAction(
  query: string,
): Promise<ActionResult<SqlQueryResult>> {
  return runAction(async () => {
    const session = await auth();
    if (!session?.user) {
      throw new UnauthorizedError();
    }
    if (!sqlQueryRateLimiter.check(session.user.id)) {
      throw new ForbiddenError(
        "Too many SQL queries. Please wait a moment and try again.",
      );
    }
    return getContainer().executeSqlExerciseUseCase.execute(query);
  });
}
