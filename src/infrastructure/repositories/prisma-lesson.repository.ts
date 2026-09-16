import type { PrismaClient } from "@/generated/prisma/client";
import type { LessonModel } from "@/generated/prisma/models/Lesson";
import { Lesson } from "@/entities/lesson/model";
import type { LessonRepository } from "@/entities/lesson/repository";

export class PrismaLessonRepository implements LessonRepository {
  constructor(private readonly db: PrismaClient) {}

  async findById(id: string): Promise<Lesson | null> {
    const record = await this.db.lesson.findUnique({ where: { id } });
    return record ? toDomain(record) : null;
  }

  async findByModuleId(moduleId: string): Promise<Lesson[]> {
    const records = await this.db.lesson.findMany({
      where: { moduleId },
      orderBy: { order: "asc" },
    });
    return records.map(toDomain);
  }

  async findBySlug(
    courseSlug: string,
    moduleSlug: string,
    lessonSlug: string,
  ): Promise<Lesson | null> {
    const record = await this.db.lesson.findFirst({
      where: {
        slug: lessonSlug,
        module: { slug: moduleSlug, course: { slug: courseSlug } },
      },
    });
    return record ? toDomain(record) : null;
  }

  async findNext(lessonId: string): Promise<Lesson | null> {
    const current = await this.db.lesson.findUnique({
      where: { id: lessonId },
      select: {
        order: true,
        moduleId: true,
        module: { select: { order: true, courseId: true } },
      },
    });
    if (!current) return null;

    const nextInModule = await this.db.lesson.findFirst({
      where: { moduleId: current.moduleId, order: { gt: current.order } },
      orderBy: { order: "asc" },
    });
    if (nextInModule) return toDomain(nextInModule);

    const nextModule = await this.db.module.findFirst({
      where: { courseId: current.module.courseId, order: { gt: current.module.order } },
      orderBy: { order: "asc" },
      include: { lessons: { orderBy: { order: "asc" }, take: 1 } },
    });
    const firstLessonOfNextModule = nextModule?.lessons[0];
    return firstLessonOfNextModule ? toDomain(firstLessonOfNextModule) : null;
  }
}

function toDomain(record: LessonModel): Lesson {
  return Lesson.create({
    id: record.id,
    moduleId: record.moduleId,
    slug: record.slug,
    title: record.title,
    description: record.description,
    order: record.order,
    contentPath: record.contentPath,
    xpReward: record.xpReward,
  });
}
