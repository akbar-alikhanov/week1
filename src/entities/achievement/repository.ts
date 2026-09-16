import type {
  Achievement,
  AchievementCode,
  AchievementStats,
} from "@/entities/achievement/model";

export interface AchievementRepository {
  findAll(): Promise<Achievement[]>;
  findUnlockedCodes(userId: string): Promise<Set<AchievementCode>>;
  unlock(userId: string, codes: AchievementCode[]): Promise<Achievement[]>;
  getStats(userId: string): Promise<AchievementStats>;
}
