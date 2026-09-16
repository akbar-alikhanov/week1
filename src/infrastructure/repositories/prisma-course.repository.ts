import type { PrismaClient } from "@/generated/prisma/client";
import type { CourseModel } from "@/generated/prisma/models/Course";
import { Course, type CourseTrack } from "@/entities/course/model";
import type { CourseRepository } from "@/entities/course/repository";

export class PrismaCourseRepository implements CourseRepository {
  constructor(private readonly db: PrismaClient) {}

  async findAll(): Promise<Course[]> {
    const records = await this.db.course.findMany({ orderBy: { order: "asc" } });
    return records.map(toDomain);
  }

  async findById(id: string): Promise<Course | null> {
    const record = await this.db.course.findUnique({ where: { id } });
    return record ? toDomain(record) : null;
  }

  async findBySlug(slug: string): Promise<Course | null> {
    const record = await this.db.course.findUnique({ where: { slug } });
    return record ? toDomain(record) : null;
  }

  async findByTrack(track: CourseTrack): Promise<Course | null> {
    const record = await this.db.course.findUnique({ where: { track } });
    return record ? toDomain(record) : null;
  }
}

function toDomain(record: CourseModel): Course {
  return Course.create({
    id: record.id,
    slug: record.slug,
    track: record.track as CourseTrack,
    title: record.title,
    description: record.description,
    order: record.order,
  });
}
