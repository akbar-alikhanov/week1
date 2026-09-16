import { Client } from "pg";

/**
 * Test-only shortcut: marks the Excel course as 100% complete for a user so
 * SQL (unlocked only once Excel is done) can be exercised directly, without
 * clicking through all 54 Excel lessons in every SQL-focused e2e spec.
 */
export async function unlockSqlCourseForUser(email: string): Promise<void> {
  const client = new Client({ connectionString: process.env.DATABASE_URL });
  await client.connect();
  try {
    const userResult = await client.query('SELECT id FROM "User" WHERE email = $1', [
      email,
    ]);
    const courseResult = await client.query('SELECT id FROM "Course" WHERE track = $1', [
      "EXCEL",
    ]);
    const userId = userResult.rows[0]?.id;
    const courseId = courseResult.rows[0]?.id;
    if (!userId || !courseId) {
      throw new Error("Could not find user or Excel course to unlock SQL for.");
    }

    await client.query(
      `INSERT INTO "UserCourseProgress" (id, "userId", "courseId", "percentComplete", "completedAt", "updatedAt")
       VALUES (gen_random_uuid()::text, $1, $2, 100, now(), now())
       ON CONFLICT ("userId", "courseId")
       DO UPDATE SET "percentComplete" = 100, "completedAt" = now(), "updatedAt" = now()`,
      [userId, courseId],
    );
  } finally {
    await client.end();
  }
}
