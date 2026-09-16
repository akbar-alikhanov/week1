import type { Metadata, Route } from "next";
import Link from "next/link";
import { ArrowDown, CheckCircle2, Lock } from "lucide-react";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { Badge } from "@/shared/ui/badge";
import { Progress } from "@/shared/ui/progress";
import { cn } from "@/shared/lib/cn";

export const metadata: Metadata = {
  title: "Roadmap",
  robots: { index: false, follow: false },
};

const FINAL_STAGES: { title: string; href: Route }[] = [
  { title: "Projects", href: "/projects" },
  { title: "Career", href: "/career" },
];

export default async function RoadmapPage() {
  const session = await auth();
  const courses = await getContainer().listCoursesUseCase.execute(
    session?.user?.id ?? null,
  );

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col items-center gap-2 p-6">
      <div className="mb-4 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Roadmap</h1>
        <p className="text-muted-foreground">Your path to Junior Data Analyst.</p>
      </div>

      {courses.map((course, index) => (
        <div key={course.id} className="flex w-full flex-col items-center">
          <RoadmapNode
            title={course.title}
            href={`/courses/${course.slug}` as Route}
            isUnlocked={course.isUnlocked}
            percentComplete={course.percentComplete}
          />
          {index < courses.length - 1 || FINAL_STAGES.length > 0 ? (
            <ArrowDown className="my-1 size-5 text-muted-foreground" />
          ) : null}
        </div>
      ))}

      {FINAL_STAGES.map((stage, index) => {
        const allCoursesComplete = courses.every((c) => c.percentComplete === 100);
        return (
          <div key={stage.title} className="flex w-full flex-col items-center">
            <RoadmapNode
              title={stage.title}
              href={stage.href}
              isUnlocked={allCoursesComplete}
              percentComplete={null}
            />
            {index < FINAL_STAGES.length - 1 ? (
              <ArrowDown className="my-1 size-5 text-muted-foreground" />
            ) : null}
          </div>
        );
      })}
    </main>
  );
}

function RoadmapNode({
  title,
  href,
  isUnlocked,
  percentComplete,
}: {
  title: string;
  href: Route;
  isUnlocked: boolean;
  percentComplete: number | null;
}) {
  const isCompleted = percentComplete === 100;

  const content = (
    <div
      className={cn(
        "flex w-full items-center justify-between gap-3 rounded-lg border px-4 py-3 transition-colors",
        isUnlocked
          ? "border-border bg-card hover:border-primary/50"
          : "border-dashed border-border bg-muted/30",
      )}
    >
      <span className={cn("font-medium", !isUnlocked && "text-muted-foreground")}>
        {title}
      </span>
      {isCompleted ? (
        <Badge variant="success" className="gap-1">
          <CheckCircle2 className="size-3" />
          Done
        </Badge>
      ) : isUnlocked ? (
        percentComplete !== null ? (
          <span className="w-24">
            <Progress value={percentComplete} />
          </span>
        ) : null
      ) : (
        <Lock className="size-4 shrink-0 text-muted-foreground" />
      )}
    </div>
  );

  return isUnlocked ? (
    <Link href={href} className="w-full">
      {content}
    </Link>
  ) : (
    <div className="w-full cursor-not-allowed">{content}</div>
  );
}
