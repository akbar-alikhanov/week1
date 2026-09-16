import type { CourseSeed } from "@/../prisma/content-source/types";
import { module01 } from "@/../prisma/content-source/excel/module-01";
import { module02 } from "@/../prisma/content-source/excel/module-02";
import { module03 } from "@/../prisma/content-source/excel/module-03";
import { module04 } from "@/../prisma/content-source/excel/module-04";
import { module05 } from "@/../prisma/content-source/excel/module-05";
import { module06 } from "@/../prisma/content-source/excel/module-06";
import { module07 } from "@/../prisma/content-source/excel/module-07";
import { module08 } from "@/../prisma/content-source/excel/module-08";

export const excelCourse: CourseSeed = {
  slug: "excel",
  track: "EXCEL",
  title: "Excel",
  description:
    "От интерфейса и базовых формул до сводных таблиц и Power Query — научись анализировать данные в Excel.",
  modules: [
    module01,
    module02,
    module03,
    module04,
    module05,
    module06,
    module07,
    module08,
  ],
};
