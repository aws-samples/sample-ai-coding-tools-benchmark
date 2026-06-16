# POST `/api/v1/orders`: gold customer ordering 13 monitors

Assuming the request has the required valid `x-api-key` and a valid body such as:

```json
{
  "customerId": "cust_1",
  "items": [
    {
      "productId": "prod_3",
      "quantity": 13
    }
  ]
}
```

## Rejection trace

1. `src/app.ts` mounts `apiKeyAuth` and the API router at `/api/v1`.
2. `src/http/routes.ts` routes `POST /orders` to `OrderController.create`.
3. `src/http/controllers.ts` parses `customerId` and the line items, then calls
   `OrderService.createOrder(customerId, items)`.
4. In `src/services/orderService.ts`, `createOrder` finds `cust_1`, which exists
   and has the `gold` tier. It then finds `prod_3`.
5. `src/repositories.ts` seeds `prod_3` as the active `MON-027` 27-inch monitor
   with `stock: 12`.
6. The rejecting check is in `src/services/orderService.ts`:

   ```ts
   const alreadyRequested = requestedByProduct.get(product.id) ?? 0;
   const totalRequested = alreadyRequested + line.quantity;
   if (totalRequested > product.stock) {
     throw new ConflictError(
       `Insufficient stock for ${product.sku}: requested ${totalRequested}, available ${product.stock}`,
     );
   }
   ```

   For this request, `totalRequested` is `13` and `product.stock` is `12`, so
   `13 > 12` is true. `OrderService` throws:

   ```text
   ConflictError("Insufficient stock for MON-027: requested 13, available 12")
   ```

The rejection occurs during the first validation pass, before stock is changed,
before an order is saved, and before `quote()` in `src/services/pricing.ts` is
called. Therefore, the customer's gold-tier discount has no effect on whether
the order is accepted.

## HTTP response

`ConflictError` is defined in `src/errors.ts` with HTTP status `409` and error
code `CONFLICT`. The central `errorHandler` in `src/middleware.ts` serializes it.

The response status is:

```text
409 Conflict
```

The response body is:

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Insufficient stock for MON-027: requested 13, available 12",
    "requestId": "req_<timestamp>_<random-suffix>"
  }
}
```

The handler includes a `details` property whose value is `undefined`; JSON
serialization omits that property. The exact `requestId` varies per request
because `requestId` middleware generates it from the current time and a random
suffix.

## What must change for the order to succeed

The stock check requires the total quantity requested for `prod_3` across all
lines in the request to be no greater than its current stock.

- Reduce the requested quantity from `13` to `12` or less; or
- Increase the current stock of `prod_3` from `12` to at least `13` before
  submitting the order.

If the intended business rule is to allow backorders, the
`totalRequested > product.stock` rejection in `OrderService.createOrder` and the
subsequent stock-decrement behavior would need to be redesigned. Changing the
customer tier or pricing rules alone cannot make this request succeed.
