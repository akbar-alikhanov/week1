import type { Metadata } from "next";
import Link from "next/link";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Progress } from "@/shared/ui/progress";

export const metadata: Metadata = {
  title: "Courses",
  robots: { index: false, follow: false },
};

export default async function CoursesPage() {
  const session = await auth();
  const courses = await getContainer().listCoursesUseCase.execute(
    session?.user?.id ?? null,
  );

  return (
    <main className="flex flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Courses</h1>
        <p className="text-muted-foreground">
          Excel → SQL → Power BI → Python → Statistics → Business Analytics.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {courses.map((course) => (
          <Link key={course.id} href={`/courses/${course.slug}`}>
            <Card className="h-full transition-colors hover:border-primary/50">
              <CardHeader>
                <CardTitle>{course.title}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground line-clamp-2">
                  {course.description}
                </p>
                <div className="space-y-1">
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>Progress</span>
                    <span>{course.percentComplete}%</span>
                  </div>
                  <Progress value={course.percentComplete} />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </main>
  );
}
