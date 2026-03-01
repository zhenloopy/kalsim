import { useState } from "react";
import Header from "./components/layout/Header";
import TabBar from "./components/layout/TabBar";
import Footer from "./components/layout/Footer";
import { useBookState, BookStateProvider } from "./hooks/useBookState";
import { DisplayPrefsProvider } from "./hooks/useDisplayPrefs";
import { useKeyboard } from "./hooks/useKeyboard";
import PositionsTab from "./components/tabs/PositionsTab";
import OrderbookTab from "./components/tabs/OrderbookTab";
import VarTab from "./components/tabs/VarTab";
import KellyTab from "./components/tabs/KellyTab";
import ScenariosTab from "./components/tabs/ScenariosTab";
import LiquidityTab from "./components/tabs/LiquidityTab";
import DocsTab from "./components/tabs/DocsTab";
import SettingsTab from "./components/tabs/SettingsTab";

const TABS = [
  "Positions",
  "Orderbook",
  "VaR/Risk",
  "Kelly",
  "Scenarios",
  "Liquidity",
  "Docs",
  "Settings",
] as const;

type TabName = (typeof TABS)[number];

function AppContent() {
  const [activeTab, setActiveTab] = useState<TabName>("Positions");
  const state = useBookState();

  useKeyboard((key) => {
    const tabIndex = parseInt(key) - 1;
    if (tabIndex >= 0 && tabIndex < TABS.length) {
      setActiveTab(TABS[tabIndex]);
      return;
    }
    if (key === "r") {
      fetch("http://127.0.0.1:8321/api/risk/refresh", { method: "POST" });
    }
  });

  const renderTab = () => {
    switch (activeTab) {
      case "Positions":
        return <PositionsTab />;
      case "Orderbook":
        return <OrderbookTab />;
      case "VaR/Risk":
        return <VarTab />;
      case "Kelly":
        return <KellyTab />;
      case "Scenarios":
        return <ScenariosTab />;
      case "Liquidity":
        return <LiquidityTab />;
      case "Docs":
        return <DocsTab />;
      case "Settings":
        return <SettingsTab />;
    }
  };

  return (
    <div className="flex flex-col h-screen bg-surface-0">
      <Header
        nav={state.nav}
        totalPnl={state.totalPnl}
        positionCount={state.positions.length}
        wsConnected={state.wsConnected}
        collectorRunning={state.collectorRunning}
      />
      <TabBar
        tabs={TABS as unknown as string[]}
        active={activeTab}
        onSelect={(t) => setActiveTab(t as TabName)}
      />
      <main className="flex-1 overflow-auto p-4">{renderTab()}</main>
      <Footer />
    </div>
  );
}

export default function App() {
  return (
    <DisplayPrefsProvider>
      <BookStateProvider>
        <AppContent />
      </BookStateProvider>
    </DisplayPrefsProvider>
  );
}
