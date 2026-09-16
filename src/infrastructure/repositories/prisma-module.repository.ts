import type { PrismaClient } from "@/generated/prisma/client";
import type { ModuleModel } from "@/generated/prisma/models/Module";
import { CourseModule } from "@/entities/module/model";
import type { ModuleRepository } from "@/entities/module/repository";

export class PrismaModuleRepository implements ModuleRepository {
  constructor(private readonly db: PrismaClient) {}

  async findById(id: string): Promise<CourseModule | null> {
    const record = await this.db.module.findUnique({ where: { id } });
    return record ? toDomain(record) : null;
  }

  async findByCourseId(courseId: string): Promise<CourseModule[]> {
    const records = await this.db.module.findMany({
      where: { courseId },
      orderBy: { order: "asc" },
    });
    return records.map(toDomain);
  }
}

function toDomain(record: ModuleModel): CourseModule {
  return CourseModule.create({
    id: record.id,
    courseId: record.courseId,
    slug: record.slug,
    title: record.title,
    description: record.description,
    order: record.order,
  });
}
