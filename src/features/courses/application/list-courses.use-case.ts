import type { CourseRepository } from "@/entities/course/repository";
import type { ProgressRepository } from "@/entities/progress/repository";
import { computeUnlockedCourseIds } from "@/entities/progress/model";

export interface CourseListItem {
  id: string;
  slug: string;
  track: string;
  title: string;
  description: string;
  percentComplete: number;
  isUnlocked: boolean;
}

export class ListCoursesUseCase {
  constructor(
    private readonly courseRepository: CourseRepository,
    private readonly progressRepository: ProgressRepository,
  ) {}

  async execute(userId: string | null): Promise<CourseListItem[]> {
    const courses = await this.courseRepository.findAll();
    const progressByCourseId = new Map<string, number>();

    if (userId) {
      const summaries = await this.progressRepository.getAllCourseProgress(userId);
      for (const summary of summaries) {
        progressByCourseId.set(summary.courseId, summary.percentComplete);
      }
    }

    const unlocked = computeUnlockedCourseIds(
      courses.map((course) => ({
        courseId: course.id,
        percentComplete: progressByCourseId.get(course.id) ?? 0,
      })),
    );

    return courses.map((course) => ({
      id: course.id,
      slug: course.slug,
      track: course.track,
      title: course.title,
      description: course.description,
      percentComplete: progressByCourseId.get(course.id) ?? 0,
      isUnlocked: unlocked.has(course.id),
    }));
  }
}
