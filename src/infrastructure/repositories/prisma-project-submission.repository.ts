import type { PrismaClient } from "@/generated/prisma/client";
import type { ProjectSubmissionModel } from "@/generated/prisma/models/ProjectSubmission";
import { ProjectSubmission, type SubmissionStatus } from "@/entities/project/submission";
import type {
  CreateProjectSubmissionInput,
  ProjectSubmissionRepository,
} from "@/entities/project/repository";

export class PrismaProjectSubmissionRepository implements ProjectSubmissionRepository {
  constructor(private readonly db: PrismaClient) {}

  async create(input: CreateProjectSubmissionInput): Promise<ProjectSubmission> {
    const record = await this.db.projectSubmission.create({
      data: {
        userId: input.userId,
        projectId: input.projectId,
        summary: input.summary,
        deliverableUrl: input.deliverableUrl,
        status: "ACCEPTED",
      },
    });
    return toDomain(record);
  }

  async findByUserAndProject(
    userId: string,
    projectId: string,
  ): Promise<ProjectSubmission[]> {
    const records = await this.db.projectSubmission.findMany({
      where: { userId, projectId },
      orderBy: { createdAt: "desc" },
    });
    return records.map(toDomain);
  }
}

function toDomain(record: ProjectSubmissionModel): ProjectSubmission {
  return ProjectSubmission.create({
    id: record.id,
    userId: record.userId,
    projectId: record.projectId,
    summary: record.summary,
    deliverableUrl: record.deliverableUrl,
    status: record.status as SubmissionStatus,
    feedback: record.feedback,
    createdAt: record.createdAt,
  });
}
