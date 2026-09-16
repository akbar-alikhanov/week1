import type { Metadata, Route } from "next";
import Link from "next/link";
import { CheckCircle2, Circle } from "lucide-react";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { cn } from "@/shared/lib/cn";

export const metadata: Metadata = {
  title: "Quizzes",
  robots: { index: false, follow: false },
};

export default async function QuizzesPage() {
  const session = await auth();
  const quizzes = await getContainer().listQuizzesUseCase.execute(session!.user!.id);

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Quizzes</h1>
        <p className="text-muted-foreground">
          {quizzes.filter((q) => q.hasPassed).length}/{quizzes.length} passed
        </p>
      </div>

      <ul className="divide-y divide-border rounded-lg border border-border">
        {quizzes.map((quiz) => (
          <li key={quiz.id}>
            <Link
              href={quiz.lessonPath as Route}
              className="flex items-center gap-3 px-4 py-3 text-sm transition-colors hover:bg-accent"
            >
              {quiz.hasPassed ? (
                <CheckCircle2 className="size-4 shrink-0 text-success" />
              ) : (
                <Circle className="size-4 shrink-0 text-muted-foreground" />
              )}
              <div className="min-w-0 flex-1">
                <p
                  className={cn(
                    "truncate font-medium",
                    quiz.hasPassed && "text-muted-foreground",
                  )}
                >
                  {quiz.title}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {quiz.courseTitle} · {quiz.lessonTitle}
                </p>
              </div>
              <span className="shrink-0 text-xs text-muted-foreground">
                {quiz.questionCount} questions
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
