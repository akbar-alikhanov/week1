import { prisma } from "@/infrastructure/database/prisma-client";
import { PrismaUserRepository } from "@/infrastructure/repositories/prisma-user.repository";
import { BcryptPasswordHasher } from "@/infrastructure/services/bcrypt-password-hasher";
import { RegisterUserUseCase } from "@/features/authentication/application/register-user.use-case";
import { AuthenticateUserUseCase } from "@/features/authentication/application/authenticate-user.use-case";

/**
 * Composition root: the one place infrastructure implementations are wired
 * to the interfaces the application layer depends on. Server Actions and
 * route handlers pull dependencies from here; nothing under
 * src/entities or src/features/*\/application ever imports this file.
 */
class Container {
  readonly userRepository = new PrismaUserRepository(prisma);
  readonly passwordHasher = new BcryptPasswordHasher();

  readonly registerUserUseCase = new RegisterUserUseCase(
    this.userRepository,
    this.passwordHasher,
  );
  readonly authenticateUserUseCase = new AuthenticateUserUseCase(
    this.userRepository,
    this.passwordHasher,
  );
}

let instance: Container | undefined;

export function getContainer(): Container {
  if (!instance) {
    instance = new Container();
  }
  return instance;
}
