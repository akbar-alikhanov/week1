import type { Metadata, Route } from "next";
import Link from "next/link";
import { CheckCircle2, Circle } from "lucide-react";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { Badge } from "@/shared/ui/badge";
import { cn } from "@/shared/lib/cn";

export const metadata: Metadata = {
  title: "Exercises",
  robots: { index: false, follow: false },
};

export default async function ExercisesPage() {
  const session = await auth();
  const exercises = await getContainer().listExercisesUseCase.execute(session!.user!.id);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Exercises</h1>
        <p className="text-muted-foreground">
          {exercises.filter((e) => e.isCompleted).length}/{exercises.length} completed
        </p>
      </div>

      <ul className="divide-y divide-border rounded-lg border border-border">
        {exercises.map((exercise) => (
          <li key={exercise.id}>
            <Link
              href={exercise.lessonPath as Route}
              className="flex items-center gap-3 px-4 py-3 text-sm transition-colors hover:bg-accent"
            >
              {exercise.isCompleted ? (
                <CheckCircle2 className="size-4 shrink-0 text-success" />
              ) : (
                <Circle className="size-4 shrink-0 text-muted-foreground" />
              )}
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    "truncate font-medium",
                    exercise.isCompleted && "text-muted-foreground",
                  )}
                >
                  {exercise.title}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {exercise.courseTitle} · {exercise.lessonTitle}
                </p>
              </div>
              <Badge variant="outline" className="shrink-0">
                {exercise.points} pts
              </Badge>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
