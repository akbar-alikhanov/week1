import { ValidationError } from "@/shared/errors/app-error";

export interface LessonProps {
  id: string;
  moduleId: string;
  slug: string;
  title: string;
  description: string;
  order: number;
  contentPath: string;
  xpReward: number;
}

export class Lesson {
  private constructor(private props: LessonProps) {}

  static create(props: LessonProps): Lesson {
    if (!props.title.trim()) {
      throw new ValidationError("Lesson title is required.");
    }
    if (!props.contentPath.trim()) {
      throw new ValidationError("Lesson content path is required.");
    }
    return new Lesson(props);
  }

  get id() {
    return this.props.id;
  }
  get moduleId() {
    return this.props.moduleId;
  }
  get slug() {
    return this.props.slug;
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
  get contentPath() {
    return this.props.contentPath;
  }
  get xpReward() {
    return this.props.xpReward;
  }

  toProps(): LessonProps {
    return { ...this.props };
  }
}
