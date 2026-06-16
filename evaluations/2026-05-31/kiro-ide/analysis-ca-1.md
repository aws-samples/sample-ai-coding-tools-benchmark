# sample-api — Analysis

## 1. What the API does

`sample-api` is a small **order-management REST API** in TypeScript on Express. The domain has three entities:

- **Product** — catalog item with `sku`, integer-cent `priceCents`, `stock`, and an `active` flag.
- **Customer** — has a loyalty `tier` (`standard` / `silver` / `gold`) that drives discounting.
- **Order** — a customer plus an immutable snapshot of `OrderItem`s (`unitPriceCents`, `lineTotalCents` captured at creation time), a priced totals breakdown, and a `status` that follows a small state machine.

Under `/api/v1` it exposes catalog browsing (`GET /products`, `GET /products/:id`), order creation and lookup (`POST /orders`, `GET /orders/:id`, `GET /customers/:customerId/orders`), and order status transitions (`PATCH /orders/:id/status`). A `/health` probe sits outside the versioned path. Storage is in-memory with deterministic seed data; the README states this is a benchmark fixture, not a production system.

The interesting domain logic lives in three places: a pricing engine (tier discount + volume bonus + cap, then tax), an all-or-nothing stock-reservation flow, and an order-status state machine with a side effect on cancellation.

## 2. Layered architecture and request flow

The codebase is a textbook layered architecture. Top to bottom:

| Layer | Module(s) | Role |
| --- | --- | --- |
| Process entry | `src/index.ts` | Reads `PORT`, calls `createApp()`, binds the listener. |
| Composition root | `src/app.ts` | Builds repos → services → controllers, registers middleware in order, mounts the router. |
| Middleware | `src/middleware.ts` | `requestId`, `requestLogger`, `apiKeyAuth` (skips GET/HEAD), `asyncHandler`, `notFound`, central `errorHandler`. |
| Routing | `src/http/routes.ts` | URL → controller method, every handler wrapped in `asyncHandler`. |
| Controllers | `src/http/controllers.ts` (+ `src/http/parse.ts` helpers) | Parse and validate input, choose status codes; no business logic. |
| Services | `src/services/orderService.ts`, `src/services/pricing.ts`, `src/services/productService.ts` | All business rules. |
| Repositories | `src/repositories.ts` | `Map`-backed implementations of `ProductRepository`, `CustomerRepository`, `OrderRepository`. Owns id generation and seed data. |
| Supporting | `src/types.ts`, `src/errors.ts` | Domain types and the `AppError` hierarchy (`ValidationError` 400, `UnauthorizedError` 401, `NotFoundError` 404, `ConflictError` 409). |

### Concrete flow: `POST /api/v1/orders`

1. Express's JSON body parser runs (`express.json()` in `app.ts`).
2. `requestId` tags the request with `req_<ts>_<rand>`; `requestLogger` schedules a finish log line.
3. `apiKeyAuth` sees a non-GET method and verifies `x-api-key` against `API_KEY` (default ``); on mismatch it forwards `UnauthorizedError`.
4. The router sends the request to `OrderController.create`, wrapped in `asyncHandler`.
5. `OrderController.create` extracts `customerId` via `requireString`, runs `parseLineItems` to validate the array shape, then calls `OrderService.createOrder`.
6. `OrderService.createOrder` looks up the customer, validates and resolves every line against `ProductRepository`, accumulates per-product running totals to detect insufficient stock, builds line snapshots, decrements stock via `products.save`, prices the order through `pricing.quote`, then `orders.save`s the new `Order`.
7. The controller returns `201` with the created order. If anything threw, `errorHandler` translates an `AppError` into `{statusCode, code, message, details, requestId}`; non-`AppError` exceptions become a generic 500.

Services and repositories never know HTTP exists; controllers and middleware never touch a `Map`.

## 3. How an order is priced

The pricing engine is in `src/services/pricing.ts` and is intentionally pure (no I/O). `quote(items, tier)` does:

1. **Subtotal** — sum each item's `lineTotalCents`.
2. **Discount rate** via `discountRateFor(tier, subtotal)`:
   - Tier base: `standard 0%`, `silver 5%`, `gold 10%`.
   - **Volume bonus**: `+5%` if subtotal ≥ `50000` cents ($500.00).
   - **Cap**: `Math.min(rate, MAX_DISCOUNT_RATE)` with cap = `0.20`.
3. **Discount cents** = `round(subtotal × rate)`.
4. **Taxable cents** = `subtotal − discountCents`.
5. **Tax cents** = `round(taxableCents × 0.08)`.
6. **Total** = `taxableCents + taxCents`.

Both rounding steps use the same `Math.round` helper.

### Worked example

Gold customer (`cust_1`) orders **3× Mechanical Keyboard** (8 900¢ each) and **1× 27-inch Monitor** (31 900¢):

- Line totals: `3 × 8 900 = 26 700` and `1 × 31 900 = 31 900`.
- **Subtotal** = `58 600¢`.
- Tier rate (gold) = `0.10`. Subtotal ≥ 50 000 → volume bonus `+0.05`. Combined `0.15`. `min(0.15, 0.20)` = `0.15`.
- **Discount** = `round(58 600 × 0.15)` = `8 790¢`.
- **Taxable** = `58 600 − 8 790` = `49 810¢`.
- **Tax** = `round(49 810 × 0.08)` = `round(3 984.8)` = `3 985¢`.
- **Total** = `49 810 + 3 985` = `53 795¢` (`$537.95`).

Note: the 20% cap is **never reached** by current constants. Gold (10%) plus volume (5%) = 15%, which is below the cap. The cap exists as a guardrail for future rate changes.

## 4. Order status state machine

Encoded as `ALLOWED_TRANSITIONS` in `orderService.ts`:

```
pending   → paid, cancelled
paid      → shipped, cancelled
shipped   → delivered
delivered → ∅      (terminal)
cancelled → ∅      (terminal)
```

`OrderService.updateStatus` looks up the order, throws `ConflictError` if the requested next status is not in the current status's allowed set, runs any side effects, then writes the updated order with a refreshed `updatedAt`.

### Side effects

- The only transition with a side effect is moving **into `cancelled`**. `RESTOCKING_STATUSES` contains `'cancelled'`, so `restock(order)` runs first: it iterates `order.items` and writes each product back with `stock + item.quantity`. Restocking happens **before** the order is saved with its new status; if a future async repository's save threw after restocking, stock would have been returned for an order still recorded as `paid`. With in-memory `Map.set`, this isn't an issue today.
- `paid`, `shipped`, and `delivered` are pure status flips. No payment, shipping, or notification side effects exist.
- Same-status "transitions" (e.g. `paid → paid`) are rejected, because no status is in its own allowed list.

Terminal states (`delivered`, `cancelled`) cannot be left.

## 5. Stock reservation: avoiding partial reservation

`OrderService.createOrder` is structured as **two passes** with no mutation in the first.

**Pass 1 — validate everything, mutate nothing:**

- Walk each `OrderLineInput`. Assert `productId` is a string and `quantity` is a positive integer; look up the product; reject if missing (`NotFoundError`) or inactive (`ConflictError`).
- Maintain a `requestedByProduct: Map<productId, runningTotal>`. For each line compute `totalRequested = previous + quantity` and compare against `product.stock` as currently stored. If the running total exceeds available stock, throw `ConflictError` immediately.
- This handles the case where the same product appears on multiple lines: stock is checked against the cumulative total, so `[{prod_1, 30}, {prod_1, 30}]` against a stock of 50 is correctly rejected.

**Pass 2 — only reached if every line passed validation:**

- Build the `OrderItem[]` snapshots, capturing `unitPriceCents`, `name`, `sku`, and `lineTotalCents`.
- Iterate `requestedByProduct` once and write `products.save({ ...product, stock: stock - qty })` per distinct product.
- Price via `quote(items, customer.tier)` and `orders.save(order)`.

Because pass 1 never calls `save`, any thrown error short-circuits the function with the catalog untouched. A bad fifth line in a five-line order cannot partially reserve the first four.

This is correct **only because the entire critical section is synchronous** — no `await` between reads and writes, and Node's event loop is single-threaded. If the repository ever became async (real database), the read-then-write gap becomes a TOCTOU race and an explicit transaction or row lock would be required.

---

## 6. Confusing, risky, or bug-prone areas

### Logic and correctness

- **The 20% discount cap is unreachable.** Max achievable rate today is `gold (10%) + volume (5%) = 15%`. `MAX_DISCOUNT_RATE = 0.20` never engages, so the cap is effectively dead code and could be raised silently if someone bumps a tier rate.
- **Reservation is only safe under synchronous execution.** The two-pass pattern protects against partial reservation within a single request but does not guard against concurrent requests. Introducing `await` between the validation reads and stock writes, or moving to a real backend, opens a race. There is no transaction, lock, or optimistic-concurrency check.
- **Restock runs before the status save.** If `orders.save` ever fails (it can't with `Map.set`, but could with a real DB), stock is returned while the order remains in its prior state.
- **Restock silently skips missing products.** `restock` checks `if (product)` and continues; the cancellation succeeds and units never return to inventory, with no log. Latent bug if delete-product is added later.
- **Duplicate-product lines produce duplicate `OrderItem` snapshots.** `requestedByProduct` aggregates quantities for stock checks, but `items.map(...)` runs over the original input lines, so `[{prod_1, 1}, {prod_1, 2}]` produces two `OrderItem` entries for the same SKU. Pricing math is unaffected (subtotal sums line totals), but downstream consumers expecting one row per product will be surprised.
- **No idempotency.** Same-status `updateStatus` calls (e.g. `paid → paid`) throw `ConflictError`. Retrying a flaky PATCH that already succeeded looks like a failure. `POST /orders` has no idempotency key either, so a retried create becomes a duplicate order.
- **`paginate` allows pages past the end.** Returns `data: []` with `totalPages` reflecting reality. Not strictly wrong, but the response gives no special signal that the client overshot.

### Validation and parsing

- **`parseBoolean` only accepts `'true'` or `'1'`.** Anything else (including `'TRUE'`, whitespace, or `'false'`) silently falls back to the default. Spec docs in the README ("`true`/`false`") don't make the case sensitivity clear.
- **`requireString` doesn't trim.** It checks for non-empty after trimming but returns the original value. A `customerId` of `"  cust_1  "` passes validation and then fails the lookup with a misleading `NotFoundError`.
- **Quantity validation is split across layers.** `parseLineItems` only checks `typeof quantity === 'number'`; `Number.isInteger`/`> 0` runs later in the service. `1.5` passes the controller before the service rejects it. Fine, but inconsistent.
- **`VALID_STATUSES` in `controllers.ts` is a separate constant from `ALLOWED_TRANSITIONS` keys in `orderService.ts`.** Add a status in one place without the other and they drift.
- **Inconsistent identifiers in error messages.** `Insufficient stock for KEYB-001` and `Product KEYB-001 is not available` use `product.sku`; `Product prod_1 not found` uses the input id. Programmatic clients trying to attribute failures will need to handle both.

### Auth and security

- **Hardcoded fallback API key.** `API_KEY = process.env.API_KEY ?? ''`. If unset in production, the service silently runs with a publicly known key. Should at least warn or refuse to start outside development.
- **Non-constant-time API-key comparison.** `provided !== API_KEY` is timing-sensitive. Trivial for a demo, but real deployments should use `crypto.timingSafeEqual`.
- **Auth is method-based, not endpoint-based.** Any future GET endpoint becomes public by default. Fine for a catalog, hazardous for `GET /admin/...`.

### Error handling consistency

- **Two response shapes coexist.** Most errors flow through `errorHandler` and include `requestId`. But `ProductController.getById` writes a 404 directly without raising `NotFoundError`, and `notFound` middleware also responds directly. Neither includes `requestId`, so clients correlating by id lose those entries.
- **`details` is included even when undefined.** It serialises away to nothing in JSON, but combined with the two shapes above it makes the envelope harder to type strictly than the README suggests.

### Operational

- **`generateId` is module-level mutable state.** Harmless with in-memory storage in one process, but ids will collide if the service ever scales across processes or persists state across restarts.
- **Request ids use `Math.random()`.** Fine for log correlation, not collision-resistant.
- **`requestLogger` uses `console.log` directly.** Production observability would need a structured logger.
- **Discount and tax are rounded independently.** A client re-deriving `subtotal − discount + tax` against `total` can disagree by up to one cent. Worth documenting; not worth fixing.

None of these break the happy paths the README demonstrates, but they are the spots most likely to surprise someone extending the code or swapping in real persistence.
