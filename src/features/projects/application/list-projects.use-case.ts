import { computeUnlockedCourseIds } from "@/entities/progress/model";
import type { ProjectRepository } from "@/entities/project/repository";
import type { ProjectSubmissionRepository } from "@/entities/project/repository";
import type { CourseRepository } from "@/entities/course/repository";
import type { ProgressRepository } from "@/entities/progress/repository";

export interface ProjectSummary {
  id: string;
  slug: string;
  title: string;
  goal: string;
  xpReward: number;
  courseSlug: string;
  courseTitle: string;
  isUnlocked: boolean;
  isCompleted: boolean;
}

export class ListProjectsUseCase {
  constructor(
    private readonly projectRepository: ProjectRepository,
    private readonly projectSubmissionRepository: ProjectSubmissionRepository,
    private readonly courseRepository: CourseRepository,
    private readonly progressRepository: ProgressRepository,
  ) {}

  async execute(userId: string | null): Promise<ProjectSummary[]> {
    const [projects, courses] = await Promise.all([
      this.projectRepository.findAll(),
      this.courseRepository.findAll(),
    ]);

    const coursesById = new Map(courses.map((course) => [course.id, course]));
    const progress = userId
      ? await this.progressRepository.getAllCourseProgress(userId)
      : [];
    const percentByCourseId = new Map(
      progress.map((p) => [p.courseId, p.percentComplete]),
    );
    const unlockedCourseIds = computeUnlockedCourseIds(
      courses
        .slice()
        .sort((a, b) => a.order - b.order)
        .map((course) => ({
          courseId: course.id,
          percentComplete: percentByCourseId.get(course.id) ?? 0,
        })),
    );

    const summaries = await Promise.all(
      projects.map(async (project) => {
        const course = coursesById.get(project.courseId);
        const submissions = userId
          ? await this.projectSubmissionRepository.findByUserAndProject(
              userId,
              project.id,
            )
          : [];
        return {
          id: project.id,
          slug: project.slug,
          title: project.title,
          goal: project.goal,
          xpReward: project.xpReward,
          courseSlug: course?.slug ?? "",
          courseTitle: course?.title ?? "",
          courseOrder: course?.order ?? 0,
          isUnlocked: userId ? unlockedCourseIds.has(project.courseId) : false,
          isCompleted: submissions.length > 0,
        };
      }),
    );

    return summaries
      .sort((a, b) => a.courseOrder - b.courseOrder)
      .map(({ courseOrder: _courseOrder, ...summary }) => summary);
  }
}
