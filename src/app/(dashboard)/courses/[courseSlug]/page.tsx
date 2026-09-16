import Link from "next/link";
import { CheckCircle2, Circle } from "lucide-react";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { ForbiddenError } from "@/shared/errors/app-error";
import { Badge } from "@/shared/ui/badge";
import { Progress } from "@/shared/ui/progress";
import { Separator } from "@/shared/ui/separator";
import { cn } from "@/shared/lib/cn";
import { LockedCourseNotice } from "@/features/courses/components/locked-course-notice";

export default async function CourseDetailPage({
  params,
}: PageProps<"/courses/[courseSlug]">) {
  const { courseSlug } = await params;
  const session = await auth();

  let course;
  try {
    course = await getContainer().getCourseUseCase.execute(
      courseSlug,
      session?.user?.id ?? null,
    );
  } catch (error) {
    if (error instanceof ForbiddenError) {
      return <LockedCourseNotice message={error.message} />;
    }
    throw error;
  }

  return (
    <main className="flex flex-1 flex-col gap-6 p-6">
      <div className="space-y-2">
        <h1 className="text-2xl font-semibold tracking-tight">{course.title}</h1>
        <p className="text-muted-foreground">{course.description}</p>
        <div className="max-w-sm space-y-1">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Course progress</span>
            <span>{course.percentComplete}%</span>
          </div>
          <Progress value={course.percentComplete} />
        </div>
      </div>

      <div className="flex flex-col gap-6">
        {course.modules.map((courseModule, moduleIndex) => (
          <div key={courseModule.id} className="space-y-3">
            <div className="flex items-center gap-2">
              <Badge variant="secondary">Module {moduleIndex + 1}</Badge>
              <h2 className="text-lg font-semibold">{courseModule.title}</h2>
            </div>
            {courseModule.lessons.length === 0 ? (
              <p className="text-sm text-muted-foreground">Content coming soon.</p>
            ) : (
              <ul className="divide-y divide-border rounded-lg border border-border">
                {courseModule.lessons.map((lesson) => (
                  <li key={lesson.id}>
                    <Link
                      href={`/courses/${course.slug}/${courseModule.slug}/${lesson.slug}`}
                      className={cn(
                        "flex items-center gap-3 px-4 py-3 text-sm transition-colors hover:bg-accent",
                      )}
                    >
                      {lesson.isCompleted ? (
                        <CheckCircle2 className="size-4 shrink-0 text-success" />
                      ) : (
                        <Circle className="size-4 shrink-0 text-muted-foreground" />
                      )}
                      <span className={cn(lesson.isCompleted && "text-muted-foreground")}>
                        {lesson.title}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
            {moduleIndex < course.modules.length - 1 ? (
              <Separator className="mt-6" />
            ) : null}
          </div>
        ))}
      </div>
    </main>
  );
}
