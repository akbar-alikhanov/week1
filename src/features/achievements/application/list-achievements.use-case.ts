import type { AchievementRepository } from "@/entities/achievement/repository";

export interface AchievementListItem {
  code: string;
  title: string;
  description: string;
  icon: string;
  isUnlocked: boolean;
}

export class ListAchievementsUseCase {
  constructor(private readonly achievementRepository: AchievementRepository) {}

  async execute(userId: string): Promise<AchievementListItem[]> {
    const [all, unlockedCodes] = await Promise.all([
      this.achievementRepository.findAll(),
      this.achievementRepository.findUnlockedCodes(userId),
    ]);

    return all.map((achievement) => ({
      code: achievement.code,
      title: achievement.title,
      description: achievement.description,
      icon: achievement.icon,
      isUnlocked: unlockedCodes.has(achievement.code),
    }));
  }
}
