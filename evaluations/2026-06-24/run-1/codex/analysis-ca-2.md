# Trace: rejected gold-tier order for 13 of prod_3

Request being traced:

```http
POST /api/v1/orders
```

with a valid API key and a body equivalent to:

```json
{
  "customerId": "cust_1",
  "items": [
    { "productId": "prod_3", "quantity": 13 }
  ]
}
```

## Where it is rejected

The rejection is in `src/services/orderService.ts`, inside `OrderService.createOrder`, during the first validation pass over the order lines.

The exact failing check is:

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

- `cust_1` exists and is seeded as tier `gold` in `src/repositories.ts`.
- `prod_3` exists, is active, and is seeded as `MON-027`, `27-inch Monitor`, `stock: 12`.
- The requested quantity is `13`.
- `alreadyRequested` is `0` for the single line.
- `totalRequested` becomes `13`.
- The stock check evaluates `13 > 12`, so it throws `ConflictError`.

No stock is decremented and no order is saved. The service intentionally performs this first pass before the second pass that builds snapshots, decrements stock, calls `quote(items, customer.tier)`, and persists the order.

The customer's gold tier is not what rejects the request. Gold tier only matters later in pricing, at the `quote(items, customer.tier)` call, and this request never reaches that line.

## HTTP status, error code, and body

`ConflictError` is defined in `src/errors.ts` with:

- HTTP status: `409`
- error code: `CONFLICT`

The route path is:

1. `src/app.ts` mounts the API router at `/api/v1` behind `apiKeyAuth`.
2. `src/http/routes.ts` maps `POST /orders` to `OrderController.create`.
3. `src/http/controllers.ts` parses `customerId` and `items`, then calls `OrderService.createOrder`.
4. `asyncHandler` in `src/middleware.ts` forwards the thrown `ConflictError` to `errorHandler`.
5. `errorHandler` serializes `AppError` instances as an `error` envelope.

The response status is:

```http
409 Conflict
```

The serialized response body looks like:

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Insufficient stock for MON-027: requested 13, available 12",
    "requestId": "req_<timestamp>_<random>"
  }
}
```

`requestId` is generated per request by `requestId` middleware, so its exact value is not deterministic. The error object constructed by `errorHandler` also includes `details: appErr.details` internally, but `ConflictError` is thrown without details, so JSON serialization omits the `details` property.

If the API key is missing or invalid, `apiKeyAuth` would reject earlier with `401 UNAUTHORIZED`; the trace above assumes the mutating request is authenticated so the order logic is reached.

## What would need to change for success

The blocking condition is only inventory: the order asks for 13 units while `prod_3` has 12 in stock.

Any of these would let the order pass this check:

- Request `quantity: 12` or less for `prod_3`.
- Increase `prod_3.stock` to at least `13` before placing the order.
- Change the business rule in `OrderService.createOrder` so `totalRequested > product.stock` no longer rejects the request, for example to support backorders. That would be a product behavior change because it permits overselling and could drive stock negative.

With sufficient stock and a valid API key/body, the request would continue into pricing with the gold-tier discount, decrement stock in the second pass, persist a `pending` order, and return `201 Created`.
