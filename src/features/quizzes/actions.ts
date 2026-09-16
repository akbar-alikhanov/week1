"use server";

import { z } from "zod";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { UnauthorizedError, ValidationError } from "@/shared/errors/app-error";
import { runAction, type ActionResult } from "@/shared/errors/action-result";
import type { SubmitQuizResult } from "@/features/quizzes/application/submit-quiz.use-case";
import type { UnlockedAchievementSummary } from "@/features/achievements/application/evaluate-achievements.use-case";

const answersSchema = z.record(z.string(), z.number().int());

export async function submitQuizAction(
  quizId: string,
  answers: unknown,
): Promise<
  ActionResult<SubmitQuizResult & { newAchievements: UnlockedAchievementSummary[] }>
> {
  return runAction(async () => {
    const session = await auth();
    if (!session?.user) {
      throw new UnauthorizedError();
    }

    const parsed = answersSchema.safeParse(answers);
    if (!parsed.success) {
      throw new ValidationError("Invalid quiz answers submitted.");
    }

    const result = await getContainer().submitQuizUseCase.execute(
      session.user.id,
      quizId,
      parsed.data,
    );
    const newAchievements =
      result.xpAwarded > 0
        ? await getContainer().evaluateAchievementsUseCase.execute(session.user.id)
        : [];
    return { ...result, newAchievements };
  });
}
