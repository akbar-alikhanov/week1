import type { Metadata } from "next";

import { auth } from "@/infrastructure/auth/auth";

export const metadata: Metadata = {
  title: "Dashboard",
  robots: { index: false, follow: false },
};

export default async function DashboardPage() {
  const session = await auth();

  return (
    <main className="flex flex-1 flex-col gap-2 p-6">
      <h1 className="text-2xl font-semibold tracking-tight">
        Good to see you, {session?.user?.name?.split(" ")[0] ?? "there"} 👋
      </h1>
      <p className="text-muted-foreground">
        Your learning dashboard is coming together in the next phases.
      </p>
    </main>
  );
}
