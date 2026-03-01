import { useBookState } from "../../hooks/useBookState";
import DataGrid, { Column } from "../shared/DataGrid";
import StatusBadge from "../shared/StatusBadge";
import ContractCell from "../shared/ContractCell";
import NavChart from "../charts/NavChart";
import { Position } from "../../api/types";

export default function PositionsTab() {
  const { positions, cash } = useBookState();

  const columns: Column<Position | { _cash: true; cash: number }>[] = [
    {
      key: "contract",
      header: "Contract",
      render: (r) => ("_cash" in r ? "$CASH" : <ContractCell contractId={r.contract_id} />),
      sortable: true,
      sortValue: (r) => ("_cash" in r ? "" : r.contract_id),
    },
    {
      key: "qty",
      header: "Qty",
      align: "right",
      render: (r) => ("_cash" in r ? "" : r.quantity),
      sortable: true,
      sortValue: (r) => ("_cash" in r ? 0 : r.quantity),
    },
    {
      key: "entry",
      header: "Entry",
      align: "right",
      render: (r) => {
        if ("_cash" in r)
          return `$${r.cash.toLocaleString("en-US", { minimumFractionDigits: 2 })}`;
        const isShort = r.quantity < 0;
        const v = isShort ? 1 - r.entry_price : r.entry_price;
        return v.toFixed(2);
      },
    },
    {
      key: "mid",
      header: "Mid",
      align: "right",
      render: (r) => {
        if ("_cash" in r) return "";
        const isShort = r.quantity < 0;
        const v = isShort ? 1 - r.current_mid : r.current_mid;
        return v.toFixed(2);
      },
    },
    {
      key: "edge",
      header: "Edge",
      align: "right",
      render: (r) => {
        if ("_cash" in r) return "";
        const color =
          r.edge > 0
            ? "text-accent-green"
            : r.edge < 0
            ? "text-accent-red"
            : "text-zinc-400";
        return (
          <span className={color}>
            {r.edge >= 0 ? "+" : ""}
            {r.edge.toFixed(3)}
          </span>
        );
      },
      sortable: true,
      sortValue: (r) => ("_cash" in r ? 0 : r.edge),
    },
    {
      key: "pnl",
      header: "PnL",
      align: "right",
      render: (r) => {
        if ("_cash" in r) return "";
        const color =
          r.pnl >= 0 ? "text-accent-green" : "text-accent-red";
        return (
          <span className={color}>
            ${r.pnl >= 0 ? "+" : ""}
            {r.pnl.toFixed(2)}
          </span>
        );
      },
      sortable: true,
      sortValue: (r) => ("_cash" in r ? 0 : r.pnl),
    },
    {
      key: "tte",
      header: "TTE",
      align: "right",
      render: (r) => ("_cash" in r ? "" : `${r.tte_days.toFixed(1)}d`),
      sortable: true,
      sortValue: (r) => ("_cash" in r ? 9999 : r.tte_days),
    },
    {
      key: "flag",
      header: "Flag",
      render: (r) =>
        "_cash" in r ? "" : <StatusBadge flag={r.liquidity_flag} />,
    },
  ];

  const rows = [{ _cash: true as const, cash }, ...positions];

  return (
    <div className="flex flex-col gap-4">
      <NavChart />
      <div className="flex-shrink-0">
        <DataGrid
          columns={columns as any}
          data={rows}
          rowKey={(r: any) => ("_cash" in r ? "$CASH" : r.contract_id)}
        />
      </div>
    </div>
  );
}
