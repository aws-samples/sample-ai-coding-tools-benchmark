/**
 * Route table. Wires URL patterns to controller methods. Handlers are wrapped
 * in asyncHandler so any thrown/rejected error reaches the central handler.
 */

import { Router } from 'express';
import { asyncHandler } from '../middleware';
import { OrderController, ProductController } from './controllers';

export function buildRouter(
  products: ProductController,
  orders: OrderController,
): Router {
  const router = Router();

  // Catalog (read-only, public).
  router.get('/products', asyncHandler(products.list));
  router.get('/products/:id', asyncHandler(products.getById));

  // Orders (mutations require x-api-key via apiKeyAuth middleware).
  router.post('/orders', asyncHandler(orders.create));
  router.get('/orders/:id', asyncHandler(orders.getById));
  router.patch('/orders/:id/status', asyncHandler(orders.updateStatus));

  // Customer-scoped order history.
  router.get('/customers/:customerId/orders', asyncHandler(orders.listByCustomer));

  return router;
}
