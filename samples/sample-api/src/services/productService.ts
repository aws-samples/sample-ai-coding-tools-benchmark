/**
 * Product service.
 *
 * Read-side logic for the catalog: filtering by active status and a free-text
 * query, plus reusable pagination. Demonstrates a second service collaborating
 * with the same repository layer as OrderService.
 */

import { ProductRepository } from '../repositories';
import { Page, PaginationParams, Product } from '../types';

export interface ProductQuery extends PaginationParams {
  /** When true, only products with active === true are returned. */
  activeOnly: boolean;
  /** Case-insensitive substring match against name and sku. */
  search?: string;
}

export class ProductService {
  constructor(private readonly products: ProductRepository) {}

  getById(id: string): Product | undefined {
    return this.products.findById(id);
  }

  /** Filter, sort by name, then paginate the catalog. */
  list(query: ProductQuery): Page<Product> {
    let results = this.products.findAll();

    if (query.activeOnly) {
      results = results.filter((p) => p.active);
    }

    if (query.search) {
      const needle = query.search.toLowerCase();
      results = results.filter(
        (p) =>
          p.name.toLowerCase().includes(needle) ||
          p.sku.toLowerCase().includes(needle),
      );
    }

    results.sort((a, b) => a.name.localeCompare(b.name));
    return paginate(results, query);
  }
}

/** Generic, zero-based-safe pagination over an in-memory array. */
export function paginate<T>(items: T[], params: PaginationParams): Page<T> {
  const total = items.length;
  const totalPages = total === 0 ? 0 : Math.ceil(total / params.pageSize);
  const start = (params.page - 1) * params.pageSize;
  const data = items.slice(start, start + params.pageSize);

  return {
    data,
    page: params.page,
    pageSize: params.pageSize,
    total,
    totalPages,
  };
}
