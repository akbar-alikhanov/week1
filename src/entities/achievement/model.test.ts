import { describe, expect, it } from "vitest";

import {
  evaluateNewAchievements,
  type AchievementStats,
} from "@/entities/achievement/model";

const baseStats: AchievementStats = {
  completedLessons: 0,
  completedExercises: 0,
  completedProjects: 0,
  currentStreak: 0,
  excelCourseCompleted: false,
  sqlCourseCompleted: false,
  passedSqlQuizzes: 0,
};

describe("evaluateNewAchievements", () => {
  it("unlocks FIRST_LESSON once completedLessons reaches 1", () => {
    const codes = evaluateNewAchievements(
      { ...baseStats, completedLessons: 1 },
      new Set(),
    );
    expect(codes).toContain("FIRST_LESSON");
  });

  it("does not re-unlock an achievement the user already has", () => {
    const codes = evaluateNewAchievements(
      { ...baseStats, completedLessons: 1 },
      new Set(["FIRST_LESSON"]),
    );
    expect(codes).not.toContain("FIRST_LESSON");
  });

  it("unlocks multiple achievements at once when several thresholds are crossed", () => {
    const codes = evaluateNewAchievements(
      { ...baseStats, completedLessons: 1, completedExercises: 10 },
      new Set(),
    );
    expect(codes).toContain("FIRST_LESSON");
    expect(codes).toContain("FIRST_EXERCISE");
    expect(codes).toContain("TEN_EXERCISES");
  });

  it("unlocks SQL_MASTERY at 5 passed SQL quizzes", () => {
    const codes = evaluateNewAchievements(
      { ...baseStats, passedSqlQuizzes: 5 },
      new Set(),
    );
    expect(codes).toContain("SQL_MASTERY");
  });

  it("unlocks SEVEN_DAY_STREAK at a 7-day streak", () => {
    const codes = evaluateNewAchievements({ ...baseStats, currentStreak: 7 }, new Set());
    expect(codes).toContain("SEVEN_DAY_STREAK");
  });

  it("returns nothing when no thresholds are crossed", () => {
    const codes = evaluateNewAchievements(baseStats, new Set());
    expect(codes).toHaveLength(0);
  });
});
