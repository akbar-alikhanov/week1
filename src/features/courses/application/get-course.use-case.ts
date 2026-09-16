import type { CourseRepository } from "@/entities/course/repository";
import type { ModuleRepository } from "@/entities/module/repository";
import type { LessonRepository } from "@/entities/lesson/repository";
import type { ProgressRepository } from "@/entities/progress/repository";
import { NotFoundError } from "@/shared/errors/app-error";

export interface CourseDetailLesson {
  id: string;
  slug: string;
  title: string;
  isCompleted: boolean;
}

export interface CourseDetailModule {
  id: string;
  slug: string;
  title: string;
  description: string;
  lessons: CourseDetailLesson[];
}

export interface CourseDetail {
  id: string;
  slug: string;
  title: string;
  description: string;
  percentComplete: number;
  modules: CourseDetailModule[];
}

export class GetCourseUseCase {
  constructor(
    private readonly courseRepository: CourseRepository,
    private readonly moduleRepository: ModuleRepository,
    private readonly lessonRepository: LessonRepository,
    private readonly progressRepository: ProgressRepository,
  ) {}

  async execute(courseSlug: string, userId: string | null): Promise<CourseDetail> {
    const course = await this.courseRepository.findBySlug(courseSlug);
    if (!course) {
      throw new NotFoundError("Course", courseSlug);
    }

    const modules = await this.moduleRepository.findByCourseId(course.id);
    const modulesWithLessons = await Promise.all(
      modules.map(async (courseModule) => {
        const lessons = await this.lessonRepository.findByModuleId(courseModule.id);
        const lessonsWithProgress = await Promise.all(
          lessons.map(async (lesson) => ({
            id: lesson.id,
            slug: lesson.slug,
            title: lesson.title,
            isCompleted: userId
              ? await this.progressRepository.isLessonCompleted(userId, lesson.id)
              : false,
          })),
        );
        return {
          id: courseModule.id,
          slug: courseModule.slug,
          title: courseModule.title,
          description: courseModule.description,
          lessons: lessonsWithProgress,
        };
      }),
    );

    const progress = userId
      ? await this.progressRepository.getCourseProgress(userId, course.id)
      : null;

    return {
      id: course.id,
      slug: course.slug,
      title: course.title,
      description: course.description,
      percentComplete: progress?.percentComplete ?? 0,
      modules: modulesWithLessons,
    };
  }
}
