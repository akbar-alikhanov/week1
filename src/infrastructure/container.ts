import { prisma } from "@/infrastructure/database/prisma-client";
import { PrismaUserRepository } from "@/infrastructure/repositories/prisma-user.repository";

/**
 * Composition root: the one place infrastructure implementations are wired
 * to the interfaces the application layer depends on. Server Actions and
 * route handlers pull dependencies from here; nothing under
 * src/entities or src/features/*\/application ever imports this file.
 */
class Container {
  readonly userRepository = new PrismaUserRepository(prisma);
}

let instance: Container | undefined;

export function getContainer(): Container {
  if (!instance) {
    instance = new Container();
  }
  return instance;
}
