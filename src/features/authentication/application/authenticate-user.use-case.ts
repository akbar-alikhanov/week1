import type { User } from "@/entities/user/model";
import type { UserRepository } from "@/entities/user/repository";
import type { PasswordHasher } from "@/features/authentication/application/ports";

export interface AuthenticateUserInput {
  email: string;
  password: string;
}

/**
 * Verifies credentials and returns the matching user, or `null` if the
 * email/password pair is invalid. Deliberately does not throw or
 * distinguish "no such user" from "wrong password" to avoid leaking which
 * emails are registered.
 */
export class AuthenticateUserUseCase {
  constructor(
    private readonly userRepository: UserRepository,
    private readonly passwordHasher: PasswordHasher,
  ) {}

  async execute(input: AuthenticateUserInput): Promise<User | null> {
    const user = await this.userRepository.findByEmail(input.email.trim().toLowerCase());
    if (!user || !user.passwordHash) {
      return null;
    }

    const isValid = await this.passwordHasher.compare(input.password, user.passwordHash);
    return isValid ? user : null;
  }
}
