import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

export type LiveStatus = "connecting" | "open" | "closed";

// Server closes with these codes when the role may not listen (4403) or the target is unknown
// (4404). Retrying would not help.
const FINAL_CLOSE_CODES = new Set([4403, 4404]);
const MIN_DELAY_MS = 1_000;
const MAX_DELAY_MS = 15_000;

export function socketUrl(path: string, location: Pick<Location, "protocol" | "host">): string {
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${location.host}${path}`;
}

/**
 * Keeps a WebSocket to `path` open (reconnecting with a growing delay) and calls `onMessage`
 * for each JSON message. Pass `null` to stay disconnected.
 */
export function useLive(path: string | null, onMessage: (data: unknown) => void): LiveStatus {
  const [status, setStatus] = useState<LiveStatus>("connecting");
  const handler = useRef(onMessage);
  useEffect(() => {
    handler.current = onMessage;
  });

  useEffect(() => {
    if (!path) return;
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = MIN_DELAY_MS;
    let stopped = false;

    const connect = () => {
      setStatus("connecting");
      socket = new WebSocket(socketUrl(path, window.location));
      socket.onopen = () => {
        delay = MIN_DELAY_MS;
        setStatus("open");
      };
      socket.onmessage = (event) => {
        try {
          handler.current(JSON.parse(event.data as string));
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onclose = (event) => {
        setStatus("closed");
        if (stopped || FINAL_CLOSE_CODES.has(event.code)) return;
        timer = setTimeout(connect, delay);
        delay = Math.min(delay * 2, MAX_DELAY_MS);
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(timer);
      socket?.close();
    };
  }, [path]);

  return status;
}

/** Refetch the given queries whenever the server pushes something (bursts are merged). */
export function useLiveRefresh(path: string | null, keys: QueryKey[]): LiveStatus {
  const queryClient = useQueryClient();
  const pending = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const keysRef = useRef(keys);
  useEffect(() => {
    keysRef.current = keys;
  });
  useEffect(() => () => clearTimeout(pending.current), []);

  return useLive(path, () => {
    clearTimeout(pending.current);
    pending.current = setTimeout(() => {
      for (const key of keysRef.current) queryClient.invalidateQueries({ queryKey: key });
    }, 150);
  });
}
