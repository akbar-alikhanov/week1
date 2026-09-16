import { ValidationError } from "@/shared/errors/app-error";
import type {
  CorrectAnswer,
  Difficulty,
  ExerciseData,
  ExerciseType,
} from "@/entities/exercise/types";

export interface ExerciseProps {
  id: string;
  lessonId: string;
  type: ExerciseType;
  title: string;
  description: string;
  difficulty: Difficulty;
  points: number;
  order: number;
  data: ExerciseData;
  explanation: string;
}

/**
 * Public-safe exercise: everything a client is allowed to receive.
 * `correctAnswer` deliberately does not exist on this type.
 */
export class Exercise {
  private constructor(private props: ExerciseProps) {}

  static create(props: ExerciseProps): Exercise {
    if (!props.title.trim()) {
      throw new ValidationError("Exercise title is required.");
    }
    if (props.points <= 0) {
      throw new ValidationError("Exercise points must be positive.");
    }
    return new Exercise(props);
  }

  get id() {
    return this.props.id;
  }
  get lessonId() {
    return this.props.lessonId;
  }
  get type() {
    return this.props.type;
  }
  get title() {
    return this.props.title;
  }
  get description() {
    return this.props.description;
  }
  get difficulty() {
    return this.props.difficulty;
  }
  get points() {
    return this.props.points;
  }
  get order() {
    return this.props.order;
  }
  get data() {
    return this.props.data;
  }
  get explanation() {
    return this.props.explanation;
  }

  toProps(): ExerciseProps {
    return { ...this.props };
  }
}

/**
 * Server-side-only pairing of an exercise with its answer key. Never
 * serialize this to a client component or API response.
 */
export interface ExerciseWithAnswer {
  exercise: Exercise;
  correctAnswer: CorrectAnswer;
}
