import type { QuizRepository } from "@/entities/quiz/repository";
import type { UserRepository } from "@/entities/user/repository";
import { NotFoundError } from "@/shared/errors/app-error";
import { XP_REWARDS } from "@/shared/constants/gamification";

export interface SubmitQuizResult {
  score: number;
  passed: boolean;
  correctCount: number;
  totalQuestions: number;
  xpAwarded: number;
  totalXp: number;
  level: number;
  leveledUp: boolean;
}

export class SubmitQuizUseCase {
  constructor(
    private readonly quizRepository: QuizRepository,
    private readonly userRepository: UserRepository,
  ) {}

  async execute(
    userId: string,
    quizId: string,
    answers: Record<string, number>,
  ): Promise<SubmitQuizResult> {
    const found = await this.quizRepository.findWithAnswersById(quizId);
    if (!found) {
      throw new NotFoundError("Quiz", quizId);
    }
    const { quiz, correctAnswers } = found;

    const alreadyPassed = await this.quizRepository.hasPassed(userId, quizId);
    const { score, passed, correctCount } = quiz.grade(answers, correctAnswers);

    await this.quizRepository.recordAttempt({ userId, quizId, answers, score, passed });

    const user = await this.userRepository.findById(userId);
    if (!user) {
      throw new NotFoundError("User", userId);
    }

    if (!passed || alreadyPassed) {
      return {
        score,
        passed,
        correctCount,
        totalQuestions: quiz.questions.length,
        xpAwarded: 0,
        totalXp: user.xp,
        level: user.level,
        leveledUp: false,
      };
    }

    const levelBefore = user.level;
    const updatedUser = user.addXp(XP_REWARDS.QUIZ_PASSED).recordActivity();
    await this.userRepository.save(updatedUser);

    return {
      score,
      passed,
      correctCount,
      totalQuestions: quiz.questions.length,
      xpAwarded: XP_REWARDS.QUIZ_PASSED,
      totalXp: updatedUser.xp,
      level: updatedUser.level,
      leveledUp: updatedUser.level > levelBefore,
    };
  }
}
