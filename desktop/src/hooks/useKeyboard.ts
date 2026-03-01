import { useEffect } from "react";

type KeyHandler = (key: string) => void;

export function useKeyboard(handler: KeyHandler): void {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;

      if (e.key >= "1" && e.key <= "8") {
        e.preventDefault();
        handler(e.key);
      } else if (e.key === "r" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        handler("r");
      } else if (e.key === "c" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        handler("c");
      } else if (e.key === "Escape") {
        handler("Escape");
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handler]);
}
