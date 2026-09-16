import type { CourseSeed, ModuleSeed } from "@/../prisma/content-source/types";

function stubModule(slug: string, title: string, topics: string[]): ModuleSeed {
  return {
    slug,
    title,
    description: topics.join(", ") + ".",
    lessons: [],
  };
}

export const powerBiCourse: CourseSeed = {
  slug: "power-bi",
  track: "POWER_BI",
  title: "Power BI",
  description:
    "Модель данных, DAX и дашборды. Полный курс появится в ближайших обновлениях.",
  modules: [
    stubModule("module-01-getting-started", "Getting Started", [
      "Интерфейс Power BI",
      "Импорт данных",
      "Power Query",
      "Очистка данных",
    ]),
    stubModule("module-02-data-modeling", "Data Modeling", [
      "Relationships",
      "Data Model",
      "Star Schema",
    ]),
    stubModule("module-03-dax", "DAX", [
      "Measures",
      "DAX",
      "CALCULATE",
      "FILTER",
      "DIVIDE",
      "Time Intelligence",
    ]),
    stubModule("module-04-reporting", "Reporting", [
      "KPI",
      "Dashboard Design",
      "Data Storytelling",
    ]),
  ],
};

export const pythonCourse: CourseSeed = {
  slug: "python",
  track: "PYTHON",
  title: "Python for Data Analytics",
  description:
    "Python, NumPy, Pandas и визуализация для анализа данных. Полный курс появится в ближайших обновлениях.",
  modules: [
    stubModule("module-01-python-basics", "Python Basics", [
      "variables",
      "data types",
      "lists",
      "dictionaries",
      "conditions",
      "loops",
      "functions",
    ]),
    stubModule("module-02-numpy", "NumPy", ["arrays", "operations", "statistics"]),
    stubModule("module-03-pandas", "Pandas", [
      "DataFrame",
      "read_csv",
      "read_excel",
      "head",
      "info",
      "describe",
      "loc",
      "iloc",
      "groupby",
      "merge",
      "pivot_table",
    ]),
    stubModule("module-04-data-cleaning", "Data Cleaning", [
      "missing values",
      "duplicates",
      "data types",
      "outliers",
      "transformations",
    ]),
    stubModule("module-05-visualization", "Visualization", ["Matplotlib", "Seaborn"]),
  ],
};

export const statisticsCourse: CourseSeed = {
  slug: "statistics",
  track: "STATISTICS",
  title: "Statistics",
  description:
    "Описательная и статистическая аналитика для принятия решений. Полный курс появится в ближайших обновлениях.",
  modules: [
    stubModule("module-01-descriptive-statistics", "Descriptive Statistics", [
      "Mean",
      "Median",
      "Mode",
      "Range",
      "Percentiles",
      "Variance",
      "Standard deviation",
      "Outliers",
    ]),
    stubModule("module-02-distributions-probability", "Distributions & Probability", [
      "Distributions",
      "Probability",
      "Correlation",
      "Correlation vs causation",
      "Sampling",
    ]),
    stubModule("module-03-inferential-statistics", "Inferential Statistics", [
      "Confidence intervals",
      "Hypothesis testing",
      "p-value",
      "A/B testing",
    ]),
  ],
};

export const businessAnalyticsCourse: CourseSeed = {
  slug: "business-analytics",
  track: "BUSINESS_ANALYTICS",
  title: "Business Analytics",
  description:
    "От постановки бизнес-задачи до презентации рекомендаций. Полный курс появится в ближайших обновлениях.",
  modules: [
    stubModule("module-01-foundations", "Foundations", [
      "постановка бизнес-задачи",
      "KPI",
      "метрики",
      "segmentation",
    ]),
    stubModule("module-02-domain-analytics", "Domain Analytics", [
      "sales analytics",
      "customer analytics",
      "inventory analytics",
      "OOS",
      "revenue",
      "retention",
      "churn",
      "conversion",
    ]),
    stubModule("module-03-insights-and-action", "Insights & Action", [
      "root cause analysis",
      "A/B testing",
      "presentation of insights",
      "business recommendations",
    ]),
  ],
};

export const stubCourses: CourseSeed[] = [
  powerBiCourse,
  pythonCourse,
  statisticsCourse,
  businessAnalyticsCourse,
];
