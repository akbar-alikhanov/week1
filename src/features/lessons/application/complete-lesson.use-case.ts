import type { LessonRepository } from "@/entities/lesson/repository";
import type { ModuleRepository } from "@/entities/module/repository";
import type { ProgressRepository } from "@/entities/progress/repository";
import type { UserRepository } from "@/entities/user/repository";
import { NotFoundError } from "@/shared/errors/app-error";

export interface CompleteLessonResult {
  alreadyCompleted: boolean;
  xpAwarded: number;
  totalXp: number;
  level: number;
  leveledUp: boolean;
  courseId: string;
  coursePercentComplete: number;
}

export class CompleteLessonUseCase {
  constructor(
    private readonly lessonRepository: LessonRepository,
    private readonly moduleRepository: ModuleRepository,
    private readonly progressRepository: ProgressRepository,
    private readonly userRepository: UserRepository,
  ) {}

  async execute(userId: string, lessonId: string): Promise<CompleteLessonResult> {
    const lesson = await this.lessonRepository.findById(lessonId);
    if (!lesson) {
      throw new NotFoundError("Lesson", lessonId);
    }

    const courseModule = await this.moduleRepository.findById(lesson.moduleId);
    if (!courseModule) {
      throw new NotFoundError("Module", lesson.moduleId);
    }

    const alreadyCompleted = await this.progressRepository.isLessonCompleted(
      userId,
      lessonId,
    );

    const user = await this.userRepository.findById(userId);
    if (!user) {
      throw new NotFoundError("User", userId);
    }

    if (alreadyCompleted) {
      const courseProgress = await this.progressRepository.recomputeCourseProgress(
        userId,
        courseModule.courseId,
      );
      return {
        alreadyCompleted: true,
        xpAwarded: 0,
        totalXp: user.xp,
        level: user.level,
        leveledUp: false,
        courseId: courseModule.courseId,
        coursePercentComplete: courseProgress.percentComplete,
      };
    }

    await this.progressRepository.markLessonCompleted(userId, lessonId);
    const courseProgress = await this.progressRepository.recomputeCourseProgress(
      userId,
      courseModule.courseId,
    );

    const levelBefore = user.level;
    const updatedUser = user.addXp(lesson.xpReward).recordActivity();
    await this.userRepository.save(updatedUser);

    return {
      alreadyCompleted: false,
      xpAwarded: lesson.xpReward,
      totalXp: updatedUser.xp,
      level: updatedUser.level,
      leveledUp: updatedUser.level > levelBefore,
      courseId: courseModule.courseId,
      coursePercentComplete: courseProgress.percentComplete,
    };
  }
}
