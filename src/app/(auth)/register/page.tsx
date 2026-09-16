import type { Metadata } from "next";
import Link from "next/link";

import { RegisterForm } from "@/features/authentication/components/register-form";

export const metadata: Metadata = {
  title: "Create account",
};

export default function RegisterPage() {
  return (
    <>
      <div className="space-y-1 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Start learning</h1>
        <p className="text-sm text-muted-foreground">
          Create a free account to track your progress.
        </p>
      </div>
      <RegisterForm />
      <p className="text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link
          href="/login"
          className="font-medium text-foreground underline underline-offset-4"
        >
          Sign in
        </Link>
      </p>
    </>
  );
}
