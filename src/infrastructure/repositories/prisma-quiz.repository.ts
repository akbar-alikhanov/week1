import type { PrismaClient, Prisma } from "@/generated/prisma/client";
import { Quiz, QuizQuestion } from "@/entities/quiz/model";
import type {
  QuizRepository,
  QuizWithAnswers,
  RecordQuizAttemptInput,
} from "@/entities/quiz/repository";

const withQuestions = { questions: { orderBy: { order: "asc" as const } } };
type QuizWithQuestions = Prisma.QuizGetPayload<{ include: typeof withQuestions }>;

export class PrismaQuizRepository implements QuizRepository {
  constructor(private readonly db: PrismaClient) {}

  async findByLessonId(lessonId: string): Promise<Quiz | null> {
    const record = await this.db.quiz.findUnique({
      where: { lessonId },
      include: withQuestions,
    });
    return record ? toDomain(record) : null;
  }

  async findWithAnswersById(id: string): Promise<QuizWithAnswers | null> {
    const record = await this.db.quiz.findUnique({
      where: { id },
      include: withQuestions,
    });
    if (!record) return null;

    const correctAnswers: Record<string, number> = {};
    for (const question of record.questions) {
      correctAnswers[question.id] = question.correctAnswer as unknown as number;
    }

    return { quiz: toDomain(record), correctAnswers };
  }

  async recordAttempt(input: RecordQuizAttemptInput): Promise<void> {
    await this.db.quizAttempt.create({
      data: {
        userId: input.userId,
        quizId: input.quizId,
        answers: input.answers,
        score: input.score,
        passed: input.passed,
      },
    });
  }

  async hasPassed(userId: string, quizId: string): Promise<boolean> {
    const attempt = await this.db.quizAttempt.findFirst({
      where: { userId, quizId, passed: true },
      select: { id: true },
    });
    return !!attempt;
  }
}

function toDomain(record: QuizWithQuestions): Quiz {
  return Quiz.create({
    id: record.id,
    lessonId: record.lessonId,
    title: record.title,
    passingScore: record.passingScore,
    questions: record.questions.map((question) =>
      QuizQuestion.create({
        id: question.id,
        question: question.question,
        options: question.options as unknown as string[],
        explanation: question.explanation,
        order: question.order,
      }),
    ),
  });
}
