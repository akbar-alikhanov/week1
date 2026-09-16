"use client";

import { useTransition } from "react";
import type { Route } from "next";
import { useRouter } from "next/navigation";
import { CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

import { completeLessonAction } from "@/features/lessons/actions";
import { Button } from "@/shared/ui/button";

export function CompleteLessonButton({
  lessonId,
  isCompleted,
  nextLessonPath,
}: {
  lessonId: string;
  isCompleted: boolean;
  nextLessonPath: string | null;
}) {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();

  function handleComplete() {
    startTransition(async () => {
      const result = await completeLessonAction(lessonId);
      if (!result.success) {
        toast.error(result.error);
        return;
      }

      if (!result.data.alreadyCompleted) {
        toast.success(
          result.data.leveledUp
            ? `+${result.data.xpAwarded} XP — level up! You're now level ${result.data.level}.`
            : `+${result.data.xpAwarded} XP`,
        );
      }

      router.refresh();
      if (nextLessonPath) {
        router.push(nextLessonPath as Route);
      }
    });
  }

  if (isCompleted) {
    return (
      <div className="flex items-center gap-3">
        <span className="inline-flex items-center gap-1.5 text-sm font-medium text-success">
          <CheckCircle2 className="size-4" />
          Completed
        </span>
        {nextLessonPath ? (
          <Button onClick={() => router.push(nextLessonPath as Route)}>
            Next lesson
          </Button>
        ) : null}
      </div>
    );
  }

  return (
    <Button onClick={handleComplete} disabled={isPending}>
      {isPending ? "Completing…" : "Mark lesson as complete"}
    </Button>
  );
}
