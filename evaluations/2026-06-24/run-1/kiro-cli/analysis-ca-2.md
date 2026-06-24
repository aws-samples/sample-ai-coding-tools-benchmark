# Analysis: Rejected Order — Gold Customer, 13× prod_3 (27-inch Monitor)

## Scenario

- **Request:** `POST /api/v1/orders`
- **Customer:** a gold-tier customer (e.g. `cust_1`, Jane Doe, `tier: 'gold'`)
- **Line item:** `{ productId: 'prod_3', quantity: 13 }`
- **Product `prod_3`:** SKU `MON-027`, "27-inch Monitor", `priceCents: 31900`, `stock: 12`, `active: true`

## Which module and check rejects it

The rejection happens in the **order service**, not in the controller, pricing engine, or middleware.

- **File:** `src/services/orderService.ts`
- **Method:** `OrderService.createOrder(...)`
- **Phase:** the *first pass* over the line items — the validate-and-resolve loop that runs **before** any stock is mutated.

The relevant check:

```ts
const alreadyRequested = requestedByProduct.get(product.id) ?? 0; // 0
const totalRequested = alreadyRequested + line.quantity;          // 0 + 13 = 13
if (totalRequested > product.stock) {                             // 13 > 12  -> true
  throw new ConflictError(
    `Insufficient stock for ${product.sku}: requested ${totalRequested}, available ${product.stock}`,
  );
}
```

With `totalRequested = 13` and `product.stock = 12`, the condition `13 > 12` is `true`, so a `ConflictError` is thrown.

### Checks that pass first (and do not reject)

The request clears every earlier guard before reaching the stock check:

1. **Controller parsing** (`src/http/controllers.ts`, `OrderController.create` → `parseLineItems`): `customerId` is a string and `items` is an array whose entry has a string `productId` and numeric `quantity` — all valid.
2. **Customer exists** (`createOrder`): `customers.findById(customerId)` returns the gold customer — not null.
3. **Non-empty line array:** `lines.length === 0` is false — passes.
4. **Line shape / quantity:** `quantity` 13 is a positive integer — passes.
5. **Product exists:** `products.findById('prod_3')` returns the monitor — passes.
6. **Product active:** `prod_3.active === true` — passes (no `ConflictError` here).
7. **Stock check:** **FAILS here** — `13 > 12`.

Because the failure occurs in the first pass, no stock is decremented and no order is persisted — the operation is atomic / all-or-nothing as designed.

## How the error becomes an HTTP response

1. `OrderService.createOrder` throws `ConflictError` (defined in `src/errors.ts`).
2. `ConflictError` declares `statusCode = 409` and `code = 'CONFLICT'`.
3. The throw propagates out of the controller. The central error handler in `src/middleware.ts` (`errorHandler`) catches it.
4. `isAppError(err)` is true, so it responds with `appErr.statusCode` and serializes the standard error envelope, including the per-request `requestId` attached by the `requestId` middleware.

## HTTP status and error code

- **HTTP status:** `409 Conflict`
- **Error code:** `CONFLICT`

## Response body

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Insufficient stock for MON-027: requested 13, available 12",
    "details": null,
    "requestId": "req_<timestamp>_<random>"
  }
}
```

Notes:
- `message` is built from `product.sku` (`MON-027`), `totalRequested` (`13`), and `product.stock` (`12`).
- `ConflictError` is constructed without a `details` argument, so `details` is `undefined`. In JSON it is either omitted or serialized as `null` depending on the serializer; `JSON.stringify` (used by `res.json`) drops keys whose value is `undefined`, so in practice the `details` field is **absent** from the emitted body. It is shown above for completeness.
- `requestId` is a runtime-generated value of the form `req_<Date.now()>_<6 random base36 chars>`.

The customer's gold tier is irrelevant to this outcome: pricing (`src/services/pricing.ts`, including the 10% gold discount) is only reached in the *second pass*, which never executes because the request fails in the first pass.

## What would need to change for the order to succeed

The order fails purely because requested quantity (13) exceeds available stock (12). Any one of the following would let it through:

1. **Reduce the requested quantity to ≤ 12.** Ordering 12 or fewer monitors satisfies `totalRequested <= product.stock`. This is the simplest change and requires no code or data edits — just a different request payload.

2. **Increase `prod_3` stock to ≥ 13.** In `src/repositories.ts`, the seed for `prod_3` sets `stock: 12`. Raising it to 13+ (or replenishing stock via the restock path, e.g. cancelling an existing order that holds monitors) would satisfy the check. Note there is no public "add stock" endpoint; stock only increases via `OrderService.restock` on cancellation, or by changing the seed.

3. **Change the business rule (not recommended without intent).** Relaxing the check in `createOrder` — e.g. allowing backorders or removing the `totalRequested > product.stock` guard — would let the order succeed despite insufficient inventory. This changes domain semantics and would also need the second-pass stock decrement logic reconsidered (it would drive `stock` negative), so it is a design change rather than a fix.

The intended, in-spec resolution is **option 1 or 2**: order no more than the available stock, or increase available stock to cover the requested quantity.
