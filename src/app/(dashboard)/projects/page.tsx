import type { Metadata } from "next";
import Link from "next/link";
import { CheckCircle2, Lock } from "lucide-react";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { Badge } from "@/shared/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { cn } from "@/shared/lib/cn";

export const metadata: Metadata = {
  title: "Projects",
  robots: { index: false, follow: false },
};

export default async function ProjectsPage() {
  const session = await auth();
  const projects = await getContainer().listProjectsUseCase.execute(
    session?.user?.id ?? null,
  );

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
        <p className="text-muted-foreground">
          Apply what you learned to realistic business problems and build a portfolio.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {projects.map((project) => {
          const card = (
            <Card
              className={cn(
                "h-full transition-colors",
                project.isUnlocked && "hover:bg-accent",
                !project.isUnlocked && "opacity-60",
              )}
            >
              <CardHeader>
                <div className="flex items-start justify-between gap-2">
                  <CardTitle className="text-base">{project.title}</CardTitle>
                  {project.isCompleted ? (
                    <CheckCircle2 className="size-4 shrink-0 text-success" />
                  ) : !project.isUnlocked ? (
                    <Lock className="size-4 shrink-0 text-muted-foreground" />
                  ) : null}
                </div>
                <p className="text-xs text-muted-foreground">{project.courseTitle}</p>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="line-clamp-2 text-sm text-muted-foreground">
                  {project.goal}
                </p>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">+{project.xpReward} XP</Badge>
                  {project.isCompleted ? (
                    <Badge variant="secondary">Submitted</Badge>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          );

          return project.isUnlocked ? (
            <Link key={project.id} href={`/projects/${project.slug}`}>
              {card}
            </Link>
          ) : (
            <div key={project.id}>{card}</div>
          );
        })}
      </div>
    </main>
  );
}
