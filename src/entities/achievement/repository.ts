import type {
  Achievement,
  AchievementCode,
  AchievementStats,
} from "@/entities/achievement/model";

export interface UnlockedAchievement {
  achievement: Achievement;
  unlockedAt: Date;
}

export interface AchievementRepository {
  findAll(): Promise<Achievement[]>;
  findUnlockedCodes(userId: string): Promise<Set<AchievementCode>>;
  findRecentUnlocked(userId: string, limit: number): Promise<UnlockedAchievement[]>;
  unlock(userId: string, codes: AchievementCode[]): Promise<Achievement[]>;
  getStats(userId: string): Promise<AchievementStats>;
}
