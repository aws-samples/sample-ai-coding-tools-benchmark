# `samples/sample-api` Analysis

## What the API Does

This is a small TypeScript/Express order-management REST API for a product
catalog, customers, inventory, and orders.

Its domain model is defined in `src/types.ts`:

- A `Product` has a SKU, name, price in integer cents, stock count, and active
  flag.
- A `Customer` has a loyalty tier: `standard`, `silver`, or `gold`.
- An `Order` belongs to a customer, contains product snapshots as line items,
  stores its calculated totals, and moves through a status lifecycle.
- An `OrderItem` copies the product's SKU, name, and price at checkout, so later
  product changes do not alter historical orders.

The API supports:

- Health checks.
- Listing, searching, filtering, and fetching products.
- Creating and fetching orders.
- Listing a customer's orders.
- Moving an order through its status lifecycle.

`src/repositories.ts` seeds two customers and four products. All data is kept in
memory and is lost when the process restarts.

## Layered Architecture and Request Flow

### Composition and process startup

1. `src/index.ts` is the process entry point. It calls `createApp()` and starts
   the HTTP listener.
2. `src/app.ts` is the composition root. It creates repositories, services, and
   controllers; registers middleware; mounts the router at `/api/v1`; and adds
   fallback error handlers.

The dependency graph assembled by `src/app.ts` is:

```text
repositories -> services -> controllers -> routes
```

### HTTP and middleware layer

`src/middleware.ts` handles cross-cutting HTTP behavior:

- `express.json()` in `src/app.ts` parses JSON bodies.
- `requestId` gives each request a correlation ID.
- `requestLogger` logs method, URL, status, and duration.
- `apiKeyAuth` permits public `GET`/`HEAD` requests but requires `x-api-key` for
  mutations.
- `asyncHandler` forwards thrown or rejected errors to Express's error path.
- `notFound` handles unmatched routes.
- `errorHandler` converts domain `AppError` instances into JSON HTTP errors and
  hides unexpected errors behind a generic 500 response.

`src/http/routes.ts` maps HTTP methods and paths to controller methods.

### Controller and parsing layer

`src/http/controllers.ts` translates HTTP inputs into service calls and service
results into responses. For example, `OrderController.create` extracts
`customerId` and line items, calls `OrderService.createOrder`, and returns HTTP
201.

`src/http/parse.ts` provides query/body parsing helpers for required strings,
booleans, and pagination. Controllers also perform shape validation, such as
checking that order items are objects with string product IDs and numeric
quantities.

### Business-service layer

- `src/services/productService.ts` implements catalog filtering, sorting, and
  pagination.
- `src/services/orderService.ts` validates orders, reserves/restocks stock,
  creates product snapshots, persists orders, and enforces status transitions.
- `src/services/pricing.ts` is a pure pricing engine that calculates discounts,
  tax, and totals.

The services depend on repository interfaces rather than concrete repository
classes.

### Storage layer and return path

`src/repositories.ts` defines repository interfaces and in-memory
implementations backed by `Map` objects. It owns entity storage, seed data, and
order ID generation.

A typical order-creation request flows as follows:

```text
POST /api/v1/orders
  -> middleware.ts: JSON parsing, request ID, logging, API-key check
  -> http/routes.ts: OrderController.create
  -> http/controllers.ts + http/parse.ts: parse and validate HTTP input
  -> services/orderService.ts: validate customer/products/stock and reserve stock
  -> services/pricing.ts: calculate the order totals
  -> repositories.ts: save changed products and the new order
  -> OrderService returns Order
  -> OrderController sends HTTP 201 JSON
  -> requestLogger records the completed response
```

Thrown domain errors travel back through `asyncHandler` to `errorHandler`,
which selects the declared HTTP status and error code.

## Order Pricing

All money is represented as integer cents. `src/services/pricing.ts` calculates
prices in this order:

1. Sum every line's `lineTotalCents` to get the subtotal.
2. Select the customer's tier discount:
   - standard: 0%
   - silver: 5%
   - gold: 10%
3. Add a 5% volume discount when the subtotal is at least 50,000 cents
   ($500.00).
4. Cap the combined discount rate at 20%.
5. Round the discount to the nearest cent.
6. Subtract the discount from the subtotal.
7. Apply 8% tax to the discounted amount, rounded to the nearest cent.
8. Add tax to the discounted amount to get the total.

Concrete example: a gold customer orders two 27-inch monitors at $319.00 each.

```text
Subtotal:                 2 * $319.00 = $638.00
Gold discount:                         10%
Volume discount:                        5%
Combined rate:                         15%
20% cap:                               no effect
Discount:                $638.00 * 15% = $95.70
Discounted taxable amount:             $542.30
Tax:                      $542.30 * 8% = $43.38
Final total:                           $585.68
```

The saved order records a subtotal of 63,800 cents, discount of 9,570 cents,
tax of 4,338 cents, total of 58,568 cents, and applied discount rate of `0.15`.

With the currently configured rules, the 20% cap is never reached: gold plus
volume is the maximum possible combination at 15%. The cap protects future
rule changes rather than affecting current orders.

## Order Status State Machine

`src/services/orderService.ts` defines these valid transitions:

| Current status | Allowed next status |
| --- | --- |
| `pending` | `paid`, `cancelled` |
| `paid` | `shipped`, `cancelled` |
| `shipped` | `delivered` |
| `delivered` | none |
| `cancelled` | none |

`delivered` and `cancelled` are terminal states. Repeating the same status is
also invalid because no status permits a transition to itself.

Every successful transition updates `updatedAt` and saves the new order.
Transitioning to `cancelled` additionally restocks every order line before
saving the cancelled order. Shipping and delivery have no other side effects.
Shipped orders cannot be cancelled.

The controller first rejects unknown status strings as a 400 validation error.
The service rejects known but invalid transitions as a 409 conflict.

## All-or-Nothing Stock Reservation

`OrderService.createOrder` uses two passes:

1. The validation pass resolves every product and checks every quantity,
   product existence, active status, and available stock without changing
   inventory.
2. Only after every line succeeds does the service build item snapshots,
   decrement stock, price the order, and save it.

The validation pass uses `requestedByProduct`, a map that accumulates requested
quantities by product ID. This matters when the same product appears more than
once: each occurrence is checked against the combined requested quantity, so
two individually valid lines cannot collectively exceed stock.

For example, if an order requests five keyboards and then an unavailable
product, validation throws on the second line before the five keyboards are
decremented. If it requests 30 keyboards twice while only 50 are available,
the second keyboard line is rejected because the accumulated request is 60.

This prevents partial reservation caused by invalid request lines in the
current synchronous in-memory implementation.

## Confusing, Risky, or Bug-Prone Areas

### Higher-risk behavior

- The stock reservation is only atomic across validation failures. Product
  stocks are saved one at a time before the order is saved. If a repository
  save fails midway, stock can be partially decremented or decremented without
  an order being recorded. The repository interfaces are described as
  swappable, but there is no transaction boundary for a real database.
- The check-then-decrement reservation strategy has no locking or conditional
  update. It is safe from interleaving in the current synchronous in-memory
  service, but concurrent requests against a shared production store could
  both observe the same available stock and oversell it.
- Cancellation restocks products before saving the cancelled order. If the
  order save fails, the order remains cancellable even though stock was already
  returned; retrying could add the stock again. A failure during multi-product
  restocking could also partially restock the order.
- Repository methods return stored objects and arrays containing stored object
  references. Callers can mutate persisted entities without calling `save`,
  weakening repository ownership and making accidental state changes possible.
- There is no customer-level authorization. All order details and customer
  order histories are publicly readable by ID; the API key only protects
  mutating HTTP methods.
- The default API key is the hard-coded value ``. Running this outside
  a demo environment without setting `API_KEY` leaves mutations protected by a
  publicly documented credential.

### Consistency and validation issues

- Malformed JSON is likely handled as an unexpected Express/body-parser error,
  producing the generic 500 response rather than a client-facing 400.
- `parseBoolean` treats every value other than `"true"` or `"1"` as false.
  Misspellings such as `activeOnly=treu` silently change query behavior instead
  of returning a validation error.
- `requireString` checks `trim()` only to decide whether a value is empty, but
  returns the original untrimmed string. IDs with surrounding spaces produce
  misleading not-found errors, and a padded status becomes an unknown status.
- `ProductController.getById` constructs its own 404 response instead of
  throwing `NotFoundError`. Unlike errors handled centrally, that response has
  no request ID, making the documented error envelope inconsistent.
- The README says all errors have a consistent envelope, but optional
  `details` is emitted as an `undefined` property and therefore omitted by JSON
  serialization; direct controller/fallback 404 responses also omit request
  IDs and details.
- Customer order history is not paginated and can grow without bound.

### Design and operational limitations

- Data is entirely in memory, so orders and stock changes disappear on restart
  and cannot be shared across processes.
- The module-level order ID counter is shared across every repository bundle in
  the process. Creating a fresh app resets data but does not reset IDs, which
  can make tests or repeated app construction less deterministic.
- There are no tests in this folder despite business rules involving rounding,
  duplicate product lines, status transitions, and restocking.
- Duplicate product inputs are aggregated for stock validation but remain
  separate order items. That is internally consistent, though clients may find
  the resulting order shape surprising.
- Restocking silently skips a product that no longer exists, leaving inventory
  unrecovered with no error or audit record.
- The comments describe line-item snapshots as immutable, but TypeScript types
  and repository behavior do not enforce immutability.
- The README setup command says `cd scenarios/sample-api`, while this project is
  located at `samples/sample-api`.
