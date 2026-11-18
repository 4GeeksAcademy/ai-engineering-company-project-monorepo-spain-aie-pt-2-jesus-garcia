/**
 * Cliente SSE sobre `fetch` + `ReadableStream`.
 *
 * No se usa `EventSource` porque no permite enviar `Authorization` de forma
 * limpia; aquí el JWT del backoffice viaja en la cabecera y la reconexión se
 * controla con backoff progresivo + jitter.
 */

export interface SseFrame {
  id: string | null;
  event: string;
  data: string;
  retry: number | null;
}

export type RealtimeStatus =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "unauthorized"
  | "stopped";

export interface RealtimeStatusDetail {
  attempt?: number;
  delayMs?: number;
  error?: string;
}

export interface BackoffOptions {
  baseMs?: number;
  maxMs?: number;
  factor?: number;
  jitter?: number;
}

export const DEFAULT_BACKOFF: Required<BackoffOptions> = {
  baseMs: 1000,
  maxMs: 30000,
  factor: 2,
  jitter: 0.2,
};

function clamp01(value: number): number {
  if (Number.isNaN(value)) return 0.5;
  return Math.min(1, Math.max(0, value));
}

/** Retardo exponencial con jitter; `attempt` empieza en 0 (1s, 2s, 4s...). */
export function backoffDelay(
  attempt: number,
  options: BackoffOptions = {},
  random: () => number = Math.random,
): number {
  const baseMs = options.baseMs ?? DEFAULT_BACKOFF.baseMs;
  const maxMs = options.maxMs ?? DEFAULT_BACKOFF.maxMs;
  const factor = options.factor ?? DEFAULT_BACKOFF.factor;
  const jitter = options.jitter ?? DEFAULT_BACKOFF.jitter;
  const raw = Math.min(maxMs, baseMs * Math.pow(factor, Math.max(0, attempt)));
  if (jitter <= 0) return Math.round(raw);
  return Math.round(raw * (1 - jitter + 2 * jitter * clamp01(random())));
}

function parseFrameBlock(block: string): SseFrame | null {
  let id: string | null = null;
  let event = "message";
  let retry: number | null = null;
  const data: string[] = [];
  let hasField = false;

  for (const rawLine of block.split("\n")) {
    if (!rawLine || rawLine.startsWith(":")) continue;
    const colon = rawLine.indexOf(":");
    const field = colon === -1 ? rawLine : rawLine.slice(0, colon);
    let value = colon === -1 ? "" : rawLine.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    switch (field) {
      case "id":
        id = value;
        hasField = true;
        break;
      case "event":
        event = value || "message";
        hasField = true;
        break;
      case "data":
        data.push(value);
        hasField = true;
        break;
      case "retry": {
        const parsed = Number(value);
        retry = Number.isFinite(parsed) ? parsed : null;
        hasField = true;
        break;
      }
      default:
        break;
    }
  }

  if (!hasField) return null;
  return { id, event, data: data.join("\n"), retry };
}

/** Parser incremental: soporta frames partidos entre chunks y CRLF. */
export class SseParser {
  private buffer = "";
  private pendingCr = false;

  push(chunk: string): SseFrame[] {
    let text = chunk;
    if (this.pendingCr) {
      text = `\r${text}`;
      this.pendingCr = false;
    }
    if (text.endsWith("\r")) {
      this.pendingCr = true;
      text = text.slice(0, -1);
    }
    this.buffer += text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    return this.drain();
  }

  flush(): SseFrame[] {
    if (!this.buffer.trim()) {
      this.buffer = "";
      return [];
    }
    const block = this.buffer;
    this.buffer = "";
    const frame = parseFrameBlock(block);
    return frame ? [frame] : [];
  }

  private drain(): SseFrame[] {
    const frames: SseFrame[] = [];
    let index = this.buffer.indexOf("\n\n");
    while (index !== -1) {
      const block = this.buffer.slice(0, index);
      this.buffer = this.buffer.slice(index + 2);
      const frame = parseFrameBlock(block);
      if (frame) frames.push(frame);
      index = this.buffer.indexOf("\n\n");
    }
    return frames;
  }
}

export function realtimeStreamUrl(): string {
  const base = (process.env.NEXT_PUBLIC_API_URL ?? "").trim().replace(/\/$/, "");
  return base ? `${base}/realtime/stream` : "/api/realtime/stream";
}

export interface RealtimeClientOptions {
  url: string;
  getToken: () => string | null;
  onEvent: (frame: SseFrame) => void;
  onStatus?: (status: RealtimeStatus, detail?: RealtimeStatusDetail) => void;
  onOpen?: (info: { reconnected: boolean }) => void;
  onAuthError?: () => void;
  backoff?: BackoffOptions;
  random?: () => number;
  fetchImpl?: typeof fetch;
  schedule?: (callback: () => void, ms: number) => unknown;
  clearSchedule?: (handle: unknown) => void;
  /**
   * Corte por inactividad (conexión medio abierta). El servidor manda un
   * keep-alive cada 15 s; 45 s son tres latidos perdidos. Un proxy que no
   * propaga el cierre del upstream deja la conexión muda: sin este guardia el
   * cliente creería estar conectado para siempre.
   */
  inactivityTimeoutMs?: number;
}

export const DEFAULT_INACTIVITY_TIMEOUT_MS = 45000;

/**
 * Conexión SSE con reconexión exponencial.
 *
 * - Reinicia el backoff al abrir el stream (una conexión sana no arrastra el
 *   retardo de una caída anterior).
 * - No reintenta ante 401/403: la sesión no es válida y reintentar solo
 *   generaría ruido; se avisa con `onAuthError`.
 * - Reenvía `Last-Event-ID` para pedir el replay corto del servidor.
 */
export class RealtimeClient {
  private controller: AbortController | null = null;
  private stopped = false;
  private started = false;
  private attempt = 0;
  private timer: unknown = null;
  private watchdog: ReturnType<typeof setTimeout> | null = null;
  private lastEventId: string | null = null;
  private hasOpenedOnce = false;

  constructor(private readonly options: RealtimeClientOptions) {}

  start(): void {
    if (this.stopped) return;
    if (this.started) return;
    this.started = true;
    void this.connect();
  }

  stop(): void {
    this.stopped = true;
    this.started = false;
    this.controller?.abort();
    this.controller = null;
    this.disarmWatchdog();
    if (this.timer !== null) {
      if (this.options.clearSchedule) this.options.clearSchedule(this.timer);
      else clearTimeout(this.timer as ReturnType<typeof setTimeout>);
      this.timer = null;
    }
    this.options.onStatus?.("stopped");
  }

  private armWatchdog(): void {
    const timeout = this.options.inactivityTimeoutMs ?? DEFAULT_INACTIVITY_TIMEOUT_MS;
    if (timeout <= 0) return;
    this.disarmWatchdog();
    this.watchdog = setTimeout(() => {
      this.watchdog = null;
      if (this.stopped) return;
      // Conexión medio abierta: se corta y el backoff programa la reconexión.
      this.controller?.abort();
      this.endWithRetry();
    }, timeout);
  }

  private disarmWatchdog(): void {
    if (this.watchdog) {
      clearTimeout(this.watchdog);
      this.watchdog = null;
    }
  }

  getLastEventId(): string | null {
    return this.lastEventId;
  }

  private schedule(callback: () => void, ms: number): void {
    const runner = this.options.schedule ?? ((fn, delay) => setTimeout(fn, delay));
    this.timer = runner(() => {
      this.timer = null;
      callback();
    }, ms);
  }

  private activeToken(): string | null {
    return this.options.getToken();
  }

  private endWithRetry(): void {
    if (this.stopped) return;
    const delayMs = backoffDelay(
      this.attempt,
      this.options.backoff,
      this.options.random,
    );
    this.attempt += 1;
    this.options.onStatus?.("reconnecting", { attempt: this.attempt, delayMs });
    this.schedule(() => void this.connect(), delayMs);
  }

  private dispatch(frame: SseFrame): void {
    if (frame.id) this.lastEventId = frame.id;
    this.options.onEvent(frame);
  }

  private async connect(): Promise<void> {
    if (this.stopped) return;
    const token = this.activeToken();
    if (!token) {
      this.options.onStatus?.("unauthorized");
      return;
    }

    this.options.onStatus?.(
      this.attempt > 0 ? "reconnecting" : "connecting",
      { attempt: this.attempt },
    );

    const controller = new AbortController();
    this.controller = controller;

    try {
      const headers: Record<string, string> = {
        Accept: "text/event-stream",
        Authorization: `Bearer ${token}`,
      };
      if (this.lastEventId) headers["Last-Event-ID"] = this.lastEventId;

      const fetchImpl = this.options.fetchImpl ?? fetch;
      const response = await fetchImpl(this.options.url, {
        method: "GET",
        headers,
        signal: controller.signal,
        cache: "no-store",
      });

      if (response.status === 401 || response.status === 403) {
        this.options.onStatus?.("unauthorized");
        this.options.onAuthError?.();
        this.stop();
        return;
      }
      if (!response.ok) {
        throw new Error(`El stream respondió ${response.status}`);
      }
      const contentType = response.headers.get("content-type") ?? "";
      if (!contentType.includes("text/event-stream")) {
        throw new Error("La respuesta no es text/event-stream");
      }

      const reconnected = this.hasOpenedOnce;
      this.hasOpenedOnce = true;
      this.attempt = 0;
      this.options.onStatus?.("open");
      this.options.onOpen?.({ reconnected });

      const reader = response.body?.getReader();
      if (!reader) throw new Error("La respuesta no tiene cuerpo legible");

      this.armWatchdog();
      const decoder = new TextDecoder();
      const parser = new SseParser();
      while (!this.stopped) {
        const { value, done } = await reader.read();
        if (done) break;
        if (!value) continue;
        this.armWatchdog();
        for (const frame of parser.push(decoder.decode(value, { stream: true }))) {
          this.dispatch(frame);
        }
      }
      for (const frame of parser.flush()) this.dispatch(frame);
      this.disarmWatchdog();
      this.endWithRetry();
    } catch (error) {
      this.disarmWatchdog();
      if (this.stopped) return;
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (!this.stopped) this.endWithRetry();
    }
  }
}
