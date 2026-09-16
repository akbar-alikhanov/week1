import { describe, expect, it } from "vitest";

import { Exercise } from "@/entities/exercise/model";
import { User } from "@/entities/user/model";
import type { ExerciseRepository } from "@/entities/exercise/repository";
import type {
  ExerciseAttemptRepository,
  CreateExerciseAttemptInput,
} from "@/entities/submission/repository";
import type {
  ProgressRepository,
  CourseProgressSummary,
} from "@/entities/progress/repository";
import type { UserRepository, CreateUserInput } from "@/entities/user/repository";
import { CourseProgress, LessonProgress } from "@/entities/progress/model";
import type { CorrectAnswer } from "@/entities/exercise/types";
import type {
  SqlQueryResult,
  SqlSandboxService,
} from "@/features/exercises/application/ports";
import { SubmitExerciseUseCase } from "@/features/exercises/application/submit-exercise.use-case";

const trueFalseExercise = Exercise.create({
  id: "ex-1",
  lessonId: "lesson-1",
  type: "TRUE_FALSE",
  title: "Is Excel a spreadsheet?",
  description: "",
  difficulty: "BEGINNER",
  points: 10,
  order: 0,
  data: { type: "TRUE_FALSE" },
  explanation: "Yes, Excel is a spreadsheet application.",
});

const sqlExercise = Exercise.create({
  id: "ex-2",
  lessonId: "lesson-2",
  type: "SQL_QUERY",
  title: "Select all products",
  description: "",
  difficulty: "BEGINNER",
  points: 15,
  order: 0,
  data: { type: "SQL_QUERY", datasetId: "shop", schemaHint: "" },
  explanation: "SELECT * FROM products; returns every row.",
});

class FakeExerciseRepository implements ExerciseRepository {
  constructor(private readonly correctAnswer: CorrectAnswer) {}

  async findById(id: string) {
    return id === trueFalseExercise.id ? trueFalseExercise : sqlExercise;
  }
  async findByLessonId() {
    return [trueFalseExercise];
  }
  async findWithAnswerById(id: string) {
    const exercise = id === trueFalseExercise.id ? trueFalseExercise : sqlExercise;
    return { exercise, correctAnswer: this.correctAnswer };
  }
}

class FakeAttemptRepository implements ExerciseAttemptRepository {
  attempts: CreateExerciseAttemptInput[] = [];

  async create(input: CreateExerciseAttemptInput) {
    this.attempts.push(input);
    return {
      id: `attempt-${this.attempts.length}`,
      ...input,
      createdAt: new Date(),
    } as never;
  }
  async countCorrectByUserId() {
    return this.attempts.filter((a) => a.isCorrect).length;
  }
  async findByUserAndExercise() {
    return [];
  }
}

class FakeProgressRepository implements ProgressRepository {
  completedExercises = new Set<string>();

  async getLessonProgress(_userId: string, lessonId: string) {
    return LessonProgress.create({ lessonId, completedAt: null });
  }
  async markLessonCompleted() {}
  async isLessonCompleted() {
    return false;
  }
  async recomputeCourseProgress(_userId: string, courseId: string) {
    return CourseProgress.fromCounts(courseId, 0, 1);
  }
  async getCourseProgress(_userId: string, courseId: string) {
    return CourseProgress.fromCounts(courseId, 0, 1);
  }
  async getAllCourseProgress(): Promise<CourseProgressSummary[]> {
    return [];
  }
  async markExerciseCompleted(_userId: string, exerciseId: string) {
    this.completedExercises.add(exerciseId);
  }
  async isExerciseCompleted(_userId: string, exerciseId: string) {
    return this.completedExercises.has(exerciseId);
  }
  async countCompletedExercises() {
    return this.completedExercises.size;
  }
}

class FakeUserRepository implements UserRepository {
  user = User.create({
    id: "user-1",
    name: "Learner",
    email: "learner@example.com",
    passwordHash: null,
    image: null,
    level: 1,
    xp: 0,
    currentStreak: 0,
    longestStreak: 0,
    lastActivityAt: null,
    createdAt: new Date(),
  });

  async findById(id: string) {
    return id === this.user.id ? this.user : null;
  }
  async findByEmail() {
    return this.user;
  }
  async create(_input: CreateUserInput) {
    return this.user;
  }
  async save(user: User) {
    this.user = user;
  }
}

class FakeSqlSandboxService implements SqlSandboxService {
  constructor(private readonly resultsByQuery: Map<string, SqlQueryResult>) {}

  async run(query: string): Promise<SqlQueryResult> {
    const result = this.resultsByQuery.get(query.trim());
    if (!result) throw new Error(`No fake result configured for query: ${query}`);
    return result;
  }
}

describe("SubmitExerciseUseCase", () => {
  it("grades a non-SQL exercise via the pure evaluator and awards XP once", async () => {
    const exerciseRepo = new FakeExerciseRepository({ type: "TRUE_FALSE", value: true });
    const attemptRepo = new FakeAttemptRepository();
    const progressRepo = new FakeProgressRepository();
    const userRepo = new FakeUserRepository();
    const sandbox = new FakeSqlSandboxService(new Map());
    const useCase = new SubmitExerciseUseCase(
      exerciseRepo,
      attemptRepo,
      progressRepo,
      userRepo,
      sandbox,
    );

    const first = await useCase.execute("user-1", "ex-1", {
      type: "TRUE_FALSE",
      value: true,
    });
    expect(first.isCorrect).toBe(true);
    expect(first.xpAwarded).toBe(20);
    expect(first.totalXp).toBe(20);

    const second = await useCase.execute("user-1", "ex-1", {
      type: "TRUE_FALSE",
      value: true,
    });
    expect(second.isCorrect).toBe(true);
    expect(second.xpAwarded).toBe(0);
    expect(second.totalXp).toBe(20);
  });

  it("marks an incorrect answer wrong without awarding XP", async () => {
    const exerciseRepo = new FakeExerciseRepository({ type: "TRUE_FALSE", value: true });
    const attemptRepo = new FakeAttemptRepository();
    const progressRepo = new FakeProgressRepository();
    const userRepo = new FakeUserRepository();
    const sandbox = new FakeSqlSandboxService(new Map());
    const useCase = new SubmitExerciseUseCase(
      exerciseRepo,
      attemptRepo,
      progressRepo,
      userRepo,
      sandbox,
    );

    const result = await useCase.execute("user-1", "ex-1", {
      type: "TRUE_FALSE",
      value: false,
    });
    expect(result.isCorrect).toBe(false);
    expect(result.xpAwarded).toBe(0);
  });

  it("grades SQL_QUERY exercises by comparing sandbox result rows, order-insensitively", async () => {
    const referenceQuery = "SELECT * FROM products;";
    const learnerQuery = "select * from products;";
    const resultsByQuery = new Map<string, SqlQueryResult>([
      [
        referenceQuery,
        {
          columns: ["id", "name"],
          rows: [
            { id: 1, name: "A" },
            { id: 2, name: "B" },
          ],
        },
      ],
      [
        learnerQuery,
        {
          columns: ["id", "name"],
          rows: [
            { id: 2, name: "B" },
            { id: 1, name: "A" },
          ],
        },
      ],
    ]);

    const exerciseRepo = new FakeExerciseRepository({
      type: "SQL_QUERY",
      referenceQuery,
    });
    const attemptRepo = new FakeAttemptRepository();
    const progressRepo = new FakeProgressRepository();
    const userRepo = new FakeUserRepository();
    const sandbox = new FakeSqlSandboxService(resultsByQuery);
    const useCase = new SubmitExerciseUseCase(
      exerciseRepo,
      attemptRepo,
      progressRepo,
      userRepo,
      sandbox,
    );

    const result = await useCase.execute("user-1", "ex-2", {
      type: "SQL_QUERY",
      query: learnerQuery,
    });
    expect(result.isCorrect).toBe(true);
    expect(result.queryResult?.rows).toHaveLength(2);
  });

  it("marks a SQL_QUERY exercise wrong when the result rows differ", async () => {
    const referenceQuery = "SELECT * FROM products;";
    const learnerQuery = "SELECT * FROM products WHERE price > 1000;";
    const resultsByQuery = new Map<string, SqlQueryResult>([
      [referenceQuery, { columns: ["id"], rows: [{ id: 1 }, { id: 2 }] }],
      [learnerQuery, { columns: ["id"], rows: [{ id: 1 }] }],
    ]);

    const exerciseRepo = new FakeExerciseRepository({
      type: "SQL_QUERY",
      referenceQuery,
    });
    const attemptRepo = new FakeAttemptRepository();
    const progressRepo = new FakeProgressRepository();
    const userRepo = new FakeUserRepository();
    const sandbox = new FakeSqlSandboxService(resultsByQuery);
    const useCase = new SubmitExerciseUseCase(
      exerciseRepo,
      attemptRepo,
      progressRepo,
      userRepo,
      sandbox,
    );

    const result = await useCase.execute("user-1", "ex-2", {
      type: "SQL_QUERY",
      query: learnerQuery,
    });
    expect(result.isCorrect).toBe(false);
  });
});
