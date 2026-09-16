import { evaluateAnswer } from "@/entities/exercise/evaluator";
import type { SubmittedAnswer } from "@/entities/exercise/types";
import type { ExerciseRepository } from "@/entities/exercise/repository";
import type { ExerciseAttemptRepository } from "@/entities/submission/repository";
import type { ProgressRepository } from "@/entities/progress/repository";
import type { UserRepository } from "@/entities/user/repository";
import { NotFoundError, ExerciseEvaluationError } from "@/shared/errors/app-error";
import { XP_REWARDS } from "@/shared/constants/gamification";
import type {
  SqlSandboxService,
  SqlQueryResult,
} from "@/features/exercises/application/ports";

export interface SubmitExerciseResult {
  isCorrect: boolean;
  pointsAwarded: number;
  explanation: string;
  xpAwarded: number;
  totalXp: number;
  level: number;
  leveledUp: boolean;
  /** Only present for SQL_QUERY exercises, to show the learner their query's output. */
  queryResult?: SqlQueryResult;
}

export class SubmitExerciseUseCase {
  constructor(
    private readonly exerciseRepository: ExerciseRepository,
    private readonly attemptRepository: ExerciseAttemptRepository,
    private readonly progressRepository: ProgressRepository,
    private readonly userRepository: UserRepository,
    private readonly sqlSandbox: SqlSandboxService,
  ) {}

  async execute(
    userId: string,
    exerciseId: string,
    answer: SubmittedAnswer,
  ): Promise<SubmitExerciseResult> {
    const found = await this.exerciseRepository.findWithAnswerById(exerciseId);
    if (!found) {
      throw new NotFoundError("Exercise", exerciseId);
    }
    const { exercise, correctAnswer } = found;

    let isCorrect: boolean;
    let queryResult: SqlQueryResult | undefined;

    if (correctAnswer.type === "SQL_QUERY") {
      if (answer.type !== "SQL_QUERY") {
        throw new ExerciseEvaluationError(
          "A SQL query answer is required for this exercise.",
        );
      }
      const [learnerResult, referenceResult] = await Promise.all([
        this.sqlSandbox.run(answer.query),
        this.sqlSandbox.run(correctAnswer.referenceQuery),
      ]);
      queryResult = learnerResult;
      isCorrect = rowsMatch(learnerResult.rows, referenceResult.rows);
    } else {
      isCorrect = evaluateAnswer(correctAnswer, answer).isCorrect;
    }

    const pointsAwarded = isCorrect ? exercise.points : 0;

    await this.attemptRepository.create({
      userId,
      exerciseId,
      answer,
      isCorrect,
      pointsAwarded,
      feedback: exercise.explanation,
    });

    const user = await this.userRepository.findById(userId);
    if (!user) {
      throw new NotFoundError("User", userId);
    }

    if (!isCorrect) {
      return {
        isCorrect,
        pointsAwarded,
        explanation: exercise.explanation,
        xpAwarded: 0,
        totalXp: user.xp,
        level: user.level,
        leveledUp: false,
        queryResult,
      };
    }

    const alreadyCompleted = await this.progressRepository.isExerciseCompleted(
      userId,
      exerciseId,
    );
    await this.progressRepository.markExerciseCompleted(
      userId,
      exerciseId,
      pointsAwarded,
    );

    if (alreadyCompleted) {
      return {
        isCorrect,
        pointsAwarded,
        explanation: exercise.explanation,
        xpAwarded: 0,
        totalXp: user.xp,
        level: user.level,
        leveledUp: false,
        queryResult,
      };
    }

    const xpAwarded = XP_REWARDS.EXERCISE_COMPLETED;
    const levelBefore = user.level;
    const updatedUser = user.addXp(xpAwarded).recordActivity();
    await this.userRepository.save(updatedUser);

    return {
      isCorrect,
      pointsAwarded,
      explanation: exercise.explanation,
      xpAwarded,
      totalXp: updatedUser.xp,
      level: updatedUser.level,
      leveledUp: updatedUser.level > levelBefore,
      queryResult,
    };
  }
}

/** Order-insensitive comparison of two SQL result sets. */
function rowsMatch(a: Record<string, unknown>[], b: Record<string, unknown>[]): boolean {
  if (a.length !== b.length) return false;
  const normalize = (rows: Record<string, unknown>[]) =>
    rows.map((row) => JSON.stringify(sortKeys(row))).sort();
  const normalizedA = normalize(a);
  const normalizedB = normalize(b);
  return normalizedA.every((row, index) => row === normalizedB[index]);
}

function sortKeys(row: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(row).sort(([keyA], [keyB]) => keyA.localeCompare(keyB)),
  );
}
