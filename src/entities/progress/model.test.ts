import { describe, expect, it } from "vitest";

import { computeUnlockedCourseIds } from "@/entities/progress/model";

describe("computeUnlockedCourseIds", () => {
  it("always unlocks the first course", () => {
    const unlocked = computeUnlockedCourseIds([{ courseId: "a", percentComplete: 0 }]);
    expect(unlocked.has("a")).toBe(true);
  });

  it("unlocks the next course only once the previous one hits 100%", () => {
    const unlocked = computeUnlockedCourseIds([
      { courseId: "a", percentComplete: 50 },
      { courseId: "b", percentComplete: 0 },
    ]);
    expect(unlocked.has("a")).toBe(true);
    expect(unlocked.has("b")).toBe(false);
  });

  it("cascades unlocks through a fully completed chain", () => {
    const unlocked = computeUnlockedCourseIds([
      { courseId: "a", percentComplete: 100 },
      { courseId: "b", percentComplete: 100 },
      { courseId: "c", percentComplete: 40 },
      { courseId: "d", percentComplete: 0 },
    ]);
    expect([...unlocked]).toEqual(["a", "b", "c"]);
  });
});
