import type { UserRepository } from "@/entities/user/repository";
import type { CourseRepository } from "@/entities/course/repository";
import type { ModuleRepository } from "@/entities/module/repository";
import type { LessonRepository } from "@/entities/lesson/repository";
import type {
  ProgressRepository,
  CourseProgressSummary,
} from "@/entities/progress/repository";
import type { AchievementRepository } from "@/entities/achievement/repository";
import { levelForXp, xpIntoCurrentLevel } from "@/entities/user/model";
import { XP_PER_LEVEL } from "@/shared/constants/gamification";
import { NotFoundError } from "@/shared/errors/app-error";

export interface ContinueLearningPointer {
  courseSlug: string;
  courseTitle: string;
  moduleTitle: string;
  lessonSlug: string;
  moduleSlug: string;
  lessonTitle: string;
}

export interface RecentAchievement {
  code: string;
  title: string;
  icon: string;
  unlockedAt: Date;
}

export interface DashboardData {
  name: string;
  level: number;
  xp: number;
  xpIntoLevel: number;
  xpPerLevel: number;
  currentStreak: number;
  longestStreak: number;
  overallPercentComplete: number;
  courses: CourseProgressSummary[];
  continueLearning: ContinueLearningPointer | null;
  recentAchievements: RecentAchievement[];
}

export class GetDashboardUseCase {
  constructor(
    private readonly userRepository: UserRepository,
    private readonly courseRepository: CourseRepository,
    private readonly moduleRepository: ModuleRepository,
    private readonly lessonRepository: LessonRepository,
    private readonly progressRepository: ProgressRepository,
    private readonly achievementRepository: AchievementRepository,
  ) {}

  async execute(userId: string): Promise<DashboardData> {
    const user = await this.userRepository.findById(userId);
    if (!user) {
      throw new NotFoundError("User", userId);
    }

    const [courses, recentAchievements, continueLearning] = await Promise.all([
      this.progressRepository.getAllCourseProgress(userId),
      this.achievementRepository.findRecentUnlocked(userId, 3),
      this.findContinueLearning(userId),
    ]);

    const overallPercentComplete =
      courses.length === 0
        ? 0
        : Math.round(
            courses.reduce((sum, c) => sum + c.percentComplete, 0) / courses.length,
          );

    return {
      name: user.name,
      level: levelForXp(user.xp),
      xp: user.xp,
      xpIntoLevel: xpIntoCurrentLevel(user.xp),
      xpPerLevel: XP_PER_LEVEL,
      currentStreak: user.currentStreak,
      longestStreak: user.longestStreak,
      overallPercentComplete,
      courses,
      continueLearning,
      recentAchievements: recentAchievements.map((r) => ({
        code: r.achievement.code,
        title: r.achievement.title,
        icon: r.achievement.icon,
        unlockedAt: r.unlockedAt,
      })),
    };
  }

  private async findContinueLearning(
    userId: string,
  ): Promise<ContinueLearningPointer | null> {
    const courses = await this.courseRepository.findAll();

    for (const course of courses) {
      const modules = await this.moduleRepository.findByCourseId(course.id);
      for (const courseModule of modules) {
        const lessons = await this.lessonRepository.findByModuleId(courseModule.id);
        for (const lesson of lessons) {
          const isCompleted = await this.progressRepository.isLessonCompleted(
            userId,
            lesson.id,
          );
          if (!isCompleted) {
            return {
              courseSlug: course.slug,
              courseTitle: course.title,
              moduleSlug: courseModule.slug,
              moduleTitle: courseModule.title,
              lessonSlug: lesson.slug,
              lessonTitle: lesson.title,
            };
          }
        }
      }
    }

    return null;
  }
}
