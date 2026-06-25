# sample-api — Code Analysis

A walkthrough of the `sample-api` project: what it does, how it is layered, how
orders are priced, the status state machine, the stock-reservation guarantee,
and a list of things that are confusing or likely to cause bugs.

---

## 1. What the API does and the domain it models

`sample-api` is a small **order-management REST API** (TypeScript + Express,
served under `/api/v1`). It models a tiny e‑commerce back office with three core
entities (`src/types.ts`):

- **Product** — a catalog item with a `sku`, `priceCents`, `stock` count, and an
  `active` flag.
- **Customer** — has a loyalty `tier` (`standard | silver | gold`) that drives
  automatic discounting.
- **Order** — a `customerId`, a `status`, an array of **line-item snapshots**, and
  a computed `totals` block plus `appliedDiscountRate`. Line items copy
  `unitPriceCents`, `sku`, and `name` from the product at creation time so later
  price changes don't rewrite history.

The functionality worth tracing across files:

- A **pricing engine** (tier discount + volume discount + cap + tax).
- A **stock-reservation flow** that is all-or-nothing.
- An **order status state machine** with side effects (restocking on cancel).

Storage is **in-memory** with a deterministic seed (2 customers, 4 products),
loaded at boot in `repositories.ts`. Money is always integer **cents** to avoid
float drift.

The HTTP surface (`README.md`, `http/routes.ts`):

| Method  | Path                            | Auth | Purpose                       |
| ------- | ------------------------------- | ---- | ----------------------------- |
| `GET`   | `/health`                       | none | Liveness (not under base path)|
| `GET`   | `/products`                     | none | List catalog (paged/filtered) |
| `GET`   | `/products/:id`                 | none | One product                   |
| `POST`  | `/orders`                       | key  | Create order                  |
| `GET`   | `/orders/:id`                   | none | Fetch order                   |
| `PATCH` | `/orders/:id/status`            | key  | Transition status             |
| `GET`   | `/customers/:customerId/orders` | none | Customer's order history      |

Auth rule (`middleware.ts`): `GET`/`HEAD` are public; mutations require an
`x-api-key` header matching `process.env.API_KEY`.

---

## 2. Layered architecture and request flow

The codebase is cleanly layered, with dependencies pointing inward
(HTTP → services → repositories). `app.ts` is the composition root that wires the
graph together — deliberately kept out of `index.ts` so tests can import the app
without binding a port.

```
index.ts            process entry — reads PORT, calls createApp(), listens
   │
app.ts              composition root — repos → services → controllers,
   │                registers middleware in order, mounts router under /api/v1
   ▼
middleware.ts       express.json → requestId → requestLogger → /health
   │                → apiKeyAuth (gate) → [router] → notFound → errorHandler
   ▼
http/routes.ts      URL patterns → controller methods, each wrapped in asyncHandler
   ▼
http/controllers.ts parse/validate input (via http/parse.ts), call a service,
   │                pick a status code — NO business logic
   ▼
services/           business logic
   ├─ orderService.ts   validation, stock reservation, state machine, restock
   ├─ pricing.ts        pure pricing (discount + tax), no I/O
   └─ productService.ts catalog filter/sort + pagination
   ▼
repositories.ts     in-memory Maps behind interfaces + deterministic seed data
```

Supporting modules: `types.ts` (domain model), `errors.ts` (typed `AppError`
hierarchy where each error carries a `statusCode` and a stable string `code`:
`ValidationError` 400, `UnauthorizedError` 401, `NotFoundError` 404,
`ConflictError` 409).

### Concrete trace: `POST /api/v1/orders`

1. **`index.ts`** boots the app via **`app.ts`** `createApp()`, which builds the
   dependency graph and starts listening.
2. **`middleware.ts`**: `express.json()` parses the body → `requestId` tags
   `req.id` (`req_<ts>_<rand>`) → `requestLogger` registers a `finish` listener
   (logs method/url/status/latency) → `apiKeyAuth` sees a non‑GET method and
   checks `x-api-key`; a mismatch forwards an `UnauthorizedError` (401).
3. **`http/routes.ts`**: `POST /orders` matches → `asyncHandler(orders.create)`
   (the wrapper routes any rejected promise to the error handler instead of
   crashing the process).
4. **`http/controllers.ts`** `OrderController.create`: pulls `customerId` (via
   `requireString` in **`http/parse.ts`**) and shape‑validates `items` via
   `parseLineItems` (array of `{ productId: string, quantity: number }`). No
   business decisions here.
5. **`services/orderService.ts`** `createOrder()`: validates the customer and
   every line, reserves stock all‑or‑nothing, builds line-item snapshots, calls
   **`services/pricing.ts`** `quote()` for totals, assigns an id via
   `generateId('order')`, and persists.
6. **`repositories.ts`**: `InMemoryProductRepository.save` (decrement stock) and
   `InMemoryOrderRepository.save` (store the order).
7. Back up the stack: the controller responds **`201`** with the order JSON. On
   any thrown `AppError`, **`errorHandler`** instead serializes
   `{ error: { code, message, details, requestId } }` with the declared status;
   unknown (non‑`AppError`) exceptions become an opaque **500 INTERNAL_ERROR**.

Read flows (`GET /products`, `GET /orders/:id`, …) follow the same path minus
auth and mutation. For `GET /products`, `ProductService.list` filters by
`activeOnly`/`search`, sorts by name, then paginates via `paginate`.

---

## 3. How an order is priced

Pricing lives entirely in the pure functions of `services/pricing.ts` (`quote()`
+ `discountRateFor()`), called once from `orderService.createOrder`. Constants:

- Tier discount: `standard` 0%, `silver` 5%, `gold` 10%.
- Volume discount: **+5%** when `subtotalCents ≥ 50000` (≥ $500), tested against
  the **pre-discount** subtotal and stacked on top of the tier discount.
- `MAX_DISCOUNT_RATE` = **20%** cap on the combined rate.
- `TAX_RATE` = **8%**, applied to the *post-discount* subtotal.

Order of operations (`quote()`) — discount first, tax second:

1. `subtotalCents` = sum of all `lineTotalCents` (each = `unitPriceCents × qty`).
2. `appliedDiscountRate` = `min(tierRate + (subtotal ≥ 50000 ? 0.05 : 0), 0.20)`.
3. `discountCents` = `round(subtotal × rate)`.
4. `taxableCents` = `subtotal − discountCents`.
5. `taxCents` = `round(taxable × 0.08)`.
6. `totalCents` = `taxable + taxCents`.

Discount and tax are each rounded independently with `Math.round`.

### Example A — below the volume threshold

Gold customer (`cust_1`) buys **2× Mechanical Keyboard** (`prod_1`, 8900¢):

| Step      | Calculation                                   | Cents                |
| --------- | --------------------------------------------- | -------------------- |
| Subtotal  | 8900 × 2                                       | 17,800               |
| Rate      | gold 0.10; 17,800 < 50,000 → no volume → 0.10  | —                    |
| Discount  | round(17800 × 0.10)                            | 1,780                |
| Taxable   | 17800 − 1780                                   | 16,020               |
| Tax       | round(16020 × 0.08)                            | 1,282                |
| **Total** | 16020 + 1282                                   | **17,302** ($173.02) |

### Example B — over the threshold, volume discount stacks

Gold customer buys **2× 27-inch Monitor** (`prod_3`, 31900¢):

| Step      | Calculation                                         | Cents                |
| --------- | --------------------------------------------------- | -------------------- |
| Subtotal  | 31900 × 2                                            | 63,800               |
| Rate      | gold 0.10 + volume 0.05 (≥ 50,000) = 0.15 (< 0.20)   | —                    |
| Discount  | round(63800 × 0.15)                                  | 9,570                |
| Taxable   | 63800 − 9570                                         | 54,230               |
| Tax       | round(54230 × 0.08) = round(4338.4)                  | 4,338                |
| **Total** | 54230 + 4338                                         | **58,568** ($585.68) |

**About the cap:** with the current tier table the maximum achievable raw rate is
gold (0.10) + volume (0.05) = **0.15**, so `Math.min(rate, 0.20)` never actually
clamps anything today. It only matters if a future tier or extra stacking discount
is added (see Risk #6). The README's claim that pricing "caps total discount at
20%" describes behavior that is currently unreachable.

---

## 4. Order status state machine

Defined by `ALLOWED_TRANSITIONS` in `orderService.ts` and enforced in
`updateStatus`:

```
pending ──▶ paid ──▶ shipped ──▶ delivered   (terminal)
   │         │
   └─────────┴──▶ cancelled                   (terminal)
```

| From        | Allowed next           |
| ----------- | ---------------------- |
| `pending`   | `paid`, `cancelled`    |
| `paid`      | `shipped`, `cancelled` |
| `shipped`   | `delivered`            |
| `delivered` | — (terminal)           |
| `cancelled` | — (terminal)           |

- **Terminal states:** `delivered` and `cancelled` — empty transition sets, no
  outgoing moves.
- **Not allowed:** skipping steps (`pending → shipped`), going backwards, no-op
  self-transitions (`paid → paid`), and — notably — **cancelling a `shipped`
  order** (only `pending`/`paid` may cancel, so stock is never returned after
  shipping).
- New orders always start in `pending` (set in `createOrder`).
- The controller (`OrderController.updateStatus`) first rejects values outside the
  five known statuses with a `ValidationError` (400); the service then decides
  whether a *known* status is a *legal* transition, throwing `ConflictError` (409)
  if not (404 first if the order doesn't exist).

**Side effect — restock on cancel.** `RESTOCKING_STATUSES = ['cancelled']`. When a
transition lands on `cancelled`, `updateStatus` calls `restock(order)` *before*
saving, adding each line item's `quantity` back to its product's `stock`. Because
`cancelled` is terminal and reachable only once, stock is credited **at most
once** — no double-credit. No other transition has an inventory side effect
(notably `paid` does not capture payment, `shipped` does not generate a shipment).
Every successful transition refreshes `updatedAt` and re-saves.

---

## 5. All-or-nothing stock reservation

`createOrder` (`orderService.ts:60`) is deliberately written in **two passes** so
an invalid line never leaves earlier lines partially reserved:

**Pass 1 — validate & resolve, no mutation.** For each line it checks that
`productId` is a string and `quantity` is a positive integer, looks up the product
(`NotFoundError` if missing), rejects inactive products (`ConflictError`), and
accumulates requested quantity per product in a `requestedByProduct` map. The
stock check compares the **running cumulative total** against `product.stock`,
throwing `ConflictError` on oversell. Crucially, **no stock is written during this
pass**, so a failure on any line aborts the request with inventory untouched.

**Pass 2 — commit (only reached if every line passed).** It builds the immutable
`OrderItem` snapshots, then decrements stock once **per product** (iterating the
deduplicated `requestedByProduct`, not once per line), prices via `quote(...)`,
and saves the order as `pending`.

A nice subtlety: per-product accumulation means **duplicate lines for the same
product are summed** before the stock check, so you can't slip past the limit by
splitting a request into multiple lines of the same SKU (e.g. two `prod_1 ×30`
lines against stock 50 are correctly rejected, 60 > 50).

> Caveat: this "atomicity" holds only because the runtime is single-threaded,
> synchronous, and in-memory — there is no real transaction or lock. See Risk #4.

---

## 6. Confusing, risky, or bug-prone areas

> No code was changed. These are observations for follow-up.

### Likely to cause real problems

1. **API-key handling contradicts the README and breaks test importability.** The
   README insists the key is a secret that is *not* read from plain config and
   sketches a `loadApiKey()` secrets-manager flow — but `middleware.ts` reads
   `process.env.API_KEY` directly **at module-load time** and `throw`s if unset.
   So the key *is* a plain env var, `loadApiKey()` is never wired in, and merely
   *importing* `app.ts` (which its own comment advertises for tests) crashes
   unless `API_KEY` is set. The key is captured once at import, so it can't be
   rotated without a restart.

2. **No authorization on order reads → IDOR / enumeration.** Auth is method-based,
   so `GET /orders/:id` and `GET /customers/:customerId/orders` need no key. Order
   ids are sequential and guessable (`order_1001`, `order_1002`, …) via the
   monotonic `generateId`, so anyone can walk ids and read any customer's full
   order history — an information-disclosure risk in a real system.

3. **Inconsistent error envelopes.** Three shapes exist despite the README
   promising one: the central `errorHandler` emits `{ code, message, details,
   requestId }`; `notFound` emits `{ code, message }` with no `requestId`; and
   `ProductController.getById` writes a 404 inline with no `requestId`, bypassing
   the typed-error path entirely (whereas `OrderController` 404s go through
   `NotFoundError`). Clients can't rely on a uniform shape. Throwing
   `NotFoundError` in those spots would unify it.

4. **Synchronous "atomicity" is fragile to future change.** The all-or-nothing
   guarantee holds only while `createOrder` stays fully synchronous on a single
   process. The interface-based repos explicitly invite swapping in an async/DB
   store — at which point the read-then-write of `stock` becomes a classic TOCTOU,
   and two concurrent orders could both pass Pass 1 and oversell in Pass 2. No
   locking or optimistic-concurrency guard exists.

5. **`PORT` parsing can silently bind a random port.** `index.ts` does
   `Number(process.env.PORT ?? 3000)`; a non-numeric `PORT` yields `NaN`, and
   `app.listen(NaN)` makes Node pick an arbitrary free port instead of failing
   fast.

### Confusing / smells (not necessarily bugs)

6. **The 20% discount cap is unreachable** with current constants (max attainable
   is 0.15). It reads as a guard that does nothing today and could silently mask a
   future constant change. Either the docs are misleading or it's an unfinished
   feature.

7. **Two-layer quantity validation with a permissive controller.**
   `parseLineItems` only checks `typeof quantity === 'number'`, so `1.5`, `-1`,
   `0`, `NaN`, `Infinity` all pass the controller; the *service* enforces
   `Number.isInteger && > 0`. Correct overall (rejected before any mutation), but
   the split is misleading and the friendly per-index controller message is
   bypassed.

8. **`parseBoolean` is asymmetric.** Only `'true'`/`'1'` are truthy; everything
   else (including `'yes'`) is false, so a malformed `activeOnly` silently includes
   inactive products — the seeded inactive `prod_4` appears in the default listing.

9. **`requireString` returns the un-trimmed value.** It rejects whitespace-only
   strings via `.trim()` but returns the original `value`, so a `customerId` like
   `" cust_1 "` passes validation and then fails the customer lookup with a 404
   rather than a 400 — a slightly confusing error for the caller.

10. **Duplicate product lines produce multiple `OrderItem`s** in the saved order
    (stock is still decremented once, correctly). Consumers expecting one line per
    product may be surprised.

11. **`restock` silently skips deleted products** (`findById` returning `undefined`
    is ignored). Harmless today (products are never deleted), but a latent
    inventory leak if deletion is ever added.

12. **Global mutable `idCounter`** (`repositories.ts`) is module-level and shared
    across `createRepositories()` calls, so two app instances in one process
    (tests) share it. Ids reset on restart, and there are no seeded *orders*, so
    the README's `PATCH .../order_1001` example only works after you create one.

13. **Asymmetric list shapes & unbounded inputs.** `GET /products` returns a paged
    `Page<T>` envelope but `GET /customers/:id/orders` returns a bare, unbounded
    array; `parsePagination` clamps `pageSize` to 100 but never bounds `page`;
    nothing caps `quantity` or line count beyond available stock; `express.json()`
    has no explicit body-size limit.

14. **Minor:** non-constant-time API-key comparison (`provided !== API_KEY`) is
    theoretically timing-attackable; `requestId` from `Date.now()` + 6 random chars
    isn't collision-proof under high concurrency; separately-rounded discount and
    tax (each `Math.round`) can drift a cent versus rounding once at the end; and
    `appliedDiscountRate` is a raw JS float (`0.1 + 0.05` stores as
    `0.150000000000000002`).
