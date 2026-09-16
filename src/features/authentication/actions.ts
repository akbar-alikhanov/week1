"use server";

import { AuthError } from "next-auth";

import { auth, signIn, signOut } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { ValidationError } from "@/shared/errors/app-error";
import { runAction, type ActionResult } from "@/shared/errors/action-result";
import { loginSchema, registerSchema } from "@/shared/validation/auth";

export async function registerAction(
  input: unknown,
): Promise<ActionResult<{ email: string }>> {
  return runAction(async () => {
    const parsed = registerSchema.safeParse(input);
    if (!parsed.success) {
      throw new ValidationError(
        "Please fix the highlighted fields.",
        parsed.error.flatten().fieldErrors,
      );
    }

    const user = await getContainer().registerUserUseCase.execute(parsed.data);

    await signIn("credentials", {
      email: parsed.data.email,
      password: parsed.data.password,
      redirect: false,
    });

    return { email: user.email };
  });
}

export async function loginAction(
  input: unknown,
): Promise<ActionResult<{ email: string }>> {
  return runAction(async () => {
    const parsed = loginSchema.safeParse(input);
    if (!parsed.success) {
      throw new ValidationError(
        "Please fix the highlighted fields.",
        parsed.error.flatten().fieldErrors,
      );
    }

    try {
      await signIn("credentials", {
        email: parsed.data.email,
        password: parsed.data.password,
        redirect: false,
      });
    } catch (error) {
      if (error instanceof AuthError) {
        throw new ValidationError("Invalid email or password.", {
          email: ["Invalid email or password."],
        });
      }
      throw error;
    }

    return { email: parsed.data.email };
  });
}

export async function logoutAction(): Promise<void> {
  await signOut({ redirect: false });
}

export async function getCurrentUserId(): Promise<string | null> {
  const session = await auth();
  return session?.user?.id ?? null;
}
