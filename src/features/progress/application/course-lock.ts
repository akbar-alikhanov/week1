import { computeUnlockedCourseIds } from "@/entities/progress/model";
import type { CourseRepository } from "@/entities/course/repository";
import type { ProgressRepository } from "@/entities/progress/repository";
import { ForbiddenError } from "@/shared/errors/app-error";

/**
 * Enforces the roadmap unlock policy (see computeUnlockedCourseIds):
 * throws ForbiddenError if `courseId` isn't unlocked yet for this user.
 * A null userId (no session) is never enforced here - every route that
 * reaches this check already requires authentication.
 */
export async function assertCourseUnlocked(
  courseId: string,
  userId: string | null,
  courseRepository: CourseRepository,
  progressRepository: ProgressRepository,
): Promise<void> {
  if (!userId) return;

  const courses = await courseRepository.findAll();
  const progress = await progressRepository.getAllCourseProgress(userId);
  const percentByCourseId = new Map(progress.map((p) => [p.courseId, p.percentComplete]));

  const unlocked = computeUnlockedCourseIds(
    courses.map((course) => ({
      courseId: course.id,
      percentComplete: percentByCourseId.get(course.id) ?? 0,
    })),
  );

  if (!unlocked.has(courseId)) {
    throw new ForbiddenError(
      "Complete the previous course to unlock this one - check the roadmap.",
    );
  }
}
