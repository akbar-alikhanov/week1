"use server";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { UnauthorizedError } from "@/shared/errors/app-error";
import { runAction, type ActionResult } from "@/shared/errors/action-result";
import type { CompleteLessonResult } from "@/features/lessons/application/complete-lesson.use-case";
import type { UnlockedAchievementSummary } from "@/features/achievements/application/evaluate-achievements.use-case";

export async function completeLessonAction(
  lessonId: string,
): Promise<
  ActionResult<CompleteLessonResult & { newAchievements: UnlockedAchievementSummary[] }>
> {
  return runAction(async () => {
    const session = await auth();
    if (!session?.user) {
      throw new UnauthorizedError();
    }
    const result = await getContainer().completeLessonUseCase.execute(
      session.user.id,
      lessonId,
    );
    const newAchievements = result.alreadyCompleted
      ? []
      : await getContainer().evaluateAchievementsUseCase.execute(session.user.id);
    return { ...result, newAchievements };
  });
}
