"use client";

import { useEffect, useRef, useState } from "react";
import {
  RealtimeClient,
  realtimeStreamUrl,
  type RealtimeStatus,
  type SseFrame,
} from "@/lib/sse";

export interface RealtimeStreamState {
  status: RealtimeStatus;
  attempt: number;
  nextRetryMs: number | null;
  reconnected: boolean;
}

interface UseRealtimeStreamOptions {
  enabled: boolean;
  token: string | null;
  onEvent: (frame: SseFrame) => void;
  onOpen?: (info: { reconnected: boolean }) => void;
}

/**
 * Mantiene una conexión SSE mientras el componente esté montado.
 *
 * La conexión es independiente por pestaña/usuario; la infraestructura
 * compartida (broker) vive en el backend.
 */
export function useRealtimeStream({
  enabled,
  token,
  onEvent,
  onOpen,
}: UseRealtimeStreamOptions): RealtimeStreamState {
  const [status, setStatus] = useState<RealtimeStatus>("idle");
  const [attempt, setAttempt] = useState(0);
  const [nextRetryMs, setNextRetryMs] = useState<number | null>(null);
  const [reconnected, setReconnected] = useState(false);

  const onEventRef = useRef(onEvent);
  const onOpenRef = useRef(onOpen);
  const active = enabled && Boolean(token);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    onOpenRef.current = onOpen;
  }, [onOpen]);

  useEffect(() => {
    if (!active || !token) return;

    let isMounted = true;
    const client = new RealtimeClient({
      url: realtimeStreamUrl(),
      getToken: () => token,
      onEvent: (frame) => {
        if (isMounted) onEventRef.current(frame);
      },
      onStatus: (next, detail) => {
        if (!isMounted) return;
        setStatus(next);
        if (detail?.attempt !== undefined) setAttempt(detail.attempt);
        setNextRetryMs(detail?.delayMs ?? null);
      },
      onOpen: (info) => {
        if (!isMounted) return;
        setReconnected(info.reconnected);
        onOpenRef.current?.(info);
      },
    });

    client.start();
    return () => {
      isMounted = false;
      client.stop();
    };
  }, [active, token]);

  return {
    status: active ? status : "idle",
    attempt: active ? attempt : 0,
    nextRetryMs: active ? nextRetryMs : null,
    reconnected,
  };
}