/**
 * In-memory persistence layer.
 *
 * Repositories own all entity storage and id generation. Services depend on
 * the repository *interfaces*, not the concrete maps, so the backing store
 * could later be swapped for a database without touching business logic.
 */

import { Customer, Order, Product } from './types';

let idCounter = 1000;

/** Monotonic id generator. Prefix keeps ids self-describing in logs. */
export function generateId(prefix: string): string {
  idCounter += 1;
  return `${prefix}_${idCounter}`;
}

export interface ProductRepository {
  findAll(): Product[];
  findById(id: string): Product | undefined;
  save(product: Product): Product;
}

export interface CustomerRepository {
  findById(id: string): Customer | undefined;
  save(customer: Customer): Customer;
}

export interface OrderRepository {
  findAll(): Order[];
  findById(id: string): Order | undefined;
  findByCustomer(customerId: string): Order[];
  save(order: Order): Order;
}

export class InMemoryProductRepository implements ProductRepository {
  private readonly products = new Map<string, Product>();

  findAll(): Product[] {
    return [...this.products.values()];
  }

  findById(id: string): Product | undefined {
    return this.products.get(id);
  }

  save(product: Product): Product {
    this.products.set(product.id, product);
    return product;
  }
}

export class InMemoryCustomerRepository implements CustomerRepository {
  private readonly customers = new Map<string, Customer>();

  findById(id: string): Customer | undefined {
    return this.customers.get(id);
  }

  save(customer: Customer): Customer {
    this.customers.set(customer.id, customer);
    return customer;
  }
}

export class InMemoryOrderRepository implements OrderRepository {
  private readonly orders = new Map<string, Order>();

  findAll(): Order[] {
    return [...this.orders.values()];
  }

  findById(id: string): Order | undefined {
    return this.orders.get(id);
  }

  findByCustomer(customerId: string): Order[] {
    return this.findAll().filter((o) => o.customerId === customerId);
  }

  save(order: Order): Order {
    this.orders.set(order.id, order);
    return order;
  }
}

/** Bundles the three repositories so they can be created and injected together. */
export interface RepositoryBundle {
  products: ProductRepository;
  customers: CustomerRepository;
  orders: OrderRepository;
}

/**
 * Builds the repository bundle and loads a small, deterministic seed dataset so
 * the API is useful the moment it boots (and so benchmark runs are repeatable).
 */
export function createRepositories(): RepositoryBundle {
  const products = new InMemoryProductRepository();
  const customers = new InMemoryCustomerRepository();
  const orders = new InMemoryOrderRepository();

  const now = new Date('2026-01-01T00:00:00.000Z').toISOString();

  products.save({
    id: 'prod_1',
    sku: 'KEYB-001',
    name: 'Mechanical Keyboard',
    priceCents: 8900,
    stock: 50,
    active: true,
    createdAt: now,
  });
  products.save({
    id: 'prod_2',
    sku: 'MOUSE-001',
    name: 'Wireless Mouse',
    priceCents: 4500,
    stock: 100,
    active: true,
    createdAt: now,
  });
  products.save({
    id: 'prod_3',
    sku: 'MON-027',
    name: '27-inch Monitor',
    priceCents: 31900,
    stock: 12,
    active: true,
    createdAt: now,
  });
  products.save({
    id: 'prod_4',
    sku: 'CABLE-USB',
    name: 'USB-C Cable (discontinued)',
    priceCents: 1200,
    stock: 0,
    active: false,
    createdAt: now,
  });

  customers.save({
    id: 'cust_1',
    name: 'Jane Doe',
    email: 'jane@example.com',
    tier: 'gold',
    createdAt: now,
  });
  customers.save({
    id: 'cust_2',
    name: 'John Stiles',
    email: 'john@example.com',
    tier: 'standard',
    createdAt: now,
  });

  return { products, customers, orders };
}
