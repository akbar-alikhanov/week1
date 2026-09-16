import { readFile } from "node:fs/promises";
import path from "node:path";

import matter from "gray-matter";

import { NotFoundError } from "@/shared/errors/app-error";
import type {
  LessonContent,
  LessonContentReader,
} from "@/features/lessons/application/ports";

const CONTENT_ROOT = path.join(process.cwd(), "content");

export class FsLessonContentReader implements LessonContentReader {
  async read(contentPath: string): Promise<LessonContent> {
    const resolved = path.join(CONTENT_ROOT, contentPath);
    if (!resolved.startsWith(CONTENT_ROOT)) {
      throw new NotFoundError("Lesson content", contentPath);
    }

    let raw: string;
    try {
      raw = await readFile(resolved, "utf8");
    } catch {
      throw new NotFoundError("Lesson content", contentPath);
    }

    const { data, content } = matter(raw);
    const objectives = Array.isArray(data.objectives)
      ? (data.objectives as string[])
      : [];

    return { objectives, markdown: content };
  }
}
