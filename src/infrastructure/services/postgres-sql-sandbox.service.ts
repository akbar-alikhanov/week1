import { Pool } from "pg";

import type {
  SqlQueryResult,
  SqlSandboxService,
} from "@/features/exercises/application/ports";
import { SqlQueryError } from "@/features/exercises/application/ports";

const MAX_ROWS = 500;
const STATEMENT_TIMEOUT_MS = 5_000;

/**
 * Statement types that must never reach the sandbox, even though the
 * database role is already SELECT-only and the transaction is read-only.
 * Defense in depth: a clear error here is a better learner experience than
 * a raw Postgres permission-denied message.
 */
const FORBIDDEN_KEYWORDS =
  /\b(DROP|DELETE|UPDATE|INSERT|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|COPY|CALL|DO|EXECUTE|VACUUM|REINDEX|ATTACH|DETACH|MERGE|REFRESH|LISTEN|NOTIFY|SECURITY)\b/i;

let pool: Pool | undefined;

function getPool(): Pool {
  if (!pool) {
    pool = new Pool({
      connectionString: process.env.SANDBOX_READONLY_DATABASE_URL,
      max: 5,
      idleTimeoutMillis: 30_000,
    });
  }
  return pool;
}

function assertSafeQuery(query: string): string {
  const trimmed = query.trim();
  if (!trimmed) {
    throw new SqlQueryError("Query cannot be empty.");
  }

  // Reject multiple statements: strip at most one trailing semicolon, then
  // make sure no semicolon remains inside the query.
  const withoutTrailingSemicolon = trimmed.endsWith(";") ? trimmed.slice(0, -1) : trimmed;
  if (withoutTrailingSemicolon.includes(";")) {
    throw new SqlQueryError("Only a single statement is allowed.");
  }

  if (!/^(SELECT|WITH)\b/i.test(withoutTrailingSemicolon)) {
    throw new SqlQueryError(
      "Only SELECT queries (optionally starting with WITH) are allowed.",
    );
  }

  if (FORBIDDEN_KEYWORDS.test(withoutTrailingSemicolon)) {
    throw new SqlQueryError(
      "This query uses a keyword that is not allowed in the sandbox.",
    );
  }

  return withoutTrailingSemicolon;
}

export class PostgresSqlSandboxService implements SqlSandboxService {
  async run(query: string): Promise<SqlQueryResult> {
    const safeQuery = assertSafeQuery(query);
    const client = await getPool().connect();

    try {
      await client.query("BEGIN TRANSACTION READ ONLY");
      await client.query(`SET LOCAL statement_timeout = ${STATEMENT_TIMEOUT_MS}`);
      // Wrap in a subquery so the cap applies regardless of whether the
      // learner's query already has its own LIMIT/ORDER BY - appending a
      // second bare LIMIT to an arbitrary query would often be a syntax error.
      const result = await client.query(
        `SELECT * FROM (${safeQuery}) AS sandboxed_query LIMIT ${MAX_ROWS}`,
      );
      await client.query("ROLLBACK");

      return {
        columns: result.fields.map((field) => field.name),
        rows: result.rows,
      };
    } catch (error) {
      await client.query("ROLLBACK").catch(() => undefined);
      if (error instanceof SqlQueryError) {
        throw error;
      }
      const message = error instanceof Error ? error.message : "Unknown database error.";
      throw new SqlQueryError(message);
    } finally {
      client.release();
    }
  }
}
