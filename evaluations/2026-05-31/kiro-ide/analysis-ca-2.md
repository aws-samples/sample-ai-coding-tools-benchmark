# Analysis: Why a 13-unit order of `prod_3` is rejected

Request under analysis:

```
POST /api/v1/orders
x-api-key: YOUR_API_KEY
Content-Type: application/json

{
  "customerId": "cust_1",
  "items": [{ "productId": "prod_3", "quantity": 13 }]
}
```

`cust_1` is the seeded gold-tier customer (Jane Doe). `prod_3` is the
27-inch monitor (`MON-027`), seeded with `stock: 12` and `active: true`.

## Request flow (where it gets all the way to)

1. `app.ts` mounts global middleware: `express.json` → `requestId` →
   `requestLogger`.
2. The path is `/api/v1/...` and the method is `POST`, so `apiKeyAuth`
   (`middleware.ts`) runs. With `x-api-key: `, this passes.
3. `routes.ts` dispatches `POST /orders` to `OrderController.create`,
   wrapped in `asyncHandler`.
4. `OrderController.create` (`http/controllers.ts`) calls `requireString`
   on `customerId` (passes) and `parseLineItems` on `items`. The single
   line is a well-formed object with a string `productId` and a numeric
   `quantity`, so parsing succeeds.
5. Control reaches `OrderService.createOrder` in
   `src/services/orderService.ts`.

## The exact module and check that rejects it

The rejection happens in `OrderService.createOrder`
(`src/services/orderService.ts`), inside the first validation pass over
the line items:

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

- `customer = cust_1` (found, gold) — passes the `NotFoundError` check.
- `lines.length === 1` — passes the empty-order `ValidationError` check.
- `line.quantity = 13`, integer and `> 0` — passes the quantity
  `ValidationError` check.
- `product = prod_3` exists and `product.active === true` — passes the
  `NotFoundError` and the inactive-product `ConflictError`.
- `alreadyRequested = 0`, so `totalRequested = 13`, and
  `product.stock = 12`. `13 > 12`, so the **stock check** throws.

The error thrown is:

```ts
new ConflictError('Insufficient stock for MON-027: requested 13, available 12')
```

Note: this happens during the *first* (validation-only) pass, before any
stock is decremented and before `pricing.quote` runs. The gold tier and
the resulting tier/volume discounts are never applied, because the
request never reaches that code path.

## HTTP status, error code, and response body

`ConflictError` is defined in `src/errors.ts` with:

- `statusCode = 409`
- `code = 'CONFLICT'`
- `details` is not set (the throw site passes no second argument).

`asyncHandler` forwards the rejection to Express's error pipeline, which
runs `errorHandler` in `src/middleware.ts`. `isAppError(err)` is true,
so the handler responds with the AppError's status and serializes:

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Insufficient stock for MON-027: requested 13, available 12",
    "requestId": "req_<timestamp>_<rand>"
  }
}
```

Status line: `HTTP/1.1 409 Conflict`.

A few details worth flagging:

- `details` is assigned `undefined`, so `JSON.stringify` omits it from
  the body entirely. The response will not contain a `details` field.
- `requestId` is the value attached by the `requestId` middleware
  (`req_<Date.now()>_<6 random base36 chars>`); the exact suffix varies
  per request.
- The `Content-Type` is `application/json; charset=utf-8` (Express's
  default for `res.json`).

## What would need to change for the order to succeed

The check is `totalRequested > product.stock` against `prod_3.stock = 12`.
To make this exact request go through, one of the following has to hold
*before* the request hits the service:

1. **Reduce the requested quantity to ≤ 12.** With `quantity: 12` (or
   less), `13 > 12` becomes `12 > 12` (false), the stock check passes,
   stock is decremented, and the order is priced and saved as `pending`.
   This is the only change available through the public API surface, as
   no endpoint exists to mutate product stock.
2. **Raise `prod_3.stock` to ≥ 13.** Stock is set in the seed in
   `src/repositories.ts` inside `createRepositories()`:

   ```ts
   products.save({
     id: 'prod_3',
     sku: 'MON-027',
     name: '27-inch Monitor',
     priceCents: 31900,
     stock: 12,
     ...
   });
   ```

   Bumping that `stock` value (e.g. to `13` or higher) and restarting
   the process would let the same payload succeed. There is no admin
   endpoint that can do this at runtime — `ProductService` is read-only
   and `routes.ts` exposes only `GET /products` and `GET /products/:id`.
3. **Cancel an existing order that reserved `prod_3` units.** When an
   order moves to `cancelled`, `OrderService.restock` returns each line
   item's quantity to product stock. If a previous order had reserved
   one or more units of `prod_3`, cancelling it would raise the
   available stock; combined with the seeded 12, that could reach 13.
   In a freshly booted process with no prior orders, this option is
   not available.

If the request did succeed (say with `quantity: 12`), pricing would
run with `tier = 'gold'`. Subtotal `12 × 31900 = 382800` cents is well
above the `VOLUME_DISCOUNT_THRESHOLD_CENTS` of `50000`, so the 10% gold
discount and the 5% volume discount stack to a 15% applied rate (still
under the 20% cap). That pricing path is never reached for the 13-unit
request.
