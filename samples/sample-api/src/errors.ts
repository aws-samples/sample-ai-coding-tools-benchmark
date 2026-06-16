/**
 * Domain error hierarchy.
 *
 * Every error carries an HTTP status code and a stable string `code` so the
 * central error-handling middleware can serialize a consistent JSON shape
 * without leaking stack traces to clients.
 */

export abstract class AppError extends Error {
  abstract readonly statusCode: number;
  abstract readonly code: string;
  /** Optional machine-readable details (e.g. which fields failed validation). */
  readonly details?: unknown;

  constructor(message: string, details?: unknown) {
    super(message);
    this.name = new.target.name;
    this.details = details;
    // Restore prototype chain for instanceof checks after transpilation.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** 400 — the request was malformed or failed validation. */
export class ValidationError extends AppError {
  readonly statusCode = 400;
  readonly code = 'VALIDATION_ERROR';
}

/** 401 — missing or invalid credentials. */
export class UnauthorizedError extends AppError {
  readonly statusCode = 401;
  readonly code = 'UNAUTHORIZED';
}

/** 404 — the requested resource does not exist. */
export class NotFoundError extends AppError {
  readonly statusCode = 404;
  readonly code = 'NOT_FOUND';
}

/**
 * 409 — the request conflicts with the current state of a resource, e.g. an
 * illegal order status transition or insufficient stock.
 */
export class ConflictError extends AppError {
  readonly statusCode = 409;
  readonly code = 'CONFLICT';
}

/** Narrowing helper used by the error-handling middleware. */
export function isAppError(err: unknown): err is AppError {
  return err instanceof AppError;
}
