# Analysis: Rejected Order for Gold-Tier Customer (13× prod_3)

## Scenario

```
POST /api/v1/orders
content-type: application/json
x-api-key: YOUR_API_KEY

{
  "customerId": "cust_1",
  "items": [{ "productId": "prod_3", "quantity": 13 }]
}
```

Seed data places `cust_1` at the `gold` tier and `prod_3` (SKU `MON-027`,
"27-inch Monitor") with `stock: 12`, `active: true`.

## Where the request is rejected

The check that rejects the request lives in
`src/services/orderService.ts`, inside `OrderService.createOrder`,
in the first ("validate-only") pass over the line items:

```ts
const alreadyRequested = requestedByProduct.get(product.id) ?? 0;
const totalRequested = alreadyRequested + line.quantity;
if (totalRequested > product.stock) {
  throw new ConflictError(
    `Insufficient stock for ${product.sku}: requested ${totalRequested}, available ${product.stock}`,
  );
}
```

For this request `totalRequested` is `13` and `product.stock` is `12`, so
the predicate `13 > 12` fires and a `ConflictError` is thrown. Because
this happens in the validate-only pass, no stock is mutated and no order
is persisted — the all-or-nothing reservation invariant holds.

### Full path the request takes before it gets there

1. `src/app.ts` — `express.json()` parses the body, `requestId` and
   `requestLogger` tag/log the request.
2. `src/app.ts` — the `/api/v1` mount runs `apiKeyAuth` first. The method
   is `POST`, so the `x-api-key` header is required; `` matches
   the default `API_KEY`, so it passes.
3. `src/http/routes.ts` — `POST /orders` is wired to
   `asyncHandler(orders.create)`.
4. `src/http/controllers.ts` — `OrderController.create`:
   - `requireString(body.customerId, 'customerId')` accepts `"cust_1"`.
   - `parseLineItems(body.items)` accepts the single
     `{ productId: "prod_3", quantity: 13 }` entry (it is a non-null
     object, `productId` is a string, `quantity` is a number).
   - Calls `orderService.createOrder("cust_1", [...])`.
5. `src/services/orderService.ts` — `createOrder` runs each preliminary
   check successfully:
   - `customers.findById("cust_1")` returns Jane Doe (gold).
   - `lines` is a non-empty array.
   - `line.productId` is a string and `line.quantity` (`13`) is a
     positive integer.
   - `products.findById("prod_3")` returns the 27-inch Monitor.
   - `product.active` is `true`.
   - **Stock check fails:** `totalRequested (13) > product.stock (12)`
     ⇒ `throw new ConflictError("Insufficient stock for MON-027: requested 13, available 12")`.

## How the error becomes the HTTP response

`ConflictError` is defined in `src/errors.ts`:

```ts
export class ConflictError extends AppError {
  readonly statusCode = 409;
  readonly code = 'CONFLICT';
}
```

Because the controller is wrapped in `asyncHandler` (see
`src/middleware.ts`), the throw is converted into a rejected promise that
Express forwards to the central `errorHandler` in the same file:

```ts
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
```

So the client sees:

- **HTTP status:** `409 Conflict`
- **Error code:** `CONFLICT`
- **Response body** (the `details` field is `undefined` because the
  `ConflictError` is constructed without details, so `JSON.stringify`
  omits it):

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Insufficient stock for MON-027: requested 13, available 12",
    "requestId": "req_<timestamp>_<6-char-suffix>"
  }
}
```

The `requestId` is whatever value the `requestId` middleware generated
for this request (format: `req_${Date.now()}_${random6chars}`).

## What would have to change for the order to succeed

Any one of the following would let this exact request through:

1. **Lower the requested quantity to ≤ 12.** The simplest fix on the
   client side: `"quantity": 12` (or less) succeeds because the stock
   check in `orderService.ts` becomes `12 > 12` (false) or smaller.
2. **Increase the available stock for `prod_3` to ≥ 13.** Two ways the
   current code allows this without source changes:
   - Edit the seed in `createRepositories()` in `src/repositories.ts`
     so `prod_3` is saved with `stock: 13` (or higher).
   - At runtime, cause a cancellation that restocks `prod_3`. In
     `OrderService.updateStatus`, transitioning an order containing
     `prod_3` to `cancelled` calls `restock`, which adds the cancelled
     order's quantities back to inventory. If a previous order had
     reserved `prod_3` units, cancelling it could push stock to ≥ 13.
3. **Relax the rule itself** by changing `orderService.ts` (e.g. allow
   backorders by removing or weakening the
   `totalRequested > product.stock` check, or by introducing a separate
   "reserved" counter). This is a code change rather than a data change
   and would alter the stated business rule that orders must be fully
   stocked at creation time.

Note that the customer's gold tier has no effect on whether the order is
accepted — tier only influences pricing in `services/pricing.ts`
(10% gold discount, capped at 20% combined with the volume discount).
The rejection is purely a stock-availability decision.
