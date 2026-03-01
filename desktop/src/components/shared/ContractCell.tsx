import { useBookState } from "../../hooks/useBookState";
import { useDisplayPrefs } from "../../hooks/useDisplayPrefs";

export default function ContractCell({ contractId }: { contractId: string }) {
  const { titleMap } = useBookState();
  const { contractNameMode } = useDisplayPrefs();
  const title = titleMap[contractId];

  if (contractNameMode === "readable" && title) {
    return <>{title}</>;
  }
  return <>{contractId}</>;
}
