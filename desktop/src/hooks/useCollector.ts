import { useState, useEffect, useCallback } from "react";
import { api } from "../api/client";
import { CollectorStatus } from "../api/types";

export function useCollector() {
  const [status, setStatus] = useState<CollectorStatus>({
    running: false,
    interval: 60,
  });

  const refresh = useCallback(() => {
    api.getCollectorStatus().then(setStatus).catch(() => {});
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, [refresh]);

  const start = useCallback(
    (interval: number) => {
      api.startCollector(interval).then(setStatus).catch(() => {});
    },
    []
  );

  const stop = useCallback(() => {
    api.stopCollector().then(setStatus).catch(() => {});
  }, []);

  return { status, start, stop, refresh };
}
