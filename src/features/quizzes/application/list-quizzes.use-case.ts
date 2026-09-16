import type { CourseRepository } from "@/entities/course/repository";
import type { ModuleRepository } from "@/entities/module/repository";
import type { LessonRepository } from "@/entities/lesson/repository";
import type { QuizRepository } from "@/entities/quiz/repository";

export interface QuizListItem {
  id: string;
  title: string;
  questionCount: number;
  passingScore: number;
  hasPassed: boolean;
  courseTitle: string;
  lessonTitle: string;
  lessonPath: string;
}

/** Same catalog-walk tradeoff as ListExercisesUseCase - see its comment. */
export class ListQuizzesUseCase {
  constructor(
    private readonly courseRepository: CourseRepository,
    private readonly moduleRepository: ModuleRepository,
    private readonly lessonRepository: LessonRepository,
    private readonly quizRepository: QuizRepository,
  ) {}

  async execute(userId: string): Promise<QuizListItem[]> {
    const items: QuizListItem[] = [];
    const courses = await this.courseRepository.findAll();

    for (const course of courses) {
      const modules = await this.moduleRepository.findByCourseId(course.id);
      for (const courseModule of modules) {
        const lessons = await this.lessonRepository.findByModuleId(courseModule.id);
        for (const lesson of lessons) {
          const quiz = await this.quizRepository.findByLessonId(lesson.id);
          if (!quiz) continue;

          const hasPassed = await this.quizRepository.hasPassed(userId, quiz.id);
          items.push({
            id: quiz.id,
            title: quiz.title,
            questionCount: quiz.questions.length,
            passingScore: quiz.passingScore,
            hasPassed,
            courseTitle: course.title,
            lessonTitle: lesson.title,
            lessonPath: `/courses/${course.slug}/${courseModule.slug}/${lesson.slug}`,
          });
        }
      }
    }

    return items;
  }
}
