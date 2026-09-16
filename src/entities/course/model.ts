import { ValidationError } from "@/shared/errors/app-error";

export const COURSE_TRACKS = [
  "EXCEL",
  "SQL",
  "POWER_BI",
  "PYTHON",
  "STATISTICS",
  "BUSINESS_ANALYTICS",
] as const;

export type CourseTrack = (typeof COURSE_TRACKS)[number];

export interface CourseProps {
  id: string;
  slug: string;
  track: CourseTrack;
  title: string;
  description: string;
  order: number;
}

export class Course {
  private constructor(private props: CourseProps) {}

  static create(props: CourseProps): Course {
    if (!props.slug.trim()) {
      throw new ValidationError("Course slug is required.");
    }
    if (!props.title.trim()) {
      throw new ValidationError("Course title is required.");
    }
    return new Course(props);
  }

  get id() {
    return this.props.id;
  }
  get slug() {
    return this.props.slug;
  }
  get track() {
    return this.props.track;
  }
  get title() {
    return this.props.title;
  }
  get description() {
    return this.props.description;
  }
  get order() {
    return this.props.order;
  }

  toProps(): CourseProps {
    return { ...this.props };
  }
}
