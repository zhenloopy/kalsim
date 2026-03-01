import { useState, useEffect, useCallback } from "react";
import { useCollector } from "../../hooks/useCollector";
import { useDisplayPrefs } from "../../hooks/useDisplayPrefs";
import { api } from "../../api/client";
import { StorageInfo } from "../../api/types";

const INTERVALS = [
  { label: "10s", seconds: 10 },
  { label: "30s", seconds: 30 },
  { label: "1m", seconds: 60 },
  { label: "5m", seconds: 300 },
  { label: "30m", seconds: 1800 },
  { label: "1hr", seconds: 3600 },
  { label: "24hr", seconds: 86400 },
];

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export default function SettingsTab() {
  const { status, start, stop } = useCollector();
  const { contractNameMode, setContractNameMode } = useDisplayPrefs();
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [confirming, setConfirming] = useState(false);

  const refreshStorage = useCallback(() => {
    api.getStorageInfo().then(setStorage).catch(() => {});
  }, []);

  useEffect(() => {
    refreshStorage();
  }, [refreshStorage]);

  const handleClear = () => {
    api.clearStorage().then((info) => {
      setStorage(info);
      setConfirming(false);
    }).catch(() => {});
  };

  return (
    <div className="max-w-md">
      <h2 className="text-xs font-semibold text-accent-cyan mb-4">SETTINGS</h2>

      <div className="mb-6">
        <div className="text-xs text-zinc-400 mb-2">Contract Names</div>
        <div className="flex gap-2">
          <button
            onClick={() => setContractNameMode("api")}
            className={`px-4 py-1.5 text-xs font-medium rounded transition-colors ${
              contractNameMode === "api"
                ? "bg-accent-cyan/20 text-accent-cyan"
                : "bg-surface-3 text-zinc-400 hover:text-zinc-300"
            }`}
          >
            API Name
          </button>
          <button
            onClick={() => setContractNameMode("readable")}
            className={`px-4 py-1.5 text-xs font-medium rounded transition-colors ${
              contractNameMode === "readable"
                ? "bg-accent-cyan/20 text-accent-cyan"
                : "bg-surface-3 text-zinc-400 hover:text-zinc-300"
            }`}
          >
            Readable Name
          </button>
        </div>
      </div>

      <div className="mb-6">
        <div className="text-xs text-zinc-400 mb-2">NAV Collector</div>
        <div className="flex gap-2 mb-2">
          <button
            onClick={() => start(status.interval)}
            className={`px-4 py-1.5 text-xs font-medium rounded transition-colors ${
              status.running
                ? "bg-accent-green/20 text-accent-green"
                : "bg-surface-3 text-zinc-400 hover:bg-surface-3/80"
            }`}
          >
            ON
          </button>
          <button
            onClick={stop}
            className={`px-4 py-1.5 text-xs font-medium rounded transition-colors ${
              !status.running
                ? "bg-accent-red/20 text-accent-red"
                : "bg-surface-3 text-zinc-400 hover:bg-surface-3/80"
            }`}
          >
            OFF
          </button>
        </div>
        <div className="text-[10px]">
          {status.running ? (
            <span className="text-accent-green">Collector is running</span>
          ) : (
            <span className="text-accent-red">Collector is stopped</span>
          )}
        </div>
      </div>

      <div className="mb-6">
        <div className="text-xs text-zinc-400 mb-2">Collection Interval</div>
        <div className="flex gap-1">
          {INTERVALS.map((iv) => (
            <button
              key={iv.label}
              onClick={() => {
                if (status.running) {
                  stop();
                  setTimeout(() => start(iv.seconds), 500);
                }
              }}
              className={`px-3 py-1.5 text-xs font-medium rounded transition-colors ${
                status.interval === iv.seconds
                  ? "bg-accent-cyan/20 text-accent-cyan"
                  : "bg-surface-3 text-zinc-400 hover:text-zinc-300"
              }`}
            >
              {iv.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="text-xs text-zinc-400 mb-2">Historical Data</div>
        {storage ? (
          <>
            <div className="flex items-baseline gap-3 mb-2">
              <span className="text-sm font-mono text-zinc-200">
                {formatBytes(storage.size_bytes)}
              </span>
              <span className="text-[10px] text-zinc-500">
                {storage.nav_snapshots.toLocaleString()} snapshots
                {" / "}
                {storage.position_snapshots.toLocaleString()} position records
              </span>
            </div>
            {confirming ? (
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-accent-red">Delete all history?</span>
                <button
                  onClick={handleClear}
                  className="px-3 py-1 text-xs font-medium rounded bg-accent-red/20 text-accent-red hover:bg-accent-red/30 transition-colors"
                >
                  Confirm
                </button>
                <button
                  onClick={() => setConfirming(false)}
                  className="px-3 py-1 text-xs font-medium rounded bg-surface-3 text-zinc-400 hover:text-zinc-300 transition-colors"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirming(true)}
                disabled={storage.nav_snapshots === 0 && storage.position_snapshots === 0}
                className="px-3 py-1.5 text-xs font-medium rounded bg-surface-3 text-zinc-400 hover:text-zinc-300 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Clear Data
              </button>
            )}
          </>
        ) : (
          <span className="text-[10px] text-zinc-500">Loading...</span>
        )}
      </div>
    </div>
  );
}
