import { redirect } from "next/navigation";

import { auth } from "@/infrastructure/auth/auth";
import { UserMenu } from "@/features/authentication/components/user-menu";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) {
    redirect("/login");
  }

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="flex h-14 items-center justify-between border-b border-border px-4 sm:px-6">
        <span className="text-sm font-semibold tracking-tight">DALA</span>
        <UserMenu
          name={session.user.name ?? "You"}
          email={session.user.email ?? ""}
          image={session.user.image ?? null}
        />
      </header>
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  );
}
