# Trace: gold-tier order for 13× prod_3 (12 in stock) → rejected

## The request

```
POST /api/v1/orders
x-api-key: <valid key>          # required: POST is a mutating request (middleware.ts:37-46)
Content-Type: application/json

{
  "customerId": "cust_1",       # Jane Doe, tier "gold" (repositories.ts:143-149)
  "items": [
    { "productId": "prod_3", "quantity": 13 }   # MON-027, 27" Monitor, stock 12 (repositories.ts:124-132)
  ]
}
```

## Which module and which check rejects it

The rejection happens in **`src/services/orderService.ts`**, in `OrderService.createOrder`, at the
**insufficient-stock check inside the first validation pass** (lines 92–98):

```ts
const alreadyRequested = requestedByProduct.get(product.id) ?? 0;   // 0
const totalRequested = alreadyRequested + line.quantity;            // 0 + 13 = 13
if (totalRequested > product.stock) {                               // 13 > 12  → true
  throw new ConflictError(
    `Insufficient stock for ${product.sku}: requested ${totalRequested}, available ${product.stock}`,
  );
}
```

### How execution reaches that check (every earlier gate passes)

1. **Routing + auth.** `POST /orders` maps to `OrderController.create`, wrapped in `asyncHandler`
   (`routes.ts:21`). The app mounts the router under `/api/v1` behind `apiKeyAuth` (`app.ts:46`). Because
   POST is a mutating method, `apiKeyAuth` requires a valid `x-api-key` header (`middleware.ts:37-46`); we
   assume it is present — otherwise the request fails earlier with `401 UNAUTHORIZED`.
2. **`src/http/controllers.ts` — `OrderController.create` (lines 49–56).**
   - `requireString(body.customerId, …)` → `"cust_1"` is a non-empty string ✅ (`parse.ts:45-50`).
   - `parseLineItems(body.items)` (lines 78–95): `items` is an array; the entry is a non-null object;
     `productId` is a string; `quantity` (`13`) is `typeof "number"` ✅. Note it only checks the *type* here —
     the integer/positivity check lives in the service.
   - Calls `this.orders.createOrder("cust_1", [{ productId: "prod_3", quantity: 13 }])`.
3. **`createOrder` preamble (lines 60–67).** Customer `cust_1` is found ✅; `lines` is a non-empty array ✅.
4. **First-pass loop (lines 74–101), single iteration for `prod_3`:**
   - `productId` is a string ✅ (lines 75–77).
   - `quantity` 13 is a positive integer ✅ (lines 78–82).
   - `products.findById("prod_3")` returns the monitor ✅ (lines 84–87).
   - `product.active` is `true`, so the "not available for sale" `ConflictError` is skipped ✅ (lines 88–90).
   - **Stock check fails: `13 > 12` → throws `ConflictError`** (lines 92–98). ⛔

This is the **first and only** failing check. Because it lives in the *first pass* — which deliberately
validates and resolves every line *before* mutating anything (comment at lines 69–70) — **no stock is
decremented and no order is persisted.** The second pass (snapshot building, stock commit, and `quote(...)`
pricing at lines 103–136) is never reached.

> The customer's **gold tier is irrelevant to the rejection.** Tier only feeds the pricing engine
> (`quote(items, customer.tier)`, line 118), which runs in the *second* pass — after the failure point.

## HTTP status and error code

- The thrown error is `ConflictError` (`src/errors.ts:46-49`), declaring `statusCode = 409` and
  `code = 'CONFLICT'`.
- The throw escapes the synchronous controller; `asyncHandler` (`middleware.ts:52-58`) catches it via the
  `Promise.resolve(...).catch(next)` wrapper and forwards it to Express's error pipeline.
- The central `errorHandler` (`middleware.ts:71-102`) sees `isAppError(err) === true` and serializes the
  declared status + code.

**HTTP status: `409 Conflict`**
**Error code: `CONFLICT`**

## Response body

`errorHandler` builds the object at `middleware.ts:82-89`:

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Insufficient stock for MON-027: requested 13, available 12",
    "requestId": "req_<timestamp>_<random>"
  }
}
```

Exact-shape notes:
- `message` uses the product **SKU** (`MON-027`), not the product id, because the throw interpolates
  `product.sku` (`orderService.ts:96`).
- The handler literally assigns `details: appErr.details`, but no `details` argument was passed to this
  `ConflictError`, so `appErr.details` is `undefined`. `JSON.stringify` **omits** keys whose value is
  `undefined`, so `details` does **not** appear in the emitted JSON (it is not rendered as `null`).
- `requestId` is the per-request id set by the `requestId` middleware
  (`req_${Date.now()}_${Math.random()...}`, `middleware.ts:15-19`); its concrete value varies per request.

## What would need to change for the order to succeed

The sole blocker is requested quantity (13) exceeding available stock (12). Any one of these clears it; the
order would then be priced with the gold-tier discount and persisted as `pending`, returning `201 Created`:

1. **Order at most the available stock.** Request `quantity ≤ 12` for `prod_3`. This is the normal
   client-side fix — no code or data change required.
2. **Increase the product's stock to ≥ 13.** The seed data creates the monitor with `stock: 12`
   (`repositories.ts:131`); raising that seed value — or restocking through another flow (cancelling an
   order returns stock via `restock`, `orderService.ts:181-188`) — would let 13 through.
3. **Relax the stock rule itself** (a behavior change, not generally desirable): weaken or remove the
   `totalRequested > product.stock` guard at `orderService.ts:94` to permit overselling/backorders. This
   lets stock go negative and affects every product, so it is a design decision rather than a fix.

The realistic answer is **(1)** — reduce the quantity to 12 or fewer — or **(2)** add inventory. The gold
tier, API key, and request format are all already satisfied; none of them is the cause of the rejection.
```