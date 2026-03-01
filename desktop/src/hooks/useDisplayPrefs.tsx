import { createContext, useContext, useState, useCallback, ReactNode } from "react";

type ContractNameMode = "api" | "readable";

interface DisplayPrefs {
  contractNameMode: ContractNameMode;
  setContractNameMode: (mode: ContractNameMode) => void;
}

const STORAGE_KEY = "kalsim_display_prefs";

function loadPrefs(): { contractNameMode: ContractNameMode } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.contractNameMode === "api" || parsed.contractNameMode === "readable") {
        return parsed;
      }
    }
  } catch {}
  return { contractNameMode: "api" };
}

function savePrefs(prefs: { contractNameMode: ContractNameMode }) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

const DisplayPrefsContext = createContext<DisplayPrefs>({
  contractNameMode: "api",
  setContractNameMode: () => {},
});

export function DisplayPrefsProvider({ children }: { children: ReactNode }) {
  const [contractNameMode, setMode] = useState<ContractNameMode>(loadPrefs().contractNameMode);

  const setContractNameMode = useCallback((mode: ContractNameMode) => {
    setMode(mode);
    savePrefs({ contractNameMode: mode });
  }, []);

  return (
    <DisplayPrefsContext.Provider value={{ contractNameMode, setContractNameMode }}>
      {children}
    </DisplayPrefsContext.Provider>
  );
}

export function useDisplayPrefs(): DisplayPrefs {
  return useContext(DisplayPrefsContext);
}
