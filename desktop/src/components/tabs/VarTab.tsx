import { useBookState } from "../../hooks/useBookState";
import DataGrid, { Column } from "../shared/DataGrid";
import ContractCell from "../shared/ContractCell";
import DistributionCurve from "../charts/DistributionCurve";
import { ComponentVaR } from "../../api/types";

export default function VarTab() {
  const { var: varData } = useBookState();

  if (!varData) {
    return (
      <div className="text-xs text-zinc-500">
        Waiting for VaR computation...
      </div>
    );
  }

  const metrics = [
    { label: "VaR 95", value: varData.var_95 },
    { label: "VaR 99", value: varData.var_99 },
    { label: "CVaR 95", value: varData.cvar_95 },
    { label: "CVaR 99", value: varData.cvar_99 },
    { label: "P(ruin)", value: varData.p_ruin, isPercent: true },
  ];

  const componentColumns: Column<ComponentVaR>[] = [
    { key: "contract", header: "Contract", render: (r) => <ContractCell contractId={r.contract_id} /> },
    {
      key: "value",
      header: "Component VaR",
      align: "right",
      render: (r) => `$${r.value.toFixed(2)}`,
      sortable: true,
      sortValue: (r) => r.value,
    },
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xs font-semibold text-accent-cyan mb-3">
          PORTFOLIO VALUE AT RISK
        </h2>
        <div className="flex flex-wrap gap-3">
          {metrics.map((m) => (
            <div
              key={m.label}
              className="bg-surface-2 rounded px-4 py-3 border border-surface-3 min-w-[120px] flex-1"
            >
              <div className="text-[10px] text-zinc-500 mb-1">{m.label}</div>
              <div className="text-sm font-mono font-semibold">
                {m.isPercent
                  ? m.value.toFixed(4)
                  : `$${m.value.toFixed(2)}`}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-xs font-semibold text-accent-cyan mb-3">
          COMPONENT VAR
        </h2>
        <DataGrid
          columns={componentColumns}
          data={varData.component_var}
          rowKey={(r) => r.contract_id}
        />
      </div>

      <div>
        <h2 className="text-xs font-semibold text-accent-cyan mb-2">
          P&L DISTRIBUTION
        </h2>
        <DistributionCurve
          data={varData.pnl_distribution}
          markers={[
            { value: -varData.var_95, label: "VaR95", color: "#eab308" },
            { value: -varData.var_99, label: "VaR99", color: "#ef4444" },
          ]}
        />
      </div>
    </div>
  );
}
