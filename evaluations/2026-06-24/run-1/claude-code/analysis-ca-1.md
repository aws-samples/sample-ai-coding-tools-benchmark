# sample-api — Code Analysis

A walkthrough of the `sample-api` order-management service: what it does, how a
request flows through its layers, how pricing and the order state machine work,
how stock reservation stays all-or-nothing, and the rough edges worth knowing
about.

---

## 1. What the API does and the domain it models

`sample-api` is a small **order-management REST API** (TypeScript + Express,
in-memory storage). It models a tiny e-commerce back office with three core
entities (`src/types.ts`):

- **Product** — catalog item with `sku`, `priceCents`, `stock`, and an `active`
  flag.
- **Customer** — has a loyalty `tier` (`standard` / `silver` / `gold`) that
  drives automatic discounts.
- **Order** — a customer's purchase: a list of **line-item snapshots**, computed
  `totals`, the `appliedDiscountRate`, and a `status` that moves through a small
  state machine.

The interesting domain logic is concentrated in three areas: a **pricing engine**
(tier + volume discounts, a cap, then tax), an **all-or-nothing stock
reservation** flow on order creation, and an **order status state machine** with
side effects (restock on cancel).

Money is stored everywhere as integer **cents** (`Cents = number`) to avoid float
drift. Line items snapshot the product's name/SKU/price at order time, so later
price or catalog changes never rewrite historical orders. Persistence is in-memory
Maps, seeded at boot with 2 customers (`cust_1` gold, `cust_2` standard) and 4
products (`prod_4` inactive, zero stock). It's explicitly a benchmark fixture.

Endpoints (base path `/api/v1`, plus a public `/health`):

| Method  | Path                            | Auth | Purpose                       |
| ------- | ------------------------------- | ---- | ----------------------------- |
| `GET`   | `/products`                     | none | List catalog (paged/filtered) |
| `GET`   | `/products/:id`                 | none | Fetch one product             |
| `POST`  | `/orders`                       | key  | Create an order               |
| `GET`   | `/orders/:id`                   | none | Fetch an order                |
| `PATCH` | `/orders/:id/status`            | key  | Transition order status       |
| `GET`   | `/customers/:customerId/orders` | none | List a customer's orders      |

Auth is coarse: `GET`/`HEAD` are public; any other method requires an `x-api-key`
header matching `process.env.API_KEY`.

---

## 2. Layered architecture and request flow

The codebase is cleanly layered, and dependencies point inward (HTTP → services →
repositories). `app.ts` is the composition root that wires everything together,
intentionally separate from `index.ts` so tests can import the app without
binding a port.

```
index.ts            process entry — reads PORT, calls createApp(), listens
   │
app.ts              composition root — builds repos → services → controllers,
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
hierarchy with `statusCode` + stable `code`).

### Worked flow: `POST /api/v1/orders`

1. **`express.json()`** parses the body; **`requestId`** tags `req.id`;
   **`requestLogger`** registers a `finish` listener to log method/status/latency.
2. **`apiKeyAuth`** runs (mounted on `/api/v1`). Because this is a `POST`, it
   checks the `x-api-key` header; a mismatch forwards an `UnauthorizedError` (401).
3. **`routes.ts`** matches `POST /orders` and dispatches to
   `OrderController.create`, wrapped in **`asyncHandler`** so any throw/rejection
   reaches the central error handler instead of crashing the process.
4. **`OrderController.create`** (`controllers.ts`) pulls `customerId` via
   `requireString` and normalizes `items` via `parseLineItems` (shape-checking
   each entry), then calls `orderService.createOrder(...)`.
5. **`OrderService.createOrder`** (`orderService.ts`) validates the customer and
   every line, reserves stock all-or-nothing, builds item snapshots, calls
   `quote(...)` from **`pricing.ts`**, assigns an id via `generateId('order')`,
   and persists through **`OrderRepository.save`** (an in-memory `Map`).
6. The saved `Order` returns up the stack; the controller responds **`201`** with
   the order JSON.
7. On any thrown `AppError`, **`errorHandler`** serializes
   `{ error: { code, message, details, requestId } }` with the declared status;
   unknown errors become an opaque **500** (`INTERNAL_ERROR`). Unmatched routes
   hit `notFound`.

Read flows (`GET /products`, `GET /orders/:id`, etc.) follow the same path minus
auth and the state mutation: controller → service → repository → JSON. For
`GET /products`, `ProductService.list` filters by `activeOnly`/`search`, sorts by
name, then paginates via `paginate`.

---

## 3. How an order is priced

Pricing lives entirely in the pure functions of `pricing.ts`. `quote(items, tier)`
runs these steps **in this order** (order matters — discount first, tax second):

1. **Subtotal** = sum of all `lineTotalCents` (each = `unitPriceCents × quantity`).
2. **Discount rate** = `discountRateFor(tier, subtotal)`:
   - Start from the **tier discount**: `standard 0%`, `silver 5%`, `gold 10%`.
   - If `subtotal ≥ 50000` cents ($500), **add a 5% volume discount**. The
     threshold is tested against the **pre-discount** subtotal.
   - **Cap** the combined rate at `MAX_DISCOUNT_RATE = 20%`.
3. **Discount cents** = `round(subtotal × rate)`.
4. **Taxable** = `subtotal − discountCents`.
5. **Tax** = `round(taxable × 8%)` (`TAX_RATE = 0.08`), applied to the *discounted*
   amount.
6. **Total** = `taxable + tax`.

Discount and tax are each rounded independently with `Math.round`.
`appliedDiscountRate` is stored on the order for traceability.

### Concrete example A — below the volume threshold

Gold customer (`cust_1`) buys **2× Mechanical Keyboard** at 8900¢ each:

- Subtotal = `2 × 8900` = **17,800¢**
- Rate: gold 10%; 17,800 < 50,000 so no volume bonus → **0.10** (under 20% cap)
- Discount = `round(17800 × 0.10)` = **1,780¢**
- Taxable = `17800 − 1780` = **16,020¢**
- Tax = `round(16020 × 0.08)` = **1,282¢**
- **Total = 16,020 + 1,282 = 17,302¢** ($173.02)

### Concrete example B — over the threshold, volume discount stacks

Gold customer buys **2× 27-inch Monitor** at 31900¢ each:

- Subtotal = `2 × 31900` = **63,800¢** (≥ 50,000 → volume applies)
- Rate = gold 10% + volume 5% = **0.15** (still under the 20% cap)
- Discount = `round(63800 × 0.15)` = **9,570¢**
- Taxable = `63800 − 9570` = **54,230¢**
- Tax = `round(54230 × 0.08)` = **4,338¢**
- **Total = 54,230 + 4,338 = 58,568¢** ($585.68)

### About the cap

The 20% cap is **defensive but currently unreachable**: the maximum achievable
rate is gold (10%) + volume (5%) = **15%**. No tier/volume combination in the code
hits 20%, so `Math.min(rate, 0.20)` never actually clamps anything today. It only
matters if a future tier or additional stacking discount is added. (See risks.)

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

- **Terminal states:** `delivered` and `cancelled` — no transitions out.
- **Once `shipped`, it can no longer be cancelled** — only `delivered` is
  reachable, so stock is never returned after shipping.
- New orders start in `pending` (set in `createOrder`).
- An illegal transition (e.g. `pending → shipped`, a same-status `paid → paid`, or
  any move out of a terminal state) raises a **`ConflictError` (409)**. The
  controller first rejects unknown status strings with a **400**; the service
  decides whether a *known* status is a *legal* transition.

**Side effect — restock on cancel.** `RESTOCKING_STATUSES = ['cancelled']`. When a
transition lands on `cancelled`, `updateStatus` calls `restock(order)`, which adds
each line item's `quantity` back to its product's `stock`. Because `cancelled` is
terminal and reachable only once, stock is credited **at most once** — no
double-credit. Other transitions have no inventory side effect (notably `paid`
triggers no payment capture). Every transition refreshes `updatedAt` and re-saves.

---

## 5. All-or-nothing stock reservation

`createOrder` is deliberately written in **two passes** so that an invalid line
never leaves earlier lines partially reserved:

**Pass 1 — validate & resolve, no mutation.** For each line it checks:
productId is a string, quantity is a positive integer, the product exists
(`NotFoundError`), and the product is `active` (`ConflictError`). It accumulates
requested quantity per product in a `requestedByProduct` map and compares the
**running total** against `product.stock`, throwing `ConflictError` if any product
would be oversold. Crucially, **no stock is written during this pass.**

**Pass 2 — commit (only reached if every line passed).** It builds the immutable
`OrderItem` snapshots, then decrements stock once per product (iterating
`requestedByProduct`, not once per line), prices via `quote(...)`, and saves the
order as `pending`.

Because all validation/throwing happens before any write, a bad line in position 3
aborts the whole request with zero side effects — inventory is untouched.

A nice subtlety: the per-product accumulation means **duplicate lines for the same
product are summed** before the stock check, so you can't sneak past the limit by
splitting a request into multiple lines of the same SKU (e.g. two `prod_1 ×30`
lines against stock 50 are correctly rejected as 60 > 50).

> Caveat: the "atomic" guarantee holds only because the runtime is single-threaded,
> synchronous, and in-memory — there is no real transaction or lock. See risks.

---

## 6. Confusing / risky / bug-prone areas

Nothing below was changed — these are observations only.

### Likely to cause real problems

1. **API-key handling contradicts the README and breaks test importability.** The
   README says the key "is a secret and is **not** read from a plain configuration
   value" and sketches a `loadApiKey()` secrets-manager flow. But `middleware.ts`
   reads `process.env.API_KEY` directly **at module-load time** and `throw`s if
   unset. So the key *is* a plain env var, the documented `loadApiKey()` is never
   wired in, and merely *importing* `app.ts` (which its own comment advertises for
   tests) crashes unless `API_KEY` is set. The key is captured once at import, so
   it can't be rotated without a restart.

2. **No authorization on order reads → IDOR / enumeration.** Auth is method-based,
   so `GET /orders/:id` and `GET /customers/:customerId/orders` need no key. Order
   ids are sequential and guessable (`order_1001`, `order_1002`, …) via the
   monotonic `generateId`, so anyone can walk ids and read any customer's full
   order history — an information-disclosure risk in a real system.

3. **Inconsistent error envelopes.** Three shapes exist despite the README
   promising one: the central `errorHandler` emits `{ code, message, details,
   requestId }`; `notFound` emits `{ code, message }` with no `requestId`; and
   `ProductController.getById` writes a 404 inline with no `requestId`, bypassing
   the typed-error path entirely (while `OrderController` 404s go through
   `NotFoundError`). Clients can't rely on a uniform shape.

4. **Synchronous "atomicity" is fragile to future change.** The all-or-nothing
   guarantee holds only while `createOrder` stays fully synchronous on a single
   process. The interface-based design explicitly invites swapping in an async/DB
   store — at which point the read-then-write of `stock` becomes a classic TOCTOU,
   and two concurrent orders could both pass Pass 1 and oversell in Pass 2. No
   locking or optimistic-concurrency guard exists.

5. **`PORT` parsing can silently bind a random port.** `index.ts` does
   `Number(process.env.PORT ?? 3000)`; a non-numeric `PORT` yields `NaN`, and
   `app.listen(NaN)` makes Node pick an arbitrary free port instead of failing fast.

### Confusing / smells (not necessarily bugs)

6. **The 20% discount cap is unreachable** with current constants (max attainable
   is 0.15). It reads as a guard that does nothing today and could silently mask a
   future constant change.

7. **Two-layer quantity validation with a permissive controller.** `parseLineItems`
   only checks `typeof quantity === 'number'`, so `1.5`, `-1`, `0`, `NaN`,
   `Infinity` all pass the controller; the *service* enforces `Number.isInteger &&
   > 0`. Correct overall (rejected before any mutation), but the split is misleading
   and easy to drift, and the friendly per-index controller message is bypassed.

8. **`parseBoolean` is asymmetric.** Only `'true'`/`'1'` are truthy; everything
   else (including `'yes'`) is false, so a malformed `activeOnly` silently includes
   inactive products — the seeded inactive `prod_4` appears in the default listing.

9. **Separately-rounded discount and tax can drift a cent** versus rounding once at
   the end. Deliberate and centralized, but worth knowing when reconciling totals.

10. **Duplicate product lines produce multiple `OrderItem`s** in the saved order
    (stock is still decremented once, correctly). Consumers expecting one line per
    product may be surprised.

11. **`restock` silently skips deleted products** (`findById` returning `undefined`
    is ignored). Harmless today (products are never deleted), but a latent inventory
    leak if deletion is ever added.

12. **Global mutable `idCounter`** (`repositories.ts`) is module-level and shared
    across `createRepositories()` calls, so two app instances in one process (tests)
    share it. Ids also reset on restart and aren't coordinated with the hardcoded
    seed ids; there are no seeded *orders*, so the README's `PATCH .../order_1001`
    example only works after you create one.

13. **No upper bound on `quantity` or line count.** Only stock limits a line;
    nothing caps total order size.

14. **Minor:** non-constant-time API-key comparison (`provided !== API_KEY`) is
    theoretically timing-attackable; `requestId` from `Date.now()` + 6 random chars
    isn't collision-proof under high concurrency.
