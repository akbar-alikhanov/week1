import { describe, expect, it } from "vitest";

import { CourseModule } from "@/entities/module/model";
import { Lesson } from "@/entities/lesson/model";
import { User } from "@/entities/user/model";
import type { LessonRepository } from "@/entities/lesson/repository";
import type { ModuleRepository } from "@/entities/module/repository";
import type {
  ProgressRepository,
  CourseProgressSummary,
} from "@/entities/progress/repository";
import type { UserRepository, CreateUserInput } from "@/entities/user/repository";
import { CourseProgress, LessonProgress } from "@/entities/progress/model";
import { CompleteLessonUseCase } from "@/features/lessons/application/complete-lesson.use-case";

const lesson = Lesson.create({
  id: "lesson-1",
  moduleId: "module-1",
  slug: "if",
  title: "ЕСЛИ",
  description: "",
  order: 0,
  contentPath: "excel/module-02/15-if.mdx",
  xpReward: 25,
});

const courseModule = CourseModule.create({
  id: "module-1",
  courseId: "course-1",
  slug: "module-02",
  title: "Basic Formulas",
  description: "",
  order: 0,
});

class FakeLessonRepository implements LessonRepository {
  async findById(id: string) {
    return id === lesson.id ? lesson : null;
  }
  async findByModuleId() {
    return [lesson];
  }
  async findBySlug() {
    return lesson;
  }
  async findNext() {
    return null;
  }
}

class FakeModuleRepository implements ModuleRepository {
  async findById(id: string) {
    return id === courseModule.id ? courseModule : null;
  }
  async findByCourseId() {
    return [courseModule];
  }
}

class FakeProgressRepository implements ProgressRepository {
  completed = new Set<string>();

  async getLessonProgress(_userId: string, lessonId: string) {
    return LessonProgress.create({
      lessonId,
      completedAt: this.completed.has(lessonId) ? new Date() : null,
    });
  }
  async markLessonCompleted(_userId: string, lessonId: string) {
    this.completed.add(lessonId);
  }
  async isLessonCompleted(_userId: string, lessonId: string) {
    return this.completed.has(lessonId);
  }
  async recomputeCourseProgress(_userId: string, courseId: string) {
    return CourseProgress.fromCounts(courseId, this.completed.size, 1);
  }
  async getCourseProgress(_userId: string, courseId: string) {
    return CourseProgress.fromCounts(courseId, this.completed.size, 1);
  }
  async getAllCourseProgress(): Promise<CourseProgressSummary[]> {
    return [];
  }
  async markExerciseCompleted() {}
  async countCompletedExercises() {
    return 0;
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
    xp: 90,
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

describe("CompleteLessonUseCase", () => {
  it("awards XP, levels up and marks the lesson complete", async () => {
    const lessonRepo = new FakeLessonRepository();
    const moduleRepo = new FakeModuleRepository();
    const progressRepo = new FakeProgressRepository();
    const userRepo = new FakeUserRepository();
    const useCase = new CompleteLessonUseCase(
      lessonRepo,
      moduleRepo,
      progressRepo,
      userRepo,
    );

    const result = await useCase.execute("user-1", "lesson-1");

    expect(result.alreadyCompleted).toBe(false);
    expect(result.xpAwarded).toBe(25);
    expect(result.totalXp).toBe(115);
    expect(result.leveledUp).toBe(true);
    expect(result.level).toBe(2);
    expect(await progressRepo.isLessonCompleted("user-1", "lesson-1")).toBe(true);
  });

  it("is idempotent: completing an already-completed lesson awards no extra XP", async () => {
    const lessonRepo = new FakeLessonRepository();
    const moduleRepo = new FakeModuleRepository();
    const progressRepo = new FakeProgressRepository();
    const userRepo = new FakeUserRepository();
    const useCase = new CompleteLessonUseCase(
      lessonRepo,
      moduleRepo,
      progressRepo,
      userRepo,
    );

    await useCase.execute("user-1", "lesson-1");
    const second = await useCase.execute("user-1", "lesson-1");

    expect(second.alreadyCompleted).toBe(true);
    expect(second.xpAwarded).toBe(0);
    expect(second.totalXp).toBe(115);
  });
});
