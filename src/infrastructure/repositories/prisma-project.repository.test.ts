import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { prisma } from "@/infrastructure/database/prisma-client";
import { PrismaProjectRepository } from "@/infrastructure/repositories/prisma-project.repository";

/**
 * Infrastructure-layer test: exercises PrismaProjectRepository against a
 * real (local) Postgres database, in particular the Json-column round-trip
 * for deliverables/evaluationCriteria/hints (string[] <-> Json) - see
 * ARCHITECTURE.md's testing strategy.
 */
describe("PrismaProjectRepository", () => {
  const repository = new PrismaProjectRepository(prisma);
  const slug = `infra-test-project-${Date.now()}`;
  let courseId: string;
  let projectId: string;

  beforeAll(async () => {
    const excelCourse = await prisma.course.findUniqueOrThrow({
      where: { slug: "excel" },
    });
    courseId = excelCourse.id;

    const project = await prisma.project.create({
      data: {
        courseId,
        slug,
        title: "Infra Test Project",
        businessContext: "context",
        datasetDescription: "dataset",
        goal: "goal",
        deliverables: ["Deliverable A", "Deliverable B"],
        evaluationCriteria: ["Criterion A"],
        hints: ["Hint A", "Hint B", "Hint C"],
        order: 999,
        xpReward: 200,
        tasks: {
          create: [
            { title: "Task 1", description: "Do the first thing", order: 0 },
            { title: "Task 2", description: "Do the second thing", order: 1 },
          ],
        },
      },
    });
    projectId = project.id;
  });

  afterAll(async () => {
    await prisma.project.delete({ where: { id: projectId } });
  });

  it("round-trips Json string-array columns and ordered tasks", async () => {
    const found = await repository.findBySlug(slug);

    expect(found).not.toBeNull();
    expect(found?.deliverables).toEqual(["Deliverable A", "Deliverable B"]);
    expect(found?.evaluationCriteria).toEqual(["Criterion A"]);
    expect(found?.hints).toEqual(["Hint A", "Hint B", "Hint C"]);
    expect(found?.tasks.map((t) => t.title)).toEqual(["Task 1", "Task 2"]);
  });

  it("finds the same project by id and lists it under its course", async () => {
    const byId = await repository.findById(projectId);
    expect(byId?.slug).toBe(slug);

    const byCourse = await repository.findByCourseId(courseId);
    expect(byCourse.some((p) => p.id === projectId)).toBe(true);
  });
});
