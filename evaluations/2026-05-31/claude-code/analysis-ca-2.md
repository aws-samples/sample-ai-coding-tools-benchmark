# Trace: `POST /api/v1/orders` for 13 × `prod_3` (gold tier)

## Request

```
POST /api/v1/orders
x-api-key: YOUR_API_KEY
Content-Type: application/json

{
  "customerId": "cust_1",
  "items": [{ "productId": "prod_3", "quantity": 13 }]
}
```

`prod_3` is the 27‑inch Monitor (`MON-027`), seeded with `stock: 12`, `active: true` in `src/repositories.ts:124-132`. `cust_1` is gold‑tier.

## Path through the code

1. **`src/app.ts:36-46`** — `express.json()` parses the body, `requestId` tags it, `requestLogger` registers a `finish` listener, then `apiKeyAuth` runs because the path matches `/api/v1`.
2. **`src/middleware.ts:35-44`** (`apiKeyAuth`) — POST is not GET/HEAD, so it requires `x-api-key === ''`. Assumed present (otherwise this would short-circuit with a `401 UNAUTHORIZED`); we proceed.
3. **`src/http/routes.ts:21`** — dispatches to `OrderController.create`, wrapped by `asyncHandler`.
4. **`src/http/controllers.ts:49-56` + `78-95`** (`OrderController.create` / `parseLineItems`) — `customerId` is a string, `items` is an array of one object with string `productId` and numeric `quantity`. All shape checks pass. Calls `orderService.createOrder('cust_1', [{ productId: 'prod_3', quantity: 13 }])`.
5. **`src/services/orderService.ts:60-101`** (`OrderService.createOrder`, first/validation pass):
   - `customers.findById('cust_1')` → Jane Doe (gold). OK.
   - `lines` is a non-empty array. OK.
   - Line 0: `productId` is a string; `quantity = 13` is a positive integer. OK.
   - `products.findById('prod_3')` → the monitor (`stock: 12`, `active: true`). OK.
   - `alreadyRequested = 0`, `totalRequested = 0 + 13 = 13`.
   - **Check at `orderService.ts:94`**: `totalRequested (13) > product.stock (12)` is **true**.
   - **`orderService.ts:95-97` throws** `new ConflictError('Insufficient stock for MON-027: requested 13, available 12')`.
6. The throw escapes the controller; `asyncHandler` (`middleware.ts:50-56`) forwards it to Express's error pipeline.
7. **`src/middleware.ts:69-100`** (`errorHandler`) — `isAppError(err)` matches `ConflictError`, which (per `src/errors.ts:46-49`) declares `statusCode = 409`, `code = 'CONFLICT'`. The handler calls `res.status(409).json({...})`.

## What the client sees

- **Status:** `409 Conflict`
- **Headers:** `Content-Type: application/json; charset=utf-8`
- **Body** (the `details` field is `undefined` and `JSON.stringify` drops it):

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Insufficient stock for MON-027: requested 13, available 12",
    "requestId": "req_<epoch-ms>_<6-char-rand>"
  }
}
```

The rejection module is `src/services/orderService.ts`; the rejecting check is the stock guard at line 94 (`totalRequested > product.stock`). The HTTP shape is owned by `errors.ts` (`ConflictError → 409 / CONFLICT`) and `middleware.ts` (`errorHandler` envelope).

Note: `prod_3.active` is `true`, so the active‑product check on line 88 is not what fails. Customer tier (`gold`) plays no role in this rejection — pricing/discount logic in `services/pricing.ts` is only reached on the **second** pass (`orderService.ts:103-118`), which we never enter because the validation pass aborts first.

## What would need to change for the order to succeed

Any one of the following would let the request through:

1. **Reduce the requested quantity to ≤ 12.** Change the request body to `"quantity": 12` (or less). With 12 in stock, `totalRequested (12) > product.stock (12)` is false and the check passes.
2. **Increase `prod_3` stock to ≥ 13.** In `src/repositories.ts:124-132`, raise the seeded `stock` (e.g., `stock: 13`). After a server restart, the same 13‑unit order would succeed.
3. **Replenish stock at runtime via a cancellation.** `OrderService.updateStatus` restocks on transition to `cancelled` (`orderService.ts:158-178` + `restock` at `181-188`). If a prior pending/paid order had reserved at least 1 unit of `prod_3`, cancelling it would push stock back to ≥ 13 and the new order would succeed. (No such order exists at boot, so this requires prior request traffic.)
4. **Split or relax the rule.** Editing the guard at `orderService.ts:94` to allow back‑order (e.g., partial fulfillment, or skipping the stock check for active products) would also let it through — but this changes business semantics, not just data.

The minimal, behavior‑preserving fix is option 1 (cap quantity at available stock) or option 2 (raise the seed). Options 3 and 4 are situational.
