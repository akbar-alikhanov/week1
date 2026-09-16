import type { Metadata } from "next";

import { ResumeBuilder } from "@/features/career/components/resume-builder";

export const metadata: Metadata = {
  title: "Resume builder",
  robots: { index: false, follow: false },
};

export default function ResumePage() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Resume builder</h1>
        <p className="text-muted-foreground">
          Draft a Data Analyst resume. Your progress is saved in this browser
          automatically.
        </p>
      </div>
      <ResumeBuilder />
    </main>
  );
}
