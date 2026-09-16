import { isAppError } from "@/shared/errors/app-error";

/**
 * Uniform result shape returned by every Server Action, so components never
 * need ad-hoc try/catch to display errors - they check `result.success`.
 */
export type ActionResult<T> =
  | { success: true; data: T }
  | { success: false; error: string; fieldErrors?: Record<string, string[]> };

export function actionSuccess<T>(data: T): ActionResult<T> {
  return { success: true, data };
}

export function actionFailure<T>(error: unknown): ActionResult<T> {
  if (isAppError(error)) {
    const fieldErrors = "fieldErrors" in error ? error.fieldErrors : undefined;
    return {
      success: false,
      error: error.message,
      fieldErrors:
        fieldErrors && typeof fieldErrors === "object"
          ? (fieldErrors as Record<string, string[]>)
          : undefined,
    };
  }

  if (error instanceof Error) {
    // Do not leak internal error messages/stack traces to the client.
    console.error(error);
    return { success: false, error: "Something went wrong. Please try again." };
  }

  console.error(error);
  return { success: false, error: "Something went wrong. Please try again." };
}

/**
 * Wraps a Server Action body so a thrown `AppError` becomes a typed
 * `ActionResult` instead of an unhandled exception / opaque 500.
 */
export async function runAction<T>(fn: () => Promise<T>): Promise<ActionResult<T>> {
  try {
    return actionSuccess(await fn());
  } catch (error) {
    return actionFailure<T>(error);
  }
}
