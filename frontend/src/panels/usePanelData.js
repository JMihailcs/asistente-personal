import { useEffect, useState } from 'react';

export function usePanelData(url, { intervalMs = 0, refreshKey = 0 } = {}) {
  const [data, setData] = useState(null);
  const [disconnected, setDisconnected] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(String(response.status));
        const payload = await response.json();
        if (!cancelled) {
          setData(payload);
          setDisconnected(false);
        }
      } catch {
        // Se marca desconectado y se conserva el ultimo dato bueno: mostrar
        // ceros mentiria sobre el estado real de la maquina.
        if (!cancelled) setDisconnected(true);
      }
    }

    load();
    if (!intervalMs) {
      return () => {
        cancelled = true;
      };
    }

    const id = setInterval(load, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [url, intervalMs, refreshKey]);

  return { data, disconnected };
}
