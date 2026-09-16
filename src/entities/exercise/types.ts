export const EXERCISE_TYPES = [
  "MULTIPLE_CHOICE",
  "TEXT_INPUT",
  "FORMULA_INPUT",
  "SQL_QUERY",
  "TRUE_FALSE",
  "MATCHING",
  "ORDERING",
  "DATA_ANALYSIS",
] as const;

export type ExerciseType = (typeof EXERCISE_TYPES)[number];

export const DIFFICULTIES = ["BEGINNER", "INTERMEDIATE", "ADVANCED"] as const;
export type Difficulty = (typeof DIFFICULTIES)[number];

// ---------------------------------------------------------------------------
// Per-type exercise "data" (safe to send to the client) and "correctAnswer"
// (server-side only) shapes, plus the shape of what the learner submits.
// ---------------------------------------------------------------------------

export interface SpreadsheetTable {
  headers: string[];
  rows: (string | number)[][];
}

export type ExerciseData =
  | { type: "MULTIPLE_CHOICE"; options: string[]; allowMultiple?: boolean }
  | { type: "TEXT_INPUT"; placeholder?: string }
  | { type: "FORMULA_INPUT"; table: SpreadsheetTable; targetCell: string }
  | { type: "SQL_QUERY"; datasetId: string; schemaHint: string }
  | { type: "TRUE_FALSE" }
  | { type: "MATCHING"; left: string[]; right: string[] }
  | { type: "ORDERING"; items: string[] }
  | { type: "DATA_ANALYSIS"; table: SpreadsheetTable; question: string };

export type CorrectAnswer =
  | { type: "MULTIPLE_CHOICE"; correctIndices: number[] }
  | { type: "TEXT_INPUT"; acceptedAnswers: string[]; caseSensitive?: boolean }
  | {
      type: "FORMULA_INPUT";
      acceptedFormulas: string[];
      expectedResult?: string | number;
    }
  | { type: "SQL_QUERY"; referenceQuery: string }
  | { type: "TRUE_FALSE"; value: boolean }
  | { type: "MATCHING"; pairs: number[] }
  | { type: "ORDERING"; order: number[] }
  | { type: "DATA_ANALYSIS"; acceptedAnswers: string[]; tolerance?: number };

export type SubmittedAnswer =
  | { type: "MULTIPLE_CHOICE"; selectedIndices: number[] }
  | { type: "TEXT_INPUT"; value: string }
  | { type: "FORMULA_INPUT"; formula: string }
  | { type: "SQL_QUERY"; query: string }
  | { type: "TRUE_FALSE"; value: boolean }
  | { type: "MATCHING"; pairs: number[] }
  | { type: "ORDERING"; order: number[] }
  | { type: "DATA_ANALYSIS"; value: string };
