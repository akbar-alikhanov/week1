import type { CourseRepository } from "@/entities/course/repository";
import type { ProgressRepository } from "@/entities/progress/repository";

export interface CourseListItem {
  id: string;
  slug: string;
  track: string;
  title: string;
  description: string;
  percentComplete: number;
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

    return courses.map((course) => ({
      id: course.id,
      slug: course.slug,
      track: course.track,
      title: course.title,
      description: course.description,
      percentComplete: progressByCourseId.get(course.id) ?? 0,
    }));
  }
}
