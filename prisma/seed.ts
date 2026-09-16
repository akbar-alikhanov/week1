import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { PrismaPg } from "@prisma/adapter-pg";
import bcrypt from "bcryptjs";

import { Prisma, PrismaClient } from "@/generated/prisma/client";
import type { AchievementCode } from "@/generated/prisma/enums";
import { excelCourse } from "@/../prisma/content-source/excel";
import { sqlCourse } from "@/../prisma/content-source/sql";
import { stubCourses } from "@/../prisma/content-source/stub-courses";
import { projects } from "@/../prisma/content-source/projects";
import type {
  CourseSeed,
  LessonSeed,
  ProjectSeed,
} from "@/../prisma/content-source/types";

const CONTENT_ROOT = path.join(process.cwd(), "content");

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL });
const prisma = new PrismaClient({ adapter });

async function writeLessonContent(
  courseSlug: string,
  moduleSlug: string,
  lesson: LessonSeed,
) {
  const relativeDir = path.join(courseSlug, moduleSlug);
  const relativePath = path.join(relativeDir, `${lesson.slug}.mdx`);
  const absoluteDir = path.join(CONTENT_ROOT, relativeDir);
  await mkdir(absoluteDir, { recursive: true });

  const frontmatter = [
    "---",
    `title: ${JSON.stringify(lesson.title)}`,
    `objectives:`,
    ...lesson.objectives.map((objective) => `  - ${JSON.stringify(objective)}`),
    "---",
  ].join("\n");

  const body = [
    "## Theory",
    "",
    lesson.theory.trim(),
    "",
    "## Example",
    "",
    lesson.example.trim(),
    "",
    "## Common mistakes",
    "",
    ...lesson.commonMistakes.map((mistake) => `- ${mistake}`),
    "",
  ].join("\n");

  await writeFile(
    path.join(CONTENT_ROOT, relativePath),
    `${frontmatter}\n\n${body}\n`,
    "utf8",
  );

  // Use forward slashes in the stored path regardless of OS.
  return relativePath.split(path.sep).join("/");
}

async function seedCourse(course: CourseSeed) {
  const dbCourse = await prisma.course.upsert({
    where: { slug: course.slug },
    create: {
      slug: course.slug,
      track: course.track,
      title: course.title,
      description: course.description,
      order: courseOrder(course.track),
    },
    update: {
      title: course.title,
      description: course.description,
      order: courseOrder(course.track),
    },
  });

  for (const [moduleIndex, moduleSeed] of course.modules.entries()) {
    const dbModule = await prisma.module.upsert({
      where: { courseId_slug: { courseId: dbCourse.id, slug: moduleSeed.slug } },
      create: {
        courseId: dbCourse.id,
        slug: moduleSeed.slug,
        title: moduleSeed.title,
        description: moduleSeed.description,
        order: moduleIndex,
      },
      update: {
        title: moduleSeed.title,
        description: moduleSeed.description,
        order: moduleIndex,
      },
    });

    for (const [lessonIndex, lessonSeed] of moduleSeed.lessons.entries()) {
      const contentPath = await writeLessonContent(
        course.slug,
        moduleSeed.slug,
        lessonSeed,
      );

      const dbLesson = await prisma.lesson.upsert({
        where: { moduleId_slug: { moduleId: dbModule.id, slug: lessonSeed.slug } },
        create: {
          moduleId: dbModule.id,
          slug: lessonSeed.slug,
          title: lessonSeed.title,
          description: lessonSeed.description,
          order: lessonIndex,
          contentPath,
          xpReward: lessonSeed.xpReward ?? 10,
        },
        update: {
          title: lessonSeed.title,
          description: lessonSeed.description,
          order: lessonIndex,
          contentPath,
          xpReward: lessonSeed.xpReward ?? 10,
        },
      });

      const exercises = [lessonSeed.exercise, ...(lessonSeed.additionalExercises ?? [])];
      for (const [exerciseIndex, exerciseSeed] of exercises.entries()) {
        const existing = await prisma.exercise.findFirst({
          where: { lessonId: dbLesson.id, order: exerciseIndex },
        });
        const data = {
          lessonId: dbLesson.id,
          type: exerciseSeed.type,
          title: exerciseSeed.title,
          description: exerciseSeed.description,
          difficulty: exerciseSeed.difficulty,
          points: exerciseSeed.points,
          order: exerciseIndex,
          data: exerciseSeed.data as unknown as Prisma.InputJsonValue,
          correctAnswer: exerciseSeed.correctAnswer as unknown as Prisma.InputJsonValue,
          explanation: exerciseSeed.explanation,
        };
        if (existing) {
          await prisma.exercise.update({ where: { id: existing.id }, data });
        } else {
          await prisma.exercise.create({ data });
        }
      }

      if (lessonSeed.quiz.length > 0) {
        const dbQuiz = await prisma.quiz.upsert({
          where: { lessonId: dbLesson.id },
          create: {
            lessonId: dbLesson.id,
            title: `${lessonSeed.title} — Quiz`,
            passingScore: 70,
          },
          update: { title: `${lessonSeed.title} — Quiz` },
        });

        await prisma.quizQuestion.deleteMany({ where: { quizId: dbQuiz.id } });
        await prisma.quizQuestion.createMany({
          data: lessonSeed.quiz.map((question, order) => ({
            quizId: dbQuiz.id,
            question: question.question,
            options: question.options,
            correctAnswer: question.correctIndex,
            explanation: question.explanation,
            order,
          })),
        });
      }
    }
  }
}

async function seedProject(project: ProjectSeed, order: number) {
  const course = await prisma.course.findUnique({ where: { slug: project.courseSlug } });
  if (!course) {
    throw new Error(
      `Cannot seed project "${project.slug}": course "${project.courseSlug}" not found.`,
    );
  }

  const data = {
    courseId: course.id,
    title: project.title,
    businessContext: project.businessContext,
    datasetDescription: project.datasetDescription,
    goal: project.goal,
    deliverables: project.deliverables,
    evaluationCriteria: project.evaluationCriteria,
    hints: project.hints,
    order,
    xpReward: project.xpReward ?? 200,
  };

  const dbProject = await prisma.project.upsert({
    where: { slug: project.slug },
    create: { slug: project.slug, ...data },
    update: data,
  });

  await prisma.projectTask.deleteMany({ where: { projectId: dbProject.id } });
  await prisma.projectTask.createMany({
    data: project.tasks.map((task, taskOrder) => ({
      projectId: dbProject.id,
      title: task.title,
      description: task.description,
      order: taskOrder,
    })),
  });
}

function courseOrder(track: string): number {
  const order = [
    "EXCEL",
    "SQL",
    "POWER_BI",
    "PYTHON",
    "STATISTICS",
    "BUSINESS_ANALYTICS",
  ];
  return order.indexOf(track);
}

const ACHIEVEMENTS: {
  code: AchievementCode;
  title: string;
  description: string;
  icon: string;
}[] = [
  {
    code: "FIRST_LESSON",
    title: "First Lesson",
    description: "Complete your first lesson.",
    icon: "GraduationCap",
  },
  {
    code: "FIRST_EXERCISE",
    title: "First Exercise",
    description: "Solve your first exercise.",
    icon: "PencilLine",
  },
  {
    code: "EXCEL_BEGINNER",
    title: "Excel Beginner",
    description: "Complete the Excel course.",
    icon: "Table",
  },
  {
    code: "SQL_BEGINNER",
    title: "SQL Beginner",
    description: "Complete the SQL course.",
    icon: "Database",
  },
  {
    code: "TEN_EXERCISES",
    title: "10 Exercises",
    description: "Complete 10 exercises.",
    icon: "ListChecks",
  },
  {
    code: "FIFTY_EXERCISES",
    title: "50 Exercises",
    description: "Complete 50 exercises.",
    icon: "Trophy",
  },
  {
    code: "FIRST_PROJECT",
    title: "First Project",
    description: "Submit your first project.",
    icon: "Rocket",
  },
  {
    code: "SQL_MASTERY",
    title: "SQL Mastery",
    description: "Pass 5 SQL quizzes.",
    icon: "Award",
  },
  {
    code: "SEVEN_DAY_STREAK",
    title: "7 Day Streak",
    description: "Learn 7 days in a row.",
    icon: "Flame",
  },
];

async function seedAchievements() {
  for (const achievement of ACHIEVEMENTS) {
    await prisma.achievement.upsert({
      where: { code: achievement.code },
      create: achievement,
      update: achievement,
    });
  }
}

const DEMO_PASSWORD = "password123";

async function seedDemoUser() {
  const passwordHash = await bcrypt.hash(DEMO_PASSWORD, 12);
  await prisma.user.upsert({
    where: { email: "demo@dala.dev" },
    create: { name: "Demo User", email: "demo@dala.dev", passwordHash },
    update: {},
  });
}

async function main() {
  console.log("Seeding achievements...");
  await seedAchievements();

  console.log("Seeding demo user...");
  await seedDemoUser();

  console.log("Seeding Excel course...");
  await seedCourse(excelCourse);

  console.log("Seeding SQL course...");
  await seedCourse(sqlCourse);

  console.log("Seeding remaining course structures...");
  for (const course of stubCourses) {
    await seedCourse(course);
  }

  console.log("Seeding projects...");
  for (const [index, project] of projects.entries()) {
    await seedProject(project, index);
  }

  console.log("Seed complete.");
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
