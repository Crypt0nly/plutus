import { useEffect, useRef, useCallback, useState } from "react";
import type { WSMessage } from "../lib/types";

type MessageHandler = (msg: WSMessage) => void;

// Token getter — injected by the Clerk-aware wrapper
let _wsTokenGetter: (() => Promise<string | null>) | null = null;

export function setWsTokenGetter(fn: () => Promise<string | null>) {
  _wsTokenGetter = fn;
}

export function useWebSocket(onMessage: MessageHandler) {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const handlersRef = useRef(onMessage);
  handlersRef.current = onMessage;

  useEffect(() => {
    let reconnectDelay = 1000;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let destroyed = false;

    async function connect() {
      if (destroyed) return;

      // In production the backend is on a different origin (api.useplutus.ai)
      // so we derive the WS URL from VITE_API_BASE_URL if available.
      // Falls back to window.location.host for local dev.
      let url: string;
      const apiBase = import.meta.env.VITE_API_BASE_URL as string | undefined;
      if (apiBase) {
        // Convert https://api.useplutus.ai → wss://api.useplutus.ai/ws
        url = apiBase.replace(/^https:/, "wss:").replace(/^http:/, "ws:") + "/ws";
      } else {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        url = `${protocol}//${window.location.host}/ws`;
      }

      // Append Clerk JWT as query param if available
      if (_wsTokenGetter) {
        try {
          const token = await _wsTokenGetter();
          if (token) {
            url = `${url}?token=${encodeURIComponent(token)}`;
          }
        } catch {
          // proceed without token
        }
      }

      const ws = new WebSocket(url);

      ws.onopen = () => {
        setConnected(true);
        reconnectDelay = 1000; // Reset backoff on successful connect

        // Request the current session list so the tab bar is populated
        ws.send(JSON.stringify({ type: "list_sessions" }));

        // Application-level ping every 15s (supplements protocol-level ping)
        const interval = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, 15000);
        ws.addEventListener("close", () => clearInterval(interval));
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WSMessage;
          handlersRef.current(data);
        } catch {
          // ignore parse errors
        }
      };

      ws.onclose = () => {
        setConnected(false);
        if (!destroyed) {
          // Reconnect with exponential backoff (1s → 2s → 4s → … → max 30s)
          reconnectTimer = setTimeout(connect, reconnectDelay);
          reconnectDelay = Math.min(reconnectDelay * 2, 30000);
        }
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    }

    connect();

    return () => {
      destroyed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, []);

  const send = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { send, connected };
}
