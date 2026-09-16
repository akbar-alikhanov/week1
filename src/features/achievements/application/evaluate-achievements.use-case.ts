import { evaluateNewAchievements } from "@/entities/achievement/model";
import type { AchievementRepository } from "@/entities/achievement/repository";

export interface UnlockedAchievementSummary {
  code: string;
  title: string;
  description: string;
  icon: string;
}

/**
 * Runs the achievement policy against the user's current stats and
 * persists any newly-earned achievements. Called after a lesson,
 * exercise, quiz, or project completes successfully - kept as its own use
 * case (rather than folded into each of those) so completion use cases
 * stay focused on their own concern.
 */
export class EvaluateAchievementsUseCase {
  constructor(private readonly achievementRepository: AchievementRepository) {}

  async execute(userId: string): Promise<UnlockedAchievementSummary[]> {
    const [stats, unlockedCodes] = await Promise.all([
      this.achievementRepository.getStats(userId),
      this.achievementRepository.findUnlockedCodes(userId),
    ]);

    const newCodes = evaluateNewAchievements(stats, unlockedCodes);
    if (newCodes.length === 0) {
      return [];
    }

    const unlocked = await this.achievementRepository.unlock(userId, newCodes);
    return unlocked.map((achievement) => ({
      code: achievement.code,
      title: achievement.title,
      description: achievement.description,
      icon: achievement.icon,
    }));
  }
}
