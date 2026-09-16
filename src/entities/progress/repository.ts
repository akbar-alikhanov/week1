import type { CourseTrack } from "@/entities/course/model";
import type { CourseProgress, LessonProgress } from "@/entities/progress/model";

export interface CourseProgressSummary {
  track: CourseTrack;
  courseId: string;
  courseSlug: string;
  courseTitle: string;
  percentComplete: number;
}

export interface ProgressRepository {
  getLessonProgress(userId: string, lessonId: string): Promise<LessonProgress | null>;
  markLessonCompleted(userId: string, lessonId: string): Promise<void>;
  isLessonCompleted(userId: string, lessonId: string): Promise<boolean>;

  recomputeCourseProgress(userId: string, courseId: string): Promise<CourseProgress>;
  getCourseProgress(userId: string, courseId: string): Promise<CourseProgress | null>;
  getAllCourseProgress(userId: string): Promise<CourseProgressSummary[]>;

  markExerciseCompleted(userId: string, exerciseId: string, score: number): Promise<void>;
  isExerciseCompleted(userId: string, exerciseId: string): Promise<boolean>;
  countCompletedExercises(userId: string): Promise<number>;
}
