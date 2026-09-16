/**
 * Base class for all errors raised by the domain and application layers.
 * Presentation code (Server Actions, route handlers) catches `AppError` and
 * maps it to the appropriate HTTP status / form error instead of leaking
 * stack traces or falling back to ad-hoc try/catch in every component.
 */
export abstract class AppError extends Error {
  abstract readonly code: string;

  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class ValidationError extends AppError {
  readonly code = "VALIDATION_ERROR";

  constructor(
    message: string,
    readonly fieldErrors?: Record<string, string[]>,
  ) {
    super(message);
  }
}

export class NotFoundError extends AppError {
  readonly code = "NOT_FOUND";

  constructor(resource: string, identifier?: string) {
    super(
      identifier
        ? `${resource} "${identifier}" was not found.`
        : `${resource} was not found.`,
    );
  }
}

export class UnauthorizedError extends AppError {
  readonly code = "UNAUTHORIZED";

  constructor(message = "You must be signed in to do this.") {
    super(message);
  }
}

export class ForbiddenError extends AppError {
  readonly code = "FORBIDDEN";

  constructor(message = "You are not allowed to do this.") {
    super(message);
  }
}

export class ExerciseEvaluationError extends AppError {
  readonly code = "EXERCISE_EVALUATION_ERROR";

  constructor(message: string) {
    super(message);
  }
}

export class DomainError extends AppError {
  readonly code = "DOMAIN_ERROR";

  constructor(message: string) {
    super(message);
  }
}

export function isAppError(error: unknown): error is AppError {
  return error instanceof AppError;
}
