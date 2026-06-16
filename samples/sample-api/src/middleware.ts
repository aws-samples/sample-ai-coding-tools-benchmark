/**
 * Express middleware: request id tagging, lightweight API-key auth, async
 * error forwarding, 404 fallback, and the central error handler.
 */

import { NextFunction, Request, Response } from 'express';
import { AppError, UnauthorizedError, isAppError } from './errors';

const API_KEY = process.env.API_KEY;
if (!API_KEY) {
  throw new Error('API_KEY environment variable is required');
}

/** Attach a per-request id so logs and error responses can be correlated. */
export function requestId(req: Request, _res: Response, next: NextFunction): void {
  (req as Request & { id: string }).id =
    `req_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
  next();
}

/** Very small structured request logger. */
export function requestLogger(req: Request, res: Response, next: NextFunction): void {
  const startedAt = Date.now();
  res.on('finish', () => {
    const id = (req as Request & { id?: string }).id ?? '-';
    const ms = Date.now() - startedAt;
    // eslint-disable-next-line no-console
    console.log(`[${id}] ${req.method} ${req.originalUrl} -> ${res.statusCode} (${ms}ms)`);
  });
  next();
}

/**
 * Require a valid `x-api-key` header on mutating requests. Read-only requests
 * (GET/HEAD) are public so the catalog can be browsed without a key.
 */
export function apiKeyAuth(req: Request, _res: Response, next: NextFunction): void {
  if (req.method === 'GET' || req.method === 'HEAD') {
    return next();
  }
  const provided = req.header('x-api-key');
  if (provided !== API_KEY) {
    return next(new UnauthorizedError('A valid x-api-key header is required'));
  }
  next();
}

/**
 * Wrap an async route handler so rejected promises are routed to Express's
 * error pipeline instead of crashing the process.
 */
export function asyncHandler(
  fn: (req: Request, res: Response, next: NextFunction) => Promise<unknown> | unknown,
) {
  return (req: Request, res: Response, next: NextFunction): void => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}

/** Terminal 404 for unmatched routes. */
export function notFound(_req: Request, res: Response): void {
  res.status(404).json({
    error: { code: 'NOT_FOUND', message: 'Route not found' },
  });
}

/**
 * Central error handler. Translates AppError instances into their declared
 * status + code, and treats anything else as an opaque 500.
 */
export function errorHandler(
  err: unknown,
  req: Request,
  res: Response,
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  _next: NextFunction,
): void {
  const id = (req as Request & { id?: string }).id;

  if (isAppError(err)) {
    const appErr = err as AppError;
    res.status(appErr.statusCode).json({
      error: {
        code: appErr.code,
        message: appErr.message,
        details: appErr.details,
        requestId: id,
      },
    });
    return;
  }

  // eslint-disable-next-line no-console
  console.error(`[${id ?? '-'}] Unhandled error:`, err);
  res.status(500).json({
    error: {
      code: 'INTERNAL_ERROR',
      message: 'An unexpected error occurred',
      requestId: id,
    },
  });
}
