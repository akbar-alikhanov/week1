"use client";

import { useState, useTransition } from "react";
import dynamic from "next/dynamic";
import { Play } from "lucide-react";

import { runSqlQueryAction } from "@/features/exercises/actions";
import type { SqlQueryResult } from "@/features/exercises/application/ports";
import { QueryResultTable } from "@/features/exercises/components/query-result-table";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

const SqlEditor = dynamic(
  () => import("@/features/exercises/components/sql-editor").then((mod) => mod.SqlEditor),
  {
    ssr: false,
    loading: () => <div className="h-72 animate-pulse rounded-md bg-muted" />,
  },
);

const SCHEMA = [
  { table: "customers", columns: ["customer_id", "name", "region", "signup_date"] },
  { table: "products", columns: ["product_id", "name", "category", "price"] },
  {
    table: "orders",
    columns: [
      "order_id",
      "customer_id",
      "product_id",
      "quantity",
      "order_date",
      "status",
    ],
  },
  {
    table: "payments",
    columns: ["payment_id", "order_id", "amount", "paid_at", "method"],
  },
];

const DEFAULT_QUERY = "SELECT * FROM customers;";

export function SqlPlayground() {
  const [query, setQuery] = useState(DEFAULT_QUERY);
  const [result, setResult] = useState<SqlQueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleRun() {
    setError(null);
    startTransition(async () => {
      const response = await runSqlQueryAction(query);
      if (!response.success) {
        setError(response.error);
        setResult(null);
        return;
      }
      setResult(response.data);
    });
  }

  return (
    <div className="grid flex-1 grid-cols-1 gap-4 p-6 lg:grid-cols-[220px_1fr]">
      <Card className="h-fit">
        <CardHeader>
          <CardTitle className="text-sm">Database</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {SCHEMA.map((table) => (
            <div key={table.table}>
              <p className="font-mono text-sm font-medium">{table.table}</p>
              <ul className="ml-2 mt-1 space-y-0.5">
                {table.columns.map((column) => (
                  <li key={column} className="font-mono text-xs text-muted-foreground">
                    {column}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </CardContent>
      </Card>

      <div className="flex flex-col gap-4">
        <Card>
          <CardContent className="space-y-3 pt-6">
            <SqlEditor value={query} onChange={setQuery} height="220px" />
            <Button onClick={handleRun} disabled={isPending || !query.trim()}>
              <Play className="size-4" />
              {isPending ? "Running…" : "Run Query"}
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Results</CardTitle>
          </CardHeader>
          <CardContent>
            {error ? (
              <p className="text-sm text-destructive">{error}</p>
            ) : result ? (
              <QueryResultTable result={result} maxRows={100} />
            ) : (
              <p className="text-sm text-muted-foreground">Run a query to see results.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
