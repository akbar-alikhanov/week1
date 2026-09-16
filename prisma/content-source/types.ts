import type {
  CorrectAnswer,
  Difficulty,
  ExerciseData,
  ExerciseType,
} from "@/entities/exercise/types";
import type { CourseTrack } from "@/entities/course/model";

export interface QuizQuestionSeed {
  question: string;
  options: string[];
  correctIndex: number;
  explanation: string;
}

export interface ExerciseSeed {
  type: ExerciseType;
  title: string;
  description: string;
  difficulty: Difficulty;
  points: number;
  data: ExerciseData;
  correctAnswer: CorrectAnswer;
  explanation: string;
}

export interface LessonSeed {
  slug: string;
  title: string;
  description: string;
  xpReward?: number;
  objectives: string[];
  /** Markdown body for the "Theory" section. */
  theory: string;
  /** Markdown body for the "Example" section (usually a code block). */
  example: string;
  commonMistakes: string[];
  exercise: ExerciseSeed;
  /** Extra exercises beyond the first, for lessons that need more practice (e.g. SQL's first modules). */
  additionalExercises?: ExerciseSeed[];
  quiz: QuizQuestionSeed[];
}

export interface ModuleSeed {
  slug: string;
  title: string;
  description: string;
  lessons: LessonSeed[];
}

export interface CourseSeed {
  slug: string;
  track: CourseTrack;
  title: string;
  description: string;
  modules: ModuleSeed[];
}
