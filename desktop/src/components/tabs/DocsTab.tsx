import { useState, useEffect, useRef } from "react";

const SECTIONS = [
  { id: "positions", label: "1. Positions" },
  { id: "orderbook", label: "2. Orderbook" },
  { id: "var-risk", label: "3. VaR / Risk" },
  { id: "kelly", label: "4. Kelly Sizing" },
  { id: "scenarios", label: "5. Scenarios" },
  { id: "liquidity", label: "6. Liquidity" },
  { id: "settings", label: "7. Settings" },
  { id: "keybindings", label: "Keybindings" },
];

export default function DocsTab() {
  const [active, setActive] = useState(SECTIONS[0].id);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = contentRef.current;
    if (!container) return;

    const onScroll = () => {
      const containerTop = container.getBoundingClientRect().top;
      let current = SECTIONS[0].id;
      for (const s of SECTIONS) {
        const el = document.getElementById(s.id);
        if (el && el.getBoundingClientRect().top - containerTop <= 60) {
          current = s.id;
        }
      }
      setActive(current);
    };

    container.addEventListener("scroll", onScroll);
    return () => container.removeEventListener("scroll", onScroll);
  }, []);

  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
    setActive(id);
  };

  return (
    <div className="flex h-full">
      <nav className="w-44 shrink-0 pr-4 pt-2 border-r border-surface-3">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            onClick={() => scrollTo(s.id)}
            className={`block w-full text-left px-3 py-1.5 text-xs rounded transition-colors mb-0.5 ${
              active === s.id
                ? "text-accent-cyan bg-accent-cyan/10"
                : "text-zinc-500 hover:text-zinc-300"
            }`}
          >
            {s.label}
          </button>
        ))}
      </nav>

      <div ref={contentRef} className="flex-1 overflow-y-auto">
        <div className="w-[70%] mx-auto py-4 text-xs leading-relaxed">
          <h1 className="text-sm font-bold text-accent-cyan mb-6">
            KALSIM RISK DESK — DOCUMENTATION
          </h1>

          <Section id="positions" title="1. POSITIONS">
            <p>Portfolio overview showing all open contracts.</p>
            <Def term="Contract">Kalshi ticker (e.g. KXBTC-26031-B5499)</Def>
            <Def term="Qty">
              Number of contracts held. Positive = long YES, negative = short
              YES (equivalent to long NO).
            </Def>
            <Def term="Entry">Average price paid per contract (0.00-1.00).</Def>
            <Def term="Mid">
              Current bid-ask midpoint, recomputed live from the orderbook:
              (best_yes_bid + best_yes_ask) / 2.
            </Def>
            <Def term="Edge">
              model_prob - market_prob. How much you believe the contract is
              mispriced.
            </Def>
            <Def term="PnL">
              Unrealized P&L: qty x (current_mid - entry_price).
            </Def>
            <Def term="TTE">Time to expiration in days.</Def>
            <Def term="Flag">Liquidity flag: NORMAL / WATCH / CRITICAL.</Def>
          </Section>

          <Section id="orderbook" title="2. ORDERBOOK">
            <p>
              Select a contract from the top table to see its live orderbook.
              Shows YES bids and NO bids (asks) sorted by price. Updated via
              WebSocket deltas in real time.
            </p>
          </Section>

          <Section id="var-risk" title="3. VaR / RISK">
            <p>
              Monte Carlo simulation (100,000 paths) of portfolio P&L assuming
              binary resolution of all contracts.
            </p>
            <p className="mt-2 font-semibold text-zinc-300">Method:</p>
            <ol className="list-decimal list-inside ml-2 text-zinc-400">
              <li>Draw correlated standard normals (Cholesky decomposition)</li>
              <li>Transform to uniform [0,1] via normal CDF</li>
              <li>{"Resolve: if U < model_prob -> YES, else NO"}</li>
              <li>Compute P&L per contract per simulation</li>
              <li>In worst 5% of sims, subtract liquidation slippage</li>
            </ol>
            <Def term="VaR 95">
              95th percentile of losses. 5% chance of losing more.
            </Def>
            <Def term="VaR 99">99th percentile of losses.</Def>
            <Def term="CVaR 95">
              Expected Shortfall. Average loss in worst 5% of scenarios.
            </Def>
            <Def term="CVaR 99">Average loss in worst 1% of scenarios.</Def>
            <Def term="P(ruin)">
              Fraction of simulations where total loss exceeds max possible
              loss.
            </Def>
            <p className="mt-2 font-semibold text-zinc-300">Component VaR:</p>
            <p className="text-zinc-400">
              Per-position marginal contribution to portfolio VaR. Computed as
              average loss of each position in the worst 5% of portfolio-level
              simulations.
            </p>
          </Section>

          <Section id="kelly" title="4. KELLY OPTIMAL SIZING">
            <p>
              Kelly criterion position sizing to maximize long-run growth rate,
              scaled down for safety.
            </p>
            <Def term="Raw">
              {"Full Kelly fraction: f* = (model_prob - market_prob) / (1 - market_prob). "}
              Zeroed if |edge| {"<"} 3c.
            </Def>
            <Def term="Target$">
              Dollar amount to hold. Raw x 0.25 (quarter-Kelly) x bankroll,
              constrained by per-contract cap (5%), liquidity cap, cluster cap
              (15%).
            </Def>
            <Def term="Current$">Dollar value currently held.</Def>
            <Def term="Trade">
              Target$ - Current$. Green = buy, Red = sell.
            </Def>
          </Section>

          <Section id="scenarios" title="5. SCENARIOS">
            <p>
              Deterministic stress tests. Define hypothetical outcomes and see
              exact P&L impact on your portfolio.
            </p>
            <p className="mt-2 font-semibold text-zinc-300">JSON fields:</p>
            <Def term="name">(required) Scenario label.</Def>
            <Def term="world_state">
              (required) Object describing the scenario state.
            </Def>
            <Def term="resolution_overrides">
              (optional) Map contract IDs to "YES" or "NO".
            </Def>
            <Def term="probability_overrides">
              (optional) Map contract IDs to a probability in [0,1].
            </Def>
            <p className="mt-2 font-semibold text-zinc-300">Priority chain:</p>
            <ol className="list-decimal list-inside ml-2 text-zinc-400">
              <li>{"probability_overrides -> expected value P&L"}</li>
              <li>{"resolution_overrides -> binary settle at $1/$0"}</li>
              <li>{"resolution_rules -> callable logic"}</li>
              <li>{"fallthrough -> mark-to-market"}</li>
            </ol>
          </Section>

          <Section id="liquidity" title="6. LIQUIDITY">
            <Def term="Spread%">
              Bid-ask spread as fraction of midpoint.
            </Def>
            <Def term="BidDepth / AskDepth">
              Contracts at best bid/ask level.
            </Def>
            <Def term="Slippage">
              Dollar cost to fully exit position at current book depth.
            </Def>
            <Def term="NORMAL">{"TTE >= 14 days AND spread <= 5%"}</Def>
            <Def term="WATCH">{"TTE < 14 days OR spread > 5%"}</Def>
            <Def term="CRITICAL">{"TTE < 3 days"}</Def>
          </Section>

          <Section id="settings" title="7. SETTINGS">
            <p>
              Controls for the background NAV collector process. The collector
              polls Kalshi REST API and writes NAV snapshots to data/nav.db
              independently of the main app.
            </p>
          </Section>

          <Section id="keybindings" title="KEYBINDINGS">
            <div className="grid grid-cols-2 gap-1 text-zinc-400 mt-1">
              <span>
                <kbd className="text-zinc-300">1-8</kbd> Switch tabs
              </span>
              <span>
                <kbd className="text-zinc-300">r</kbd> Refresh risk
              </span>
              <span>
                <kbd className="text-zinc-300">c</kbd> Toggle collector
              </span>
              <span>
                <kbd className="text-zinc-300">Esc</kbd> Navigation
              </span>
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section id={id} className="mb-8">
      <h2 className="text-xs font-bold text-accent-cyan mb-2 border-b border-surface-3 pb-1">
        {title}
      </h2>
      <div className="text-zinc-400">{children}</div>
    </section>
  );
}

function Def({
  term,
  children,
}: {
  term: string;
  children: React.ReactNode;
}) {
  return (
    <div className="ml-2 mb-1">
      <span className="text-zinc-300 font-semibold">{term}: </span>
      <span>{children}</span>
    </div>
  );
}
