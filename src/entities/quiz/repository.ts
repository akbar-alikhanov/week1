import type { Quiz } from "@/entities/quiz/model";

export interface QuizWithAnswers {
  quiz: Quiz;
  /** questionId -> correct option index. Server-side only. */
  correctAnswers: Record<string, number>;
}

export interface RecordQuizAttemptInput {
  userId: string;
  quizId: string;
  answers: Record<string, number>;
  score: number;
  passed: boolean;
}

export interface QuizRepository {
  findByLessonId(lessonId: string): Promise<Quiz | null>;
  findWithAnswersById(id: string): Promise<QuizWithAnswers | null>;
  recordAttempt(input: RecordQuizAttemptInput): Promise<void>;
  hasPassed(userId: string, quizId: string): Promise<boolean>;
}
