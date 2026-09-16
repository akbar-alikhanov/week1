import { User } from "@/entities/user/model";
import type { UserRepository } from "@/entities/user/repository";
import { ValidationError } from "@/shared/errors/app-error";
import type { PasswordHasher } from "@/features/authentication/application/ports";

export interface RegisterUserInput {
  name: string;
  email: string;
  password: string;
}

export class RegisterUserUseCase {
  constructor(
    private readonly userRepository: UserRepository,
    private readonly passwordHasher: PasswordHasher,
  ) {}

  async execute(input: RegisterUserInput): Promise<User> {
    const email = input.email.trim().toLowerCase();
    const existing = await this.userRepository.findByEmail(email);
    if (existing) {
      throw new ValidationError("An account with this email already exists.", {
        email: ["An account with this email already exists."],
      });
    }

    const passwordHash = await this.passwordHasher.hash(input.password);

    return this.userRepository.create({
      name: input.name.trim(),
      email,
      passwordHash,
    });
  }
}
