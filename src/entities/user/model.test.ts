import { describe, expect, it } from "vitest";

import { User, levelForXp } from "@/entities/user/model";

function buildUser(overrides: Partial<Parameters<typeof User.create>[0]> = {}) {
  return User.create({
    id: "user-1",
    name: "Ada Lovelace",
    email: "ada@example.com",
    passwordHash: "hash",
    image: null,
    level: 1,
    xp: 0,
    currentStreak: 0,
    longestStreak: 0,
    lastActivityAt: null,
    createdAt: new Date("2026-01-01T00:00:00Z"),
    ...overrides,
  });
}

describe("User", () => {
  it("rejects an invalid email", () => {
    expect(() => buildUser({ email: "not-an-email" })).toThrowError(/valid email/i);
  });

  it("computes level from XP in 100-XP increments", () => {
    expect(levelForXp(0)).toBe(1);
    expect(levelForXp(99)).toBe(1);
    expect(levelForXp(100)).toBe(2);
    expect(levelForXp(250)).toBe(3);
  });

  it("adds XP and recomputes level immutably", () => {
    const user = buildUser({ xp: 90 });
    const leveledUp = user.addXp(20);

    expect(user.xp).toBe(90);
    expect(user.level).toBe(1);
    expect(leveledUp.xp).toBe(110);
    expect(leveledUp.level).toBe(2);
  });

  it("rejects a non-positive XP award", () => {
    const user = buildUser();
    expect(() => user.addXp(0)).toThrowError(/positive/i);
  });

  it("starts a streak at 1 on first activity", () => {
    const user = buildUser();
    const active = user.recordActivity(new Date("2026-03-10T09:00:00Z"));
    expect(active.currentStreak).toBe(1);
    expect(active.longestStreak).toBe(1);
  });

  it("increments the streak for consecutive days", () => {
    const user = buildUser({
      currentStreak: 3,
      longestStreak: 5,
      lastActivityAt: new Date("2026-03-10T09:00:00Z"),
    });
    const active = user.recordActivity(new Date("2026-03-11T08:00:00Z"));
    expect(active.currentStreak).toBe(4);
    expect(active.longestStreak).toBe(5);
  });

  it("does not double-count activity on the same day", () => {
    const user = buildUser({
      currentStreak: 3,
      longestStreak: 3,
      lastActivityAt: new Date("2026-03-10T09:00:00Z"),
    });
    const active = user.recordActivity(new Date("2026-03-10T20:00:00Z"));
    expect(active.currentStreak).toBe(3);
  });

  it("resets the streak after a missed day", () => {
    const user = buildUser({
      currentStreak: 5,
      longestStreak: 5,
      lastActivityAt: new Date("2026-03-10T09:00:00Z"),
    });
    const active = user.recordActivity(new Date("2026-03-13T09:00:00Z"));
    expect(active.currentStreak).toBe(1);
    expect(active.longestStreak).toBe(5);
  });
});
