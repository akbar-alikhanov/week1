import { describe, expect, it } from "vitest";

import { Quiz, QuizQuestion } from "@/entities/quiz/model";
import { User } from "@/entities/user/model";
import type {
  QuizRepository,
  QuizWithAnswers,
  RecordQuizAttemptInput,
} from "@/entities/quiz/repository";
import type { CreateUserInput, UserRepository } from "@/entities/user/repository";
import { SubmitQuizUseCase } from "@/features/quizzes/application/submit-quiz.use-case";

const quiz = Quiz.create({
  id: "quiz-1",
  lessonId: "lesson-1",
  title: "Sample quiz",
  passingScore: 70,
  questions: [
    QuizQuestion.create({
      id: "q1",
      question: "2 + 2?",
      options: ["3", "4"],
      explanation: "",
      order: 0,
    }),
  ],
});
const correctAnswers = { q1: 1 };

class FakeQuizRepository implements QuizRepository {
  passedAttempts = new Set<string>();

  async findByLessonId() {
    return quiz;
  }
  async findWithAnswersById(id: string): Promise<QuizWithAnswers | null> {
    return id === quiz.id ? { quiz, correctAnswers } : null;
  }
  async recordAttempt(input: RecordQuizAttemptInput) {
    if (input.passed) this.passedAttempts.add(`${input.userId}:${input.quizId}`);
  }
  async hasPassed(userId: string, quizId: string) {
    return this.passedAttempts.has(`${userId}:${quizId}`);
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

describe("SubmitQuizUseCase", () => {
  it("awards XP on a passing attempt", async () => {
    const useCase = new SubmitQuizUseCase(
      new FakeQuizRepository(),
      new FakeUserRepository(),
    );

    const result = await useCase.execute("user-1", "quiz-1", { q1: 1 });

    expect(result.passed).toBe(true);
    expect(result.score).toBe(100);
    expect(result.xpAwarded).toBe(30);
    expect(result.totalXp).toBe(30);
  });

  it("awards no XP on a failing attempt", async () => {
    const useCase = new SubmitQuizUseCase(
      new FakeQuizRepository(),
      new FakeUserRepository(),
    );

    const result = await useCase.execute("user-1", "quiz-1", { q1: 0 });

    expect(result.passed).toBe(false);
    expect(result.xpAwarded).toBe(0);
    expect(result.totalXp).toBe(0);
  });

  it("does not re-award XP for a second passing attempt", async () => {
    const quizRepository = new FakeQuizRepository();
    const useCase = new SubmitQuizUseCase(quizRepository, new FakeUserRepository());

    await useCase.execute("user-1", "quiz-1", { q1: 1 });
    const second = await useCase.execute("user-1", "quiz-1", { q1: 1 });

    expect(second.passed).toBe(true);
    expect(second.xpAwarded).toBe(0);
  });
});
