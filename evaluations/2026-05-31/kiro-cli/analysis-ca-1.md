# sample-api — Analysis

## What the API does

`samples/sample-api` is a small TypeScript + Express **order-management REST API** intended as a benchmark fixture. The domain has three entities — `Product`, `Customer`, `Order` — and three pieces of non-trivial business logic glued together:

1. A **product catalog** with filtering (active-only, free-text search) and pagination.
2. An **order creation flow** that validates input, reserves stock atomically, snapshots line items at current price, and prices the order through a discount + tax engine.
3. An **order status state machine** (`pending → paid → shipped → delivered`, plus `cancelled`) that drives side effects like restocking inventory.

All persistence is in-memory with seed data loaded at boot (two customers, four products). Money is stored as integer cents (`Cents = number`) to avoid float drift, and authentication is a simple `x-api-key` header required only for mutating verbs (`POST` / `PATCH`).

Endpoints (under `/api/v1`):

| Method  | Path                              | Auth |
| ------- | --------------------------------- | ---- |
| `GET`   | `/products`                       | none |
| `GET`   | `/products/:id`                   | none |
| `POST`  | `/orders`                         | key  |
| `GET`   | `/orders/:id`                     | none |
| `PATCH` | `/orders/:id/status`              | key  |
| `GET`   | `/customers/:customerId/orders`   | none |

Plus `GET /health` mounted outside the base path as a liveness probe.

## Layered architecture and request flow

The codebase is laid out as classic top-down layers, with each layer depending only on the one below:

```
HTTP request
   │
   ▼
src/middleware.ts          requestId, requestLogger, apiKeyAuth, asyncHandler,
   │                       notFound, errorHandler
   ▼
src/http/routes.ts         URL pattern → controller method
   │
   ▼
src/http/controllers.ts    parse + validate input, set status code,
   │                       no business logic
   ▼
src/services/              business logic
   │  ├─ orderService.ts   validation, stock reservation, state machine
   │  ├─ pricing.ts        pure pricing engine (discount + tax)
   │  └─ productService.ts catalog filtering + pagination
   ▼
src/repositories.ts        in-memory Map storage + seed data,
                           swappable repository interfaces
```

Supporting modules: `src/types.ts` (domain types), `src/errors.ts` (typed `AppError` hierarchy with `statusCode` + stable `code`), `src/app.ts` (composition root that wires repositories → services → controllers and registers middleware), `src/index.ts` (process entry point).

### Walkthrough: `POST /api/v1/orders`

1. `index.ts` boots the server: `createApp()` from `app.ts`, then `app.listen(PORT)`.
2. `app.ts::createApp` constructs the dependency graph (`createRepositories()` → `OrderService`/`ProductService` → `OrderController`/`ProductController`) and registers global middleware in order: `express.json()` → `requestId` → `requestLogger` → `/health` route → `apiKeyAuth` mounted on `/api/v1` → the router from `buildRouter` → `notFound` → `errorHandler`.
3. `middleware.ts::requestId` attaches a unique `req.id` (`req_<timestamp>_<rand>`) for log/error correlation.
4. `middleware.ts::requestLogger` records start time and logs the response on `res.on('finish')`.
5. `middleware.ts::apiKeyAuth` lets `GET`/`HEAD` through, otherwise compares `x-api-key` against `API_KEY` (default ``) and forwards an `UnauthorizedError` to the error pipeline if it doesn't match.
6. `http/routes.ts::buildRouter` matches `POST /orders` to `orderController.create`, wrapped in `asyncHandler` so any thrown/rejected error reaches the central handler.
7. `http/controllers.ts::OrderController.create` parses `customerId` via `requireString`, validates `items` is an array of `{ productId: string, quantity: number }`, then calls `orderService.createOrder(customerId, items)` and responds with `201` and the created order.
8. `services/orderService.ts::createOrder` runs the two-pass stock reservation (see below), calls `pricing.quote(items, customer.tier)`, builds the `Order`, and persists via `orders.save`.
9. `repositories.ts::InMemoryOrderRepository.save` stores in a `Map<string, Order>` and returns it.
10. The `Order` returned bubbles back up through the controller into the JSON response. If anything in steps 7–9 throws an `AppError`, `asyncHandler` forwards it to `middleware.ts::errorHandler`, which serializes `{ error: { code, message, details, requestId } }` with the right HTTP status. Anything else becomes an opaque 500.

`GET` reads follow the same path minus `apiKeyAuth` (which short-circuits on read methods) and minus the second pass / mutation in the service.

## Pricing — concrete walkthrough

Implemented in `src/services/pricing.ts` as pure functions. Constants:

- `TIER_DISCOUNT`: `standard` 0%, `silver` 5%, `gold` 10%
- `VOLUME_DISCOUNT_THRESHOLD_CENTS`: `50000` (i.e. $500.00)
- `VOLUME_DISCOUNT_RATE`: 5% added when the **subtotal** crosses the threshold
- `MAX_DISCOUNT_RATE`: 20% — combined rate is clamped to this
- `TAX_RATE`: 8%, applied to the **discounted** subtotal

Formula in `quote`:

```
subtotal       = Σ lineTotalCents
discountRate   = min(tier + (subtotal ≥ 50000 ? volume : 0), 0.20)
discountCents  = round(subtotal × discountRate)
taxableCents   = subtotal − discountCents
taxCents       = round(taxableCents × 0.08)
totalCents     = taxableCents + taxCents
```

Discount is applied first, then tax on the post-discount amount. Both rounded values are computed with `Math.round`.

### Worked example — gold customer, two-line order over the volume threshold

Customer: `cust_1` (gold). Items:

- 2 × `prod_1` Mechanical Keyboard @ 8900¢ → 17800¢
- 4 × `prod_3` 27-inch Monitor @ 31900¢ → 127600¢

| Step | Value |
| ---- | ----- |
| `subtotalCents` | `17800 + 127600 = 145400` |
| Tier rate (gold) | `0.10` |
| Volume rate (`145400 ≥ 50000`) | `+0.05` |
| Combined rate | `0.15` (well under the `0.20` cap) |
| `discountCents` | `round(145400 × 0.15) = 21810` |
| `taxableCents` | `145400 − 21810 = 123590` |
| `taxCents` | `round(123590 × 0.08) = round(9887.2) = 9887` |
| `totalCents` | `123590 + 9887 = 133477` ($1,334.77) |

Note that with the current rule set the **20% cap is unreachable**: the maximum combined rate is `gold(0.10) + volume(0.05) = 0.15`. So `MAX_DISCOUNT_RATE` is effectively dead code today; it only matters if a higher tier or a larger volume bonus is added later.

## Order status state machine

Defined in `services/orderService.ts::ALLOWED_TRANSITIONS`:

```
pending ──▶ paid ──▶ shipped ──▶ delivered  (terminal)
   │         │
   └────┬────┘
        ▼
    cancelled  (terminal)
```

| From       | Allowed next        |
| ---------- | ------------------- |
| pending    | paid, cancelled     |
| paid       | shipped, cancelled  |
| shipped    | delivered           |
| delivered  | (terminal)          |
| cancelled  | (terminal)          |

`updateStatus(orderId, next)` enforces the transition: if `next` is not in `ALLOWED_TRANSITIONS[order.status]`, it throws `ConflictError` (HTTP 409).

### Side effects

The only modeled side effect is on cancellation. `RESTOCKING_STATUSES = ['cancelled']`, so when an order moves into `cancelled` (from `pending` or `paid`), `restock(order)` runs and adds each line's `quantity` back onto the corresponding product's `stock`. After that, the order is saved with the new status and an updated `updatedAt`.

There is no side effect on any other transition — `paid`, `shipped`, and `delivered` are status-only changes. There is also no record on the order indicating that restocking already happened (relevant only because future code might allow re-cancellation; today it can't because `cancelled` is terminal).

## Stock reservation — all-or-nothing

`OrderService.createOrder` deliberately runs in **two passes** so a bad later line never partially reserves earlier products.

Pass 1 — pure validation, **no mutation**:

```ts
const resolved: Array<{ product: Product; quantity: number }> = [];
const requestedByProduct = new Map<string, number>();

for (const line of lines) {
  // shape checks
  // findById / active checks
  const alreadyRequested = requestedByProduct.get(product.id) ?? 0;
  const totalRequested = alreadyRequested + line.quantity;
  if (totalRequested > product.stock) throw new ConflictError(...);
  requestedByProduct.set(product.id, totalRequested);
  resolved.push({ product, quantity: line.quantity });
}
```

The `requestedByProduct` map matters: if a multi-line order has two lines for the same `productId`, the loop sums them and validates **the cumulative total** against `product.stock`. Without it, two lines of 30 each against a stock of 50 would each pass individually and oversell.

Pass 2 — only reached if every line passed validation — builds immutable `OrderItem` snapshots (price/sku/name copied so future product changes don't rewrite history) and decrements stock once per product (using `requestedByProduct`, again to avoid double-decrementing on duplicate lines). Then it calls `pricing.quote`, builds the `Order`, and persists.

Because the first failing line throws before any `products.save` is called, the catalog is untouched and the order is never persisted. The "all-or-nothing" guarantee follows directly from this two-phase ordering.

## Confusing, risky, or likely-buggy areas

These are observations, not changes — the code is not modified.

1. **No concurrency safety.** Stock reservation is "atomic" only because everything in `createOrder` is synchronous and Node is single-threaded. The repositories share mutable `Map` state with no locking. The moment any `await` is introduced in `createOrder` (e.g. swapping in a real DB), two concurrent requests can both pass the "sufficient stock" check and oversell. The all-or-nothing property is structural, not transactional.

2. **The 20% discount cap is currently unreachable.** With `gold = 0.10` and volume `= 0.05`, the maximum combined rate is `0.15`. `MAX_DISCOUNT_RATE = 0.20` will never bind under existing inputs, which is easy to miss when reasoning about pricing edge cases. Either the cap is forward-looking (fine, but worth a comment) or one of the rates is wrong.

3. **Inconsistent error envelope.** `ProductController.getById` returns 404 directly with `res.status(404).json({ error: { code, message } })`, **without** a `requestId`. The order endpoints throw `NotFoundError`, which goes through `errorHandler` and **does** include `requestId`. A client correlating logs by `requestId` will silently get nothing for product 404s. Same issue with the global `notFound` middleware: it never reads `req.id`, so unmatched-route 404s also lack `requestId`.

4. **Money arithmetic still goes through floats.** Despite the README's "integer cents to avoid float drift", `subtotalCents * appliedDiscountRate` and `taxableCents * TAX_RATE` are float multiplications, then `Math.round`. For most realistic inputs this is fine, but rounding choices are not banker's rounding and can leave a one-cent gap between what a human computes by hand and what the API returns.

5. **`Math.round` on floats can flip pennies in unexpected ways.** Standard JS rounding (`0.5 → 1`, `1.5 → 2`, `2.5 → 3`) means any cent with a `0.5` fractional part rounds up. If accounting expects banker's rounding, this is wrong.

6. **`apiKeyAuth` uses a plain string comparison (`provided !== API_KEY`).** Not constant-time, so it's technically timing-attackable. For a demo it's fine, but worth noting in a security pass.

7. **No rate limiting, no body size limit beyond Express defaults, no CORS, no helmet.** A single client can submit a thousand-line order or hammer `POST /orders`; nothing pushes back. `items` length isn't bounded.

8. **`generateId` is module-global mutable state.** `let idCounter = 1000` lives at the top of `repositories.ts`. It's reset to 1000 on every process start, and tests that import the module multiple times share the counter. This is correct for the benchmark but bad for any kind of distributed deployment or for parallelizable tests.

9. **`restock` silently skips deleted/missing products.** `if (product) products.save(...)`: if a product was removed between order creation and cancellation, the inventory of those units is permanently lost with no warning or error. The current code has no delete path so this is latent, but it's a future foot-gun.

10. **`controllers.ts::updateStatus` casts `as OrderStatus` before the runtime check.** It works because `VALID_STATUSES.includes(...)` runs immediately after, but the cast-then-validate pattern can drift if someone adds a code path between the two lines. Validating first and casting after would be safer.

11. **`asyncHandler` wraps synchronous handlers.** All controllers in this codebase are synchronous; `asyncHandler` is a no-op for them. Not a bug, just noise that suggests the codebase used to or expects to be async — relevant because if someone later adds an `await` in a service, point (1) above starts to bite.

12. **`pageSize` is silently clamped to 100.** A client requesting `pageSize=500` gets 100 results back with no indication their request was modified. Sometimes desired, sometimes a debugging time-sink.

13. **`appliedDiscountRate` is stored on the persisted order as a JS number.** It's the rate, not the discount value, so for some combinations it can serialize as e.g. `0.15000000000000002`. Audit-wise, the discount **amount** in cents is the source of truth (`discountCents`), so this is mostly cosmetic.

14. **`InMemoryOrderRepository.findByCustomer` is O(n) over all orders.** Acceptable here, but the repository interface doesn't surface this characteristic, so a swap to a real backend will need an index.

15. **Line item `lineTotalCents = priceCents * quantity` is integer-safe today** because `priceCents` is an integer. If anyone changes `priceCents` to a non-integer (e.g. fractions of a cent for tax-inclusive pricing), this product silently becomes a float.

16. **The `requestId` typing trick (`(req as Request & { id: string })`)** is repeated across `middleware.ts`. Cleaner approach is module-level Express type augmentation; the current style risks drift if a handler reads `req.id` without re-applying the cast.

17. **Volume threshold uses pre-discount subtotal.** The `discountRateFor` checks `subtotalCents` before any discount is applied, which is a reasonable choice but worth flagging — it means a tier discount cannot push a borderline order back below the threshold and re-evaluating order requires recomputing from scratch if either rule changes.

18. **`createRepositories` hardcodes `createdAt`** to `2026-01-01T00:00:00.000Z` for seed entities, while live orders use `Date.now()`. The fixed seed timestamp aids repeatability for benchmarks, but mixed timestamp sources can confuse anyone debugging "why does prod_1 say it was created in the future?".
