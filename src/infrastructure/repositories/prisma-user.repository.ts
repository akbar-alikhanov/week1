import type { PrismaClient } from "@/generated/prisma/client";
import type { UserModel as PrismaUser } from "@/generated/prisma/models/User";
import { User } from "@/entities/user/model";
import type { CreateUserInput, UserRepository } from "@/entities/user/repository";

export class PrismaUserRepository implements UserRepository {
  constructor(private readonly db: PrismaClient) {}

  async findById(id: string): Promise<User | null> {
    const record = await this.db.user.findUnique({ where: { id } });
    return record ? toDomain(record) : null;
  }

  async findByEmail(email: string): Promise<User | null> {
    const record = await this.db.user.findUnique({ where: { email } });
    return record ? toDomain(record) : null;
  }

  async create(input: CreateUserInput): Promise<User> {
    const record = await this.db.user.create({
      data: {
        name: input.name,
        email: input.email,
        passwordHash: input.passwordHash,
      },
    });
    return toDomain(record);
  }

  async save(user: User): Promise<void> {
    const props = user.toProps();
    await this.db.user.update({
      where: { id: props.id },
      data: {
        name: props.name,
        xp: props.xp,
        level: props.level,
        currentStreak: props.currentStreak,
        longestStreak: props.longestStreak,
        lastActivityAt: props.lastActivityAt,
      },
    });
  }
}

function toDomain(record: PrismaUser): User {
  return User.create({
    id: record.id,
    name: record.name,
    email: record.email,
    passwordHash: record.passwordHash,
    image: record.image,
    level: record.level,
    xp: record.xp,
    currentStreak: record.currentStreak,
    longestStreak: record.longestStreak,
    lastActivityAt: record.lastActivityAt,
    createdAt: record.createdAt,
  });
}
