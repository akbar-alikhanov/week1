import { ValidationError } from "@/shared/errors/app-error";

export interface QuizQuestionProps {
  id: string;
  question: string;
  options: string[];
  explanation: string;
  order: number;
}

/** Public-safe quiz question (no `correctAnswer`). */
export class QuizQuestion {
  private constructor(private props: QuizQuestionProps) {}

  static create(props: QuizQuestionProps): QuizQuestion {
    if (props.options.length < 2) {
      throw new ValidationError("A quiz question needs at least two options.");
    }
    return new QuizQuestion(props);
  }

  get id() {
    return this.props.id;
  }
  get question() {
    return this.props.question;
  }
  get options() {
    return this.props.options;
  }
  get explanation() {
    return this.props.explanation;
  }
  get order() {
    return this.props.order;
  }

  toProps(): QuizQuestionProps {
    return { ...this.props };
  }
}

export interface QuizProps {
  id: string;
  lessonId: string;
  title: string;
  passingScore: number;
  questions: QuizQuestion[];
}

export class Quiz {
  private constructor(private props: QuizProps) {}

  static create(props: QuizProps): Quiz {
    return new Quiz(props);
  }

  get id() {
    return this.props.id;
  }
  get lessonId() {
    return this.props.lessonId;
  }
  get title() {
    return this.props.title;
  }
  get passingScore() {
    return this.props.passingScore;
  }
  get questions() {
    return this.props.questions;
  }

  /** Grades answers (questionId -> selected option index) against `correctAnswers`. */
  grade(
    answers: Record<string, number>,
    correctAnswers: Record<string, number>,
  ): { score: number; passed: boolean; correctCount: number } {
    const total = this.props.questions.length;
    const correctCount = this.props.questions.filter(
      (q) => answers[q.id] === correctAnswers[q.id],
    ).length;
    const score = total === 0 ? 0 : Math.round((correctCount / total) * 100);
    return { score, passed: score >= this.props.passingScore, correctCount };
  }

  toProps(): QuizProps {
    return { ...this.props };
  }
}
