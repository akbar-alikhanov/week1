import type { Metadata } from "next";
import Link from "next/link";

import { LoginForm } from "@/features/authentication/components/login-form";

export const metadata: Metadata = {
  title: "Sign in",
};

export default function LoginPage() {
  return (
    <>
      <div className="space-y-1 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
        <p className="text-sm text-muted-foreground">Sign in to continue learning.</p>
      </div>
      <LoginForm />
      <p className="text-center text-sm text-muted-foreground">
        No account yet?{" "}
        <Link
          href="/register"
          className="font-medium text-foreground underline underline-offset-4"
        >
          Create one
        </Link>
      </p>
    </>
  );
}
