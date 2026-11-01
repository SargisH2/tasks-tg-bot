import { useEffect, useRef, useState } from "react";
import type { WebSocketTaskEvent } from "../types";

interface UseTaskWebSocketOptions {
  token: string | null;
  onEvent: (event: WebSocketTaskEvent) => void;
}

function buildWebSocketUrl(token: string): string {
  const configuredPath =
    (import.meta.env.VITE_WS_URL as string | undefined) ?? "/ws/tasks";
  if (
    configuredPath.startsWith("ws://") ||
    configuredPath.startsWith("wss://")
  ) {
    const separator = configuredPath.includes("?") ? "&" : "?";
    return `${configuredPath}${separator}token=${encodeURIComponent(token)}`;
  }
  const scheme = window.location.protocol === "https:" ? "wss://" : "ws://";
  const host = window.location.host;
  return `${scheme}${host}${configuredPath}?token=${encodeURIComponent(token)}`;
}

export function useTaskWebSocket({
  token,
  onEvent,
}: UseTaskWebSocketOptions): { isConnected: boolean } {
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!token) {
      setIsConnected(false);
      return;
    }

    let isUnmounted = false;
    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let pingInterval: number | null = null;

    const connect = () => {
      if (isUnmounted) {
        return;
      }
      const wsUrl = buildWebSocketUrl(token);
      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        if (isUnmounted) {
          return;
        }
        setIsConnected(true);
        pingInterval = window.setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send("ping");
          }
        }, 25000);
      };

      ws.onmessage = (messageEvent: MessageEvent) => {
        try {
          const parsed = JSON.parse(
            String(messageEvent.data),
          ) as WebSocketTaskEvent;
          onEventRef.current(parsed);
        } catch {
          return;
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        if (pingInterval !== null) {
          window.clearInterval(pingInterval);
          pingInterval = null;
        }
        if (!isUnmounted) {
          reconnectTimer = window.setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => {
        ws?.close();
      };
    };

    connect();

    return () => {
      isUnmounted = true;
      if (reconnectTimer !== null) {
        window.clearTimeout(reconnectTimer);
      }
      if (pingInterval !== null) {
        window.clearInterval(pingInterval);
      }
      ws?.close();
    };
  }, [token]);

  return { isConnected };
}
