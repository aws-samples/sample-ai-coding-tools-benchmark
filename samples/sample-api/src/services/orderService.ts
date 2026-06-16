/**
 * Order service — the core business logic of the API.
 *
 * Responsibilities:
 *  - Validate order line input against the product catalog.
 *  - Reserve stock atomically (all-or-nothing) when an order is created.
 *  - Build immutable line-item snapshots and price the order via the pricing
 *    engine.
 *  - Enforce the order status state machine and the side effects of each
 *    transition (e.g. restocking on cancellation).
 *
 * The service depends only on repository interfaces, so it is storage-agnostic.
 */

import { ConflictError, NotFoundError, ValidationError } from '../errors';
import {
  CustomerRepository,
  OrderRepository,
  ProductRepository,
  generateId,
} from '../repositories';
import {
  Order,
  OrderItem,
  OrderLineInput,
  OrderStatus,
  Product,
} from '../types';
import { quote } from './pricing';

/**
 * Allowed status transitions. A status maps to the set of states it may move
 * to next; terminal states map to an empty set.
 */
const ALLOWED_TRANSITIONS: Record<OrderStatus, OrderStatus[]> = {
  pending: ['paid', 'cancelled'],
  paid: ['shipped', 'cancelled'],
  shipped: ['delivered'],
  delivered: [],
  cancelled: [],
};

/** Transitions after which reserved stock should be returned to inventory. */
const RESTOCKING_STATUSES: OrderStatus[] = ['cancelled'];

export class OrderService {
  constructor(
    private readonly orders: OrderRepository,
    private readonly products: ProductRepository,
    private readonly customers: CustomerRepository,
  ) {}

  /**
   * Create an order for a customer from a list of {productId, quantity} lines.
   *
   * Validates the customer and every line, ensures stock is sufficient for all
   * lines before mutating anything, then decrements stock and persists the
   * priced order.
   */
  createOrder(customerId: string, lines: OrderLineInput[]): Order {
    const customer = this.customers.findById(customerId);
    if (!customer) {
      throw new NotFoundError(`Customer ${customerId} not found`);
    }
    if (!Array.isArray(lines) || lines.length === 0) {
      throw new ValidationError('An order must contain at least one line item');
    }

    // First pass: validate and resolve every line without mutating stock, so a
    // failure on a later line cannot leave earlier products partially reserved.
    const resolved: Array<{ product: Product; quantity: number }> = [];
    const requestedByProduct = new Map<string, number>();

    for (const line of lines) {
      if (!line || typeof line.productId !== 'string') {
        throw new ValidationError('Each line item requires a productId');
      }
      if (!Number.isInteger(line.quantity) || line.quantity <= 0) {
        throw new ValidationError(
          `Quantity for product ${line.productId} must be a positive integer`,
        );
      }

      const product = this.products.findById(line.productId);
      if (!product) {
        throw new NotFoundError(`Product ${line.productId} not found`);
      }
      if (!product.active) {
        throw new ConflictError(`Product ${product.sku} is not available for sale`);
      }

      const alreadyRequested = requestedByProduct.get(product.id) ?? 0;
      const totalRequested = alreadyRequested + line.quantity;
      if (totalRequested > product.stock) {
        throw new ConflictError(
          `Insufficient stock for ${product.sku}: requested ${totalRequested}, available ${product.stock}`,
        );
      }
      requestedByProduct.set(product.id, totalRequested);
      resolved.push({ product, quantity: line.quantity });
    }

    // Second pass: build snapshots and commit stock changes.
    const items: OrderItem[] = resolved.map(({ product, quantity }) => ({
      productId: product.id,
      sku: product.sku,
      name: product.name,
      quantity,
      unitPriceCents: product.priceCents,
      lineTotalCents: product.priceCents * quantity,
    }));

    for (const [productId, qty] of requestedByProduct) {
      const product = this.products.findById(productId)!;
      this.products.save({ ...product, stock: product.stock - qty });
    }

    const priced = quote(items, customer.tier);
    const now = new Date().toISOString();
    const order: Order = {
      id: generateId('order'),
      customerId,
      status: 'pending',
      items,
      totals: {
        subtotalCents: priced.subtotalCents,
        discountCents: priced.discountCents,
        taxCents: priced.taxCents,
        totalCents: priced.totalCents,
      },
      appliedDiscountRate: priced.appliedDiscountRate,
      createdAt: now,
      updatedAt: now,
    };

    return this.orders.save(order);
  }

  getOrder(orderId: string): Order {
    const order = this.orders.findById(orderId);
    if (!order) {
      throw new NotFoundError(`Order ${orderId} not found`);
    }
    return order;
  }

  listByCustomer(customerId: string): Order[] {
    if (!this.customers.findById(customerId)) {
      throw new NotFoundError(`Customer ${customerId} not found`);
    }
    return this.orders.findByCustomer(customerId);
  }

  /**
   * Move an order to a new status, enforcing the state machine. Cancelling a
   * non-terminal order returns its reserved stock to inventory.
   */
  updateStatus(orderId: string, next: OrderStatus): Order {
    const order = this.getOrder(orderId);
    const allowed = ALLOWED_TRANSITIONS[order.status];

    if (!allowed.includes(next)) {
      throw new ConflictError(
        `Cannot transition order ${orderId} from ${order.status} to ${next}`,
      );
    }

    if (RESTOCKING_STATUSES.includes(next)) {
      this.restock(order);
    }

    const updated: Order = {
      ...order,
      status: next,
      updatedAt: new Date().toISOString(),
    };
    return this.orders.save(updated);
  }

  /** Return every line item's quantity back to product stock. */
  private restock(order: Order): void {
    for (const item of order.items) {
      const product = this.products.findById(item.productId);
      if (product) {
        this.products.save({ ...product, stock: product.stock + item.quantity });
      }
    }
  }
}
