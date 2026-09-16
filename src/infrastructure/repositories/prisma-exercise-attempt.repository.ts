import type { PrismaClient } from "@/generated/prisma/client";
import type { ExerciseAttemptModel } from "@/generated/prisma/models/ExerciseAttempt";
import { ExerciseAttempt } from "@/entities/submission/model";
import type {
  CreateExerciseAttemptInput,
  ExerciseAttemptRepository,
} from "@/entities/submission/repository";
import type { SubmittedAnswer } from "@/entities/exercise/types";
import type { Prisma } from "@/generated/prisma/client";

export class PrismaExerciseAttemptRepository implements ExerciseAttemptRepository {
  constructor(private readonly db: PrismaClient) {}

  async create(input: CreateExerciseAttemptInput): Promise<ExerciseAttempt> {
    const record = await this.db.exerciseAttempt.create({
      data: {
        userId: input.userId,
        exerciseId: input.exerciseId,
        answer: input.answer as unknown as Prisma.InputJsonValue,
        isCorrect: input.isCorrect,
        pointsAwarded: input.pointsAwarded,
        feedback: input.feedback,
      },
    });
    return toDomain(record);
  }

  async countCorrectByUserId(userId: string): Promise<number> {
    const distinctExercises = await this.db.exerciseAttempt.findMany({
      where: { userId, isCorrect: true },
      distinct: ["exerciseId"],
      select: { exerciseId: true },
    });
    return distinctExercises.length;
  }

  async findByUserAndExercise(
    userId: string,
    exerciseId: string,
  ): Promise<ExerciseAttempt[]> {
    const records = await this.db.exerciseAttempt.findMany({
      where: { userId, exerciseId },
      orderBy: { createdAt: "desc" },
    });
    return records.map(toDomain);
  }
}

function toDomain(record: ExerciseAttemptModel): ExerciseAttempt {
  return ExerciseAttempt.create({
    id: record.id,
    userId: record.userId,
    exerciseId: record.exerciseId,
    answer: record.answer as unknown as SubmittedAnswer,
    isCorrect: record.isCorrect,
    pointsAwarded: record.pointsAwarded,
    feedback: record.feedback,
    createdAt: record.createdAt,
  });
}
