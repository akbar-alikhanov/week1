import type {
  ProjectRepository,
  ProjectSubmissionRepository,
} from "@/entities/project/repository";
import type { CourseRepository } from "@/entities/course/repository";
import type { ProgressRepository } from "@/entities/progress/repository";
import { NotFoundError } from "@/shared/errors/app-error";
import { assertCourseUnlocked } from "@/features/progress/application/course-lock";

export interface ProjectTaskDetail {
  id: string;
  title: string;
  description: string;
}

export interface ProjectSubmissionDetail {
  id: string;
  summary: string;
  deliverableUrl: string | null;
  status: string;
  feedback: string | null;
  createdAt: string;
}

export interface ProjectDetail {
  id: string;
  slug: string;
  title: string;
  courseSlug: string;
  courseTitle: string;
  businessContext: string;
  datasetDescription: string;
  goal: string;
  deliverables: string[];
  evaluationCriteria: string[];
  hints: string[];
  xpReward: number;
  tasks: ProjectTaskDetail[];
  submissions: ProjectSubmissionDetail[];
}

export class GetProjectUseCase {
  constructor(
    private readonly projectRepository: ProjectRepository,
    private readonly projectSubmissionRepository: ProjectSubmissionRepository,
    private readonly courseRepository: CourseRepository,
    private readonly progressRepository: ProgressRepository,
  ) {}

  async execute(projectSlug: string, userId: string | null): Promise<ProjectDetail> {
    const project = await this.projectRepository.findBySlug(projectSlug);
    if (!project) {
      throw new NotFoundError("Project", projectSlug);
    }

    await assertCourseUnlocked(
      project.courseId,
      userId,
      this.courseRepository,
      this.progressRepository,
    );

    const course = await this.courseRepository.findById(project.courseId);
    if (!course) {
      throw new NotFoundError("Course", project.courseId);
    }

    const submissions = userId
      ? await this.projectSubmissionRepository.findByUserAndProject(userId, project.id)
      : [];

    return {
      id: project.id,
      slug: project.slug,
      title: project.title,
      courseSlug: course.slug,
      courseTitle: course.title,
      businessContext: project.businessContext,
      datasetDescription: project.datasetDescription,
      goal: project.goal,
      deliverables: project.deliverables,
      evaluationCriteria: project.evaluationCriteria,
      hints: project.hints,
      xpReward: project.xpReward,
      tasks: project.tasks
        .slice()
        .sort((a, b) => a.order - b.order)
        .map((task) => ({
          id: task.id,
          title: task.title,
          description: task.description,
        })),
      submissions: submissions.map((submission) => ({
        id: submission.id,
        summary: submission.summary,
        deliverableUrl: submission.deliverableUrl,
        status: submission.status,
        feedback: submission.feedback,
        createdAt: submission.createdAt.toISOString(),
      })),
    };
  }
}
