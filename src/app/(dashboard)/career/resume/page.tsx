import type { Metadata } from "next";

import { ComingSoon } from "@/shared/components/coming-soon";

export const metadata: Metadata = {
  title: "Resume",
  robots: { index: false, follow: false },
};

export default function ResumePage() {
  return (
    <ComingSoon
      title="Resume builder"
      description="A guided resume builder for Data Analyst roles is coming in the next update."
    />
  );
}
