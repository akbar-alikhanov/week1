export const SUBMISSION_STATUSES = [
  "SUBMITTED",
  "REVIEWED",
  "ACCEPTED",
  "NEEDS_REVISION",
] as const;

export type SubmissionStatus = (typeof SUBMISSION_STATUSES)[number];

export interface ProjectSubmissionProps {
  id: string;
  userId: string;
  projectId: string;
  summary: string;
  deliverableUrl: string | null;
  status: SubmissionStatus;
  feedback: string | null;
  createdAt: Date;
}

export class ProjectSubmission {
  private constructor(private props: ProjectSubmissionProps) {}

  static create(props: ProjectSubmissionProps): ProjectSubmission {
    return new ProjectSubmission(props);
  }

  get id() {
    return this.props.id;
  }
  get userId() {
    return this.props.userId;
  }
  get projectId() {
    return this.props.projectId;
  }
  get summary() {
    return this.props.summary;
  }
  get deliverableUrl() {
    return this.props.deliverableUrl;
  }
  get status() {
    return this.props.status;
  }
  get feedback() {
    return this.props.feedback;
  }
  get createdAt() {
    return this.props.createdAt;
  }

  toProps(): ProjectSubmissionProps {
    return { ...this.props };
  }
}
