import type { Route } from "next";

export interface NavItem {
  label: string;
  href: Route;
}

export interface NavSection {
  label?: string;
  items: NavItem[];
}

export const NAV_SECTIONS: NavSection[] = [
  {
    items: [
      { label: "Dashboard", href: "/dashboard" },
      { label: "Roadmap", href: "/roadmap" },
    ],
  },
  {
    label: "Learn",
    items: [
      { label: "Excel", href: "/courses/excel" as Route },
      { label: "SQL", href: "/courses/sql" as Route },
      { label: "Power BI", href: "/courses/power-bi" as Route },
      { label: "Python", href: "/courses/python" as Route },
      { label: "Statistics", href: "/courses/statistics" as Route },
      { label: "Business Analytics", href: "/courses/business-analytics" as Route },
    ],
  },
  {
    label: "Practice",
    items: [
      { label: "Exercises", href: "/exercises" },
      { label: "Quizzes", href: "/quizzes" },
      { label: "SQL Playground", href: "/playground" },
    ],
  },
  {
    label: "Projects",
    items: [{ label: "Projects", href: "/projects" }],
  },
  {
    label: "Career",
    items: [
      { label: "Interview prep", href: "/career" },
      { label: "Resume", href: "/career/resume" },
    ],
  },
  {
    label: "Profile",
    items: [
      { label: "Achievements", href: "/profile/achievements" },
      { label: "Settings", href: "/profile/settings" },
    ],
  },
];
