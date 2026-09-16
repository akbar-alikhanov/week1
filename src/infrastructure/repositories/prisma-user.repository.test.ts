import { afterAll, describe, expect, it } from "vitest";

import { prisma } from "@/infrastructure/database/prisma-client";
import { PrismaUserRepository } from "@/infrastructure/repositories/prisma-user.repository";

/**
 * Infrastructure-layer test: exercises PrismaUserRepository against a real
 * (local) Postgres database, rather than a fake - see ARCHITECTURE.md's
 * testing strategy. Requires DATABASE_URL (loaded from .env).
 */
describe("PrismaUserRepository", () => {
  const repository = new PrismaUserRepository(prisma);
  const email = `infra-test-${Date.now()}@example.com`;

  afterAll(async () => {
    await prisma.user.deleteMany({ where: { email } });
  });

  it("creates a user, finds it by id/email, and persists XP updates via save()", async () => {
    const created = await repository.create({
      name: "Infra Test User",
      email,
      passwordHash: "hashed",
    });

    expect(created.email).toBe(email);
    expect(created.xp).toBe(0);
    expect(created.level).toBe(1);

    const byId = await repository.findById(created.id);
    const byEmail = await repository.findByEmail(email);
    expect(byId?.id).toBe(created.id);
    expect(byEmail?.id).toBe(created.id);

    const leveledUp = created.addXp(150).recordActivity();
    await repository.save(leveledUp);

    const reloaded = await repository.findById(created.id);
    expect(reloaded?.xp).toBe(150);
    expect(reloaded?.level).toBe(2);
    expect(reloaded?.currentStreak).toBe(1);
  });

  it("returns null for an id/email that doesn't exist", async () => {
    expect(await repository.findById("does-not-exist")).toBeNull();
    expect(await repository.findByEmail("nobody@example.com")).toBeNull();
  });
});
