# sample-api — Code Analysis

## 1. What the API does and the domain it models

`sample-api` is a small **order-management REST API** built with TypeScript and
Express. It models a simplified e-commerce backend with three core domain
entities:

- **Product** — a catalog item with a SKU, unit price (in integer cents),
  available stock, and an `active` flag.
- **Customer** — a buyer with a loyalty `tier` (`standard`, `silver`, `gold`)
  that drives automatic discounting.
- **Order** — a customer's purchase: a set of immutable line-item snapshots, a
  computed totals breakdown (subtotal, discount, tax, total), an applied
  discount rate, and a lifecycle `status`.

It exposes these operations (base path `/api/v1`):

| Method  | Path                            | Auth | Purpose                       |
| ------- | ------------------------------- | ---- | ----------------------------- |
| `GET`   | `/health`                       | none | Liveness probe (not under base) |
| `GET`   | `/products`                     | none | List catalog (paginated/filterable) |
| `GET`   | `/products/:id`                 | none | Fetch one product             |
| `POST`  | `/orders`                       | key  | Create an order               |
| `GET`   | `/orders/:id`                   | none | Fetch an order                |
| `PATCH` | `/orders/:id/status`            | key  | Transition an order's status  |
| `GET`   | `/customers/:customerId/orders` | none | List a customer's orders      |

Notable domain rules:
- Money is stored as integer **cents** to avoid floating-point drift.
- Order line items are **snapshots** (price/name copied at order time) so later
  product price changes don't rewrite history.
- Read requests are public; mutating requests require an `x-api-key` header.
- Storage is **in-memory** with a deterministic seed dataset (2 customers, 4
  products), suitable for a benchmark fixture.

## 2. Layered architecture and request flow

The app is layered top-to-bottom, with each layer depending only on the one
below it. Services depend on repository *interfaces*, not concrete classes, so
storage is swappable.

```
HTTP request
   │
   ▼  middleware.ts        requestId, requestLogger, apiKeyAuth, asyncHandler, errorHandler
   ▼  http/routes.ts       URL patterns → controller methods
   ▼  http/controllers.ts  parse + validate input, pick status codes (no business logic)
   ▼  http/parse.ts        typed parsing helpers (pagination, booleans, strings)
   ▼  services/            business logic
   │    ├─ orderService.ts   order creation, stock reservation, status state machine
   │    ├─ pricing.ts        pure pricing engine (discounts + tax)
   │    └─ productService.ts catalog filtering + pagination
   ▼  repositories.ts      in-memory storage + id generation + seed data
```

Supporting modules: `types.ts` (domain model), `errors.ts` (typed error
hierarchy with HTTP status + stable code), `app.ts` (composition root), and
`index.ts` (process entry point).

### Walkthrough: `POST /api/v1/orders`

1. **Entry / middleware** (`index.ts` → `app.ts` → `middleware.ts`):
   `index.ts` boots the app from `createApp()`. `app.ts` registers global
   middleware in order: `express.json()` (body parse) → `requestId` (tags the
   request) → `requestLogger` (logs on response finish). The `/api/v1` mount
   first runs `apiKeyAuth`, which—since `POST` is a mutation—checks the
   `x-api-key` header and throws `UnauthorizedError` if it doesn't match.
2. **Routing** (`http/routes.ts`): `buildRouter` maps `POST /orders` to
   `orderController.create`, wrapped in `asyncHandler` so any thrown error is
   forwarded to the central error handler.
3. **Controller** (`http/controllers.ts`): `OrderController.create` reads
   `customerId` (via `requireString`) and validates/normalizes `items` via the
   private `parseLineItems` (asserts array of `{productId: string,
   quantity: number}`). It calls `orderService.createOrder(...)` and responds
   `201` with the order JSON. The controller contains no business logic.
4. **Service** (`services/orderService.ts`): `createOrder` validates the
   customer and every line, reserves stock all-or-nothing, builds line-item
   snapshots, prices the order via `quote(...)` (`services/pricing.ts`),
   assembles the `Order`, and persists it.
5. **Repository** (`repositories.ts`): `InMemoryProductRepository.save`
   decrements stock; `generateId('order')` mints an id;
   `InMemoryOrderRepository.save` stores the order in a `Map`.
6. **Response back up**: the saved `Order` returns through the service to the
   controller, which serializes it with `res.status(201).json(order)`. On the
   way out, `requestLogger`'s `finish` handler logs method/path/status/latency.
   Any error thrown anywhere unwinds to `errorHandler`, which converts
   `AppError` subclasses into their declared status + code envelope (and
   anything else into an opaque `500`).

## 3. How an order is priced

Pricing lives in the pure functions of `services/pricing.ts`. The order of
operations is: compute subtotal → determine discount rate → apply discount →
tax the *discounted* amount → sum to total.

Key constants:
- Tier discount: `standard` 0%, `silver` 5%, `gold` 10%.
- Volume discount: +5% when subtotal ≥ `VOLUME_DISCOUNT_THRESHOLD_CENTS`
  (`50000` cents = $500). Stacked on top of tier discount.
- `MAX_DISCOUNT_RATE`: combined discount capped at 20%.
- `TAX_RATE`: flat 8%, applied to the post-discount subtotal.
- `roundCents` (Math.round) is applied to the discount amount and to the tax
  amount independently.

`discountRateFor(tier, subtotal)`:
```
rate = TIER_DISCOUNT[tier]
if subtotal >= 50000: rate += 0.05
return min(rate, 0.20)
```

`quote(items, tier)`:
```
subtotalCents = sum(lineTotalCents)
appliedDiscountRate = discountRateFor(tier, subtotalCents)
discountCents = round(subtotalCents * appliedDiscountRate)
taxableCents = subtotalCents - discountCents
taxCents = round(taxableCents * 0.08)
totalCents = taxableCents + taxCents
```

### Concrete example (where the cap actually bites)

Gold customer (`cust_1`) buys 2 × Mechanical Keyboard (`prod_1`,
`priceCents = 8900`):

- subtotal = 2 × 8900 = **17,800 cents** ($178.00)
- subtotal < 50,000, so no volume discount; rate = gold 10% = `0.10`
- discount = round(17800 × 0.10) = **1,780 cents**
- taxable = 17800 − 1780 = 16,020 cents
- tax = round(16020 × 0.08) = round(1281.6) = **1,282 cents**
- total = 16020 + 1282 = **17,302 cents** ($173.02)

Now an example that triggers both volume discount **and** the cap. Gold
customer buys 2 × 27-inch Monitor (`prod_3`, `priceCents = 31900`):

- subtotal = 2 × 31900 = **63,800 cents** ($638.00)
- subtotal ≥ 50,000 → rate = gold 10% + volume 5% = 15% (under the 20% cap)
- discount = round(63800 × 0.15) = **9,570 cents**
- taxable = 63800 − 9570 = 54,230 cents
- tax = round(54230 × 0.08) = round(4338.4) = **4,338 cents**
- total = 54230 + 4338 = **58,568 cents** ($585.68)

To show the cap engaging you'd need tier + volume to exceed 20%. With the
current tiers the max is gold 10% + volume 5% = 15%, so **the 20% cap is
currently unreachable** given the seeded tiers (see risks below).

## 4. Order status state machine

Defined in `orderService.ts` as `ALLOWED_TRANSITIONS`:

```
pending   → paid, cancelled
paid      → shipped, cancelled
shipped   → delivered
delivered → (none)   ← terminal
cancelled → (none)   ← terminal
```

Visual:
```
pending ──▶ paid ──▶ shipped ──▶ delivered
   │          │
   └────┬─────┘
        ▼
    cancelled
```

- **Terminal states:** `delivered` and `cancelled` — no further transitions.
- **Cancellation paths:** only `pending` and `paid` can be cancelled. A
  `shipped` order cannot be cancelled (must go to `delivered`).
- **Enforcement:** `updateStatus` looks up the allowed set for the current
  status; if `next` isn't in it, it throws `ConflictError` (HTTP 409).
- **Side effect — restocking:** `RESTOCKING_STATUSES = ['cancelled']`. When an
  order transitions to `cancelled`, `restock(order)` runs first, adding each
  line item's `quantity` back to the corresponding product's `stock` via
  `products.save`. Other transitions have no inventory side effect. After the
  side effect, the order is saved with the new status and an updated
  `updatedAt` timestamp.
- The controller also pre-validates that the requested status is one of the
  five known values (`VALID_STATUSES`), returning `VALIDATION_ERROR` (400) for
  unknown strings, before the service applies the transition rules.

## 5. All-or-nothing stock reservation

`createOrder` deliberately uses a **two-pass** algorithm so an invalid line
later in a multi-line order can't leave earlier lines partially reserved.

**First pass (validate + resolve, no mutation):**
- Iterates each line and validates shape (`productId` string, `quantity` a
  positive integer).
- Looks up the product; throws `NotFoundError` if missing, `ConflictError` if
  `!product.active`.
- Accumulates requested quantity **per product** in a `requestedByProduct`
  `Map`, so multiple lines referencing the same product are summed. The check
  `totalRequested > product.stock` uses the running total, catching the case
  where two lines individually fit but together exceed stock.
- On any failure it throws immediately — and because **no stock has been
  written yet**, nothing is left half-reserved.

**Second pass (commit):**
- Only runs if the entire first pass succeeded.
- Builds immutable `OrderItem` snapshots (copying sku/name/unit price).
- Decrements stock once per product (using the summed quantity from the map),
  then prices and saves the order.

So the invariant "validate everything before mutating anything" is what
prevents partial reservation. Because storage is a synchronous in-memory `Map`
and Node is single-threaded here, the two passes are effectively atomic for a
single request.

## 6. Confusing, risky, or bug-prone areas

> No code was changed. These are observations only.

1. **The 20% discount cap is unreachable.** Max tier (gold, 10%) + volume (5%)
   = 15% < `MAX_DISCOUNT_RATE` (20%). The cap and the test scenario it implies
   can never actually trigger with current tiers/rates — likely a latent
   intent (e.g., a future higher tier) or dead safeguard. Worth confirming.

2. **Validation logic is duplicated between controller and service.** The
   controller's `parseLineItems` checks `productId`/`quantity` types, and
   `OrderService.createOrder` re-checks them (plus positive-integer). The two
   diverge: the controller accepts any `number` quantity (including `0`,
   negative, or fractional), while the service rejects non-positive/non-integer
   quantities with a different error. Direct service callers and HTTP callers
   get different guarantees, and the messages differ.

3. **No transactional rollback if a later repository write fails.** The second
   pass writes stock decrements in a loop, then saves the order. With the
   in-memory `Map` this won't throw, but if the repository were swapped for a
   real database (as the interfaces invite), a failure mid-loop would leave
   stock partially decremented with no order recorded. The "atomicity" only
   holds for the current synchronous in-memory store.

4. **Stock reservation is not concurrency-safe in general.** The all-or-nothing
   guarantee relies on Node's single-threaded synchronous execution of the two
   passes. With an async/remote repository, two concurrent `createOrder` calls
   could both pass validation against the same stock and then both decrement
   (oversell). No locking/optimistic-concurrency mechanism exists.

5. **`requireString` allows whitespace-padded `status`/`customerId` through to
   downstream logic.** It trims for the empty check but returns the original
   (untrimmed) value. A `status` of `" paid"` would fail `VALID_STATUSES`
   (good), but a padded `customerId` would be used verbatim in a lookup and
   simply 404 — minor, but a source of confusing errors.

6. **API key is read at module load and compared with `!==`.** In
   `middleware.ts`, `API_KEY` is captured at import time; the comparison is a
   non-constant-time string compare (minor timing-side-channel concern) and the
   key comes straight from `process.env.API_KEY` despite the README advising a
   managed secret store. The README's guidance and the actual implementation
   diverge.

7. **No upper bound or overflow consideration on quantity/line totals.**
   `lineTotalCents = priceCents * quantity` and the subtotal `reduce` have no
   guard against very large quantities. Not a practical issue for the fixture,
   but `quantity` is only bounded to be a positive integer.

8. **`updateStatus` restocks before persisting, with no failure handling.** If
   `restock` partially completed and a later step failed (again, only relevant
   for a non-in-memory store), stock could be returned without the order
   actually moving to `cancelled`.

9. **`GET` endpoints are entirely public, including order/customer reads.**
   `apiKeyAuth` only gates non-GET methods, so `GET /orders/:id` and
   `GET /customers/:customerId/orders` expose order and customer data to anyone
   who can guess/enumerate sequential ids (`order_1001`, `cust_1`, ...). IDs are
   generated from a simple monotonic counter, making enumeration easy. This may
   be intentional for a benchmark, but it's a real authorization gap.

10. **Pagination `totalPages` vs. out-of-range pages.** `paginate` computes
    `totalPages` correctly, but requesting a `page` beyond the range just
    returns an empty `data` array rather than an error — acceptable, but callers
    might expect a 404 or a clamped page.

11. **`roundCents` applied independently to discount and tax** can produce
    half-cent rounding that doesn't reconcile against a single end-to-end
    computation. Consistent and centralized, but worth noting if exact
    reconciliation against an external system is ever required.
