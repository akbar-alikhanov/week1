import { MDXRemote } from "next-mdx-remote/rsc";
import Link from "next/link";
import { notFound } from "next/navigation";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { ForbiddenError, NotFoundError } from "@/shared/errors/app-error";
import { Badge } from "@/shared/ui/badge";
import { CompleteLessonButton } from "@/features/lessons/components/complete-lesson-button";
import { lessonMdxComponents } from "@/features/lessons/components/mdx-components";
import { ExerciseCard } from "@/features/exercises/components/exercise-card";
import { QuizCard } from "@/features/quizzes/components/quiz-card";
import { LockedCourseNotice } from "@/features/courses/components/locked-course-notice";

export default async function LessonPage({
  params,
}: PageProps<"/courses/[courseSlug]/[moduleSlug]/[lessonSlug]">) {
  const { courseSlug, moduleSlug, lessonSlug } = await params;
  const session = await auth();

  let lesson;
  try {
    lesson = await getContainer().getLessonUseCase.execute(
      courseSlug,
      moduleSlug,
      lessonSlug,
      session?.user?.id ?? null,
    );
  } catch (error) {
    if (error instanceof NotFoundError) {
      notFound();
    }
    if (error instanceof ForbiddenError) {
      return <LockedCourseNotice message={error.message} />;
    }
    throw error;
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Link href={`/courses/${lesson.courseSlug}`} className="hover:text-foreground">
            {lesson.courseTitle}
          </Link>
          <span>/</span>
          <span>{lesson.moduleTitle}</span>
        </div>
        <h1 className="text-2xl font-semibold tracking-tight">{lesson.title}</h1>
        <p className="text-muted-foreground">{lesson.description}</p>
        <Badge variant="secondary">+{lesson.xpReward} XP</Badge>
      </div>

      {lesson.objectives.length > 0 ? (
        <div className="rounded-lg border border-border bg-muted/40 p-4">
          <p className="mb-2 text-sm font-medium">Learning objectives</p>
          <ul className="ml-5 list-disc space-y-1 text-sm text-muted-foreground">
            {lesson.objectives.map((objective) => (
              <li key={objective}>{objective}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <article>
        <MDXRemote source={lesson.markdown} components={lessonMdxComponents} />
      </article>

      {lesson.exercises.length > 0 ? (
        <div className="space-y-4 border-t border-border pt-6">
          <h2 className="text-lg font-semibold tracking-tight">🧪 Practice</h2>
          {lesson.exercises.map((exercise, index) => (
            <ExerciseCard key={exercise.id} exercise={exercise} index={index} />
          ))}
        </div>
      ) : null}

      {lesson.quiz ? (
        <div className="space-y-4 border-t border-border pt-6">
          <h2 className="text-lg font-semibold tracking-tight">Quiz</h2>
          <QuizCard quiz={lesson.quiz} />
        </div>
      ) : null}

      <div className="border-t border-border pt-6">
        <CompleteLessonButton
          lessonId={lesson.id}
          isCompleted={lesson.isCompleted}
          nextLessonPath={lesson.nextLessonPath}
        />
      </div>
    </main>
  );
}
