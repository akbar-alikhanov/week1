import type { PrismaClient } from "@/generated/prisma/client";
import type { AchievementModel } from "@/generated/prisma/models/Achievement";
import {
  Achievement,
  type AchievementCode,
  type AchievementStats,
} from "@/entities/achievement/model";
import type {
  AchievementRepository,
  UnlockedAchievement,
} from "@/entities/achievement/repository";

export class PrismaAchievementRepository implements AchievementRepository {
  constructor(private readonly db: PrismaClient) {}

  async findAll(): Promise<Achievement[]> {
    const records = await this.db.achievement.findMany();
    return records.map(toDomain);
  }

  async findUnlockedCodes(userId: string): Promise<Set<AchievementCode>> {
    const records = await this.db.userAchievement.findMany({
      where: { userId },
      select: { achievement: { select: { code: true } } },
    });
    return new Set(records.map((r) => r.achievement.code as AchievementCode));
  }

  async findRecentUnlocked(
    userId: string,
    limit: number,
  ): Promise<UnlockedAchievement[]> {
    const records = await this.db.userAchievement.findMany({
      where: { userId },
      orderBy: { unlockedAt: "desc" },
      take: limit,
      include: { achievement: true },
    });
    return records.map((record) => ({
      achievement: toDomain(record.achievement),
      unlockedAt: record.unlockedAt,
    }));
  }

  async unlock(userId: string, codes: AchievementCode[]): Promise<Achievement[]> {
    if (codes.length === 0) return [];

    const achievements = await this.db.achievement.findMany({
      where: { code: { in: codes } },
    });
    await this.db.userAchievement.createMany({
      data: achievements.map((achievement) => ({
        userId,
        achievementId: achievement.id,
      })),
      skipDuplicates: true,
    });
    return achievements.map(toDomain);
  }

  async getStats(userId: string): Promise<AchievementStats> {
    const [
      completedLessons,
      completedExercises,
      completedProjects,
      user,
      excelProgress,
      sqlProgress,
      passedSqlQuizzes,
    ] = await Promise.all([
      this.db.userLessonProgress.count({ where: { userId, completedAt: { not: null } } }),
      this.db.userExerciseProgress.count({
        where: { userId, completedAt: { not: null } },
      }),
      this.db.projectSubmission.findMany({
        where: { userId },
        distinct: ["projectId"],
        select: { projectId: true },
      }),
      this.db.user.findUniqueOrThrow({
        where: { id: userId },
        select: { currentStreak: true },
      }),
      this.db.userCourseProgress.findFirst({
        where: { userId, course: { track: "EXCEL" } },
        select: { percentComplete: true },
      }),
      this.db.userCourseProgress.findFirst({
        where: { userId, course: { track: "SQL" } },
        select: { percentComplete: true },
      }),
      this.db.quizAttempt.findMany({
        where: {
          userId,
          passed: true,
          quiz: { lesson: { module: { course: { track: "SQL" } } } },
        },
        distinct: ["quizId"],
        select: { quizId: true },
      }),
    ]);

    return {
      completedLessons,
      completedExercises,
      completedProjects: completedProjects.length,
      currentStreak: user.currentStreak,
      excelCourseCompleted: excelProgress?.percentComplete === 100,
      sqlCourseCompleted: sqlProgress?.percentComplete === 100,
      passedSqlQuizzes: passedSqlQuizzes.length,
    };
  }
}

function toDomain(record: AchievementModel): Achievement {
  return Achievement.create({
    id: record.id,
    code: record.code as AchievementCode,
    title: record.title,
    description: record.description,
    icon: record.icon,
  });
}
