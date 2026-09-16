import type { CourseSeed } from "@/../prisma/content-source/types";
import { module01 } from "@/../prisma/content-source/sql/module-01";
import { module02 } from "@/../prisma/content-source/sql/module-02";
import { module03 } from "@/../prisma/content-source/sql/module-03";
import { module04 } from "@/../prisma/content-source/sql/module-04";
import { module05 } from "@/../prisma/content-source/sql/module-05";
import { module06 } from "@/../prisma/content-source/sql/module-06";

export const sqlCourse: CourseSeed = {
  slug: "sql",
  track: "SQL",
  title: "SQL",
  description:
    "От SELECT и WHERE до JOIN, подзапросов и оконных функций — на реальном датасете интернет-магазина, с песочницей для практики.",
  modules: [module01, module02, module03, module04, module05, module06],
};
