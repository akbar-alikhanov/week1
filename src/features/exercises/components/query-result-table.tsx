export function QueryResultTable({
  result,
  maxRows = 20,
}: {
  result: { columns: string[]; rows: Record<string, unknown>[] };
  maxRows?: number;
}) {
  if (result.rows.length === 0) {
    return <p className="text-sm text-muted-foreground">Query returned no rows.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-muted/60">
            {result.columns.map((col) => (
              <th
                key={col}
                className="border-b border-border p-1.5 text-left font-medium"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.slice(0, maxRows).map((row, i) => (
            <tr key={i}>
              {result.columns.map((col) => (
                <td key={col} className="border-b border-border p-1.5">
                  {String(row[col] ?? "")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {result.rows.length > maxRows ? (
        <p className="p-1.5 text-xs text-muted-foreground">
          Showing {maxRows} of {result.rows.length} rows.
        </p>
      ) : null}
    </div>
  );
}
