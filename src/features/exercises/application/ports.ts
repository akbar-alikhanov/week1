export interface SqlQueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
}

export class SqlQueryError extends Error {}

/**
 * Port for executing an untrusted SQL string against the sandbox dataset.
 * The implementation (infrastructure) is responsible for every safety
 * mechanism: statement denylist, read-only transaction, timeout, and using
 * a database role that only has SELECT - see ARCHITECTURE.md > SQL Sandbox.
 */
export interface SqlSandboxService {
  run(query: string): Promise<SqlQueryResult>;
}
