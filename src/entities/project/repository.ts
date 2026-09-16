import type { Project } from "@/entities/project/model";
import type { ProjectSubmission } from "@/entities/project/submission";

export interface CreateProjectSubmissionInput {
  userId: string;
  projectId: string;
  summary: string;
  deliverableUrl: string | null;
}

export interface ProjectRepository {
  findAll(): Promise<Project[]>;
  findById(id: string): Promise<Project | null>;
  findBySlug(slug: string): Promise<Project | null>;
  findByCourseId(courseId: string): Promise<Project[]>;
}

export interface ProjectSubmissionRepository {
  create(input: CreateProjectSubmissionInput): Promise<ProjectSubmission>;
  findByUserAndProject(userId: string, projectId: string): Promise<ProjectSubmission[]>;
}
