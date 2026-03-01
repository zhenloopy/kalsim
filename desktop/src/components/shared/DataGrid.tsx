import { useState, useMemo } from "react";

interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => string | number | React.ReactNode;
  align?: "left" | "right" | "center";
  sortable?: boolean;
  sortValue?: (row: T) => number | string;
}

interface DataGridProps<T> {
  columns: Column<T>[];
  data: T[];
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  compact?: boolean;
}

export default function DataGrid<T>({
  columns,
  data,
  rowKey,
  onRowClick,
  selectedKey,
  compact,
}: DataGridProps<T>) {
  const [sortCol, setSortCol] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const sorted = useMemo(() => {
    if (!sortCol) return data;
    const col = columns.find((c) => c.key === sortCol);
    if (!col?.sortable) return data;
    const getValue = col.sortValue || col.render;
    return [...data].sort((a, b) => {
      const va = getValue(a);
      const vb = getValue(b);
      if (typeof va === "number" && typeof vb === "number") {
        return sortDir === "asc" ? va - vb : vb - va;
      }
      const sa = String(va);
      const sb = String(vb);
      return sortDir === "asc" ? sa.localeCompare(sb) : sb.localeCompare(sa);
    });
  }, [data, sortCol, sortDir, columns]);

  const handleSort = (key: string) => {
    if (sortCol === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(key);
      setSortDir("asc");
    }
  };

  const py = compact ? "py-1" : "py-1.5";

  return (
    <div className="overflow-auto">
      <table className="w-full text-xs font-mono">
        <thead>
          <tr className="border-b border-surface-3">
            {columns.map((col) => (
              <th
                key={col.key}
                className={`${py} px-3 text-zinc-500 font-medium whitespace-nowrap ${
                  col.align === "right" ? "text-right" : "text-left"
                } ${col.sortable ? "cursor-pointer hover:text-zinc-300" : ""}`}
                onClick={() => col.sortable && handleSort(col.key)}
              >
                {col.header}
                {sortCol === col.key && (
                  <span className="ml-1">
                    {sortDir === "asc" ? "\u25B2" : "\u25BC"}
                  </span>
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const key = rowKey(row);
            return (
              <tr
                key={key}
                onClick={() => onRowClick?.(row)}
                className={`border-b border-surface-3/50 transition-colors ${
                  onRowClick ? "cursor-pointer hover:bg-surface-2" : ""
                } ${selectedKey === key ? "bg-surface-2" : ""}`}
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={`${py} px-3 whitespace-nowrap ${
                      col.align === "right" ? "text-right" : "text-left"
                    }`}
                  >
                    {col.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export type { Column };
