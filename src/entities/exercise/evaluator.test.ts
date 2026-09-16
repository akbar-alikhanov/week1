import { describe, expect, it } from "vitest";

import { evaluateAnswer } from "@/entities/exercise/evaluator";
import type { CorrectAnswer, SubmittedAnswer } from "@/entities/exercise/types";

describe("evaluateAnswer", () => {
  it("grades MULTIPLE_CHOICE regardless of selection order", () => {
    const correct: CorrectAnswer = { type: "MULTIPLE_CHOICE", correctIndices: [1, 2] };
    expect(
      evaluateAnswer(correct, { type: "MULTIPLE_CHOICE", selectedIndices: [2, 1] })
        .isCorrect,
    ).toBe(true);
    expect(
      evaluateAnswer(correct, { type: "MULTIPLE_CHOICE", selectedIndices: [0] })
        .isCorrect,
    ).toBe(false);
  });

  it("grades TEXT_INPUT case-insensitively by default", () => {
    const correct: CorrectAnswer = {
      type: "TEXT_INPUT",
      acceptedAnswers: ["Высокие продажи"],
    };
    expect(
      evaluateAnswer(correct, { type: "TEXT_INPUT", value: "высокие продажи" }).isCorrect,
    ).toBe(true);
    expect(
      evaluateAnswer(correct, { type: "TEXT_INPUT", value: "низкие" }).isCorrect,
    ).toBe(false);
  });

  it("grades FORMULA_INPUT ignoring whitespace, case and , vs ; separators", () => {
    const correct: CorrectAnswer = {
      type: "FORMULA_INPUT",
      acceptedFormulas: ['=ЕСЛИ(C2>100000;"Высокие";"Обычные")'],
    };
    const submitted: SubmittedAnswer = {
      type: "FORMULA_INPUT",
      formula: '=если(c2>100000,"Высокие","Обычные")',
    };
    expect(evaluateAnswer(correct, submitted).isCorrect).toBe(true);
  });

  it("grades TRUE_FALSE", () => {
    const correct: CorrectAnswer = { type: "TRUE_FALSE", value: true };
    expect(evaluateAnswer(correct, { type: "TRUE_FALSE", value: true }).isCorrect).toBe(
      true,
    );
    expect(evaluateAnswer(correct, { type: "TRUE_FALSE", value: false }).isCorrect).toBe(
      false,
    );
  });

  it("grades MATCHING as an exact positional match", () => {
    const correct: CorrectAnswer = { type: "MATCHING", pairs: [2, 0, 1] };
    expect(
      evaluateAnswer(correct, { type: "MATCHING", pairs: [2, 0, 1] }).isCorrect,
    ).toBe(true);
    expect(
      evaluateAnswer(correct, { type: "MATCHING", pairs: [0, 2, 1] }).isCorrect,
    ).toBe(false);
  });

  it("grades ORDERING as an exact sequence match", () => {
    const correct: CorrectAnswer = { type: "ORDERING", order: [3, 1, 2, 0] };
    expect(
      evaluateAnswer(correct, { type: "ORDERING", order: [3, 1, 2, 0] }).isCorrect,
    ).toBe(true);
    expect(
      evaluateAnswer(correct, { type: "ORDERING", order: [0, 1, 2, 3] }).isCorrect,
    ).toBe(false);
  });

  it("grades DATA_ANALYSIS numerically within tolerance", () => {
    const correct: CorrectAnswer = {
      type: "DATA_ANALYSIS",
      acceptedAnswers: ["125000"],
      tolerance: 500,
    };
    expect(
      evaluateAnswer(correct, { type: "DATA_ANALYSIS", value: "125200" }).isCorrect,
    ).toBe(true);
    expect(
      evaluateAnswer(correct, { type: "DATA_ANALYSIS", value: "130000" }).isCorrect,
    ).toBe(false);
  });

  it("throws for SQL_QUERY, which must be graded via the sandbox", () => {
    const correct: CorrectAnswer = { type: "SQL_QUERY", referenceQuery: "SELECT 1" };
    expect(() =>
      evaluateAnswer(correct, { type: "SQL_QUERY", query: "SELECT 1" }),
    ).toThrowError(/sandbox/i);
  });

  it("throws when the submitted answer type does not match the exercise type", () => {
    const correct: CorrectAnswer = { type: "TRUE_FALSE", value: true };
    expect(() =>
      evaluateAnswer(correct, { type: "TEXT_INPUT", value: "true" }),
    ).toThrowError(/does not match/i);
  });
});
