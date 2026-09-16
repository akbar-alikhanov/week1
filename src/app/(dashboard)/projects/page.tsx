import type { Metadata } from "next";

import { ComingSoon } from "@/shared/components/coming-soon";

export const metadata: Metadata = {
  title: "Projects",
  robots: { index: false, follow: false },
};

export default function ProjectsPage() {
  return (
    <ComingSoon
      title="Projects"
      description="Portfolio projects (Sales Analysis, E-commerce Analytics, and more) are coming in the next update."
    />
  );
}
