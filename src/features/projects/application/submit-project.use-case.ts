import type {
  ProjectRepository,
  ProjectSubmissionRepository,
} from "@/entities/project/repository";
import type { CourseRepository } from "@/entities/course/repository";
import type { ProgressRepository } from "@/entities/progress/repository";
import type { UserRepository } from "@/entities/user/repository";
import { NotFoundError } from "@/shared/errors/app-error";
import { assertCourseUnlocked } from "@/features/progress/application/course-lock";
import { XP_REWARDS } from "@/shared/constants/gamification";

export interface SubmitProjectResult {
  submissionId: string;
  status: string;
  xpAwarded: number;
  totalXp: number;
  level: number;
  leveledUp: boolean;
}

/**
 * Projects have no rubric-based auto-grading (unlike exercises/quizzes, which
 * check against a stored correct answer): the "Evaluation" section is
 * displayed to the learner as a self-review checklist. The simplest
 * production-ready resolution is to accept every submission automatically
 * and award project XP once, on the learner's first submission for that
 * project - resubmissions are recorded (e.g. to update the deliverable) but
 * do not re-award XP. See ARCHITECTURE.md.
 */
export class SubmitProjectUseCase {
  constructor(
    private readonly projectRepository: ProjectRepository,
    private readonly projectSubmissionRepository: ProjectSubmissionRepository,
    private readonly courseRepository: CourseRepository,
    private readonly progressRepository: ProgressRepository,
    private readonly userRepository: UserRepository,
  ) {}

  async execute(
    userId: string,
    projectId: string,
    summary: string,
    deliverableUrl: string | null,
  ): Promise<SubmitProjectResult> {
    const project = await this.projectRepository.findById(projectId);
    if (!project) {
      throw new NotFoundError("Project", projectId);
    }

    await assertCourseUnlocked(
      project.courseId,
      userId,
      this.courseRepository,
      this.progressRepository,
    );

    const previousSubmissions =
      await this.projectSubmissionRepository.findByUserAndProject(userId, projectId);
    const isFirstSubmission = previousSubmissions.length === 0;

    const submission = await this.projectSubmissionRepository.create({
      userId,
      projectId,
      summary,
      deliverableUrl,
    });

    const user = await this.userRepository.findById(userId);
    if (!user) {
      throw new NotFoundError("User", userId);
    }

    if (!isFirstSubmission) {
      return {
        submissionId: submission.id,
        status: submission.status,
        xpAwarded: 0,
        totalXp: user.xp,
        level: user.level,
        leveledUp: false,
      };
    }

    const levelBefore = user.level;
    const updatedUser = user.addXp(XP_REWARDS.PROJECT_COMPLETED).recordActivity();
    await this.userRepository.save(updatedUser);

    return {
      submissionId: submission.id,
      status: submission.status,
      xpAwarded: XP_REWARDS.PROJECT_COMPLETED,
      totalXp: updatedUser.xp,
      level: updatedUser.level,
      leveledUp: updatedUser.level > levelBefore,
    };
  }
}
