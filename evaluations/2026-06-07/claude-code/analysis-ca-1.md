# sample-api — Code Analysis

## 1. What the API does

`sample-api` is a small **order-management REST API** in TypeScript / Express,
built as a benchmark fixture. It models a tiny e‑commerce backend with three
core entities:

- **Products** — a catalog of SKUs with a unit price (in integer cents),
  on-hand `stock`, and an `active` flag.
- **Customers** — keyed by id, each with a loyalty `tier`
  (`standard` / `silver` / `gold`) that drives pricing.
- **Orders** — line-item snapshots taken at order time, an immutable totals
  block (subtotal / discount / tax / total), the `appliedDiscountRate`, and a
  status that walks through a small lifecycle.

Headline business rules:

- Money is stored as **integer cents** end-to-end to avoid float drift.
- **Stock reservation is all-or-nothing** — an order is fully validated
  against the catalog before any inventory is decremented.
- Pricing applies a **tier discount** plus an optional **volume discount**,
  capped, then **8% tax** on the discounted subtotal.
- Orders move through `pending → paid → shipped → delivered`, with
  `pending`/`paid` also able to move to `cancelled`. Cancelling restocks.

Endpoints (base `/api/v1`, plus an unauthenticated `/health`): list/get
products, create/get orders, patch order status, list a customer's orders.
`GET` is public; `POST`/`PATCH` require `x-api-key`.

---

## 2. Layered architecture and request flow

The codebase is split into clear layers, each module owning one concern:

```
HTTP request
   │
   ▼
src/middleware.ts          requestId → requestLogger → apiKeyAuth → asyncHandler
   │
   ▼
src/http/routes.ts         URL → controller method
   │
   ▼
src/http/controllers.ts    parse body/query, call service, pick status code
src/http/parse.ts          parsePagination / parsePositiveInt / parseBoolean / requireString
   │
   ▼
src/services/              business logic
   ├─ orderService.ts        create, validate, reserve stock, state machine
   ├─ pricing.ts             pure quote() — discounts, cap, tax
   └─ productService.ts      filter, sort, paginate
   │
   ▼
src/repositories.ts        InMemory{Product,Customer,Order}Repository + seed
   │
   ▼
src/types.ts               Cents, CustomerTier, Product, Customer, Order, …
src/errors.ts              AppError → ValidationError / Unauthorized / NotFound / Conflict
```

`src/app.ts` is the composition root: it builds the repository bundle,
constructs services and controllers, registers middleware in the right order,
mounts the router under `/api/v1`, and wires the 404 + central error handler
last. `src/index.ts` is just the listen-on-PORT entry point.

### Walkthrough — `POST /api/v1/orders`

1. **Express** receives the request and runs `express.json()` so `req.body`
   is parsed.
2. `requestId` (middleware.ts) stamps `req.id = req_<ts>_<rand>` for log
   correlation.
3. `requestLogger` (middleware.ts) registers a `res.on('finish')` hook that
   prints `[id] METHOD URL -> status (Xms)`.
4. `apiKeyAuth` (middleware.ts) is mounted at `/api/v1`. Because the method
   is `POST`, it requires `x-api-key === API_KEY`, otherwise it forwards an
   `UnauthorizedError` to the error pipeline.
5. **Router** (`http/routes.ts`) matches `POST /orders` to
   `OrderController.create` wrapped in `asyncHandler` (so promise rejections
   reach the error middleware).
6. **Controller** (`http/controllers.ts`):
   - `requireString(body.customerId, 'customerId')` — throws
     `ValidationError` if missing/blank.
   - `parseLineItems(body.items)` — asserts an array of
     `{productId: string, quantity: number}` objects, throwing
     `ValidationError` with index-tagged messages on bad shape.
   - Calls `orders.createOrder(customerId, items)`.
   - On success, responds `201` with the created order JSON.
7. **Service** (`services/orderService.ts → createOrder`):
   - `customers.findById(customerId)` — throws `NotFoundError` if unknown.
   - Rejects empty/non-array `lines` with `ValidationError`.
   - **First pass (validation only)**: for each line, checks productId
     present, quantity is a positive integer, product exists, product is
     `active`, and the *running* requested-per-product total stays within
     `product.stock`. No mutations yet.
   - **Second pass (commit)**: builds `OrderItem` snapshots (sku, name,
     unit price, line total), then decrements stock by the aggregated
     amount per product, then calls `quote(items, customer.tier)`.
   - Builds the `Order`, status `pending`, `createdAt`/`updatedAt` = now,
     id from `generateId('order')`, persists via `orders.save`.
8. **Repository** (`repositories.ts`): `InMemoryOrderRepository.save`
   stores the entity in a `Map<string, Order>` and returns it.
9. The service returns the saved order back up to the controller, which
   serializes it to JSON. The `requestLogger`'s `finish` callback fires.
10. If anything along the way throws an `AppError`, `asyncHandler` /
    Express forwards it to `errorHandler`, which serializes
    `{ error: { code, message, details, requestId } }` with the matching
    HTTP status. Anything else becomes an opaque `500 INTERNAL_ERROR`.

The same shape applies to the other routes — controllers stay thin
(parse + delegate + status code), services own the rules, repositories own
storage.

---

## 3. How an order is priced

Source: `services/pricing.ts`, in `quote(items, tier)`.

Inputs and constants:

- `TIER_DISCOUNT`: `standard 0`, `silver 0.05`, `gold 0.10`.
- `VOLUME_DISCOUNT_THRESHOLD_CENTS = 50000` (i.e. $500.00) and
  `VOLUME_DISCOUNT_RATE = 0.05`.
- `MAX_DISCOUNT_RATE = 0.20`.
- `TAX_RATE = 0.08`.

Algorithm:

1. **Subtotal** = sum of every line's `lineTotalCents`
   (`quantity * unitPriceCents`).
2. **Effective discount rate** = `TIER_DISCOUNT[tier]`, plus
   `VOLUME_DISCOUNT_RATE` **iff** `subtotalCents >= 50000`, then
   `Math.min(rate, MAX_DISCOUNT_RATE)`.
3. **Discount cents** = `round(subtotal * rate)`.
4. **Taxable subtotal** = `subtotal − discount`.
5. **Tax cents** = `round(taxable * 0.08)`.
6. **Total** = `taxable + tax`.

Both `discountCents` and `taxCents` are independently `Math.round`-ed.

### Worked example — gold customer, 2× 27" Monitor (`prod_3` @ 31900¢)

- Lines: `[{ qty: 2, unit: 31900 }]` → `lineTotalCents = 63800`.
- `subtotalCents = 63800`.
- `tier = gold` → base rate `0.10`. `63800 >= 50000`, so **+0.05 volume**
  → 0.15. `min(0.15, 0.20) = 0.15`. **`appliedDiscountRate = 0.15`**.
- `discountCents = round(63800 * 0.15) = round(9570) = 9570`.
- `taxableCents = 63800 − 9570 = 54230`.
- `taxCents = round(54230 * 0.08) = round(4338.4) = 4338`.
- `totalCents = 54230 + 4338 = 58568`.

Result returned and persisted on the order:

```json
{
  "subtotalCents": 63800,
  "discountCents": 9570,
  "taxCents": 4338,
  "totalCents": 58568,
  "appliedDiscountRate": 0.15
}
```

### Where the cap matters

The cap is `MAX_DISCOUNT_RATE = 0.20`. With the current tier table the
maximum *raw* rate is `gold (0.10) + volume (0.05) = 0.15`, which is below
the cap, so the cap is currently never the binding constraint (see
"Risks" below).

---

## 4. Order status state machine

Defined in `services/orderService.ts`:

```ts
const ALLOWED_TRANSITIONS = {
  pending:   ['paid', 'cancelled'],
  paid:      ['shipped', 'cancelled'],
  shipped:   ['delivered'],
  delivered: [],
  cancelled: [],
};
```

- **Initial state** on `createOrder`: `pending`.
- **Valid transitions**:
  - `pending → paid`
  - `pending → cancelled`
  - `paid → shipped`
  - `paid → cancelled`
  - `shipped → delivered`
- **Terminal states**: `delivered` and `cancelled` (empty allowed-set).
- Any other transition (including `X → X` self-loops, `shipped → cancelled`,
  going backwards) is rejected with `ConflictError 409` —
  `Cannot transition order <id> from <status> to <next>`.
- The controller additionally rejects an unknown status string with
  `ValidationError 400` before the service is even called
  (`controllers.ts` checks against `VALID_STATUSES`).

### Side effects of a transition

- The only transition with a side effect is **→ `cancelled`**: `restock(order)`
  walks every line item and adds `item.quantity` back to that product's
  `stock`. If a product no longer exists in the repository, it's silently
  skipped.
- All other transitions just persist the new `status` and bump `updatedAt`.
- `paid` does **not** charge anything, `shipped` does **not** dispatch
  anything, `delivered` does **not** notify — they're purely state changes
  in this fixture.
- Note: stock is reserved at `createOrder` time (status `pending`), so a
  `pending → cancelled` cancellation also restocks (which is what you
  want — the order had inventory on hold).

---

## 5. How stock reservation avoids partial reservation

The key idea in `OrderService.createOrder` is **two passes**: validate
everything, only then mutate.

```ts
const resolved: Array<{ product: Product; quantity: number }> = [];
const requestedByProduct = new Map<string, number>();

for (const line of lines) {
  // ... shape checks ...
  const product = this.products.findById(line.productId);
  if (!product)            throw new NotFoundError(...);
  if (!product.active)     throw new ConflictError(...);

  const alreadyRequested = requestedByProduct.get(product.id) ?? 0;
  const totalRequested   = alreadyRequested + line.quantity;
  if (totalRequested > product.stock) {
    throw new ConflictError(`Insufficient stock for ${product.sku}: ...`);
  }
  requestedByProduct.set(product.id, totalRequested);
  resolved.push({ product, quantity: line.quantity });
}

// Only after every line passes do we touch state:
for (const [productId, qty] of requestedByProduct) {
  const product = this.products.findById(productId)!;
  this.products.save({ ...product, stock: product.stock - qty });
}
```

Why this protects inventory:

1. **No mutation in pass 1.** All checks (existence, active, quantity,
   stock) run against an unchanged catalog. Throwing on any line aborts
   `createOrder` before `products.save` is ever called, so partially
   reserving inventory is structurally impossible: either the whole order
   commits or the catalog is untouched.
2. **Aggregation across lines.** `requestedByProduct` accumulates demand
   per product *during* validation. If the same product appears on two
   lines (e.g. `[{prod_1, 30}, {prod_1, 25}]` against `stock = 50`), the
   second line sees `totalRequested = 55 > 50` and rejects the whole
   order. A naive per-line check would have let the first line "pass"
   conceptually and overdraw on commit.
3. **Single-shot stock decrement.** The commit loop subtracts the
   aggregated total per product once, instead of once per line — so the
   stored stock reflects the same number that was validated.

Caveat: this is only "atomic" in a single-process, synchronous-call sense.
Because everything between the read (`product.stock`) and the write
(`save({ ...product, stock: ... })`) is synchronous JS in a single event
loop, two `createOrder` invocations cannot interleave inside `createOrder`
itself. With a real async DB it would not be safe (see Risks).

---

## 6. Things that are confusing, risky, or likely to cause bugs

### Pricing / business logic

- **The 20% discount cap is unreachable.** The maximum raw rate the engine
  can produce is `gold (10%) + volume (5%) = 15%`. `MAX_DISCOUNT_RATE = 0.20`
  is therefore dead code today and silently masks any future bug where the
  rate accidentally goes over 15%. A unit test exercising the cap would never
  exercise it. (`services/pricing.ts:30,32-38`.)
- **Two-step rounding.** `discountCents` and `taxCents` are each
  `Math.round`-ed independently. For most realistic inputs this is fine,
  but it can produce results that differ by a cent from a "round once at
  the end" approach. Worth being explicit about in the spec.
- **Volume threshold compares to *raw* subtotal.** Customer-facing logic
  ("orders over $500 get an extra discount") is tied to pre-discount
  subtotal — that's a design choice, not a bug, but it's the kind of detail
  a future contributor will get wrong if it's not stated in product docs.

### State machine

- **No way to cancel a `shipped` order.** `shipped` transitions only to
  `delivered`. There's no path for "shipment lost / returned" that restocks
  inventory. If this is intentional, fine; if not, it's silently impossible
  to express.
- **No idempotency / no-op transition.** `paid → paid` (or any self-loop)
  returns 409, instead of being a safe no-op. Clients that retry a status
  PATCH after a flaky network will see a confusing conflict the second time.
- **`RESTOCKING_STATUSES` is a one-element array** that pretends to be
  extensible. If anyone adds another value (say `'returned'`) without
  reading `restock`, they get restocking but no other returned-state
  semantics. Minor over-engineering.

### Stock reservation

- **No concurrency control.** Synchronous in-memory ops happen to be safe
  today, but the moment the repositories become async (real DB, network),
  the read-then-write between stock check and `save` becomes a TOCTOU race
  — two concurrent orders for the same product can both pass validation
  and oversell. There is no row-level lock, optimistic-locking version
  field, or atomic decrement.
- **`restock` swallows missing products silently.** If a product has been
  removed from the catalog between order time and cancellation, that
  line's quantity is simply lost. No log, no error.

### HTTP / error handling

- **Two different "not found" code paths for products.**
  `ProductController.getById` writes its own `404` JSON literal that
  *does not include `requestId`* and skips the central error middleware,
  while `OrderController.getById` throws `NotFoundError` and goes through
  `errorHandler` (which *does* include `requestId`). Inconsistent envelope.
  (`http/controllers.ts:34-43` vs `services/orderService.ts:139-145` →
  `middleware.ts:69-100`.)
- **`notFound` middleware also drops `requestId`.** The fallback 404 for
  unmatched routes returns `{ error: { code, message } }` with no
  `requestId` — also inconsistent with `errorHandler`.
- **`requireString` doesn't trim.** It rejects whitespace-only strings,
  but returns the *un-trimmed* original. `requireString('  cust_1  ', …)`
  will pass validation and then fail `customers.findById`. Surprising for
  the caller.
- **`parseBoolean` only treats `'true'` / `'1'` as true.** `'yes'`, `'on'`,
  even `'TRUE'` are silently false, and any other string also reads as
  false. If a client sends `activeOnly=false`, the result is correct for
  the wrong reason — just because everything-except-`true`-or-`1` maps to
  false. (`http/parse.ts:37-42`.)
- **Controller doesn't validate quantity range.** `parseLineItems` only
  checks `typeof quantity === 'number'`, so `NaN`, `Infinity`, `0`,
  negatives, and floats all pass the controller and are caught one layer
  deeper in the service. Defense-in-depth is fine, but the controller-layer
  message would be more pinpointed.

### Identity / global state

- **`idCounter` is module-level.** `generateId` lives at module scope in
  `repositories.ts`, so it survives across `createApp()` calls and is
  shared across every "instance" of the app in the same process. In tests
  that build multiple apps this leaks, and ids aren't deterministic across
  runs of multiple suites.
- **Order ids start at `1001`, mixed across product/customer/order.** They
  share the same counter (`generateId('order')`, etc.), so the next id
  depends on whatever else has been created. Fine for a fixture, surprising
  if anyone relies on the prefix-numbering monotonicity per type.
- **`requestId` uses `Math.random`.** Adequate for log correlation,
  worth noting it's not unique under high load and not cryptographically
  meaningful.

### Auth / config

- **Default API key is `''` baked in source.** README documents it,
  but if `API_KEY` is not set in production, the server happily accepts
  ``. A real deployment should fail-closed when the env var is
  missing.
- **`apiKeyAuth` lets `HEAD` through** alongside `GET`. Probably fine, but
  worth confirming none of the routes have HEAD-implicit side effects
  (none do today).

### Persistence

- **In-memory only.** Restarting the process loses every order and resets
  the seeded stock. Documented, but relevant to anyone pointing a real
  client at it.
- **No `findAll` for customers.** No way to enumerate customers via the
  repo (or the API). Fine for a fixture, easy to forget when extending.

### Idempotency

- **`POST /orders` is not idempotent.** No idempotency key — replaying the
  same request creates a second order and reserves stock again.

### Pagination

- **No 404 / hint for past-the-end pages.** `GET /products?page=999`
  returns `{ data: [], total, totalPages, page: 999 }`. Conventionally
  fine, but a noisy client can't tell from the status code that they
  asked for nonsense.
