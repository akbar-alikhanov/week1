import type { SubmittedAnswer } from "@/entities/exercise/types";

export interface ExerciseAttemptProps {
  id: string;
  userId: string;
  exerciseId: string;
  answer: SubmittedAnswer;
  isCorrect: boolean;
  pointsAwarded: number;
  feedback: string | null;
  createdAt: Date;
}

/** Immutable record of one graded attempt at an exercise. */
export class ExerciseAttempt {
  private constructor(private props: ExerciseAttemptProps) {}

  static create(props: ExerciseAttemptProps): ExerciseAttempt {
    return new ExerciseAttempt(props);
  }

  get id() {
    return this.props.id;
  }
  get userId() {
    return this.props.userId;
  }
  get exerciseId() {
    return this.props.exerciseId;
  }
  get answer() {
    return this.props.answer;
  }
  get isCorrect() {
    return this.props.isCorrect;
  }
  get pointsAwarded() {
    return this.props.pointsAwarded;
  }
  get feedback() {
    return this.props.feedback;
  }
  get createdAt() {
    return this.props.createdAt;
  }

  toProps(): ExerciseAttemptProps {
    return { ...this.props };
  }
}
