import Link from "next/link";
import { Lock } from "lucide-react";

import { Button } from "@/shared/ui/button";
import { Card, CardContent } from "@/shared/ui/card";

export function LockedCourseNotice({ message }: { message: string }) {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
      <Lock className="size-8 text-muted-foreground" />
      <Card>
        <CardContent className="space-y-3 pt-6">
          <p className="text-sm text-muted-foreground">{message}</p>
          <Button asChild>
            <Link href="/roadmap">View roadmap</Link>
          </Button>
        </CardContent>
      </Card>
    </main>
  );
}
