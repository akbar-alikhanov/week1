import type { Exercise, ExerciseWithAnswer } from "@/entities/exercise/model";

export interface ExerciseRepository {
  findById(id: string): Promise<Exercise | null>;
  findByLessonId(lessonId: string): Promise<Exercise[]>;
  /** Server-side only: includes the answer key, used exclusively by the grading use case. */
  findWithAnswerById(id: string): Promise<ExerciseWithAnswer | null>;
}
