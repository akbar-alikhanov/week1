import type { Metadata } from "next";

import { ComingSoon } from "@/shared/components/coming-soon";

export const metadata: Metadata = {
  title: "Career",
  robots: { index: false, follow: false },
};

export default function CareerPage() {
  return (
    <ComingSoon
      title="Career prep"
      description="Interview practice (SQL, Excel, business cases) is coming in the next update."
    />
  );
}
