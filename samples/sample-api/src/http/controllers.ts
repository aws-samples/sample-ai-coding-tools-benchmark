/**
 * Controllers translate HTTP requests into service calls and service results
 * into HTTP responses. They contain no business logic — only parsing,
 * delegation, and status-code selection.
 */

import { Request, Response } from 'express';
import { ValidationError } from '../errors';
import { OrderService } from '../services/orderService';
import { ProductService } from '../services/productService';
import { OrderLineInput, OrderStatus } from '../types';
import { parseBoolean, parsePagination, requireString } from './parse';

const VALID_STATUSES: OrderStatus[] = [
  'pending',
  'paid',
  'shipped',
  'delivered',
  'cancelled',
];

export class ProductController {
  constructor(private readonly products: ProductService) {}

  list = (req: Request, res: Response): void => {
    const pagination = parsePagination(req.query as Record<string, unknown>);
    const activeOnly = parseBoolean(req.query.activeOnly, false);
    const search = typeof req.query.search === 'string' ? req.query.search : undefined;

    const page = this.products.list({ ...pagination, activeOnly, search });
    res.json(page);
  };

  getById = (req: Request, res: Response): void => {
    const product = this.products.getById(req.params.id);
    if (!product) {
      res.status(404).json({
        error: { code: 'NOT_FOUND', message: `Product ${req.params.id} not found` },
      });
      return;
    }
    res.json(product);
  };
}

export class OrderController {
  constructor(private readonly orders: OrderService) {}

  create = (req: Request, res: Response): void => {
    const body = (req.body ?? {}) as { customerId?: unknown; items?: unknown };
    const customerId = requireString(body.customerId, 'customerId');
    const items = this.parseLineItems(body.items);

    const order = this.orders.createOrder(customerId, items);
    res.status(201).json(order);
  };

  getById = (req: Request, res: Response): void => {
    res.json(this.orders.getOrder(req.params.id));
  };

  updateStatus = (req: Request, res: Response): void => {
    const body = (req.body ?? {}) as { status?: unknown };
    const status = requireString(body.status, 'status') as OrderStatus;
    if (!VALID_STATUSES.includes(status)) {
      throw new ValidationError(`Unknown order status '${status}'`, {
        allowed: VALID_STATUSES,
      });
    }
    res.json(this.orders.updateStatus(req.params.id, status));
  };

  listByCustomer = (req: Request, res: Response): void => {
    res.json(this.orders.listByCustomer(req.params.customerId));
  };

  /** Validate and normalize the raw `items` array from the request body. */
  private parseLineItems(raw: unknown): OrderLineInput[] {
    if (!Array.isArray(raw)) {
      throw new ValidationError("Field 'items' must be an array of line items");
    }
    return raw.map((entry, index) => {
      if (typeof entry !== 'object' || entry === null) {
        throw new ValidationError(`items[${index}] must be an object`);
      }
      const { productId, quantity } = entry as Record<string, unknown>;
      if (typeof productId !== 'string') {
        throw new ValidationError(`items[${index}].productId must be a string`);
      }
      if (typeof quantity !== 'number') {
        throw new ValidationError(`items[${index}].quantity must be a number`);
      }
      return { productId, quantity };
    });
  }
}
