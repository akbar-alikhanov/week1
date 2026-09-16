import type { Course, CourseTrack } from "@/entities/course/model";

export interface CourseRepository {
  findAll(): Promise<Course[]>;
  findById(id: string): Promise<Course | null>;
  findBySlug(slug: string): Promise<Course | null>;
  findByTrack(track: CourseTrack): Promise<Course | null>;
}
