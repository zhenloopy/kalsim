import {
  createContext,
  useContext,
  useState,
  useEffect,
  useMemo,
  ReactNode,
} from "react";
import { kalsimWS } from "../api/ws";
import { api } from "../api/client";
import {
  Position,
  VaRData,
  KellyData,
  LiquidityMetric,
  WSMessage,
} from "../api/types";

export interface BookState {
  nav: number;
  cash: number;
  portfolioValue: number;
  totalPnl: number;
  wsConnected: boolean;
  collectorRunning: boolean;
  positions: Position[];
  titleMap: Record<string, string>;
  var: VaRData | null;
  kelly: KellyData | null;
  liquidity: LiquidityMetric[];
}

const defaultState: BookState = {
  nav: 0,
  cash: 0,
  portfolioValue: 0,
  totalPnl: 0,
  wsConnected: false,
  collectorRunning: false,
  positions: [],
  titleMap: {},
  var: null,
  kelly: null,
  liquidity: [],
};

const BookStateContext = createContext<BookState>(defaultState);

export function BookStateProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<BookState>(defaultState);

  useEffect(() => {
    api.getStatus().then((s) =>
      setState((prev) => ({
        ...prev,
        nav: s.nav,
        cash: s.cash,
        portfolioValue: s.portfolio_value,
        totalPnl: s.total_pnl,
        wsConnected: s.ws_connected,
        collectorRunning: s.collector_running,
      }))
    ).catch(() => {});

    api.getPositions().then((p) =>
      setState((prev) => ({ ...prev, positions: p }))
    ).catch(() => {});

    api.getVaR().then((v) =>
      setState((prev) => ({ ...prev, var: v }))
    ).catch(() => {});

    api.getKelly().then((k) =>
      setState((prev) => ({ ...prev, kelly: k }))
    ).catch(() => {});

    api.getLiquidity().then((l) =>
      setState((prev) => ({ ...prev, liquidity: l }))
    ).catch(() => {});
  }, []);

  useEffect(() => {
    kalsimWS.connect();

    const unsub = kalsimWS.subscribe((msg: WSMessage) => {
      if (msg.type === "book_update") {
        setState((prev) => ({
          ...prev,
          nav: msg.nav,
          cash: msg.cash,
          portfolioValue: msg.portfolio_value,
          totalPnl: msg.total_pnl,
          wsConnected: msg.ws_connected,
          collectorRunning: msg.collector_running,
          positions: msg.positions,
        }));
      } else if (msg.type === "risk_update") {
        setState((prev) => ({
          ...prev,
          var: msg.var ?? prev.var,
          kelly: msg.kelly ?? prev.kelly,
          liquidity: msg.liquidity ?? prev.liquidity,
        }));
      }
    });

    return () => {
      unsub();
      kalsimWS.disconnect();
    };
  }, []);

  const stateWithTitles = useMemo(() => {
    const titleMap: Record<string, string> = {};
    for (const p of state.positions) {
      if (p.title) titleMap[p.contract_id] = p.title;
    }
    return { ...state, titleMap };
  }, [state]);

  return (
    <BookStateContext.Provider value={stateWithTitles}>
      {children}
    </BookStateContext.Provider>
  );
}

export function useBookState(): BookState {
  return useContext(BookStateContext);
}
