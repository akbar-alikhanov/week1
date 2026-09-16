export interface LessonContent {
  objectives: string[];
  /** Raw MDX body (Theory / Example / Key points / Common mistakes sections). */
  markdown: string;
}

/**
 * Port for reading lesson theory content. The implementation lives in
 * infrastructure (filesystem today; could be a CMS later) - use cases only
 * depend on this interface, never on `fs` or `next-mdx-remote` directly.
 */
export interface LessonContentReader {
  read(contentPath: string): Promise<LessonContent>;
}
