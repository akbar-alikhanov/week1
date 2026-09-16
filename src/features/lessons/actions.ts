"use server";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { UnauthorizedError } from "@/shared/errors/app-error";
import { runAction, type ActionResult } from "@/shared/errors/action-result";
import type { CompleteLessonResult } from "@/features/lessons/application/complete-lesson.use-case";

export async function completeLessonAction(
  lessonId: string,
): Promise<ActionResult<CompleteLessonResult>> {
  return runAction(async () => {
    const session = await auth();
    if (!session?.user) {
      throw new UnauthorizedError();
    }
    return getContainer().completeLessonUseCase.execute(session.user.id, lessonId);
  });
}
