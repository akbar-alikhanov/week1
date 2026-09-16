import type { CourseModule } from "@/entities/module/model";

export interface ModuleRepository {
  findById(id: string): Promise<CourseModule | null>;
  findByCourseId(courseId: string): Promise<CourseModule[]>;
}
