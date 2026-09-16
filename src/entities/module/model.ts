import { ValidationError } from "@/shared/errors/app-error";

export interface ModuleProps {
  id: string;
  courseId: string;
  slug: string;
  title: string;
  description: string;
  order: number;
}

export class CourseModule {
  private constructor(private props: ModuleProps) {}

  static create(props: ModuleProps): CourseModule {
    if (!props.title.trim()) {
      throw new ValidationError("Module title is required.");
    }
    return new CourseModule(props);
  }

  get id() {
    return this.props.id;
  }
  get courseId() {
    return this.props.courseId;
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

  toProps(): ModuleProps {
    return { ...this.props };
  }
}
