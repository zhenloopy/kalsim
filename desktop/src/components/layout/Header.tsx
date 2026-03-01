interface HeaderProps {
  nav: number;
  totalPnl: number;
  positionCount: number;
  wsConnected: boolean;
  collectorRunning: boolean;
}

export default function Header({
  nav,
  totalPnl,
  positionCount,
  wsConnected,
  collectorRunning,
}: HeaderProps) {
  const pnlColor = totalPnl >= 0 ? "text-accent-green" : "text-accent-red";

  return (
    <header className="flex items-center justify-between px-4 py-2 bg-surface-1 border-b border-surface-3">
      <div className="flex items-center gap-6">
        <span className="text-sm font-bold text-accent-cyan tracking-wider">
          kalsim
        </span>
        <span className="text-sm text-zinc-300">
          NAV:{" "}
          <span className="font-mono font-semibold">
            ${nav.toLocaleString("en-US", { minimumFractionDigits: 2 })}
          </span>
        </span>
        <span className={`text-sm font-mono ${pnlColor}`}>
          PnL: ${totalPnl >= 0 ? "+" : ""}
          {totalPnl.toFixed(2)}
        </span>
        <span className="text-sm text-zinc-500">
          {positionCount} position{positionCount !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="flex items-center gap-4 text-xs">
        <span
          className={`flex items-center gap-1 ${
            wsConnected ? "text-accent-green" : "text-accent-red"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              wsConnected ? "bg-accent-green" : "bg-accent-red"
            }`}
          />
          {wsConnected ? "Connected" : "Disconnected"}
        </span>
        <span
          className={`flex items-center gap-1 ${
            collectorRunning ? "text-accent-green" : "text-zinc-500"
          }`}
        >
          <span
            className={`w-1.5 h-1.5 rounded-full ${
              collectorRunning ? "bg-accent-green" : "bg-zinc-600"
            }`}
          />
          Collector:{collectorRunning ? "ON" : "OFF"}
        </span>
      </div>
    </header>
  );
}
