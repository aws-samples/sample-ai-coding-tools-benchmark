/**
 * Application composition root.
 *
 * Builds the dependency graph (repositories -> services -> controllers),
 * registers middleware in the correct order, mounts the router under /api/v1,
 * and returns a ready-to-listen Express app. Keeping construction here (and out
 * of index.ts) makes the app importable by tests without binding a port.
 */

import express, { Application, Request, Response } from 'express';
import { createRepositories } from './repositories';
import { OrderService } from './services/orderService';
import { ProductService } from './services/productService';
import { OrderController, ProductController } from './http/controllers';
import { buildRouter } from './http/routes';
import {
  apiKeyAuth,
  errorHandler,
  notFound,
  requestId,
  requestLogger,
} from './middleware';

export function createApp(): Application {
  const repos = createRepositories();

  const productService = new ProductService(repos.products);
  const orderService = new OrderService(repos.orders, repos.products, repos.customers);

  const productController = new ProductController(productService);
  const orderController = new OrderController(orderService);

  const app = express();

  // --- Global middleware (order matters) ---
  app.use(express.json());
  app.use(requestId);
  app.use(requestLogger);

  // Liveness probe, mounted before auth so it is always reachable.
  app.get('/health', (_req: Request, res: Response) => {
    res.json({ status: 'ok', uptimeSeconds: process.uptime() });
  });

  // Auth gate for mutating requests, then the API routes.
  app.use('/api/v1', apiKeyAuth, buildRouter(productController, orderController));

  // --- Fallbacks (must be last) ---
  app.use(notFound);
  app.use(errorHandler);

  return app;
}
