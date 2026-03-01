export default function Footer() {
  return (
    <footer className="flex items-center justify-between px-4 py-1 bg-surface-1 border-t border-surface-3 text-xs text-zinc-500">
      <div className="flex gap-4">
        <span>
          <kbd className="text-zinc-400">1-8</kbd> tabs
        </span>
        <span>
          <kbd className="text-zinc-400">r</kbd> refresh
        </span>
        <span>
          <kbd className="text-zinc-400">c</kbd> collector
        </span>
        <span>
          <kbd className="text-zinc-400">Esc</kbd> nav
        </span>
      </div>
      <span className="text-zinc-600">kalsim Risk Desk</span>
    </footer>
  );
}
