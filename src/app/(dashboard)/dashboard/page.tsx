import type { Metadata } from "next";
import Link from "next/link";
import { Flame, Trophy } from "lucide-react";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Progress } from "@/shared/ui/progress";

export const metadata: Metadata = {
  title: "Dashboard",
  robots: { index: false, follow: false },
};

export default async function DashboardPage() {
  const session = await auth();
  const userId = session!.user!.id;
  const dashboard = await getContainer().getDashboardUseCase.execute(userId);

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Good to see you, {dashboard.name.split(" ")[0]} 👋
        </h1>
        <p className="text-muted-foreground">Here&apos;s where you left off.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Your progress</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <Stat label="Level" value={dashboard.level} />
            <Stat label="XP" value={`${dashboard.xpIntoLevel}/${dashboard.xpPerLevel}`} />
            <Stat
              label="Streak"
              value={
                <span className="inline-flex items-center gap-1">
                  {dashboard.currentStreak}
                  {dashboard.currentStreak > 0 ? (
                    <Flame className="size-4 text-warning" />
                  ) : null}
                </span>
              }
            />
            <Stat label="Overall" value={`${dashboard.overallPercentComplete}%`} />
          </div>
          <div className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>Data Analytics</span>
              <span>{dashboard.overallPercentComplete}%</span>
            </div>
            <Progress value={dashboard.overallPercentComplete} />
          </div>
        </CardContent>
      </Card>

      {dashboard.continueLearning ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Continue learning</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-start justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <p className="text-sm text-muted-foreground">
                {dashboard.continueLearning.courseTitle} ·{" "}
                {dashboard.continueLearning.moduleTitle}
              </p>
              <p className="text-lg font-semibold">
                {dashboard.continueLearning.lessonTitle}
              </p>
            </div>
            <Button asChild>
              <Link
                href={`/courses/${dashboard.continueLearning.courseSlug}/${dashboard.continueLearning.moduleSlug}/${dashboard.continueLearning.lessonSlug}`}
              >
                Continue
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="py-6 text-center text-muted-foreground">
            You&apos;ve completed every available lesson. Nicely done!
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Courses</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {dashboard.courses.map((course) => (
            <Link
              key={course.courseId}
              href={`/courses/${course.courseSlug}`}
              className="block space-y-1 rounded-md p-2 transition-colors hover:bg-accent"
            >
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">{course.courseTitle}</span>
                <span className="text-muted-foreground">{course.percentComplete}%</span>
              </div>
              <Progress value={course.percentComplete} />
            </Link>
          ))}
        </CardContent>
      </Card>

      {dashboard.recentAchievements.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent achievements</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {dashboard.recentAchievements.map((achievement) => (
              <Badge key={achievement.code} variant="success" className="gap-1 py-1">
                <Trophy className="size-3" />
                {achievement.title}
              </Badge>
            ))}
          </CardContent>
        </Card>
      ) : null}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-semibold">{value}</p>
    </div>
  );
}
