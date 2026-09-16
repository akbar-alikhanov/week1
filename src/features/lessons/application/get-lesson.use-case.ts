import type { LessonRepository } from "@/entities/lesson/repository";
import type { ModuleRepository } from "@/entities/module/repository";
import type { CourseRepository } from "@/entities/course/repository";
import type { ProgressRepository } from "@/entities/progress/repository";
import { NotFoundError } from "@/shared/errors/app-error";
import type { LessonContentReader } from "@/features/lessons/application/ports";

export interface LessonDetail {
  id: string;
  slug: string;
  title: string;
  description: string;
  xpReward: number;
  objectives: string[];
  markdown: string;
  isCompleted: boolean;
  courseSlug: string;
  courseTitle: string;
  moduleSlug: string;
  moduleTitle: string;
  moduleIndex: number;
  lessonIndex: number;
  nextLessonPath: string | null;
}

export class GetLessonUseCase {
  constructor(
    private readonly lessonRepository: LessonRepository,
    private readonly moduleRepository: ModuleRepository,
    private readonly courseRepository: CourseRepository,
    private readonly progressRepository: ProgressRepository,
    private readonly contentReader: LessonContentReader,
  ) {}

  async execute(
    courseSlug: string,
    moduleSlug: string,
    lessonSlug: string,
    userId: string | null,
  ): Promise<LessonDetail> {
    const lesson = await this.lessonRepository.findBySlug(
      courseSlug,
      moduleSlug,
      lessonSlug,
    );
    if (!lesson) {
      throw new NotFoundError("Lesson", lessonSlug);
    }

    const courseModule = await this.moduleRepository.findById(lesson.moduleId);
    if (!courseModule) {
      throw new NotFoundError("Module", moduleSlug);
    }

    const course = await this.courseRepository.findById(courseModule.courseId);
    if (!course) {
      throw new NotFoundError("Course", courseSlug);
    }

    const [content, isCompleted, next] = await Promise.all([
      this.contentReader.read(lesson.contentPath),
      userId
        ? this.progressRepository.isLessonCompleted(userId, lesson.id)
        : Promise.resolve(false),
      this.lessonRepository.findNext(lesson.id),
    ]);

    let nextLessonPath: string | null = null;
    if (next) {
      const nextModule = await this.moduleRepository.findById(next.moduleId);
      if (nextModule) {
        nextLessonPath = `/courses/${course.slug}/${nextModule.slug}/${next.slug}`;
      }
    }

    return {
      id: lesson.id,
      slug: lesson.slug,
      title: lesson.title,
      description: lesson.description,
      xpReward: lesson.xpReward,
      objectives: content.objectives,
      markdown: content.markdown,
      isCompleted,
      courseSlug: course.slug,
      courseTitle: course.title,
      moduleSlug: courseModule.slug,
      moduleTitle: courseModule.title,
      moduleIndex: courseModule.order,
      lessonIndex: lesson.order,
      nextLessonPath,
    };
  }
}
