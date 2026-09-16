import { prisma } from "@/infrastructure/database/prisma-client";
import { PrismaUserRepository } from "@/infrastructure/repositories/prisma-user.repository";
import { PrismaCourseRepository } from "@/infrastructure/repositories/prisma-course.repository";
import { PrismaModuleRepository } from "@/infrastructure/repositories/prisma-module.repository";
import { PrismaLessonRepository } from "@/infrastructure/repositories/prisma-lesson.repository";
import { PrismaProgressRepository } from "@/infrastructure/repositories/prisma-progress.repository";
import { PrismaExerciseRepository } from "@/infrastructure/repositories/prisma-exercise.repository";
import { PrismaExerciseAttemptRepository } from "@/infrastructure/repositories/prisma-exercise-attempt.repository";
import { PrismaQuizRepository } from "@/infrastructure/repositories/prisma-quiz.repository";
import { PrismaAchievementRepository } from "@/infrastructure/repositories/prisma-achievement.repository";
import { BcryptPasswordHasher } from "@/infrastructure/services/bcrypt-password-hasher";
import { PostgresSqlSandboxService } from "@/infrastructure/services/postgres-sql-sandbox.service";
import { FsLessonContentReader } from "@/infrastructure/content/fs-lesson-content-reader";
import { RegisterUserUseCase } from "@/features/authentication/application/register-user.use-case";
import { AuthenticateUserUseCase } from "@/features/authentication/application/authenticate-user.use-case";
import { ListCoursesUseCase } from "@/features/courses/application/list-courses.use-case";
import { GetCourseUseCase } from "@/features/courses/application/get-course.use-case";
import { GetLessonUseCase } from "@/features/lessons/application/get-lesson.use-case";
import { CompleteLessonUseCase } from "@/features/lessons/application/complete-lesson.use-case";
import { SubmitExerciseUseCase } from "@/features/exercises/application/submit-exercise.use-case";
import { ExecuteSqlExerciseUseCase } from "@/features/exercises/application/execute-sql-exercise.use-case";
import { SubmitQuizUseCase } from "@/features/quizzes/application/submit-quiz.use-case";
import { ListQuizzesUseCase } from "@/features/quizzes/application/list-quizzes.use-case";
import { ListExercisesUseCase } from "@/features/exercises/application/list-exercises.use-case";
import { EvaluateAchievementsUseCase } from "@/features/achievements/application/evaluate-achievements.use-case";
import { ListAchievementsUseCase } from "@/features/achievements/application/list-achievements.use-case";
import { GetDashboardUseCase } from "@/features/progress/application/get-dashboard.use-case";

/**
 * Composition root: the one place infrastructure implementations are wired
 * to the interfaces the application layer depends on. Server Actions and
 * route handlers pull dependencies from here; nothing under
 * src/entities or src/features/*\/application ever imports this file.
 */
class Container {
  readonly userRepository = new PrismaUserRepository(prisma);
  readonly courseRepository = new PrismaCourseRepository(prisma);
  readonly moduleRepository = new PrismaModuleRepository(prisma);
  readonly lessonRepository = new PrismaLessonRepository(prisma);
  readonly progressRepository = new PrismaProgressRepository(prisma);
  readonly exerciseRepository = new PrismaExerciseRepository(prisma);
  readonly exerciseAttemptRepository = new PrismaExerciseAttemptRepository(prisma);
  readonly quizRepository = new PrismaQuizRepository(prisma);
  readonly achievementRepository = new PrismaAchievementRepository(prisma);

  readonly passwordHasher = new BcryptPasswordHasher();
  readonly lessonContentReader = new FsLessonContentReader();
  readonly sqlSandbox = new PostgresSqlSandboxService();

  readonly registerUserUseCase = new RegisterUserUseCase(
    this.userRepository,
    this.passwordHasher,
  );
  readonly authenticateUserUseCase = new AuthenticateUserUseCase(
    this.userRepository,
    this.passwordHasher,
  );

  readonly listCoursesUseCase = new ListCoursesUseCase(
    this.courseRepository,
    this.progressRepository,
  );
  readonly getCourseUseCase = new GetCourseUseCase(
    this.courseRepository,
    this.moduleRepository,
    this.lessonRepository,
    this.progressRepository,
  );
  readonly getLessonUseCase = new GetLessonUseCase(
    this.lessonRepository,
    this.moduleRepository,
    this.courseRepository,
    this.progressRepository,
    this.lessonContentReader,
    this.exerciseRepository,
    this.quizRepository,
  );
  readonly completeLessonUseCase = new CompleteLessonUseCase(
    this.lessonRepository,
    this.moduleRepository,
    this.progressRepository,
    this.userRepository,
  );
  readonly submitExerciseUseCase = new SubmitExerciseUseCase(
    this.exerciseRepository,
    this.exerciseAttemptRepository,
    this.progressRepository,
    this.userRepository,
    this.sqlSandbox,
  );
  readonly executeSqlExerciseUseCase = new ExecuteSqlExerciseUseCase(this.sqlSandbox);
  readonly submitQuizUseCase = new SubmitQuizUseCase(
    this.quizRepository,
    this.userRepository,
  );
  readonly listQuizzesUseCase = new ListQuizzesUseCase(
    this.courseRepository,
    this.moduleRepository,
    this.lessonRepository,
    this.quizRepository,
  );
  readonly listExercisesUseCase = new ListExercisesUseCase(
    this.courseRepository,
    this.moduleRepository,
    this.lessonRepository,
    this.exerciseRepository,
    this.progressRepository,
  );
  readonly evaluateAchievementsUseCase = new EvaluateAchievementsUseCase(
    this.achievementRepository,
  );
  readonly listAchievementsUseCase = new ListAchievementsUseCase(
    this.achievementRepository,
  );
  readonly getDashboardUseCase = new GetDashboardUseCase(
    this.userRepository,
    this.courseRepository,
    this.moduleRepository,
    this.lessonRepository,
    this.progressRepository,
    this.achievementRepository,
  );
}

let instance: Container | undefined;

export function getContainer(): Container {
  if (!instance) {
    instance = new Container();
  }
  return instance;
}
