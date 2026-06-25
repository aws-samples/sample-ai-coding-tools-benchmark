# sample-api — Code Analysis

A walkthrough of the `samples/sample-api` project based on reading every source
file under that folder.

## 1. What the API does and the domain it models

`sample-api` is a small **order-management REST API** built with TypeScript and
Express. It is intentionally non-trivial — it carries a pricing engine, a stock
reservation flow, and an order status state machine — so it can serve as a
benchmark fixture for code-comprehension tasks.

The domain has three core entities (defined in `src/types.ts`):

- **Product** — a catalog item with `sku`, `name`, `priceCents`, `stock`, and an
  `active` flag.
- **Customer** — has a loyalty `tier` (`standard` | `silver` | `gold`) that
  drives automatic discounting.
- **Order** — references a customer, carries a `status`, an array of
  **OrderItem** snapshots (price/sku/name copied at checkout so later price
  changes don't rewrite history), computed `totals`, and the
  `appliedDiscountRate`.

Money is consistently stored as **integer cents** (`Cents = number`) to avoid
floating-point drift.

Endpoints (base path `/api/v1`, see `src/http/routes.ts`):

| Method  | Path                            | Auth | Purpose                         |
| ------- | ------------------------------- | ---- | ------------------------------- |
| `GET`   | `/health`                       | none | Liveness probe (off base path). |
| `GET`   | `/products`                     | none | Paginated/filterable catalog.   |
| `GET`   | `/products/:id`                 | none | Single product.                 |
| `POST`  | `/orders`                       | key  | Create an order.                |
| `GET`   | `/orders/:id`                   | none | Fetch an order.                 |
| `PATCH` | `/orders/:id/status`            | key  | Transition order status.        |
| `GET`   | `/customers/:customerId/orders` | none | Customer order history.         |

Mutating requests (`POST`/`PATCH`) require an `x-api-key` header; reads are
public. Seed data loads two customers (`cust_1` gold, `cust_2` standard) and
four products (`prod_1`..`prod_4`, the last inactive with zero stock).

## 2. Layered architecture and request flow

Construction happens in the composition root `src/app.ts`, which builds the
dependency graph **repositories → services → controllers**, wires middleware in
order, mounts the router under `/api/v1`, and returns the app.
`src/index.ts` is just the process entry point that calls `createApp()` and
listens.

A request flows top-to-bottom:

1. **`src/middleware.ts`** — `express.json()` body parsing, then `requestId`
   (tags each request with `req_<ts>_<rand>` for log/error correlation),
   `requestLogger` (logs method/url/status/latency on response finish), and
   `apiKeyAuth` (mounted on `/api/v1`; lets `GET`/`HEAD` through, requires a
   matching `x-api-key` on everything else).
2. **`src/http/routes.ts`** — `buildRouter` maps URL patterns to controller
   methods. Every handler is wrapped in `asyncHandler` so thrown/rejected
   errors are forwarded to Express's error pipeline instead of crashing.
3. **`src/http/controllers.ts`** (`ProductController`, `OrderController`) — pure
   HTTP glue. They parse and validate input (using helpers in
   **`src/http/parse.ts`**: `parsePagination`, `parsePositiveInt`,
   `parseBoolean`, `requireString`), call a service, and choose status codes
   (e.g. `201` on order creation). No business logic lives here.
4. **`src/services/`** — business logic:
   - **`orderService.ts`** (`OrderService`) — order creation, stock
     reservation, and the status state machine.
   - **`pricing.ts`** — a pure pricing engine (`quote`, `discountRateFor`).
   - **`productService.ts`** (`ProductService`) — catalog filtering, sorting,
     and pagination (`paginate`).
5. **`src/repositories.ts`** — in-memory storage (`InMemoryProductRepository`,
   `InMemoryCustomerRepository`, `InMemoryOrderRepository`) behind interfaces,
   plus `generateId` and the `createRepositories` seed loader. Services depend
   on the *interfaces*, so the store could be swapped for a database without
   touching business logic.

Supporting modules: `src/types.ts` (domain model) and `src/errors.ts` (typed
`AppError` hierarchy: `ValidationError` 400, `UnauthorizedError` 401,
`NotFoundError` 404, `ConflictError` 409, plus a 500 fallback).

**Response path on error:** any `AppError` thrown deep in a service bubbles up
through `asyncHandler` to the central `errorHandler` in `middleware.ts`, which
serializes a consistent `{ error: { code, message, details, requestId } }`
envelope using the error's declared `statusCode`/`code`. Unknown errors become
an opaque `500 INTERNAL_ERROR`. On success the controller writes the service
result via `res.json(...)`.

Example happy path for `POST /api/v1/orders`:
`json body → apiKeyAuth → routes → OrderController.create → parseLineItems →
OrderService.createOrder → quote() + repository saves → 201 + order JSON`.

## 3. How an order is priced

Pricing lives in `src/services/pricing.ts` and is invoked once during
`OrderService.createOrder` via `quote(items, customer.tier)`.

Constants:

- Tier discount: `standard` 0%, `silver` 5%, `gold` 10%.
- Volume discount: **+5%** when `subtotalCents >= 50000` (i.e. $500.00).
- `MAX_DISCOUNT_RATE = 0.20` — combined discount cap.
- `TAX_RATE = 0.08` — flat 8% applied **after** discount.

`discountRateFor(tier, subtotal)` = `min(tierRate + (volume ? 0.05 : 0), 0.20)`.

`quote` then computes, in this order:

1. `subtotalCents` = sum of `lineTotalCents`.
2. `discountCents` = `round(subtotalCents * appliedDiscountRate)`.
3. `taxableCents` = `subtotalCents - discountCents`.
4. `taxCents` = `round(taxableCents * TAX_RATE)`.
5. `totalCents` = `taxableCents + taxCents`.

Rounding is centralized in `roundCents` (`Math.round`), applied separately to
discount and tax.

### Worked example A — gold customer, below volume threshold

`cust_1` (gold) orders 2 × `prod_1` (Mechanical Keyboard @ 8900 cents):

- subtotal = 2 × 8900 = **17800**
- tier = gold 0.10; subtotal 17800 < 50000 → no volume discount; cap not hit →
  rate = **0.10**
- discount = round(17800 × 0.10) = **1780**
- taxable = 17800 − 1780 = **16020**
- tax = round(16020 × 0.08) = round(1281.6) = **1282**
- total = 16020 + 1282 = **17302** ($173.02)

### Worked example B — gold customer, above volume threshold

`cust_1` (gold) orders 2 × `prod_3` (27-inch Monitor @ 31900 cents):

- subtotal = 2 × 31900 = **63800** (≥ 50000 → volume discount applies)
- rate = 0.10 (gold) + 0.05 (volume) = 0.15; below the 0.20 cap → **0.15**
- discount = round(63800 × 0.15) = round(9570) = **9570**
- taxable = 63800 − 9570 = **54230**
- tax = round(54230 × 0.08) = round(4338.4) = **4338**
- total = 54230 + 4338 = **58568** ($585.68)

> Note: with the current rates the **0.20 cap can never actually bind** — the
> maximum reachable rate is gold (0.10) + volume (0.05) = 0.15. See risks below.

## 4. Order status state machine

Defined in `src/services/orderService.ts` as `ALLOWED_TRANSITIONS` and enforced
by `updateStatus`:

```
pending ─▶ paid ─▶ shipped ─▶ delivered
   │        │
   └────────┴─▶ cancelled
```

| From        | Allowed next        |
| ----------- | ------------------- |
| `pending`   | `paid`, `cancelled` |
| `paid`      | `shipped`, `cancelled` |
| `shipped`   | `delivered`         |
| `delivered` | — (terminal)        |
| `cancelled` | — (terminal)        |

- **Terminal states:** `delivered` and `cancelled` (empty transition sets).
- An order can only be cancelled while `pending` or `paid` — once `shipped` it
  must proceed to `delivered`, and cannot be cancelled (so shipped goods aren't
  restocked).
- **Side effect:** transitioning to `cancelled` (the only member of
  `RESTOCKING_STATUSES`) runs `restock(order)`, which adds each line item's
  quantity back to the corresponding product's `stock`. This happens *before*
  the order is saved with the new status.
- Any disallowed transition (or a transition out of a terminal state) throws a
  `ConflictError` (409). New orders always start in `pending`.
- Controller-side, `OrderController.updateStatus` rejects unknown status strings
  with a `ValidationError` (400) before the service is even called.

Double-restock is prevented structurally: once an order is `cancelled` it's
terminal, so `cancelled → cancelled` is rejected and `restock` cannot run twice.

## 5. All-or-nothing stock reservation

`OrderService.createOrder` deliberately uses **two passes** so a bad line cannot
partially reserve inventory:

**Pass 1 — validate and resolve, no mutation.** For every input line it:
- validates `productId` is a string and `quantity` is a positive integer;
- looks up the product (`NotFoundError` if missing);
- rejects inactive products (`ConflictError`);
- accumulates requested quantity per product in a `requestedByProduct` map and
  checks the **running total** against `product.stock`, throwing a
  `ConflictError` if `totalRequested > stock`.

Crucially, **no stock is decremented during pass 1** — only validation and an
in-memory tally. If any line fails, the method throws and nothing has been
mutated, so earlier lines are never left half-reserved.

The per-product accumulation also handles **duplicate lines for the same
product correctly**: two lines of the same product are summed before the stock
check, so you can't sneak past the limit by splitting a request across lines.

**Pass 2 — commit (only reached if pass 1 fully succeeds).** It builds immutable
`OrderItem` snapshots, then decrements stock once per product using the
aggregated `requestedByProduct` totals, prices the order via `quote`, and
persists it with status `pending`.

Because Node executes this synchronous code on a single thread, there's no
interleaving between the validation and commit passes within one request.

## 6. Things that are confusing, risky, or likely to cause bugs

**Pricing**

- **The discount cap is dead code.** `MAX_DISCOUNT_RATE = 0.20` can never bind:
  the highest achievable rate is gold (0.10) + volume (0.05) = 0.15. Either the
  tier/volume rates are wrong, or the cap is aspirational. A reader could waste
  time reasoning about a cap that never triggers.
- **Separate rounding of discount and tax** can produce off-by-a-cent results
  versus rounding once at the end. It's internally consistent, but worth knowing
  when reconciling totals.

**Authentication / security**

- **README vs. code mismatch on the API key.** The README strongly states the
  key must come from a managed secret store and is "not read from a plain
  configuration value," yet `middleware.ts` reads `process.env.API_KEY`
  directly. The documented `loadApiKey()`/Secrets Manager flow isn't wired in.
- **Import-time throw.** `middleware.ts` throws at module load if `API_KEY` is
  unset. Since `app.ts` imports it, `createApp()` (and any test importing the
  app) cannot run without `API_KEY` in the environment — surprising for a module
  whose stated goal is to be importable by tests without binding a port.
- **Non-constant-time key comparison** (`provided !== API_KEY`) is technically
  timing-attack-prone (minor for this fixture).
- **Reads are fully public, including order data.** `GET /orders/:id` and
  `GET /customers/:customerId/orders` require no auth, so anyone who can guess or
  enumerate the sequential ids (`order_1001`, `cust_1`, ...) can read other
  customers' orders — an IDOR / information-disclosure concern. IDs are
  generated by a simple monotonic counter (`generateId`), which makes
  enumeration trivial.

**Validation inconsistencies**

- **Quantity is validated in two places with different rigor.** The controller's
  `parseLineItems` only checks `typeof quantity === 'number'`, which lets
  `0`, negatives, floats, `NaN`, and `Infinity` through; `OrderService` then
  rejects them via `Number.isInteger(...) && > 0`. It works, but the duplicated
  responsibility and differing error messages (controller says `items[index]`,
  service says `product <id>`) are confusing.
- **Inconsistent 404 error envelopes.** `ProductController.getById` builds a
  `404` JSON inline *without* a `requestId`, the `notFound` middleware likewise
  omits `requestId`, while the central `errorHandler` includes it. Clients get
  different error shapes depending on the path.

**Other**

- **`listByCustomer` is unbounded.** Unlike the product catalog, customer order
  history returns a raw array with no pagination — fine for seed data, but it
  could grow without limit.
- **No rollback after stock is decremented.** In pass 2, stock is mutated before
  `quote`/`generateId`/`save`. These can't realistically throw with the
  in-memory store, but if the repository were swapped for a database (the stated
  design goal), a failure after the decrement would leak reserved stock with no
  compensating transaction. The "all-or-nothing" guarantee only holds for pass 1.
- **No concurrency safety for a real backend.** The two-pass reservation relies
  on Node's single-threaded synchronous execution. The moment repositories
  become async (DB), two concurrent orders could both pass validation and
  oversell stock — there's no locking or optimistic-concurrency check.
- **`requestId` uses `Math.random`**, so ids are non-cryptographic and could
  collide; fine for log correlation, not for anything security-sensitive.
- **Pagination doesn't clamp `page` to `totalPages`.** A large `page` yields an
  empty `data` array rather than an error — acceptable, but undocumented.
