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
