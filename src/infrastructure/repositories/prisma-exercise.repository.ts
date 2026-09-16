import type { PrismaClient } from "@/generated/prisma/client";
import type { ExerciseModel } from "@/generated/prisma/models/Exercise";
import { Exercise } from "@/entities/exercise/model";
import type { ExerciseWithAnswer } from "@/entities/exercise/model";
import type { ExerciseRepository } from "@/entities/exercise/repository";
import type {
  CorrectAnswer,
  Difficulty,
  ExerciseData,
  ExerciseType,
} from "@/entities/exercise/types";

export class PrismaExerciseRepository implements ExerciseRepository {
  constructor(private readonly db: PrismaClient) {}

  async findById(id: string): Promise<Exercise | null> {
    const record = await this.db.exercise.findUnique({ where: { id } });
    return record ? toDomain(record) : null;
  }

  async findByLessonId(lessonId: string): Promise<Exercise[]> {
    const records = await this.db.exercise.findMany({
      where: { lessonId },
      orderBy: { order: "asc" },
    });
    return records.map(toDomain);
  }

  async findWithAnswerById(id: string): Promise<ExerciseWithAnswer | null> {
    const record = await this.db.exercise.findUnique({ where: { id } });
    if (!record) return null;
    return {
      exercise: toDomain(record),
      correctAnswer: record.correctAnswer as unknown as CorrectAnswer,
    };
  }
}

function toDomain(record: ExerciseModel): Exercise {
  return Exercise.create({
    id: record.id,
    lessonId: record.lessonId,
    type: record.type as ExerciseType,
    title: record.title,
    description: record.description,
    difficulty: record.difficulty as Difficulty,
    points: record.points,
    order: record.order,
    data: record.data as unknown as ExerciseData,
    explanation: record.explanation,
  });
}
