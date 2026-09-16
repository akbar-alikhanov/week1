import { toast } from "sonner";

import type { UnlockedAchievementSummary } from "@/features/achievements/application/evaluate-achievements.use-case";

export function toastNewAchievements(achievements: UnlockedAchievementSummary[]) {
  for (const achievement of achievements) {
    toast.success(`🏆 Achievement unlocked: ${achievement.title}`, {
      description: achievement.description,
    });
  }
}
