import { useBookState } from "../../hooks/useBookState";
import DataGrid, { Column } from "../shared/DataGrid";
import ContractCell from "../shared/ContractCell";
import { KellyAllocation } from "../../api/types";

export default function KellyTab() {
  const { kelly } = useBookState();

  if (!kelly) {
    return (
      <div className="text-xs text-zinc-500">
        Waiting for Kelly computation...
      </div>
    );
  }

  const columns: Column<KellyAllocation>[] = [
    { key: "contract", header: "Contract", render: (r) => <ContractCell contractId={r.contract_id} /> },
    {
      key: "raw",
      header: "Raw",
      align: "right",
      render: (r) => (
        <span className={r.raw_kelly >= 0 ? "text-accent-green" : "text-accent-red"}>
          {r.raw_kelly >= 0 ? "+" : ""}{r.raw_kelly.toFixed(4)}
        </span>
      ),
      sortable: true,
      sortValue: (r) => r.raw_kelly,
    },
    {
      key: "target",
      header: "Target$",
      align: "right",
      render: (r) => `${r.target_dollars >= 0 ? "+" : ""}${r.target_dollars.toFixed(2)}`,
      sortable: true,
      sortValue: (r) => r.target_dollars,
    },
    {
      key: "current",
      header: "Current$",
      align: "right",
      render: (r) => `${r.current_dollars >= 0 ? "+" : ""}${r.current_dollars.toFixed(2)}`,
    },
    {
      key: "trade",
      header: "Trade",
      align: "right",
      render: (r) => {
        const color =
          r.trade_dollars > 0.01
            ? "text-accent-green"
            : r.trade_dollars < -0.01
            ? "text-accent-red"
            : "text-zinc-500";
        return (
          <span className={color}>
            {r.trade_dollars >= 0 ? "+" : ""}
            {r.trade_dollars.toFixed(2)}
          </span>
        );
      },
      sortable: true,
      sortValue: (r) => Math.abs(r.trade_dollars),
    },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-xs font-semibold text-accent-cyan mb-3">
          KELLY OPTIMAL SIZING
        </h2>
        <div className="flex gap-6 text-xs mb-4">
          <span>
            Bankroll:{" "}
            <span className="font-mono font-semibold">
              ${kelly.bankroll.toLocaleString("en-US", { minimumFractionDigits: 2 })}
            </span>
          </span>
          <span className="text-zinc-500">
            Cash: ${kelly.cash.toFixed(2)} + Portfolio: $
            {kelly.portfolio_value.toFixed(2)}
          </span>
        </div>
      </div>
      <DataGrid
        columns={columns}
        data={kelly.allocations}
        rowKey={(r) => r.contract_id}
      />
    </div>
  );
}
