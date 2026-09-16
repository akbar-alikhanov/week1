/**
 * Provisions the SQL Playground sandbox database: schema, seed data, and a
 * read-only Postgres role used at query-execution time. Run with:
 *   pnpm db:seed:sandbox
 *
 * This is intentionally plain `pg`, not Prisma - the sandbox is a separate
 * database the main Prisma schema never touches (see ARCHITECTURE.md > SQL
 * Sandbox).
 */
import { Client } from "pg";

const ownerUrl = process.env.SANDBOX_DATABASE_URL;
if (!ownerUrl) {
  throw new Error("SANDBOX_DATABASE_URL is required to seed the sandbox database.");
}

const readerPassword =
  process.env.SANDBOX_READER_PASSWORD ?? "sandbox_reader_dev_password";

const DDL = `
DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;

CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  region TEXT NOT NULL,
  signup_date DATE NOT NULL
);

CREATE TABLE products (
  product_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  category TEXT NOT NULL,
  price NUMERIC(10, 2) NOT NULL
);

CREATE TABLE orders (
  order_id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
  product_id INTEGER NOT NULL REFERENCES products(product_id),
  quantity INTEGER NOT NULL,
  order_date DATE NOT NULL,
  status TEXT NOT NULL
);

CREATE TABLE payments (
  payment_id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(order_id),
  amount NUMERIC(10, 2) NOT NULL,
  paid_at TIMESTAMP,
  method TEXT NOT NULL
);
`;

const SEED_DATA = `
INSERT INTO customers (customer_id, name, region, signup_date) VALUES
  (1, 'Alice Johnson', 'North', '2025-01-10'),
  (2, 'Bob Smith', 'South', '2025-02-15'),
  (3, 'Carol White', 'North', '2025-03-01'),
  (4, 'David Brown', 'South', '2025-01-20'),
  (5, 'Amanda Lee', 'North', '2025-04-05'),
  (6, 'Evan Wright', 'South', '2025-02-28'),
  (7, 'Amelia Clark', 'North', '2025-05-12'),
  (8, 'Frank Miller', 'South', '2025-03-19');

INSERT INTO products (product_id, name, category, price) VALUES
  (101, 'Wireless Mouse', 'Accessories', 25.00),
  (102, 'Mechanical Keyboard', 'Accessories', 85.00),
  (103, '27" Monitor', 'Electronics', 320.00),
  (104, 'Laptop Stand', 'Accessories', 40.00),
  (105, 'Noise Cancelling Headphones', 'Electronics', 150.00),
  (106, 'Webcam HD', 'Electronics', 60.00),
  (107, 'USB-C Hub', 'Accessories', 35.00),
  (108, 'Standing Desk', 'Furniture', 450.00);

INSERT INTO orders (order_id, customer_id, product_id, quantity, order_date, status) VALUES
  (1001, 1, 103, 1, '2026-01-05', 'delivered'),
  (1002, 2, 101, 2, '2026-01-08', 'delivered'),
  (1003, 3, 105, 1, '2026-01-15', 'shipped'),
  (1004, 4, 102, 1, '2026-01-18', 'cancelled'),
  (1005, 1, 107, 3, '2026-01-22', 'delivered'),
  (1006, 5, 108, 1, '2026-02-01', 'pending'),
  (1007, 6, 104, 2, '2026-02-03', 'delivered'),
  (1008, 2, 106, 1, '2026-02-10', 'shipped'),
  (1009, 7, 103, 1, '2026-02-14', 'delivered'),
  (1010, 3, 101, 1, '2026-02-20', 'pending'),
  (1011, 8, 105, 2, '2026-02-25', 'cancelled'),
  (1012, 4, 108, 1, '2026-03-02', 'delivered'),
  (1013, 1, 102, 1, '2026-03-06', 'shipped'),
  (1014, 5, 106, 2, '2026-03-11', 'delivered'),
  (1015, 6, 103, 1, '2026-03-15', 'pending'),
  (1016, 7, 107, 4, '2026-03-19', 'delivered'),
  (1017, 2, 108, 1, '2026-03-24', 'shipped'),
  (1018, 8, 101, 3, '2026-03-28', 'delivered'),
  (1019, 3, 105, 1, '2026-04-02', 'delivered'),
  (1020, 4, 104, 1, '2026-04-06', 'pending');

INSERT INTO payments (payment_id, order_id, amount, paid_at, method) VALUES
  (1, 1001, 320.00, '2026-01-06 10:00:00', 'card'),
  (2, 1002, 50.00, '2026-01-09 11:30:00', 'paypal'),
  (3, 1003, 150.00, NULL, 'card'),
  (4, 1005, 105.00, '2026-01-23 09:15:00', 'card'),
  (5, 1007, 80.00, '2026-02-04 14:00:00', 'bank_transfer'),
  (6, 1008, 60.00, NULL, 'card'),
  (7, 1009, 320.00, '2026-02-15 16:45:00', 'card'),
  (8, 1012, 450.00, '2026-03-03 08:20:00', 'paypal'),
  (9, 1013, 85.00, '2026-03-07 12:10:00', 'card'),
  (10, 1014, 120.00, '2026-03-12 10:05:00', 'card'),
  (11, 1016, 140.00, '2026-03-20 15:30:00', 'bank_transfer'),
  (12, 1017, 450.00, NULL, 'card'),
  (13, 1018, 75.00, '2026-03-29 09:40:00', 'paypal'),
  (14, 1019, 150.00, '2026-04-03 11:00:00', 'card');
`;

async function main() {
  const owner = new Client({ connectionString: ownerUrl });
  await owner.connect();

  console.log("Creating sandbox schema...");
  await owner.query(DDL);

  console.log("Seeding sandbox data...");
  await owner.query(SEED_DATA);

  console.log("Provisioning read-only role...");
  const roleExists = await owner.query(
    "SELECT 1 FROM pg_roles WHERE rolname = 'sandbox_reader'",
  );
  if (roleExists.rowCount === 0) {
    await owner.query(
      `CREATE ROLE sandbox_reader LOGIN PASSWORD '${readerPassword}' NOSUPERUSER NOCREATEDB NOCREATEROLE;`,
    );
  }
  await owner.query("GRANT CONNECT ON DATABASE dala_sandbox TO sandbox_reader;");
  await owner.query("GRANT USAGE ON SCHEMA public TO sandbox_reader;");
  await owner.query("GRANT SELECT ON ALL TABLES IN SCHEMA public TO sandbox_reader;");
  await owner.query(
    "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO sandbox_reader;",
  );
  // sandbox_reader must never be able to change its own privileges or data.
  await owner.query("REVOKE CREATE ON SCHEMA public FROM sandbox_reader;");

  await owner.end();
  console.log("Sandbox seed complete.");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
