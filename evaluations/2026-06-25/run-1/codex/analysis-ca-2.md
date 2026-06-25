# Static trace: gold customer ordering 13 of prod_3

Request assumed:

```http
POST /api/v1/orders
x-api-key: <valid API key>
Content-Type: application/json
```

```json
{
  "customerId": "cust_1",
  "items": [
    { "productId": "prod_3", "quantity": 13 }
  ]
}
```

`cust_1` is the seeded gold-tier customer in `src/repositories.ts` lines 143-149.
`prod_3` is the seeded 27-inch monitor, SKU `MON-027`, with `stock: 12` and
`active: true` in `src/repositories.ts` lines 124-131.

## Where the request goes

`src/app.ts` mounts the API router under `/api/v1` behind `apiKeyAuth` at line 46.
For a POST, `apiKeyAuth` in `src/middleware.ts` lines 37-46 requires a matching
`x-api-key`; without it the request would be rejected earlier with 401
`UNAUTHORIZED`. With a valid key, routing continues.

`src/http/routes.ts` line 21 maps `POST /orders` to `OrderController.create`.
`OrderController.create` in `src/http/controllers.ts` lines 49-55 parses
`customerId`, normalizes the line items, then calls:

```ts
this.orders.createOrder(customerId, items);
```

## Exact rejecting module and check

The rejection happens in `src/services/orderService.ts`, inside
`OrderService.createOrder`, at the first-pass stock sufficiency check on lines
92-98:

```ts
const alreadyRequested = requestedByProduct.get(product.id) ?? 0;
const totalRequested = alreadyRequested + line.quantity;
if (totalRequested > product.stock) {
  throw new ConflictError(
    `Insufficient stock for ${product.sku}: requested ${totalRequested}, available ${product.stock}`,
  );
}
```

For this request:

- `alreadyRequested` is `0`
- `line.quantity` is `13`
- `totalRequested` is `13`
- `product.stock` is `12`
- `13 > 12` is true

So the service throws:

```ts
new ConflictError("Insufficient stock for MON-027: requested 13, available 12")
```

The earlier service checks pass: `cust_1` exists, the line array is non-empty,
quantity `13` is a positive integer, `prod_3` exists, and `prod_3.active` is
true. The gold tier does not affect this rejection because pricing via
`quote(items, customer.tier)` is later in the method, after the stock check.

Because the error is thrown during the first validation pass, the second pass is
never reached: no stock is decremented, no order item snapshots are built, no
pricing is calculated, and no order is persisted.

## HTTP status, error code, and body

`ConflictError` in `src/errors.ts` declares:

```ts
readonly statusCode = 409;
readonly code = 'CONFLICT';
```

The central `errorHandler` in `src/middleware.ts` lines 80-89 serializes
`AppError` instances using that status and code.

HTTP status:

```text
409 Conflict
```

Error code:

```text
CONFLICT
```

Response body shape:

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Insufficient stock for MON-027: requested 13, available 12",
    "requestId": "req_<timestamp>_<random>"
  }
}
```

`requestId` is generated per request by `requestId` middleware, so its exact
value is dynamic. The handler includes `details: appErr.details` internally, but
this `ConflictError` is created without details; JSON serialization omits the
`details` key because its value is `undefined`.

## What would need to change for success

The blocking condition is only inventory: requested quantity 13 exceeds available
stock 12.

The order would succeed if the request quantity for `prod_3` were reduced to 12
or less, or if `prod_3` stock were increased to at least 13 before the order is
created. A larger behavior change would be to relax/remove the
`totalRequested > product.stock` guard to allow backorders or overselling, but
that changes the API's inventory rule globally.

With the current code and a valid API key, gold tier, request parsing, product
existence, and product activity are all already satisfied; they are not the
cause of the rejection.
