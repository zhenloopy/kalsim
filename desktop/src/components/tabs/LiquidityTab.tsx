import { useBookState } from "../../hooks/useBookState";
import DataGrid, { Column } from "../shared/DataGrid";
import StatusBadge from "../shared/StatusBadge";
import ContractCell from "../shared/ContractCell";
import { LiquidityMetric } from "../../api/types";

export default function LiquidityTab() {
  const { liquidity } = useBookState();

  const columns: Column<LiquidityMetric>[] = [
    {
      key: "contract",
      header: "Contract",
      render: (r) => <ContractCell contractId={r.contract_id} />,
      sortable: true,
    },
    {
      key: "spread",
      header: "Spread%",
      align: "right",
      render: (r) =>
        r.spread_pct === Infinity ? "N/A" : r.spread_pct.toFixed(3),
      sortable: true,
      sortValue: (r) => (r.spread_pct === Infinity ? 999 : r.spread_pct),
    },
    {
      key: "bidDepth",
      header: "BidDepth",
      align: "right",
      render: (r) => r.depth_at_best_bid,
      sortable: true,
      sortValue: (r) => r.depth_at_best_bid,
    },
    {
      key: "askDepth",
      header: "AskDepth",
      align: "right",
      render: (r) => r.depth_at_best_ask,
      sortable: true,
      sortValue: (r) => r.depth_at_best_ask,
    },
    {
      key: "slippage",
      header: "Slippage",
      align: "right",
      render: (r) => `$${r.liquidation_slippage.toFixed(2)}`,
      sortable: true,
      sortValue: (r) => r.liquidation_slippage,
    },
    {
      key: "flag",
      header: "Flag",
      render: (r) => <StatusBadge flag={r.liquidity_flag} />,
    },
  ];

  return (
    <div>
      <h2 className="text-xs font-semibold text-accent-cyan mb-3">
        LIQUIDITY METRICS
      </h2>
      {liquidity.length === 0 ? (
        <div className="text-xs text-zinc-500">
          Waiting for liquidity analysis...
        </div>
      ) : (
        <DataGrid
          columns={columns}
          data={liquidity}
          rowKey={(r) => r.contract_id}
        />
      )}
    </div>
  );
}
