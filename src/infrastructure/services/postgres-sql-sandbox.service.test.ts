import { describe, expect, it, vi } from "vitest";

vi.mock("pg", () => ({ Pool: vi.fn() }));

import { PostgresSqlSandboxService } from "@/infrastructure/services/postgres-sql-sandbox.service";
import { SqlQueryError } from "@/features/exercises/application/ports";

describe("PostgresSqlSandboxService", () => {
  const service = new PostgresSqlSandboxService();

  it.each([
    "DROP TABLE customers;",
    "DELETE FROM orders;",
    "UPDATE products SET price = 0;",
    "INSERT INTO customers VALUES (1);",
    "ALTER TABLE orders ADD COLUMN x INT;",
    "CREATE TABLE hack (id INT);",
    "TRUNCATE orders;",
    "GRANT ALL ON orders TO PUBLIC;",
    "SELECT * FROM orders; DROP TABLE orders;",
    "",
    "   ",
    "orders SELECT *",
  ])("rejects unsafe query: %s", async (query) => {
    await expect(service.run(query)).rejects.toThrow(SqlQueryError);
  });
});
