import type { PrismaClient, Prisma } from "@/generated/prisma/client";
import { Project, ProjectTask } from "@/entities/project/model";
import type { ProjectRepository } from "@/entities/project/repository";

const withTasks = { tasks: { orderBy: { order: "asc" as const } } };
type ProjectWithTasks = Prisma.ProjectGetPayload<{ include: typeof withTasks }>;

export class PrismaProjectRepository implements ProjectRepository {
  constructor(private readonly db: PrismaClient) {}

  async findAll(): Promise<Project[]> {
    const records = await this.db.project.findMany({
      include: withTasks,
      orderBy: { order: "asc" },
    });
    return records.map(toDomain);
  }

  async findById(id: string): Promise<Project | null> {
    const record = await this.db.project.findUnique({
      where: { id },
      include: withTasks,
    });
    return record ? toDomain(record) : null;
  }

  async findBySlug(slug: string): Promise<Project | null> {
    const record = await this.db.project.findUnique({
      where: { slug },
      include: withTasks,
    });
    return record ? toDomain(record) : null;
  }

  async findByCourseId(courseId: string): Promise<Project[]> {
    const records = await this.db.project.findMany({
      where: { courseId },
      include: withTasks,
      orderBy: { order: "asc" },
    });
    return records.map(toDomain);
  }
}

function toDomain(record: ProjectWithTasks): Project {
  return Project.create({
    id: record.id,
    courseId: record.courseId,
    slug: record.slug,
    title: record.title,
    businessContext: record.businessContext,
    datasetDescription: record.datasetDescription,
    goal: record.goal,
    deliverables: record.deliverables as unknown as string[],
    evaluationCriteria: record.evaluationCriteria as unknown as string[],
    hints: record.hints as unknown as string[],
    order: record.order,
    xpReward: record.xpReward,
    tasks: record.tasks.map((task) =>
      ProjectTask.create({
        id: task.id,
        title: task.title,
        description: task.description,
        order: task.order,
      }),
    ),
  });
}
