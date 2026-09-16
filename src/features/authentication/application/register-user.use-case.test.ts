import { describe, expect, it } from "vitest";

import { User } from "@/entities/user/model";
import type { CreateUserInput, UserRepository } from "@/entities/user/repository";
import type { PasswordHasher } from "@/features/authentication/application/ports";
import { RegisterUserUseCase } from "@/features/authentication/application/register-user.use-case";

class FakeUserRepository implements UserRepository {
  private users: User[] = [];

  async findById(id: string) {
    return this.users.find((u) => u.id === id) ?? null;
  }

  async findByEmail(email: string) {
    return this.users.find((u) => u.email === email) ?? null;
  }

  async create(input: CreateUserInput) {
    const user = User.create({
      id: `user-${this.users.length + 1}`,
      name: input.name,
      email: input.email,
      passwordHash: input.passwordHash,
      image: null,
      level: 1,
      xp: 0,
      currentStreak: 0,
      longestStreak: 0,
      lastActivityAt: null,
      createdAt: new Date(),
    });
    this.users.push(user);
    return user;
  }

  async save(user: User) {
    this.users = this.users.map((u) => (u.id === user.id ? user : u));
  }
}

class FakePasswordHasher implements PasswordHasher {
  async hash(plainText: string) {
    return `hashed:${plainText}`;
  }
  async compare(plainText: string, hash: string) {
    return hash === `hashed:${plainText}`;
  }
}

describe("RegisterUserUseCase", () => {
  it("creates a user with a hashed password", async () => {
    const repo = new FakeUserRepository();
    const useCase = new RegisterUserUseCase(repo, new FakePasswordHasher());

    const user = await useCase.execute({
      name: "Grace Hopper",
      email: "Grace@Example.com",
      password: "s3cret!!",
    });

    expect(user.email).toBe("grace@example.com");
    expect(user.passwordHash).toBe("hashed:s3cret!!");
  });

  it("rejects a duplicate email", async () => {
    const repo = new FakeUserRepository();
    const useCase = new RegisterUserUseCase(repo, new FakePasswordHasher());

    await useCase.execute({ name: "A", email: "dup@example.com", password: "password1" });

    await expect(
      useCase.execute({ name: "B", email: "dup@example.com", password: "password2" }),
    ).rejects.toThrowError(/already exists/i);
  });
});
