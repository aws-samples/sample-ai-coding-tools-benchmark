# sample-api

A small but non-trivial **order-management REST API** written in TypeScript with
Express. It exists as a shared benchmark fixture: a realistic, layered codebase
that AI dev tools can be asked to explain, extend, refactor, and debug.

The domain is deliberately a little involved — a pricing engine, a stock
reservation flow, and an order status state machine — so that comprehension
prompts have real cross-file data flow to trace.

## Architecture

Requests flow top-to-bottom through clearly separated layers:

```
HTTP request
   │
   ▼
middleware.ts        request id, logging, API-key auth, async error forwarding
   │
   ▼
http/routes.ts       URL patterns ─▶ controller methods
   │
   ▼
http/controllers.ts  parse + validate input, choose status codes (no logic)
   │
   ▼
services/            business logic
   ├─ orderService.ts   order creation, stock reservation, state machine
   ├─ pricing.ts        pure pricing engine (discounts + tax)
   └─ productService.ts catalog filtering + pagination
   │
   ▼
repositories.ts      in-memory storage + seed data (swappable interfaces)
```

Supporting modules: `types.ts` (domain model), `errors.ts` (typed error
hierarchy), `app.ts` (composition root), `index.ts` (entry point).

## Setup

```bash
cd scenarios/sample-api
npm install
npm run dev       # start with ts-node on http://localhost:3000
# or
npm run build && npm start
```

Type-check without emitting: `npm run typecheck`.

### Configuration

| Variable | Default | Purpose                        |
| -------- | ------- | ------------------------------ |
| `PORT`   | `3000`  | Port the server listens on.    |

`PORT` is non-sensitive operational configuration and is safe to set via an
environment variable.

The API key is a secret and is **not** read from a plain configuration value.
See [Authentication](#authentication) for how it is resolved.

## Authentication

Read-only requests (`GET`) are public. Mutating requests (`POST`, `PATCH`)
require an `x-api-key` header matching the application's API key. The server
fails to start if no API key can be resolved.

### Managing the API key secret

Do not hardcode the key or commit it to source control. Retrieve it at startup
from a managed secrets service:

- AWS: [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/) or
  [AWS Systems Manager](https://docs.aws.amazon.com/systems-manager/latest/userguide/systems-manager-parameter-store.html)
  (SecureString).
- Other platforms: the equivalent managed secret store (for example HashiCorp
  Vault, Azure Key Vault, or GCP Secret Manager).

Example: load the key from AWS Secrets Manager at boot.

```ts
import {
  SecretsManagerClient,
  GetSecretValueCommand,
} from '@aws-sdk/client-secrets-manager';

/**
 * Resolve the API key from AWS Secrets Manager. The secret name is supplied
 * via API_KEY_SECRET_ID (a reference, not the secret itself). Fails closed
 * if the secret cannot be retrieved.
 */
export async function loadApiKey(): Promise<string> {
  const secretId = process.env.API_KEY_SECRET_ID;
  if (!secretId) {
    throw new Error('API_KEY_SECRET_ID environment variable is required');
  }

  const client = new SecretsManagerClient({});
  const { SecretString } = await client.send(
    new GetSecretValueCommand({ SecretId: secretId }),
  );
  if (!SecretString) {
    throw new Error(`Secret '${secretId}' did not return a value`);
  }
  return SecretString;
}
```

> Note: the IDs above (`API_KEY_SECRET_ID`, secret names, ARNs) are
> non-sensitive *references* used to look up the secret. The secret material
> itself is never stored in configuration or environment variables.

For purely local development you may still inject the key through the
environment, but treat that as a convenience that must not be used in shared or
production environments.

## Endpoints

Base path: `/api/v1`

| Method  | Path                              | Auth | Description                          |
| ------- | --------------------------------- | ---- | ------------------------------------ |
| `GET`   | `/health`                         | none | Liveness probe (not under base path).|
| `GET`   | `/products`                       | none | List catalog (paginated, filterable).|
| `GET`   | `/products/:id`                   | none | Fetch a single product.              |
| `POST`  | `/orders`                         | key  | Create an order.                     |
| `GET`   | `/orders/:id`                     | none | Fetch an order.                      |
| `PATCH` | `/orders/:id/status`              | key  | Transition an order's status.        |
| `GET`   | `/customers/:customerId/orders`   | none | List a customer's orders.            |

### Query params for `GET /products`

- `page` (default `1`), `pageSize` (default `20`, max `100`)
- `activeOnly` (`true`/`false`, default `false`)
- `search` — case-insensitive substring match on name and SKU

## Business rules worth knowing

- **Money** is stored as integer **cents** everywhere to avoid float drift.
- **Stock reservation** is all-or-nothing: an order is validated in full before
  any stock is decremented, so a bad line can't partially reserve inventory.
- **Pricing** applies a tier discount (`standard` 0%, `silver` 5%, `gold` 10%),
  adds a 5% volume discount over a threshold, caps total discount at 20%, then
  applies 8% tax to the discounted subtotal.
- **Order status** follows `pending → paid → shipped → delivered`, with
  `pending`/`paid` also able to move to `cancelled`. Cancelling restocks items.

## Seed data

Two customers (`cust_1` gold, `cust_2` standard) and four products
(`prod_1`..`prod_4`, the last inactive with zero stock) are loaded at boot.

## Example requests

```bash
# Browse the active catalog
curl "http://localhost:3000/api/v1/products?activeOnly=true&search=mouse"

# Create an order for the gold-tier customer
curl -X POST http://localhost:3000/api/v1/orders \
  -H 'content-type: application/json' \
  -H 'x-api-key: YOUR_API_KEY' \
  -d '{"customerId":"cust_1","items":[{"productId":"prod_1","quantity":2}]}'

# Advance an order to paid
curl -X PATCH http://localhost:3000/api/v1/orders/order_1001/status \
  -H 'content-type: application/json' \
  -H 'x-api-key: YOUR_API_KEY' \
  -d '{"status":"paid"}'
```

## Error shape

All errors return a consistent envelope:

```json
{
  "error": {
    "code": "CONFLICT",
    "message": "Insufficient stock for KEYB-001: requested 60, available 50",
    "requestId": "req_..."
  }
}
```

Codes: `VALIDATION_ERROR` (400), `UNAUTHORIZED` (401), `NOT_FOUND` (404),
`CONFLICT` (409), `INTERNAL_ERROR` (500).
