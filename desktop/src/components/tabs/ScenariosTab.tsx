import { useState, useEffect } from "react";
import { api } from "../../api/client";
import ContractCell from "../shared/ContractCell";
import { ScenarioResult } from "../../api/types";

const TEMPLATE = JSON.stringify(
  {
    name: "",
    world_state: {},
    description: "",
    resolution_overrides: {},
    probability_overrides: {},
  },
  null,
  2
);

export default function ScenariosTab() {
  const [json, setJson] = useState(TEMPLATE);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [results, setResults] = useState<ScenarioResult[]>([]);

  useEffect(() => {
    api.getScenarios().then(setResults).catch(() => {});
  }, []);

  const handleSubmit = async () => {
    setError(null);
    setSuccess(null);
    try {
      await api.submitScenario(json);
      setSuccess("Scenario saved");
      setJson(TEMPLATE);
      api.getScenarios().then(setResults).catch(() => {});
    } catch (e: any) {
      setError(e.message || "Failed to submit");
    }
  };

  return (
    <div className="flex flex-col gap-4 h-full">
      <div>
        <h2 className="text-xs font-semibold text-accent-cyan mb-2">
          ADD SCENARIO
        </h2>
        <textarea
          value={json}
          onChange={(e) => setJson(e.target.value)}
          className="w-full h-40 bg-surface-2 border border-surface-3 rounded p-3 text-xs font-mono text-zinc-300 resize-none focus:outline-none focus:border-accent-cyan/50"
          spellCheck={false}
        />
        <div className="flex items-center gap-3 mt-2">
          <button
            onClick={handleSubmit}
            className="px-4 py-1.5 bg-accent-cyan/20 text-accent-cyan text-xs font-medium rounded hover:bg-accent-cyan/30 transition-colors"
          >
            Submit
          </button>
          {error && <span className="text-xs text-accent-red">{error}</span>}
          {success && (
            <span className="text-xs text-accent-green">{success}</span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <h2 className="text-xs font-semibold text-accent-cyan mb-3">
          SCENARIO STRESS TESTS
        </h2>
        {results.length === 0 ? (
          <div className="text-xs text-zinc-500">No scenarios defined.</div>
        ) : (
          <div className="flex flex-col gap-3">
            {results.map((r, i) => (
              <div
                key={i}
                className="bg-surface-2 rounded px-4 py-3 border border-surface-3"
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-semibold">{r.name}</span>
                  <span
                    className={`text-xs font-mono font-semibold ${
                      r.pnl >= 0 ? "text-accent-green" : "text-accent-red"
                    }`}
                  >
                    ${r.pnl >= 0 ? "+" : ""}
                    {r.pnl.toFixed(2)}
                  </span>
                  {r.exceeds_var99 && (
                    <span className="px-2 py-0.5 bg-red-900/40 text-accent-red text-[10px] font-semibold rounded">
                      EXCEEDS VaR99
                    </span>
                  )}
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {r.position_pnls.map((p) => (
                    <span key={p.contract_id} className="text-[10px] text-zinc-500">
                      <ContractCell contractId={p.contract_id} />:{" "}
                      <span
                        className={
                          p.pnl >= 0 ? "text-accent-green" : "text-accent-red"
                        }
                      >
                        ${p.pnl >= 0 ? "+" : ""}
                        {p.pnl.toFixed(2)}
                      </span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
