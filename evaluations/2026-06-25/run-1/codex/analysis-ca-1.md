# sample-api analysis

## What the API does

`sample-api` is a small TypeScript/Express order-management REST API. It models a simple commerce domain:

- `Product`: catalog items with SKU, name, unit price in cents, stock count, and active/inactive state.
- `Customer`: buyers with a loyalty tier of `standard`, `silver`, or `gold`.
- `Order`: a customer's order with line-item snapshots, computed totals, current status, and timestamps.

The API supports:

- Health checks at `GET /health`.
- Product catalog reads at `GET /api/v1/products` and `GET /api/v1/products/:id`.
- Order creation at `POST /api/v1/orders`.
- Order reads at `GET /api/v1/orders/:id`.
- Order status updates at `PATCH /api/v1/orders/:id/status`.
- Customer order history at `GET /api/v1/customers/:customerId/orders`.

Read requests are public. Mutating requests are guarded by `apiKeyAuth` and require `x-api-key`.

## Layered architecture and request flow

The project is organized as a conventional layered API:

1. Process entry
   - `src/index.ts` reads `PORT`, calls `createApp()`, and starts the Express listener.

2. Composition root
   - `src/app.ts` builds the dependency graph:
     - `createRepositories()` from `src/repositories.ts`
     - `ProductService` from `src/services/productService.ts`
     - `OrderService` from `src/services/orderService.ts`
     - `ProductController` and `OrderController` from `src/http/controllers.ts`
     - route table from `src/http/routes.ts`
   - It also registers global middleware and mounts the API router under `/api/v1`.

3. Middleware
   - `src/middleware.ts` provides:
     - `requestId`: assigns a request id.
     - `requestLogger`: logs method, URL, status, and duration.
     - `apiKeyAuth`: allows `GET` and `HEAD`, requires `x-api-key` for mutations.
     - `asyncHandler`: forwards thrown/rejected handler errors.
     - `notFound`: emits a route-level 404.
     - `errorHandler`: serializes `AppError` instances and unexpected errors.

4. Routing
   - `src/http/routes.ts` maps URL patterns to controller methods:
     - `/products` and `/products/:id` to `ProductController`.
     - `/orders`, `/orders/:id`, `/orders/:id/status`, and `/customers/:customerId/orders` to `OrderController`.

5. Controllers and parsing
   - `src/http/controllers.ts` translates HTTP requests into service calls and chooses HTTP response codes.
   - `src/http/parse.ts` validates primitive request values such as pagination, booleans, and required strings.
   - Controllers intentionally do not contain core business logic.

6. Services
   - `src/services/productService.ts` handles catalog filtering, sorting, and pagination.
   - `src/services/orderService.ts` handles customer/order validation, stock reservation, order creation, order lookup, customer order history, and order status transitions.
   - `src/services/pricing.ts` is a pure pricing engine for subtotal, discounts, tax, and total.

7. Repository/storage layer
   - `src/repositories.ts` defines repository interfaces and in-memory implementations backed by `Map`.
   - It also provides `generateId()` and `createRepositories()`, which seeds products and customers.
   - Services depend on repository interfaces, so the storage implementation is swappable in principle.

### Example: create-order request flow

For `POST /api/v1/orders`:

1. Express receives the request in `src/app.ts`.
2. `express.json()` parses the body.
3. `requestId` and `requestLogger` run.
4. The request enters `/api/v1`, where `apiKeyAuth` verifies `x-api-key` because this is a mutating request.
5. `src/http/routes.ts` routes `POST /orders` to `OrderController.create`.
6. `OrderController.create` in `src/http/controllers.ts` validates `customerId` and parses `items`.
7. `OrderService.createOrder` in `src/services/orderService.ts`:
   - Loads the customer from `CustomerRepository`.
   - Validates every requested line against `ProductRepository`.
   - Checks active status and sufficient stock.
   - Reserves stock by decrementing product records.
   - Builds order item snapshots.
   - Calls `quote()` in `src/services/pricing.ts`.
   - Saves the order through `OrderRepository`.
8. The saved order is returned through the controller as a `201` JSON response.
9. If a service throws an `AppError`, `errorHandler` turns it into the standard error envelope.

## How an order is priced

Pricing is implemented in `src/services/pricing.ts`. Money is stored as integer cents.

The order of operations is:

1. Compute `subtotalCents` as the sum of all `lineTotalCents`.
2. Compute a tier discount:
   - `standard`: 0%
   - `silver`: 5%
   - `gold`: 10%
3. Add a 5% volume discount when subtotal is at least `50000` cents ($500.00).
4. Cap the combined discount rate at `MAX_DISCOUNT_RATE`, which is 20%.
5. Round `subtotalCents * appliedDiscountRate` to get `discountCents`.
6. Compute `taxableCents = subtotalCents - discountCents`.
7. Apply 8% tax to `taxableCents`, rounded to the nearest cent.
8. Compute `totalCents = taxableCents + taxCents`.

Concrete example using seeded data:

- Customer: `cust_1`, a `gold` customer.
- Items: 2 x `prod_3`, the 27-inch Monitor.
- Unit price: `31900` cents ($319.00).
- Subtotal: `2 * 31900 = 63800` cents ($638.00).
- Tier discount: gold gives 10%.
- Volume discount: subtotal is at least $500.00, so add 5%.
- Combined discount before cap: `10% + 5% = 15%`.
- Cap check: `min(15%, 20%) = 15%`, so the cap does not reduce this order.
- Discount: `63800 * 0.15 = 9570` cents ($95.70).
- Taxable subtotal: `63800 - 9570 = 54230` cents ($542.30).
- Tax: `54230 * 0.08 = 4338.4`, rounded to `4338` cents ($43.38).
- Total: `54230 + 4338 = 58568` cents ($585.68).

The current configured discounts cannot actually reach the 20% cap: the maximum is gold 10% plus volume 5%, or 15%. The cap still matters as a guardrail if new tiers or discount rules are added later. For example, if a future rule produced a 25% combined rate on the same $638.00 subtotal, the cap would limit the discount to `63800 * 0.20 = 12760` cents ($127.60), not $159.50.

## Order status state machine

The status model is defined in `src/types.ts` and enforced by `ALLOWED_TRANSITIONS` in `src/services/orderService.ts`.

Valid statuses:

- `pending`
- `paid`
- `shipped`
- `delivered`
- `cancelled`

Valid transitions:

| Current status | Allowed next statuses |
| --- | --- |
| `pending` | `paid`, `cancelled` |
| `paid` | `shipped`, `cancelled` |
| `shipped` | `delivered` |
| `delivered` | none |
| `cancelled` | none |

Terminal states:

- `delivered`
- `cancelled`

Side effects:

- Orders are created in `pending`.
- Moving to `paid`, `shipped`, or `delivered` only updates the order status and `updatedAt`.
- Moving to `cancelled` restocks every order item by adding its quantity back to the corresponding product's stock.
- Cancellation is only reachable from `pending` or `paid`. A `shipped` order cannot be cancelled.
- Invalid transitions throw a `ConflictError`.

## All-or-nothing stock reservation

`OrderService.createOrder` avoids partial stock reservation with a two-pass process.

First pass: validate without mutation.

- It validates the customer exists.
- It validates the `lines` array is present and non-empty.
- For each line, it checks:
  - `productId` exists and is a string.
  - `quantity` is a positive integer.
  - the product exists.
  - the product is active.
  - total requested quantity for that product does not exceed stock.
- It stores resolved products and quantities in `resolved`.
- It also accumulates requested quantities in `requestedByProduct`, so duplicate lines for the same product are checked against combined stock.

Second pass: mutate only after the whole order is known to be valid.

- It builds immutable order item snapshots from the resolved products.
- It loops over `requestedByProduct` and decrements product stock once per product.
- It prices and saves the order.

This means a multi-line order cannot reserve the first product and then fail on the second product. For example, if an order requests 1 keyboard and then 1 inactive discontinued cable, the inactive cable check throws before any product stock is saved.

## Confusing, risky, or likely bug-prone areas

- The README says the API key should be resolved from a managed secret and not from a plain configuration value, but the implementation reads `process.env.API_KEY` directly in `src/middleware.ts`.

- `API_KEY` is read at module import time in `src/middleware.ts`. Importing the app without `API_KEY` set throws immediately, which can make tests or tooling fail before they can construct an app.

- `express.json()` is registered before `requestId`. If JSON parsing fails, the central error handler can return an `INTERNAL_ERROR` without a request id instead of a client-friendly validation error.

- Invalid JSON is not mapped to `ValidationError`; body-parser syntax errors are treated as unexpected errors by `errorHandler`, so malformed JSON likely becomes a 500 instead of a 400.

- `ProductController.getById` manually returns a 404 JSON shape instead of throwing `NotFoundError`. That response lacks `requestId` and is inconsistent with the central error envelope used elsewhere.

- `parseBoolean` treats anything other than `true` or `1` as false. A typo such as `activeOnly=yes` or `activeOnly=treu` silently changes behavior instead of producing a validation error.

- The volume discount threshold is implemented as `subtotalCents >= 50000`, while the README describes the discount as applying "over a threshold." If "over" is meant literally, an exactly $500.00 order currently receives the volume discount.

- The 20% discount cap is unreachable with the current discount table because the largest possible configured discount is 15%. That is not a runtime bug, but it can confuse readers expecting a seeded or normal scenario to demonstrate the cap.

- Repositories return stored object references directly. With the current code this is mostly controlled, but future code could accidentally mutate repository state without calling `save`.

- Stock reservation is all-or-nothing inside the current synchronous in-memory service. If repositories are later made asynchronous or backed by a real database, the stock check and decrement need a transaction or conditional update to avoid overselling under concurrent requests.

- Cancellation restocks products before saving the updated order status. In memory this is unlikely to fail, but with real persistence the restock and status update should be atomic.

- `restock()` silently skips missing products. If products can ever be deleted or hidden from the repository before cancellation, inventory may not be restored even though the order becomes `cancelled`.

- Duplicate product lines are allowed. Stock checks and stock decrement aggregate them correctly, but the final order keeps duplicate line items rather than merging them. That may be fine, but clients may not expect it.

- `totalPages` is `0` for empty product-list results while the returned `page` can still be `1` or greater. Some API clients expect at least one page, so this convention should be documented if intentional.
