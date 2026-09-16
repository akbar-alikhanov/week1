import type { PrismaClient } from "@/generated/prisma/client";
import { CourseProgress, LessonProgress } from "@/entities/progress/model";
import type {
  CourseProgressSummary,
  ProgressRepository,
} from "@/entities/progress/repository";
import type { CourseTrack } from "@/entities/course/model";

export class PrismaProgressRepository implements ProgressRepository {
  constructor(private readonly db: PrismaClient) {}

  async getLessonProgress(
    userId: string,
    lessonId: string,
  ): Promise<LessonProgress | null> {
    const record = await this.db.userLessonProgress.findUnique({
      where: { userId_lessonId: { userId, lessonId } },
    });
    return record
      ? LessonProgress.create({ lessonId, completedAt: record.completedAt })
      : null;
  }

  async markLessonCompleted(userId: string, lessonId: string): Promise<void> {
    await this.db.userLessonProgress.upsert({
      where: { userId_lessonId: { userId, lessonId } },
      create: { userId, lessonId, completedAt: new Date() },
      update: { completedAt: new Date() },
    });
  }

  async isLessonCompleted(userId: string, lessonId: string): Promise<boolean> {
    const record = await this.db.userLessonProgress.findUnique({
      where: { userId_lessonId: { userId, lessonId } },
      select: { completedAt: true },
    });
    return !!record?.completedAt;
  }

  async recomputeCourseProgress(
    userId: string,
    courseId: string,
  ): Promise<CourseProgress> {
    const [totalLessons, completedLessons] = await Promise.all([
      this.db.lesson.count({ where: { module: { courseId } } }),
      this.db.userLessonProgress.count({
        where: { userId, completedAt: { not: null }, lesson: { module: { courseId } } },
      }),
    ]);

    const progress = CourseProgress.fromCounts(courseId, completedLessons, totalLessons);
    await this.db.userCourseProgress.upsert({
      where: { userId_courseId: { userId, courseId } },
      create: {
        userId,
        courseId,
        percentComplete: progress.percentComplete,
        completedAt: progress.completedAt,
      },
      update: {
        percentComplete: progress.percentComplete,
        completedAt: progress.completedAt,
      },
    });
    return progress;
  }

  async getCourseProgress(
    userId: string,
    courseId: string,
  ): Promise<CourseProgress | null> {
    const record = await this.db.userCourseProgress.findUnique({
      where: { userId_courseId: { userId, courseId } },
    });
    return record
      ? CourseProgress.create({
          courseId,
          percentComplete: record.percentComplete,
          completedAt: record.completedAt,
        })
      : null;
  }

  async getAllCourseProgress(userId: string): Promise<CourseProgressSummary[]> {
    const courses = await this.db.course.findMany({
      orderBy: { order: "asc" },
      include: { progress: { where: { userId } } },
    });
    return courses.map((course) => ({
      track: course.track as CourseTrack,
      courseId: course.id,
      courseSlug: course.slug,
      courseTitle: course.title,
      percentComplete: course.progress[0]?.percentComplete ?? 0,
    }));
  }

  async markExerciseCompleted(
    userId: string,
    exerciseId: string,
    score: number,
  ): Promise<void> {
    const existing = await this.db.userExerciseProgress.findUnique({
      where: { userId_exerciseId: { userId, exerciseId } },
    });
    await this.db.userExerciseProgress.upsert({
      where: { userId_exerciseId: { userId, exerciseId } },
      create: {
        userId,
        exerciseId,
        completedAt: new Date(),
        bestScore: score,
        attempts: 1,
      },
      update: {
        completedAt: new Date(),
        bestScore: Math.max(existing?.bestScore ?? 0, score),
        attempts: { increment: 1 },
      },
    });
  }

  async isExerciseCompleted(userId: string, exerciseId: string): Promise<boolean> {
    const record = await this.db.userExerciseProgress.findUnique({
      where: { userId_exerciseId: { userId, exerciseId } },
      select: { completedAt: true },
    });
    return !!record?.completedAt;
  }

  async countCompletedExercises(userId: string): Promise<number> {
    return this.db.userExerciseProgress.count({
      where: { userId, completedAt: { not: null } },
    });
  }
}
