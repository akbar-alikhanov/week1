"use client";

import { useMemo, useState, useTransition } from "react";
import dynamic from "next/dynamic";
import { ArrowDown, ArrowUp, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";

import type { ExerciseProps } from "@/entities/exercise/model";
import type { SubmittedAnswer } from "@/entities/exercise/types";
import { submitExerciseAction } from "@/features/exercises/actions";
import type { SubmitExerciseResult } from "@/features/exercises/application/submit-exercise.use-case";
import { toastNewAchievements } from "@/features/achievements/components/toast-achievements";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Input } from "@/shared/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import { cn } from "@/shared/lib/cn";
import { SpreadsheetTablePreview } from "@/features/exercises/components/spreadsheet-table";

const SqlEditor = dynamic(
  () => import("@/features/exercises/components/sql-editor").then((mod) => mod.SqlEditor),
  {
    ssr: false,
    loading: () => <div className="h-40 animate-pulse rounded-md bg-muted" />,
  },
);

function initialAnswer(exercise: ExerciseProps): SubmittedAnswer {
  switch (exercise.data.type) {
    case "MULTIPLE_CHOICE":
      return { type: "MULTIPLE_CHOICE", selectedIndices: [] };
    case "TEXT_INPUT":
      return { type: "TEXT_INPUT", value: "" };
    case "FORMULA_INPUT":
      return { type: "FORMULA_INPUT", formula: "" };
    case "SQL_QUERY":
      return { type: "SQL_QUERY", query: "" };
    case "TRUE_FALSE":
      return { type: "TRUE_FALSE", value: true };
    case "MATCHING":
      return { type: "MATCHING", pairs: exercise.data.left.map(() => -1) };
    case "ORDERING":
      return { type: "ORDERING", order: exercise.data.items.map((_, i) => i) };
    case "DATA_ANALYSIS":
      return { type: "DATA_ANALYSIS", value: "" };
  }
}

export function ExerciseCard({
  exercise,
  index,
}: {
  exercise: ExerciseProps;
  index: number;
}) {
  const [answer, setAnswer] = useState<SubmittedAnswer>(() => initialAnswer(exercise));
  const [result, setResult] = useState<SubmitExerciseResult | null>(null);
  const [isPending, startTransition] = useTransition();

  const isAnswerReady = useMemo(() => isComplete(answer), [answer]);

  function handleSubmit() {
    startTransition(async () => {
      const response = await submitExerciseAction(exercise.id, answer);
      if (!response.success) {
        toast.error(response.error);
        return;
      }
      setResult(response.data);
      if (response.data.isCorrect && response.data.xpAwarded > 0) {
        toast.success(
          response.data.leveledUp
            ? `+${response.data.xpAwarded} XP — level up! You're now level ${response.data.level}.`
            : `+${response.data.xpAwarded} XP`,
        );
      }
      toastNewAchievements(response.data.newAchievements);
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-base">
            Exercise {index + 1}: {exercise.title}
          </CardTitle>
          <Badge variant="outline">{exercise.points} pts</Badge>
        </div>
        <p className="text-sm text-muted-foreground">{exercise.description}</p>
      </CardHeader>
      <CardContent className="space-y-4">
        <ExerciseInput exercise={exercise} answer={answer} onChange={setAnswer} />

        {result ? (
          <div
            className={cn(
              "flex items-start gap-2 rounded-md border p-3 text-sm",
              result.isCorrect
                ? "border-success/30 bg-success/10 text-success-foreground"
                : "border-destructive/30 bg-destructive/10",
            )}
          >
            {result.isCorrect ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
            ) : (
              <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
            )}
            <div>
              <p
                className={cn(
                  "font-medium",
                  result.isCorrect ? "text-success" : "text-destructive",
                )}
              >
                {result.isCorrect ? "Correct!" : "Not quite."}
              </p>
              <p className="mt-1 text-muted-foreground">{result.explanation}</p>
            </div>
          </div>
        ) : null}

        {result?.queryResult ? <QueryResultTable result={result.queryResult} /> : null}

        <Button onClick={handleSubmit} disabled={isPending || !isAnswerReady}>
          {isPending ? "Checking…" : result?.isCorrect ? "Check again" : "Check answer"}
        </Button>
      </CardContent>
    </Card>
  );
}

function ExerciseInput({
  exercise,
  answer,
  onChange,
}: {
  exercise: ExerciseProps;
  answer: SubmittedAnswer;
  onChange: (answer: SubmittedAnswer) => void;
}) {
  const data = exercise.data;

  if (data.type === "MULTIPLE_CHOICE" && answer.type === "MULTIPLE_CHOICE") {
    return (
      <div className="space-y-2">
        {data.options.map((option, i) => (
          <button
            key={i}
            type="button"
            onClick={() => onChange({ type: "MULTIPLE_CHOICE", selectedIndices: [i] })}
            className={cn(
              "w-full rounded-md border px-3 py-2 text-left text-sm transition-colors",
              answer.selectedIndices.includes(i)
                ? "border-primary bg-primary/10"
                : "border-input hover:bg-accent",
            )}
          >
            {option}
          </button>
        ))}
      </div>
    );
  }

  if (data.type === "TRUE_FALSE" && answer.type === "TRUE_FALSE") {
    return (
      <div className="flex gap-2">
        {[true, false].map((value) => (
          <button
            key={String(value)}
            type="button"
            onClick={() => onChange({ type: "TRUE_FALSE", value })}
            className={cn(
              "flex-1 rounded-md border px-3 py-2 text-sm font-medium transition-colors",
              answer.value === value
                ? "border-primary bg-primary/10"
                : "border-input hover:bg-accent",
            )}
          >
            {value ? "True" : "False"}
          </button>
        ))}
      </div>
    );
  }

  if (data.type === "TEXT_INPUT" && answer.type === "TEXT_INPUT") {
    return (
      <Input
        value={answer.value}
        placeholder={data.placeholder}
        onChange={(e) => onChange({ type: "TEXT_INPUT", value: e.target.value })}
      />
    );
  }

  if (data.type === "DATA_ANALYSIS" && answer.type === "DATA_ANALYSIS") {
    return (
      <div className="space-y-3">
        <SpreadsheetTablePreview table={data.table} />
        <p className="text-sm font-medium">{data.question}</p>
        <Input
          value={answer.value}
          onChange={(e) => onChange({ type: "DATA_ANALYSIS", value: e.target.value })}
          placeholder="Your answer"
        />
      </div>
    );
  }

  if (data.type === "FORMULA_INPUT" && answer.type === "FORMULA_INPUT") {
    return (
      <div className="space-y-3">
        <SpreadsheetTablePreview table={data.table} targetCell={data.targetCell} />
        <Input
          value={answer.formula}
          onChange={(e) => onChange({ type: "FORMULA_INPUT", formula: e.target.value })}
          placeholder={`Formula for ${data.targetCell}, e.g. =СУММ(A1:A3)`}
          className="font-mono"
        />
      </div>
    );
  }

  if (data.type === "SQL_QUERY" && answer.type === "SQL_QUERY") {
    return (
      <div className="space-y-2">
        {data.schemaHint ? (
          <pre className="overflow-x-auto rounded-md bg-muted/60 p-3 text-xs text-muted-foreground">
            {data.schemaHint}
          </pre>
        ) : null}
        <SqlEditor
          value={answer.query}
          onChange={(query) => onChange({ type: "SQL_QUERY", query })}
        />
      </div>
    );
  }

  if (data.type === "MATCHING" && answer.type === "MATCHING") {
    return (
      <div className="space-y-2">
        {data.left.map((leftItem, i) => (
          <div key={i} className="flex items-center gap-3">
            <span className="w-1/2 text-sm">{leftItem}</span>
            <Select
              value={answer.pairs[i] >= 0 ? String(answer.pairs[i]) : undefined}
              onValueChange={(value) => {
                const pairs = [...answer.pairs];
                pairs[i] = Number(value);
                onChange({ type: "MATCHING", pairs });
              }}
            >
              <SelectTrigger className="w-1/2">
                <SelectValue placeholder="Select a match" />
              </SelectTrigger>
              <SelectContent>
                {data.right.map((rightItem, j) => (
                  <SelectItem key={j} value={String(j)}>
                    {rightItem}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ))}
      </div>
    );
  }

  if (data.type === "ORDERING" && answer.type === "ORDERING") {
    const orderedItems = answer.order.map((originalIndex) => data.items[originalIndex]);

    function move(position: number, direction: -1 | 1) {
      if (answer.type !== "ORDERING") return;
      const target = position + direction;
      if (target < 0 || target >= answer.order.length) return;
      const nextOrder = [...answer.order];
      [nextOrder[position], nextOrder[target]] = [nextOrder[target], nextOrder[position]];
      onChange({ type: "ORDERING", order: nextOrder });
    }

    return (
      <ol className="space-y-2">
        {orderedItems.map((item, position) => (
          <li
            key={position}
            className="flex items-center justify-between gap-3 rounded-md border border-input px-3 py-2 text-sm"
          >
            <span>
              {position + 1}. {item}
            </span>
            <span className="flex gap-1">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-7"
                disabled={position === 0}
                onClick={() => move(position, -1)}
              >
                <ArrowUp className="size-3.5" />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="size-7"
                disabled={position === orderedItems.length - 1}
                onClick={() => move(position, 1)}
              >
                <ArrowDown className="size-3.5" />
              </Button>
            </span>
          </li>
        ))}
      </ol>
    );
  }

  return null;
}

function QueryResultTable({
  result,
}: {
  result: { columns: string[]; rows: Record<string, unknown>[] };
}) {
  if (result.rows.length === 0) {
    return <p className="text-sm text-muted-foreground">Query returned no rows.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-muted/60">
            {result.columns.map((col) => (
              <th
                key={col}
                className="border-b border-border p-1.5 text-left font-medium"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.slice(0, 20).map((row, i) => (
            <tr key={i}>
              {result.columns.map((col) => (
                <td key={col} className="border-b border-border p-1.5">
                  {String(row[col] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function isComplete(answer: SubmittedAnswer): boolean {
  switch (answer.type) {
    case "MULTIPLE_CHOICE":
      return answer.selectedIndices.length > 0;
    case "TEXT_INPUT":
      return answer.value.trim().length > 0;
    case "FORMULA_INPUT":
      return answer.formula.trim().length > 0;
    case "SQL_QUERY":
      return answer.query.trim().length > 0;
    case "TRUE_FALSE":
      return true;
    case "MATCHING":
      return answer.pairs.every((value) => value >= 0);
    case "ORDERING":
      return true;
    case "DATA_ANALYSIS":
      return answer.value.trim().length > 0;
  }
}
