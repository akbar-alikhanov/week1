import { describe, expect, it } from "vitest";

import { Course } from "@/entities/course/model";
import { Project, ProjectTask } from "@/entities/project/model";
import { ProjectSubmission } from "@/entities/project/submission";
import { User } from "@/entities/user/model";
import type { CourseRepository } from "@/entities/course/repository";
import type {
  CreateProjectSubmissionInput,
  ProjectRepository,
  ProjectSubmissionRepository,
} from "@/entities/project/repository";
import type {
  ProgressRepository,
  CourseProgressSummary,
} from "@/entities/progress/repository";
import type { CreateUserInput, UserRepository } from "@/entities/user/repository";
import { SubmitProjectUseCase } from "@/features/projects/application/submit-project.use-case";

const course = Course.create({
  id: "course-1",
  slug: "excel",
  track: "EXCEL",
  title: "Excel",
  description: "",
  order: 0,
});

const project = Project.create({
  id: "project-1",
  courseId: course.id,
  slug: "sales-analysis-excel",
  title: "Sales Analysis",
  businessContext: "",
  datasetDescription: "",
  goal: "",
  deliverables: [],
  evaluationCriteria: [],
  hints: [],
  order: 0,
  xpReward: 200,
  tasks: [ProjectTask.create({ id: "task-1", title: "t", description: "d", order: 0 })],
});

class FakeCourseRepository implements CourseRepository {
  async findAll() {
    return [course];
  }
  async findById(id: string) {
    return id === course.id ? course : null;
  }
  async findBySlug() {
    return course;
  }
  async findByTrack() {
    return course;
  }
}

class FakeProgressRepository implements ProgressRepository {
  async getLessonProgress(): Promise<never> {
    throw new Error("not used");
  }
  async markLessonCompleted() {}
  async isLessonCompleted() {
    return false;
  }
  async recomputeCourseProgress(): Promise<never> {
    throw new Error("not used");
  }
  async getCourseProgress(): Promise<never> {
    throw new Error("not used");
  }
  async getAllCourseProgress(): Promise<CourseProgressSummary[]> {
    return [];
  }
  async markExerciseCompleted() {}
  async isExerciseCompleted() {
    return false;
  }
  async countCompletedExercises() {
    return 0;
  }
}

class FakeProjectRepository implements ProjectRepository {
  async findAll() {
    return [project];
  }
  async findById(id: string) {
    return id === project.id ? project : null;
  }
  async findBySlug() {
    return project;
  }
  async findByCourseId() {
    return [project];
  }
}

class FakeProjectSubmissionRepository implements ProjectSubmissionRepository {
  submissions: ProjectSubmission[] = [];

  async create(input: CreateProjectSubmissionInput) {
    const submission = ProjectSubmission.create({
      id: `submission-${this.submissions.length + 1}`,
      userId: input.userId,
      projectId: input.projectId,
      summary: input.summary,
      deliverableUrl: input.deliverableUrl,
      status: "ACCEPTED",
      feedback: null,
      createdAt: new Date(),
    });
    this.submissions.push(submission);
    return submission;
  }

  async findByUserAndProject(userId: string, projectId: string) {
    return this.submissions.filter(
      (s) => s.userId === userId && s.projectId === projectId,
    );
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

describe("SubmitProjectUseCase", () => {
  it("awards project XP on the first submission", async () => {
    const useCase = new SubmitProjectUseCase(
      new FakeProjectRepository(),
      new FakeProjectSubmissionRepository(),
      new FakeCourseRepository(),
      new FakeProgressRepository(),
      new FakeUserRepository(),
    );

    const result = await useCase.execute("user-1", "project-1", "My analysis...", null);

    expect(result.xpAwarded).toBe(200);
    expect(result.totalXp).toBe(200);
    expect(result.status).toBe("ACCEPTED");
  });

  it("does not re-award XP on a resubmission", async () => {
    const projectSubmissionRepository = new FakeProjectSubmissionRepository();
    const useCase = new SubmitProjectUseCase(
      new FakeProjectRepository(),
      projectSubmissionRepository,
      new FakeCourseRepository(),
      new FakeProgressRepository(),
      new FakeUserRepository(),
    );

    await useCase.execute("user-1", "project-1", "First attempt...", null);
    const second = await useCase.execute(
      "user-1",
      "project-1",
      "Revised attempt...",
      null,
    );

    expect(second.xpAwarded).toBe(0);
    expect(second.totalXp).toBe(200);
    expect(projectSubmissionRepository.submissions).toHaveLength(2);
  });
});
