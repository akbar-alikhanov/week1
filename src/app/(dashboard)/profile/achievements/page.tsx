import type { Metadata } from "next";
import { Lock, Trophy } from "lucide-react";

import { auth } from "@/infrastructure/auth/auth";
import { getContainer } from "@/infrastructure/container";
import { Card, CardContent } from "@/shared/ui/card";
import { cn } from "@/shared/lib/cn";

export const metadata: Metadata = {
  title: "Achievements",
  robots: { index: false, follow: false },
};

export default async function AchievementsPage() {
  const session = await auth();
  const achievements = await getContainer().listAchievementsUseCase.execute(
    session!.user!.id,
  );

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Achievements</h1>
        <p className="text-muted-foreground">
          {achievements.filter((a) => a.isUnlocked).length}/{achievements.length} unlocked
        </p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {achievements.map((achievement) => (
          <Card
            key={achievement.code}
            className={cn(!achievement.isUnlocked && "opacity-60")}
          >
            <CardContent className="flex items-center gap-3 pt-6">
              <div
                className={cn(
                  "flex size-10 shrink-0 items-center justify-center rounded-full",
                  achievement.isUnlocked
                    ? "bg-success/15 text-success"
                    : "bg-muted text-muted-foreground",
                )}
              >
                {achievement.isUnlocked ? (
                  <Trophy className="size-5" />
                ) : (
                  <Lock className="size-4" />
                )}
              </div>
              <div>
                <p className="font-medium">{achievement.title}</p>
                <p className="text-sm text-muted-foreground">{achievement.description}</p>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </main>
  );
}
