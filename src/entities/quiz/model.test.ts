import { describe, expect, it } from "vitest";

import { Quiz, QuizQuestion } from "@/entities/quiz/model";

const questions = [
  QuizQuestion.create({
    id: "q1",
    question: "2 + 2?",
    options: ["3", "4", "5"],
    explanation: "2 + 2 = 4",
    order: 0,
  }),
  QuizQuestion.create({
    id: "q2",
    question: "Capital of France?",
    options: ["Berlin", "Paris", "Rome"],
    explanation: "Paris is the capital of France.",
    order: 1,
  }),
];

const quiz = Quiz.create({
  id: "quiz-1",
  lessonId: "lesson-1",
  title: "Sample quiz",
  passingScore: 70,
  questions,
});

const correctAnswers = { q1: 1, q2: 1 };

describe("Quiz.grade", () => {
  it("scores 100% and passes when every answer is correct", () => {
    const result = quiz.grade({ q1: 1, q2: 1 }, correctAnswers);
    expect(result).toEqual({ score: 100, passed: true, correctCount: 2 });
  });

  it("scores 50% and fails against a 70% passing score", () => {
    const result = quiz.grade({ q1: 1, q2: 0 }, correctAnswers);
    expect(result).toEqual({ score: 50, passed: false, correctCount: 1 });
  });

  it("treats a missing answer as incorrect rather than throwing", () => {
    const result = quiz.grade({ q1: 1 }, correctAnswers);
    expect(result).toEqual({ score: 50, passed: false, correctCount: 1 });
  });
});

describe("QuizQuestion.create", () => {
  it("rejects a question with fewer than two options", () => {
    expect(() =>
      QuizQuestion.create({
        id: "q3",
        question: "Only one option?",
        options: ["Only one"],
        explanation: "",
        order: 0,
      }),
    ).toThrow();
  });
});
