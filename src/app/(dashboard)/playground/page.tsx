import type { Metadata } from "next";

import { ComingSoon } from "@/shared/components/coming-soon";

export const metadata: Metadata = {
  title: "SQL Playground",
  robots: { index: false, follow: false },
};

export default function PlaygroundPage() {
  return (
    <ComingSoon
      title="SQL Playground"
      description="A free-form SQL editor against the sandbox dataset is coming in the next update. In the meantime, try the SQL exercises inside any SQL lesson."
    />
  );
}
