import type { Metadata } from "next";

import { SqlPlayground } from "@/features/exercises/components/sql-playground";

export const metadata: Metadata = {
  title: "SQL Playground",
  robots: { index: false, follow: false },
};

export default function PlaygroundPage() {
  return (
    <div className="flex flex-1 flex-col">
      <div className="border-b border-border px-6 py-4">
        <h1 className="text-2xl font-semibold tracking-tight">SQL Playground</h1>
        <p className="text-muted-foreground">
          Run read-only SELECT queries against the sandbox dataset. Writes and schema
          changes are blocked.
        </p>
      </div>
      <SqlPlayground />
    </div>
  );
}
