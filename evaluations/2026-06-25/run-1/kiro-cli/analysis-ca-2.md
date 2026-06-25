# Analysis: Rejected order — gold customer, 13× prod_3 (12 in stock)

## Request

```
POST /api/v1/orders
x-api-key: <valid key>
Content-Type: application/json

{
  "customerId": "cust_1",          // Jane Doe, tier: gold
  "items": [
    { "productId": "prod_3", "quantity": 13 }   // 27-inch Monitor (MON-027), stock: 12
  ]
}
```

Seed facts (from `src/repositories.ts`):
- `prod_3` = SKU `MON-027`, `priceCents: 31900`, `stock: 12`, `active: true`.
- `cust_1` = Jane Doe, `tier: gold`.

## Execution trace

1. **`src/http/routes.ts`** — `POST /orders` is wired to `orders.create`, wrapped in `asyncHandler`. (Mounted under `/api/v1` in `app.ts`, so the full path is `/api/v1/orders`.)

2. **`src/middleware.ts` → `apiKeyAuth`** — This is a POST (mutating), so a valid `x-api-key` header is required. Assuming the key is valid, it passes. (If it were missing/wrong, you'd instead get a 401 `UNAUTHORIZED` and the stock check would never run.)

3. **`src/http/controllers.ts` → `OrderController.create`** — Parsing succeeds:
   - `requireString(body.customerId, 'customerId')` → `"cust_1"` is a non-empty string. OK.
   - `parseLineItems(body.items)` → `items` is an array; the one entry is an object with a string `productId` and a numeric `quantity`. OK. Returns `[{ productId: "prod_3", quantity: 13 }]`.
   - Calls `this.orders.createOrder("cust_1", [...])`.

4. **`src/services/orderService.ts` → `OrderService.createOrder`** — this is where it is rejected. Step by step:
   - `customers.findById("cust_1")` → found. OK.
   - `lines` is a non-empty array. OK.
   - First validation pass over the single line:
     - `line.productId` is a string. OK.
     - `Number.isInteger(13) && 13 > 0` → quantity is valid. OK.
     - `products.findById("prod_3")` → found. OK.
     - `product.active` is `true`. OK.
     - **Stock check (the rejecting check):**
       ```ts
       const alreadyRequested = requestedByProduct.get(product.id) ?? 0; // 0
       const totalRequested = alreadyRequested + line.quantity;          // 0 + 13 = 13
       if (totalRequested > product.stock) {                            // 13 > 12  → TRUE
         throw new ConflictError(
           `Insufficient stock for ${product.sku}: requested ${totalRequested}, available ${product.stock}`,
         );
       }
       ```
       `13 > 12` is true, so a **`ConflictError`** is thrown. No stock is mutated (the throw happens in the first, read-only validation pass, before the second commit pass), and the pricing engine (`quote`, including the gold-tier discount) is never reached.

5. **`src/errors.ts` → `ConflictError`** — declares `statusCode = 409`, `code = 'CONFLICT'`, with no `details`.

6. **`src/middleware.ts` → `errorHandler`** — `asyncHandler` forwards the thrown error here. `isAppError(err)` is true, so it responds with the error's declared status and a JSON envelope including the per-request id set by the `requestId` middleware.

## What the client receives

- **HTTP status:** `409 Conflict`
- **Error code:** `CONFLICT`

Response body (note: `details` is `undefined`, so `JSON.stringify` omits the key; `requestId` is generated per request):

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Insufficient stock for MON-027: requested 13, available 12",
    "requestId": "req_<timestamp>_<random>"
  }
}
```

## Module / check that rejects it

- **Module:** `src/services/orderService.ts`, method `OrderService.createOrder`.
- **Check:** the per-line stock guard `if (totalRequested > product.stock)` in the first validation pass — `13 > 12`.

## What would need to change for the order to succeed

The rejection is purely the stock guard; the customer, product, activeness, and input parsing are all fine. Any one of the following makes it pass:

1. **Order at or below available stock** — request `quantity` ≤ `12` for `prod_3`. This is the only change that requires no code/data edits and is the intended behavior.
2. **Increase inventory** — in `src/repositories.ts` seed data, set `prod_3.stock` to `13` or more (or replenish via a restock, e.g. cancelling an existing order that holds `prod_3`, which triggers `OrderService.restock`).
3. **Relax/alter the rule (not recommended)** — change the guard in `createOrder` (e.g. allow backorders, clamp quantity to available stock). This changes business semantics and would let stock go negative or silently reduce the requested quantity, so it should only be done deliberately.

Note: the gold tier (10% discount) and the volume discount are irrelevant to this rejection — pricing runs only in the second pass, which is never reached. They would only matter once the order passes the stock check. For reference, 12× prod_3 = 12 × 31900 = 382,800¢ subtotal; ≥ 50,000¢ triggers the +5% volume discount on top of the 10% gold tier = 15% total discount, then 8% tax on the discounted amount.
