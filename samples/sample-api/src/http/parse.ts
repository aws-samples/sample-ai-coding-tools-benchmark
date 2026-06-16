/**
 * Tiny request-parsing helpers that convert raw query/body values into typed,
 * validated shapes, throwing ValidationError on bad input.
 */

import { ValidationError } from '../errors';
import { PaginationParams } from '../types';

const DEFAULT_PAGE = 1;
const DEFAULT_PAGE_SIZE = 20;
const MAX_PAGE_SIZE = 100;

/** Parse and clamp `page`/`pageSize` query params. */
export function parsePagination(query: Record<string, unknown>): PaginationParams {
  const page = parsePositiveInt(query.page, DEFAULT_PAGE, 'page');
  const pageSizeRaw = parsePositiveInt(query.pageSize, DEFAULT_PAGE_SIZE, 'pageSize');
  return { page, pageSize: Math.min(pageSizeRaw, MAX_PAGE_SIZE) };
}

/** Parse an optional positive integer, falling back to a default when absent. */
export function parsePositiveInt(
  value: unknown,
  fallback: number,
  field: string,
): number {
  if (value === undefined || value === null || value === '') {
    return fallback;
  }
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new ValidationError(`Query param '${field}' must be a positive integer`);
  }
  return parsed;
}

/** Interpret common truthy strings as booleans. */
export function parseBoolean(value: unknown, fallback: boolean): boolean {
  if (value === undefined || value === null || value === '') {
    return fallback;
  }
  return value === 'true' || value === '1';
}

/** Assert that a value is a non-empty string. */
export function requireString(value: unknown, field: string): string {
  if (typeof value !== 'string' || value.trim() === '') {
    throw new ValidationError(`Field '${field}' is required and must be a non-empty string`);
  }
  return value;
}
