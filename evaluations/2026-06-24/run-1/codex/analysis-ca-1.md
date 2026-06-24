# sample-api analysis

## What the API does and the domain it models

`sample-api` is a TypeScript/Express order-management REST API for a small
commerce domain. It exposes a product catalog, order creation, order lookup,
customer order history, and order status transitions.

The domain model is defined in `src/types.ts`:

- `Product`: catalog item with `sku`, `name`, `priceCents`, `stock`, `active`,
  and `createdAt`.
- `Customer`: buyer with `name`, `email`, and a loyalty `tier` of `standard`,
  `silver`, or `gold`.
- `Order`: a purchase belonging to a customer, with status, line-item snapshots,
  computed totals, the applied discount rate, and timestamps.
- `OrderItem`: a snapshot of product data at checkout. It stores the product
  id, SKU, name, quantity, unit price, and line total so later product price
  changes do not rewrite historical orders.

Storage is in memory. `src/repositories.ts` seeds four products and two
customers at startup. Money is represented as integer cents.

The public API is mounted under `/api/v1`, except `/health`:

- `GET /health`
- `GET /api/v1/products`
- `GET /api/v1/products/:id`
- `POST /api/v1/orders`
- `GET /api/v1/orders/:id`
- `PATCH /api/v1/orders/:id/status`
- `GET /api/v1/customers/:customerId/orders`

Read-only `GET`/`HEAD` requests are public. Mutating requests require an
`x-api-key` header matching `process.env.API_KEY`.

## Layered architecture and request flow

The project is organized as a conventional layered API:

```text
HTTP request
  -> src/index.ts
  -> src/app.ts
  -> src/middleware.ts
  -> src/http/routes.ts
  -> src/http/controllers.ts + src/http/parse.ts
  -> src/services/*
  -> src/repositories.ts
  -> response or src/middleware.ts errorHandler
```

### Modules by layer

- Entry point: `src/index.ts`
  - Reads `PORT`, calls `createApp()`, and starts `app.listen`.

- Composition root: `src/app.ts`
  - Creates repositories with `createRepositories()`.
  - Creates `ProductService` and `OrderService`.
  - Creates `ProductController` and `OrderController`.
  - Registers middleware and mounts routes under `/api/v1`.

- Middleware: `src/middleware.ts`
  - `requestId` attaches a request id.
  - `requestLogger` logs method, URL, status, and latency.
  - `apiKeyAuth` gates non-GET/non-HEAD requests.
  - `asyncHandler` forwards thrown/rejected route errors.
  - `notFound` handles unmatched routes.
  - `errorHandler` serializes `AppError` instances and unknown errors.

- Routing: `src/http/routes.ts`
  - Maps URL patterns to controller methods.
  - Wraps handlers with `asyncHandler`.

- Controllers and parsing: `src/http/controllers.ts`, `src/http/parse.ts`
  - Controllers translate HTTP input into service calls and service results into
    HTTP responses.
  - Parsing helpers validate pagination, booleans, required strings, and order
    line item shape.

- Services: `src/services/productService.ts`, `src/services/orderService.ts`,
  `src/services/pricing.ts`
  - `ProductService` handles catalog filtering, sorting, and pagination.
  - `OrderService` handles order creation, inventory reservation, order lookup,
    customer order history, and the status state machine.
  - `pricing.ts` is pure pricing logic: subtotal, discounts, tax, and total.

- Storage: `src/repositories.ts`
  - Defines repository interfaces and in-memory `Map` implementations.
  - Owns id generation via `generateId`.
  - Seeds deterministic product/customer data.

- Shared types and errors: `src/types.ts`, `src/errors.ts`
  - `types.ts` defines the domain model.
  - `errors.ts` defines `AppError`, `ValidationError`, `UnauthorizedError`,
    `NotFoundError`, and `ConflictError`.

### Example flow: `POST /api/v1/orders`

1. `src/index.ts` starts the Express app created by `src/app.ts`.
2. `src/app.ts` has already built repositories, services, controllers, and the
   router.
3. `express.json()` parses the body.
4. `requestId` assigns `req.id`.
5. `requestLogger` registers logging for when the response finishes.
6. `/health` is checked first, then `/api/v1` middleware runs.
7. `apiKeyAuth` rejects the request with `UnauthorizedError` unless the
   non-GET request has a matching `x-api-key`.
8. `src/http/routes.ts` routes `POST /orders` to `OrderController.create`.
9. `OrderController.create` uses `requireString` for `customerId` and
   `parseLineItems` for the `items` array.
10. `OrderService.createOrder` validates the customer and all lines, checks
    stock, builds order item snapshots, decrements product stock, prices the
    order with `quote`, creates an order id with `generateId('order')`, and
    saves the order.
11. `InMemoryProductRepository.save` persists stock changes and
    `InMemoryOrderRepository.save` stores the order.
12. The controller responds with HTTP 201 and the order JSON.
13. If any service/controller layer throws an `AppError`, `errorHandler`
    serializes it as an error response. Unknown errors become 500 responses.

## How an order is priced

Pricing is implemented in `src/services/pricing.ts`.

Constants:

- Tier discount:
  - `standard`: 0%
  - `silver`: 5%
  - `gold`: 10%
- Volume discount: +5% when the pre-discount subtotal is at least 50,000 cents
  ($500).
- Discount cap: maximum combined discount rate is 20%.
- Tax: 8% on the post-discount subtotal.

The order of operations in `quote` is:

1. Sum line totals into `subtotalCents`.
2. Compute `appliedDiscountRate` with `discountRateFor`.
3. Compute `discountCents = Math.round(subtotalCents * appliedDiscountRate)`.
4. Compute `taxableCents = subtotalCents - discountCents`.
5. Compute `taxCents = Math.round(taxableCents * 0.08)`.
6. Compute `totalCents = taxableCents + taxCents`.

Concrete example: gold customer buys 2 monitors.

- Product: `prod_3`, 27-inch Monitor, 31,900 cents each.
- Quantity: 2.
- Subtotal: `31,900 * 2 = 63,800` cents.
- Tier discount: gold = 10%.
- Volume discount: subtotal is at least 50,000 cents, so add 5%.
- Combined rate before cap: `10% + 5% = 15%`.
- Cap: max is 20%, so 15% is allowed unchanged.
- Discount: `Math.round(63,800 * 0.15) = 9,570` cents.
- Taxable subtotal: `63,800 - 9,570 = 54,230` cents.
- Tax: `Math.round(54,230 * 0.08) = Math.round(4,338.4) = 4,338` cents.
- Total: `54,230 + 4,338 = 58,568` cents, or `$585.68`.

With the current constants, the 20% cap is not reachable because the highest
possible configured discount is gold 10% plus volume 5%, for 15%. The cap only
matters if another discount source or a higher tier discount is added later.

## Order status state machine

The state machine is defined in `ALLOWED_TRANSITIONS` in
`src/services/orderService.ts`.

Valid transitions:

```text
pending -> paid
pending -> cancelled
paid -> shipped
paid -> cancelled
shipped -> delivered
```

Terminal states:

- `delivered`
- `cancelled`

Invalid transitions include:

- `pending -> shipped`
- `pending -> delivered`
- `paid -> delivered`
- `shipped -> cancelled`
- any transition out of `delivered`
- any transition out of `cancelled`
- any no-op transition such as `paid -> paid`

New orders are created as `pending`.

`OrderController.updateStatus` first validates that the requested status is one
of the known `OrderStatus` values. Then `OrderService.updateStatus` checks
whether the transition is allowed from the current state. Unknown statuses are
400 `ValidationError`s; known-but-illegal transitions are 409 `ConflictError`s.

Side effects:

- Transitioning to `cancelled` restocks inventory. `updateStatus` calls
  `restock(order)` before saving the new status, and `restock` adds each order
  line quantity back to the matching product.
- Successful transitions update `updatedAt` and save the order.
- No other transition has a side effect. `paid`, `shipped`, and `delivered` only
  change status and `updatedAt`.

Because only `pending` and `paid` can transition to `cancelled`, and
`cancelled` is terminal, a normal order can be restocked at most once.

## How stock reservation avoids partial inventory changes

`OrderService.createOrder` uses a two-pass flow.

Pass 1 validates and resolves all input without mutating storage:

- Confirms the customer exists.
- Confirms `lines` is a non-empty array.
- For each line:
  - validates `productId`;
  - validates `quantity` is a positive integer;
  - loads the product;
  - rejects missing products;
  - rejects inactive products;
  - accumulates requested quantity per product in `requestedByProduct`;
  - checks the cumulative requested quantity against current stock.

No stock is decremented during this first pass. If any line in a multi-line
order is invalid, missing, inactive, or over stock, the method throws before any
repository save happens.

Pass 2 runs only after every line has passed validation:

- Builds immutable `OrderItem` snapshots from the resolved products.
- Iterates `requestedByProduct` and decrements each product once by the total
  requested quantity.
- Prices the order.
- Saves the order.

The per-product accumulation matters for duplicate lines. If the request has
two lines for the same product, the stock check uses the combined quantity, so a
caller cannot bypass stock limits by splitting one product across multiple
lines.

This is all-or-nothing for the current synchronous in-memory implementation. It
is not a database transaction and would need concurrency control if storage
became asynchronous, shared, or multi-process.

## Confusing, risky, or likely bug sources

1. README/API-key behavior mismatch.
   The README says the API key should be loaded from a managed secret and not
   from plain configuration. The implementation reads `process.env.API_KEY`
   directly in `src/middleware.ts` at module load and throws if it is missing.
   That also makes importing the app fail unless the environment variable is
   already set.

2. Public order reads are risky.
   `apiKeyAuth` allows all `GET` requests without authentication, including
   `GET /orders/:id` and `GET /customers/:customerId/orders`. Order ids are
   sequential (`order_1001`, `order_1002`, etc.), so real customer order data
   would be easy to enumerate.

3. Error response shape is inconsistent.
   Most errors go through `errorHandler` and include `code`, `message`,
   `details`, and `requestId`. But `notFound` omits `requestId`, and
   `ProductController.getById` writes its own 404 response instead of throwing
   `NotFoundError`.

4. Stock reservation is not concurrency-safe outside this in-memory setup.
   `createOrder` checks stock and later writes stock without a lock or compare
   and swap. Two concurrent requests against a real shared database could both
   pass validation and then oversell.

5. The 20% discount cap is currently unreachable.
   The maximum current discount is 15%, so the cap may give readers the
   impression there are discount combinations that do not actually exist.

6. `parseBoolean` silently treats malformed values as false.
   Only `'true'` and `'1'` become true. Values such as `'yes'`, `'false'`, and
   arbitrary strings are accepted as false rather than rejected.

7. Quantity validation is split in a surprising way.
   `OrderController.parseLineItems` only checks that `quantity` is a number.
   `OrderService.createOrder` later rejects non-integers, zero, and negative
   values. The behavior is correct overall, but validation responsibility is
   split across layers.

8. `requireString` does not return a trimmed value.
   A value like `" cust_1 "` is non-empty after trimming, so it passes required
   string validation, but the returned original string will fail lookup as a
   404 instead of a cleaner 400.

9. Duplicate product lines remain duplicated in the saved order.
   Stock is handled correctly by summing per product, but the order's `items`
   array still contains separate line snapshots. That may surprise clients that
   expect one order item per product.

10. Restock silently skips missing products.
    `restock` ignores a missing product. Products are never deleted today, but
    if deletion were added later, cancelling an old order could fail to return
    inventory without surfacing an error.

11. Global id generation is process-local and reset-prone.
    `idCounter` is a module-level variable in `repositories.ts`. It resets on
    process restart and is shared across multiple app/repository bundles in the
    same process.

12. `PORT` parsing is loose.
    `src/index.ts` uses `Number(process.env.PORT ?? 3000)`. A non-numeric value
    becomes `NaN`, which can lead to surprising listen behavior rather than a
    clear configuration failure.

13. Some response shapes are asymmetric.
    Product listing returns a paginated `Page<Product>`, while customer order
    history returns a bare `Order[]`. That may be fine for a toy API, but it is
    a likely consistency issue if the API grows.

14. `middleware.ts` reads `API_KEY` during import.
    Besides the README mismatch, this makes test setup order fragile and means
    key rotation requires restarting the process.
