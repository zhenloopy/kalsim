interface TabBarProps {
  tabs: string[];
  active: string;
  onSelect: (tab: string) => void;
}

export default function TabBar({ tabs, active, onSelect }: TabBarProps) {
  return (
    <nav className="flex bg-surface-1 border-b border-surface-3 px-2">
      {tabs.map((tab, i) => (
        <button
          key={tab}
          onClick={() => onSelect(tab)}
          className={`px-4 py-2 text-xs font-medium transition-colors ${
            active === tab
              ? "text-accent-cyan border-b-2 border-accent-cyan"
              : "text-zinc-400 hover:text-zinc-200 border-b-2 border-transparent"
          }`}
        >
          <span className="text-zinc-600 mr-1">{i + 1}:</span>
          {tab}
        </button>
      ))}
    </nav>
  );
}
