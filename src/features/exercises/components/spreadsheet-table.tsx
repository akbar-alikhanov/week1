import type { SpreadsheetTable } from "@/entities/exercise/types";
import { cn } from "@/shared/lib/cn";

function columnLetter(index: number): string {
  return String.fromCharCode(65 + index);
}

export function SpreadsheetTablePreview({
  table,
  targetCell,
}: {
  table: SpreadsheetTable;
  targetCell?: string;
}) {
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="bg-muted/60">
            <th className="w-10 border-b border-r border-border p-1.5 text-xs text-muted-foreground" />
            {table.headers.map((_, colIndex) => (
              <th
                key={colIndex}
                className="border-b border-r border-border p-1.5 text-xs font-medium text-muted-foreground last:border-r-0"
              >
                {columnLetter(colIndex)}
              </th>
            ))}
          </tr>
          <tr>
            <th className="border-b border-r border-border bg-muted/60 p-1.5 text-xs text-muted-foreground">
              1
            </th>
            {table.headers.map((header, colIndex) => (
              <th
                key={colIndex}
                className="border-b border-r border-border p-1.5 text-left font-medium last:border-r-0"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              <td className="border-b border-r border-border bg-muted/60 p-1.5 text-center text-xs text-muted-foreground">
                {rowIndex + 2}
              </td>
              {row.map((cell, colIndex) => {
                const cellRef = `${columnLetter(colIndex)}${rowIndex + 2}`;
                return (
                  <td
                    key={colIndex}
                    className={cn(
                      "border-b border-r border-border p-1.5 last:border-r-0",
                      cellRef === targetCell && "bg-primary/10 font-medium",
                    )}
                  >
                    {cell}
                  </td>
                );
              })}
            </tr>
          ))}
          {targetCell ? (
            <tr>
              <td className="border-r border-border bg-muted/60 p-1.5 text-center text-xs text-muted-foreground">
                {table.rows.length + 2}
              </td>
              {table.headers.map((_, colIndex) => {
                const cellRef = `${columnLetter(colIndex)}${table.rows.length + 2}`;
                return (
                  <td
                    key={colIndex}
                    className={cn(
                      "border-r border-border p-1.5 text-muted-foreground last:border-r-0",
                      cellRef === targetCell &&
                        "bg-primary/10 font-medium text-foreground",
                    )}
                  >
                    {cellRef === targetCell ? "?" : ""}
                  </td>
                );
              })}
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
