import type { Lesson } from "@/entities/lesson/model";

export interface LessonRepository {
  findById(id: string): Promise<Lesson | null>;
  findByModuleId(moduleId: string): Promise<Lesson[]>;
  findBySlug(
    courseSlug: string,
    moduleSlug: string,
    lessonSlug: string,
  ): Promise<Lesson | null>;
  /** Lesson immediately after the given one within the same course, across module boundaries. */
  findNext(lessonId: string): Promise<Lesson | null>;
}
