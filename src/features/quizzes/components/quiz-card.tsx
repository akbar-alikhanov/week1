"use client";

import { useState, useTransition } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";

import type { QuizSummary } from "@/features/lessons/application/get-lesson.use-case";
import { submitQuizAction } from "@/features/quizzes/actions";
import type { SubmitQuizResult } from "@/features/quizzes/application/submit-quiz.use-case";
import { toastNewAchievements } from "@/features/achievements/components/toast-achievements";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { cn } from "@/shared/lib/cn";

export function QuizCard({ quiz }: { quiz: QuizSummary }) {
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [result, setResult] = useState<SubmitQuizResult | null>(null);
  const [isPending, startTransition] = useTransition();

  const allAnswered = quiz.questions.every((q) => answers[q.id] !== undefined);

  function handleSubmit() {
    startTransition(async () => {
      const response = await submitQuizAction(quiz.id, answers);
      if (!response.success) {
        toast.error(response.error);
        return;
      }
      setResult(response.data);
      if (response.data.xpAwarded > 0) {
        toast.success(`+${response.data.xpAwarded} XP — quiz passed!`);
      }
      toastNewAchievements(response.data.newAchievements);
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{quiz.title}</CardTitle>
        <p className="text-sm text-muted-foreground">
          Passing score: {quiz.passingScore}%
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {quiz.questions.map((question, qIndex) => (
          <div key={question.id} className="space-y-2">
            <p className="text-sm font-medium">
              {qIndex + 1}. {question.question}
            </p>
            <div className="space-y-1.5">
              {question.options.map((option, oIndex) => (
                <button
                  key={oIndex}
                  type="button"
                  disabled={result?.passed}
                  onClick={() =>
                    setAnswers((prev) => ({ ...prev, [question.id]: oIndex }))
                  }
                  className={cn(
                    "w-full rounded-md border px-3 py-2 text-left text-sm transition-colors disabled:cursor-not-allowed",
                    answers[question.id] === oIndex
                      ? "border-primary bg-primary/10"
                      : "border-input hover:bg-accent",
                  )}
                >
                  {option}
                </button>
              ))}
            </div>
          </div>
        ))}

        {result ? (
          <div
            className={cn(
              "flex items-start gap-2 rounded-md border p-3 text-sm",
              result.passed
                ? "border-success/30 bg-success/10"
                : "border-destructive/30 bg-destructive/10",
            )}
          >
            {result.passed ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
            ) : (
              <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
            )}
            <p>
              You scored {result.score}% ({result.correctCount}/{result.totalQuestions}{" "}
              correct)
              {result.passed
                ? " — you passed!"
                : ` — you need ${quiz.passingScore}% to pass. Try again.`}
            </p>
          </div>
        ) : null}

        {!result?.passed ? (
          <Button onClick={handleSubmit} disabled={isPending || !allAnswered}>
            {isPending ? "Submitting…" : "Submit quiz"}
          </Button>
        ) : null}
      </CardContent>
    </Card>
  );
}
