export {
  Exercise,
  type ExerciseProps,
  type ExerciseWithAnswer,
} from "@/entities/exercise/model";
export {
  EXERCISE_TYPES,
  DIFFICULTIES,
  type ExerciseType,
  type Difficulty,
  type ExerciseData,
  type CorrectAnswer,
  type SubmittedAnswer,
  type SpreadsheetTable,
} from "@/entities/exercise/types";
export { evaluateAnswer, type EvaluationResult } from "@/entities/exercise/evaluator";
export type { ExerciseRepository } from "@/entities/exercise/repository";
