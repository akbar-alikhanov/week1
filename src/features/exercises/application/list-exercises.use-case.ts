import type { CourseRepository } from "@/entities/course/repository";
import type { ModuleRepository } from "@/entities/module/repository";
import type { LessonRepository } from "@/entities/lesson/repository";
import type { ExerciseRepository } from "@/entities/exercise/repository";
import type { ProgressRepository } from "@/entities/progress/repository";

export interface ExerciseListItem {
  id: string;
  title: string;
  type: string;
  difficulty: string;
  points: number;
  isCompleted: boolean;
  courseTitle: string;
  lessonTitle: string;
  lessonPath: string;
}

/**
 * Walks the full course catalog to build a flat practice list. Fine at
 * today's content volume (~90 lessons, one exercise-set each); would need
 * a dedicated denormalized read model if the catalog grows much larger.
 */
export class ListExercisesUseCase {
  constructor(
    private readonly courseRepository: CourseRepository,
    private readonly moduleRepository: ModuleRepository,
    private readonly lessonRepository: LessonRepository,
    private readonly exerciseRepository: ExerciseRepository,
    private readonly progressRepository: ProgressRepository,
  ) {}

  async execute(userId: string): Promise<ExerciseListItem[]> {
    const items: ExerciseListItem[] = [];
    const courses = await this.courseRepository.findAll();

    for (const course of courses) {
      const modules = await this.moduleRepository.findByCourseId(course.id);
      for (const courseModule of modules) {
        const lessons = await this.lessonRepository.findByModuleId(courseModule.id);
        for (const lesson of lessons) {
          const exercises = await this.exerciseRepository.findByLessonId(lesson.id);
          for (const exercise of exercises) {
            const isCompleted = await this.progressRepository.isExerciseCompleted(
              userId,
              exercise.id,
            );
            items.push({
              id: exercise.id,
              title: exercise.title,
              type: exercise.type,
              difficulty: exercise.difficulty,
              points: exercise.points,
              isCompleted,
              courseTitle: course.title,
              lessonTitle: lesson.title,
              lessonPath: `/courses/${course.slug}/${courseModule.slug}/${lesson.slug}`,
            });
          }
        }
      }
    }

    return items;
  }
}
