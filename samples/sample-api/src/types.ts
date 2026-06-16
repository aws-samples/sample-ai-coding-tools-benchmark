/**
 * Shared domain types for the order-management API.
 *
 * The domain has three core entities — Product, Customer, and Order — plus a
 * few value types (money, pagination). Orders move through a small state
 * machine and embed a snapshot of line items so that historical orders are
 * not retroactively changed when product prices move.
 */

/** Money is stored in integer cents to avoid floating point rounding errors. */
export type Cents = number;

/** Customer loyalty tiers drive automatic discounting in the pricing engine. */
export type CustomerTier = 'standard' | 'silver' | 'gold';

export interface Customer {
  id: string;
  name: string;
  email: string;
  tier: CustomerTier;
  createdAt: string;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  /** Unit price in cents. */
  priceCents: Cents;
  /** Units currently available to sell. */
  stock: number;
  active: boolean;
  createdAt: string;
}

/**
 * A line item captures a snapshot of the product at the time the order was
 * placed. unitPriceCents is copied from the product so later price changes do
 * not alter past orders.
 */
export interface OrderItem {
  productId: string;
  sku: string;
  name: string;
  quantity: number;
  unitPriceCents: Cents;
  /** quantity * unitPriceCents */
  lineTotalCents: Cents;
}

/**
 * The order lifecycle. Allowed transitions are enforced in OrderService:
 *
 *   pending ─▶ paid ─▶ shipped ─▶ delivered
 *      │        │
 *      └────────┴─▶ cancelled
 *
 * delivered and cancelled are terminal states.
 */
export type OrderStatus =
  | 'pending'
  | 'paid'
  | 'shipped'
  | 'delivered'
  | 'cancelled';

export interface OrderTotals {
  subtotalCents: Cents;
  discountCents: Cents;
  taxCents: Cents;
  totalCents: Cents;
}

export interface Order {
  id: string;
  customerId: string;
  status: OrderStatus;
  items: OrderItem[];
  totals: OrderTotals;
  /** Discount rate applied at checkout, as a fraction (e.g. 0.1 == 10%). */
  appliedDiscountRate: number;
  createdAt: string;
  updatedAt: string;
}

/** A single line requested when creating an order. */
export interface OrderLineInput {
  productId: string;
  quantity: number;
}

/** Generic, repository-agnostic pagination envelope. */
export interface Page<T> {
  data: T[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface PaginationParams {
  page: number;
  pageSize: number;
}
