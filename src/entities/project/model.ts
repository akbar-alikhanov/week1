import { ValidationError } from "@/shared/errors/app-error";

export interface ProjectTaskProps {
  id: string;
  title: string;
  description: string;
  order: number;
}

export class ProjectTask {
  private constructor(private props: ProjectTaskProps) {}

  static create(props: ProjectTaskProps): ProjectTask {
    return new ProjectTask(props);
  }

  get id() {
    return this.props.id;
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

  toProps(): ProjectTaskProps {
    return { ...this.props };
  }
}

export interface ProjectProps {
  id: string;
  courseId: string;
  slug: string;
  title: string;
  businessContext: string;
  datasetDescription: string;
  goal: string;
  deliverables: string[];
  evaluationCriteria: string[];
  hints: string[];
  order: number;
  xpReward: number;
  tasks: ProjectTask[];
}

export class Project {
  private constructor(private props: ProjectProps) {}

  static create(props: ProjectProps): Project {
    if (!props.title.trim()) {
      throw new ValidationError("Project title is required.");
    }
    return new Project(props);
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
  get businessContext() {
    return this.props.businessContext;
  }
  get datasetDescription() {
    return this.props.datasetDescription;
  }
  get goal() {
    return this.props.goal;
  }
  get deliverables() {
    return this.props.deliverables;
  }
  get evaluationCriteria() {
    return this.props.evaluationCriteria;
  }
  get hints() {
    return this.props.hints;
  }
  get order() {
    return this.props.order;
  }
  get xpReward() {
    return this.props.xpReward;
  }
  get tasks() {
    return this.props.tasks;
  }

  toProps(): ProjectProps {
    return { ...this.props };
  }
}
