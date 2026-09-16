"use server";

import { z } from "zod";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { UnauthorizedError, ValidationError } from "@/shared/errors/app-error";
import { runAction, type ActionResult } from "@/shared/errors/action-result";
import type { SubmitProjectResult } from "@/features/projects/application/submit-project.use-case";
import type { UnlockedAchievementSummary } from "@/features/achievements/application/evaluate-achievements.use-case";

const submitProjectSchema = z.object({
  projectId: z.string().min(1),
  summary: z.string().trim().min(20, "Describe your solution in at least 20 characters."),
  deliverableUrl: z
    .union([z.string().trim().url(), z.literal("")])
    .optional()
    .transform((value) => (value ? value : null)),
});

export async function submitProjectAction(
  input: unknown,
): Promise<
  ActionResult<SubmitProjectResult & { newAchievements: UnlockedAchievementSummary[] }>
> {
  return runAction(async () => {
    const session = await auth();
    if (!session?.user) {
      throw new UnauthorizedError();
    }

    const parsed = submitProjectSchema.safeParse(input);
    if (!parsed.success) {
      throw new ValidationError(parsed.error.issues[0]?.message ?? "Invalid submission.");
    }

    const result = await getContainer().submitProjectUseCase.execute(
      session.user.id,
      parsed.data.projectId,
      parsed.data.summary,
      parsed.data.deliverableUrl,
    );
    const newAchievements =
      result.xpAwarded > 0
        ? await getContainer().evaluateAchievementsUseCase.execute(session.user.id)
        : [];
    return { ...result, newAchievements };
  });
}
