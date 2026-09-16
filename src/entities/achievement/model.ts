import { ACHIEVEMENT_THRESHOLDS } from "@/shared/constants/gamification";

export const ACHIEVEMENT_CODES = [
  "FIRST_LESSON",
  "FIRST_EXERCISE",
  "EXCEL_BEGINNER",
  "SQL_BEGINNER",
  "TEN_EXERCISES",
  "FIFTY_EXERCISES",
  "FIRST_PROJECT",
  "SQL_MASTERY",
  "SEVEN_DAY_STREAK",
] as const;

export type AchievementCode = (typeof ACHIEVEMENT_CODES)[number];

export interface AchievementProps {
  id: string;
  code: AchievementCode;
  title: string;
  description: string;
  icon: string;
}

export class Achievement {
  private constructor(private props: AchievementProps) {}

  static create(props: AchievementProps): Achievement {
    return new Achievement(props);
  }

  get id() {
    return this.props.id;
  }
  get code() {
    return this.props.code;
  }
  get title() {
    return this.props.title;
  }
  get description() {
    return this.props.description;
  }
  get icon() {
    return this.props.icon;
  }

  toProps(): AchievementProps {
    return { ...this.props };
  }
}

/** Stats snapshot used to decide which achievements a user has newly earned. */
export interface AchievementStats {
  completedLessons: number;
  completedExercises: number;
  completedProjects: number;
  currentStreak: number;
  excelCourseCompleted: boolean;
  sqlCourseCompleted: boolean;
  passedSqlQuizzes: number;
}

/**
 * Pure policy: given the user's current stats and which achievements they
 * already have, returns the codes of achievements newly unlocked. Framework-
 * and persistence-free by design so it is trivial to unit test.
 */
export function evaluateNewAchievements(
  stats: AchievementStats,
  alreadyUnlocked: ReadonlySet<AchievementCode>,
): AchievementCode[] {
  const candidates: [AchievementCode, boolean][] = [
    ["FIRST_LESSON", stats.completedLessons >= 1],
    ["FIRST_EXERCISE", stats.completedExercises >= 1],
    ["EXCEL_BEGINNER", stats.excelCourseCompleted],
    ["SQL_BEGINNER", stats.sqlCourseCompleted],
    ["TEN_EXERCISES", stats.completedExercises >= ACHIEVEMENT_THRESHOLDS.TEN_EXERCISES],
    [
      "FIFTY_EXERCISES",
      stats.completedExercises >= ACHIEVEMENT_THRESHOLDS.FIFTY_EXERCISES,
    ],
    ["FIRST_PROJECT", stats.completedProjects >= 1],
    ["SQL_MASTERY", stats.passedSqlQuizzes >= 5],
    ["SEVEN_DAY_STREAK", stats.currentStreak >= ACHIEVEMENT_THRESHOLDS.SEVEN_DAY_STREAK],
  ];

  return candidates
    .filter(([code, earned]) => earned && !alreadyUnlocked.has(code))
    .map(([code]) => code);
}
