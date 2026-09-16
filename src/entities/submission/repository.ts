import type { ExerciseAttempt, ExerciseAttemptProps } from "@/entities/submission/model";

export type CreateExerciseAttemptInput = Omit<ExerciseAttemptProps, "id" | "createdAt">;

export interface ExerciseAttemptRepository {
  create(input: CreateExerciseAttemptInput): Promise<ExerciseAttempt>;
  countCorrectByUserId(userId: string): Promise<number>;
  findByUserAndExercise(userId: string, exerciseId: string): Promise<ExerciseAttempt[]>;
}
