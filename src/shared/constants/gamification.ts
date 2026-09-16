/** XP rewarded per completed unit of work (see spec § 17). */
export const XP_REWARDS = {
  LESSON_COMPLETED: 10,
  EXERCISE_COMPLETED: 20,
  QUIZ_PASSED: 30,
  PROJECT_COMPLETED: 200,
} as const;

/** XP required to go from level N to level N+1. */
export const XP_PER_LEVEL = 100;

export const ACHIEVEMENT_THRESHOLDS = {
  TEN_EXERCISES: 10,
  FIFTY_EXERCISES: 50,
  SEVEN_DAY_STREAK: 7,
} as const;
