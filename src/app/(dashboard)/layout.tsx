import Link from "next/link";
import { redirect } from "next/navigation";

import { auth } from "@/infrastructure/auth/auth";
import { UserMenu } from "@/features/authentication/components/user-menu";
import { SidebarNav } from "@/shared/components/sidebar-nav";
import { MobileNav } from "@/shared/components/mobile-nav";

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
    <div className="flex min-h-full flex-1">
      <aside className="hidden w-60 shrink-0 border-r border-sidebar-border bg-sidebar sm:block">
        <div className="flex h-14 items-center border-b border-sidebar-border px-4">
          <Link href="/dashboard" className="text-sm font-semibold tracking-tight">
            DALA
          </Link>
        </div>
        <SidebarNav />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b border-border px-4 sm:px-6">
          <div className="flex items-center gap-2">
            <MobileNav />
            <span className="text-sm font-semibold tracking-tight sm:hidden">DALA</span>
          </div>
          <UserMenu
            name={session.user.name ?? "You"}
            email={session.user.email ?? ""}
            image={session.user.image ?? null}
          />
        </header>
        <div className="flex flex-1 flex-col">{children}</div>
      </div>
    </div>
  );
}
