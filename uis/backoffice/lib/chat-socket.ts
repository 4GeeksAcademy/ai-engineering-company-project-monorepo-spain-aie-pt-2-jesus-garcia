/**
 * Cliente WebSocket del chat con reconexión progresiva.
 *
 * Reutiliza el backoff del SSE de la Parte 1 (1 s → 30 s con jitter) y reenvía
 * siempre el mismo `session_id`: el servidor responde con `session_snapshot`
 * antes de continuar con tokens nuevos, así no se pierde el hilo.
 */

import { backoffDelay, type BackoffOptions } from "./sse";
import type { ChatEvent } from "./chat-types";

export type ChatSocketStatus =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "unauthorized"
  | "stopped";

export interface ChatSocketStatusDetail {
  attempt?: number;
  delayMs?: number;
  error?: string;
}

export interface WebSocketLike {
  readyState: number;
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  onerror: ((event: Event) => void) | null;
  send(data: string): void;
  close(code?: number, reason?: string): void;
}

export type WebSocketFactory = (url: string) => WebSocketLike;

export interface ChatSocketOptions {
  sessionId: string;
  token: string;
  url?: string;
  onEvent: (event: ChatEvent) => void;
  onStatus?: (status: ChatSocketStatus, detail?: ChatSocketStatusDetail) => void;
  onOpen?: (info: { reconnected: boolean }) => void;
  onAuthError?: () => void;
  backoff?: BackoffOptions;
  random?: () => number;
  createSocket?: WebSocketFactory;
  schedule?: (callback: () => void, ms: number) => unknown;
  clearSchedule?: (handle: unknown) => void;
  inactivityTimeoutMs?: number;
}

export const CHAT_INACTIVITY_TIMEOUT_MS = 45_000;

const AUTH_CLOSE_CODES = new Set([4401, 4403, 4404]);

export function chatSocketUrl(sessionId: string, token: string): string {
  const configured = (process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/$/, "");
  const isLocalBrowser =
    typeof window !== "undefined" &&
    (window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1");
  // En dev local el backoffice no define NEXT_PUBLIC_API_URL: se usa el API
  // del compose en localhost. En Docker la variable llega desde el .env raíz.
  const base = configured || (isLocalBrowser ? "http://localhost:8000" : "");
  const fallbackOrigin =
    typeof window !== "undefined" ? window.location.origin : "http://localhost:8000";
  const url = new URL(base || fallbackOrigin);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = base ? "/chat/ws" : "/api/chat/ws";
  url.search = "";
  url.searchParams.set("session_id", sessionId);
  url.searchParams.set("token", token);
  return url.toString();
}

export class ChatSocket {
  private socket: WebSocketLike | null = null;
  private stopped = false;
  private started = false;
  private attempt = 0;
  private timer: unknown = null;
  private watchdog: ReturnType<typeof setTimeout> | null = null;
  private hasOpenedOnce = false;

  constructor(private readonly options: ChatSocketOptions) {}

  start(): void {
    if (this.stopped || this.started) return;
    this.started = true;
    void this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.started = false;
    this.clearWatchdog();
    this.clearTimer();
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onclose = null;
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      try {
        socket.close(1000, "client_stop");
      } catch {
        /* socket ya cerrado */
      }
    }
    this.options.onStatus?.("stopped");
  }

  isOpen(): boolean {
    return this.socket?.readyState === 1;
  }

  sendUserMessage(text: string): boolean {
    return this.send({
      event: "user_message",
      data: { session_id: this.options.sessionId, text },
    });
  }

  sendInterrupt(newInput: string | null): boolean {
    return this.send({
      event: "interrupt_requested",
      data: {
        session_id: this.options.sessionId,
        new_input: newInput,
      },
    });
  }

  private send(payload: unknown): boolean {
    if (!this.isOpen()) return false;
    try {
      this.socket?.send(JSON.stringify(payload));
      return true;
    } catch {
      return false;
    }
  }

  private connect(): void {
    if (this.stopped) return;
    this.options.onStatus?.(this.attempt ? "reconnecting" : "connecting");
    const factory: WebSocketFactory =
      this.options.createSocket ??
      ((url) => new WebSocket(url) as unknown as WebSocketLike);
    let socket: WebSocketLike;
    try {
      socket = factory(
        this.options.url ??
          chatSocketUrl(this.options.sessionId, this.options.token),
      );
    } catch (error) {
      this.options.onStatus?.("reconnecting", {
        attempt: this.attempt + 1,
        error: String(error),
      });
      this.scheduleReconnect();
      return;
    }
    this.socket = socket;

    socket.onopen = () => {
      if (this.stopped) return;
      const reconnected = this.hasOpenedOnce;
      this.hasOpenedOnce = true;
      this.attempt = 0;
      this.options.onStatus?.("open");
      this.options.onOpen?.({ reconnected });
      this.armWatchdog();
    };

    socket.onmessage = (event: MessageEvent) => {
      if (this.stopped) return;
      this.armWatchdog();
      const parsed = this.parse(event.data);
      if (!parsed) return;
      if (parsed.event === "ping") {
        this.send({
          event: "pong",
          data: { session_id: this.options.sessionId },
        });
        return;
      }
      this.options.onEvent(parsed);
    };

    socket.onerror = () => {
      // `onclose` llega después y decide si toca reconectar.
    };

    socket.onclose = (event: CloseEvent) => {
      if (this.stopped) return;
      this.socket = null;
      this.clearWatchdog();
      if (AUTH_CLOSE_CODES.has(event.code)) {
        this.options.onStatus?.("unauthorized", {
          error: `close_${event.code}`,
        });
        this.options.onAuthError?.();
        return;
      }
      this.options.onStatus?.("reconnecting", {
        attempt: this.attempt + 1,
        error: event.reason || `close_${event.code}`,
      });
      this.scheduleReconnect();
    };
  }

  private parse(raw: unknown): ChatEvent | null {
    if (typeof raw !== "string") return null;
    try {
      const parsed = JSON.parse(raw) as ChatEvent;
      if (!parsed || typeof parsed.event !== "string") return null;
      return parsed;
    } catch {
      return null;
    }
  }

  private scheduleReconnect(): void {
    if (this.stopped) return;
    const delayMs = backoffDelay(
      this.attempt,
      this.options.backoff,
      this.options.random,
    );
    this.attempt += 1;
    this.clearTimer();
    const callback = () => {
      this.timer = null;
      this.connect();
    };
    this.timer = this.options.schedule
      ? this.options.schedule(callback, delayMs)
      : setTimeout(callback, delayMs);
  }

  private clearTimer(): void {
    if (this.timer === null) return;
    if (this.options.clearSchedule) this.options.clearSchedule(this.timer);
    else clearTimeout(this.timer as ReturnType<typeof setTimeout>);
    this.timer = null;
  }

  private armWatchdog(): void {
    const timeout =
      this.options.inactivityTimeoutMs ?? CHAT_INACTIVITY_TIMEOUT_MS;
    this.clearWatchdog();
    if (timeout <= 0) return;
    this.watchdog = setTimeout(() => {
      this.watchdog = null;
      if (this.stopped || !this.socket) return;
      try {
        this.socket.close(4000, "inactivity");
      } catch {
        /* el socket ya está cerrado */
      }
    }, timeout);
  }

  private clearWatchdog(): void {
    if (this.watchdog) {
      clearTimeout(this.watchdog);
      this.watchdog = null;
    }
  }
}
