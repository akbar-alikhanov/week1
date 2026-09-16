import { ExerciseEvaluationError } from "@/shared/errors/app-error";
import type { CorrectAnswer, SubmittedAnswer } from "@/entities/exercise/types";

export interface EvaluationResult {
  isCorrect: boolean;
}

/**
 * Pure, deterministic grading for every exercise type except SQL_QUERY.
 *
 * SQL_QUERY cannot be graded here: correctness depends on executing the
 * learner's query against the sandbox dataset and comparing result rows,
 * which requires a database connection. That is an infrastructure concern,
 * orchestrated by ExecuteSqlExerciseUseCase via a SqlSandboxService port -
 * see src/features/exercises/application.
 */
export function evaluateAnswer(
  correctAnswer: CorrectAnswer,
  submitted: SubmittedAnswer,
): EvaluationResult {
  if (correctAnswer.type !== submitted.type) {
    throw new ExerciseEvaluationError(
      `Answer type "${submitted.type}" does not match exercise type "${correctAnswer.type}".`,
    );
  }

  switch (correctAnswer.type) {
    case "MULTIPLE_CHOICE": {
      const submittedIndices = (
        submitted as Extract<SubmittedAnswer, { type: "MULTIPLE_CHOICE" }>
      ).selectedIndices;
      return { isCorrect: sameSet(correctAnswer.correctIndices, submittedIndices) };
    }

    case "TEXT_INPUT": {
      const value = (submitted as Extract<SubmittedAnswer, { type: "TEXT_INPUT" }>).value;
      return {
        isCorrect: correctAnswer.acceptedAnswers.some(
          (accepted) =>
            normalizeText(accepted, correctAnswer.caseSensitive) ===
            normalizeText(value, correctAnswer.caseSensitive),
        ),
      };
    }

    case "FORMULA_INPUT": {
      const formula = (submitted as Extract<SubmittedAnswer, { type: "FORMULA_INPUT" }>)
        .formula;
      return {
        isCorrect: correctAnswer.acceptedFormulas.some(
          (accepted) => normalizeFormula(accepted) === normalizeFormula(formula),
        ),
      };
    }

    case "SQL_QUERY":
      throw new ExerciseEvaluationError(
        "SQL_QUERY exercises must be graded through the SQL sandbox, not evaluateAnswer().",
      );

    case "TRUE_FALSE": {
      const value = (submitted as Extract<SubmittedAnswer, { type: "TRUE_FALSE" }>).value;
      return { isCorrect: correctAnswer.value === value };
    }

    case "MATCHING": {
      const pairs = (submitted as Extract<SubmittedAnswer, { type: "MATCHING" }>).pairs;
      return {
        isCorrect:
          pairs.length === correctAnswer.pairs.length &&
          pairs.every((value, index) => value === correctAnswer.pairs[index]),
      };
    }

    case "ORDERING": {
      const order = (submitted as Extract<SubmittedAnswer, { type: "ORDERING" }>).order;
      return {
        isCorrect:
          order.length === correctAnswer.order.length &&
          order.every((value, index) => value === correctAnswer.order[index]),
      };
    }

    case "DATA_ANALYSIS": {
      const value = (submitted as Extract<SubmittedAnswer, { type: "DATA_ANALYSIS" }>)
        .value;
      const numeric = Number(value.replace(",", "."));
      if (!Number.isNaN(numeric) && correctAnswer.tolerance !== undefined) {
        const target = correctAnswer.acceptedAnswers
          .map(Number)
          .find((accepted) => !Number.isNaN(accepted));
        if (target !== undefined) {
          return { isCorrect: Math.abs(numeric - target) <= correctAnswer.tolerance };
        }
      }
      return {
        isCorrect: correctAnswer.acceptedAnswers.some(
          (accepted) => normalizeText(accepted, false) === normalizeText(value, false),
        ),
      };
    }
  }
}

function sameSet(a: number[], b: number[]): boolean {
  if (a.length !== b.length) return false;
  const sortedA = [...a].sort();
  const sortedB = [...b].sort();
  return sortedA.every((value, index) => value === sortedB[index]);
}

function normalizeText(value: string, caseSensitive?: boolean): string {
  const trimmed = value.trim().replace(/\s+/g, " ");
  return caseSensitive ? trimmed : trimmed.toLowerCase();
}

/** Normalizes Excel formula syntax differences (spacing, `,` vs `;`, case) before comparison. */
function normalizeFormula(formula: string): string {
  return formula.trim().toUpperCase().replace(/\s+/g, "").replace(/,/g, ";");
}
