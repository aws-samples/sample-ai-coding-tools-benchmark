/**
 * Pricing engine.
 *
 * Pure functions, no I/O. Given the line items and the customer's tier, it
 * computes the subtotal, a tier-based discount, tax on the discounted amount,
 * and the grand total. Keeping this pure makes it trivial to unit test and to
 * reason about during code-comprehension exercises.
 */

import { Cents, CustomerTier, OrderItem, OrderTotals } from '../types';

/** Flat tax applied to the post-discount subtotal. */
export const TAX_RATE = 0.08;

/** Discount rate granted automatically based on loyalty tier. */
const TIER_DISCOUNT: Record<CustomerTier, number> = {
  standard: 0,
  silver: 0.05,
  gold: 0.1,
};

/**
 * Orders above this subtotal earn an extra volume discount, stacked on top of
 * the tier discount (capped — see MAX_DISCOUNT_RATE).
 */
const VOLUME_DISCOUNT_THRESHOLD_CENTS: Cents = 50000;
const VOLUME_DISCOUNT_RATE = 0.05;

/** Discounts never exceed this combined rate, regardless of tier + volume. */
export const MAX_DISCOUNT_RATE = 0.2;

export function discountRateFor(tier: CustomerTier, subtotalCents: Cents): number {
  let rate = TIER_DISCOUNT[tier];
  if (subtotalCents >= VOLUME_DISCOUNT_THRESHOLD_CENTS) {
    rate += VOLUME_DISCOUNT_RATE;
  }
  return Math.min(rate, MAX_DISCOUNT_RATE);
}

/** Round to the nearest cent. Centralized so rounding is consistent. */
function roundCents(value: number): Cents {
  return Math.round(value);
}

export interface PriceQuote extends OrderTotals {
  appliedDiscountRate: number;
}

/**
 * Compute totals for a set of line items and a customer tier.
 *
 * Order of operations matters: discount is applied to the subtotal first, then
 * tax is computed on the discounted amount.
 */
export function quote(items: OrderItem[], tier: CustomerTier): PriceQuote {
  const subtotalCents = items.reduce((sum, item) => sum + item.lineTotalCents, 0);
  const appliedDiscountRate = discountRateFor(tier, subtotalCents);
  const discountCents = roundCents(subtotalCents * appliedDiscountRate);
  const taxableCents = subtotalCents - discountCents;
  const taxCents = roundCents(taxableCents * TAX_RATE);
  const totalCents = taxableCents + taxCents;

  return {
    subtotalCents,
    discountCents,
    taxCents,
    totalCents,
    appliedDiscountRate,
  };
}
