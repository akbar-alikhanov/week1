export interface CourseProgressProps {
  courseId: string;
  percentComplete: number;
  completedAt: Date | null;
}

export class CourseProgress {
  private constructor(private props: CourseProgressProps) {}

  static create(props: CourseProgressProps): CourseProgress {
    return new CourseProgress(props);
  }

  /** Derives percent-complete (0-100) from completed vs. total lesson counts. */
  static fromCounts(
    courseId: string,
    completedLessons: number,
    totalLessons: number,
  ): CourseProgress {
    const percentComplete =
      totalLessons === 0 ? 0 : Math.round((completedLessons / totalLessons) * 100);
    return new CourseProgress({
      courseId,
      percentComplete,
      completedAt: percentComplete === 100 ? new Date() : null,
    });
  }

  get courseId() {
    return this.props.courseId;
  }
  get percentComplete() {
    return this.props.percentComplete;
  }
  get completedAt() {
    return this.props.completedAt;
  }

  toProps(): CourseProgressProps {
    return { ...this.props };
  }
}

export interface RoadmapCourseInput {
  courseId: string;
  percentComplete: number;
}

/**
 * The roadmap unlock policy: the first course is always unlocked; every
 * following course unlocks once the previous one reaches 100%. Pure so it
 * can back both the visual roadmap and the actual access check in
 * GetCourseUseCase/GetLessonUseCase from a single source of truth.
 */
export function computeUnlockedCourseIds(
  coursesInOrder: RoadmapCourseInput[],
): Set<string> {
  const unlocked = new Set<string>();
  let previousComplete = true;
  for (const course of coursesInOrder) {
    if (previousComplete) {
      unlocked.add(course.courseId);
    }
    previousComplete = course.percentComplete === 100;
  }
  return unlocked;
}

export interface LessonProgressProps {
  lessonId: string;
  completedAt: Date | null;
}

export class LessonProgress {
  private constructor(private props: LessonProgressProps) {}

  static create(props: LessonProgressProps): LessonProgress {
    return new LessonProgress(props);
  }

  get lessonId() {
    return this.props.lessonId;
  }
  get isCompleted() {
    return this.props.completedAt !== null;
  }
  get completedAt() {
    return this.props.completedAt;
  }

  toProps(): LessonProgressProps {
    return { ...this.props };
  }
}
