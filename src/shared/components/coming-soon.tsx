import { Card, CardContent } from "@/shared/ui/card";

export function ComingSoon({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      </div>
      <Card>
        <CardContent className="pt-6 text-sm text-muted-foreground">
          {description}
        </CardContent>
      </Card>
    </main>
  );
}
