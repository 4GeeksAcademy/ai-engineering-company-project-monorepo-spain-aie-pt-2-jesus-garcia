import {
  BATCH_SIZE,
  FLUSH_INTERVAL_MS,
  SCHEMA_VERSION,
  type TelemetryApp,
  type TelemetryEnvelope,
} from "@shared/telemetry/schema";
import { getEventDefinition } from "@shared/telemetry/catalog";
import { isAnalyticsAllowed } from "../telemetry/consent";
import { isTelemetryTransportEnabled } from "../telemetry/environment";
import { applyAllowlist } from "../telemetry/allowlist";
import { shouldSample } from "../telemetry/sampling";
import { sanitizeProperties } from "../telemetry/sanitize";
import { sendTelemetryBatch } from "../telemetry/transport";

const APP: TelemetryApp = "backoffice";
const SESSION_STORAGE_KEY = "trackflow_session_id";

let queue: TelemetryEnvelope[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;
let sessionId: string | null = null;
let userId: string | null = null;
let currentRequestId: string | null = null;
let listenersRegistered = false;

function uuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (char) => {
    const random = (Math.random() * 16) | 0;
    const value = char === "x" ? random : (random & 0x3) | 0x8;
    return value.toString(16);
  });
}

function readStoredSession(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(SESSION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeSession(id: string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(SESSION_STORAGE_KEY, id);
  } catch {
    // storage unavailable (private mode)
  }
}

function getSessionId(): string {
  if (sessionId) return sessionId;
  sessionId = readStoredSession() ?? uuid();
  storeSession(sessionId);
  return sessionId;
}

export function startTelemetrySession(): string {
  sessionId = uuid();
  storeSession(sessionId);
  return sessionId;
}

export function setTelemetryUserId(userIdValue: string | null): void {
  userId = userIdValue;
}

export function clearTelemetrySession(): void {
  sessionId = null;
  userId = null;
  currentRequestId = null;
  if (typeof window !== "undefined") {
    try {
      window.sessionStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {
      // ignore
    }
  }
}

export function beginTelemetryRequest(): string {
  currentRequestId = uuid();
  return currentRequestId;
}

function enqueue(envelope: TelemetryEnvelope): void {
  queue.push(envelope);
  if (queue.length >= BATCH_SIZE) {
    void flushTelemetry();
  } else {
    scheduleFlush();
  }
}

function scheduleFlush(): void {
  if (flushTimer !== null) return;
  flushTimer = setTimeout(() => {
    flushTimer = null;
    void flushTelemetry();
  }, FLUSH_INTERVAL_MS);
}

export async function flushTelemetry(options: { beacon?: boolean } = {}): Promise<void> {
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  if (queue.length === 0) return;
  const batch = queue;
  queue = [];
  await sendTelemetryBatch(batch, options);
}

export function track(
  eventType: string,
  properties: Record<string, unknown> = {},
): void {
  if (typeof window === "undefined") return;

  const definition = getEventDefinition(eventType);
  if (!definition) return;

  if (definition.requiresConsent && !isAnalyticsAllowed()) return;

  const sanitized = sanitizeProperties(properties);
  const filtered = applyAllowlist(eventType, sanitized);

  const currentSessionId = getSessionId();
  if (!shouldSample(eventType, currentSessionId)) return;

  if (!isTelemetryTransportEnabled()) return;

  enqueue({
    event_id: uuid(),
    timestamp: new Date().toISOString(),
    session_id: currentSessionId,
    user_id: userId,
    event_type: eventType,
    schema_version: SCHEMA_VERSION,
    request_id: currentRequestId,
    source: definition.source,
    app: APP,
    properties: filtered,
  });
}

export function initTelemetry(): () => void {
  if (typeof document === "undefined" || listenersRegistered) return () => {};
  const handler = () => {
    if (document.visibilityState === "hidden") {
      void flushTelemetry({ beacon: true });
    }
  };
  document.addEventListener("visibilitychange", handler);
  listenersRegistered = true;
  return () => {
    document.removeEventListener("visibilitychange", handler);
    listenersRegistered = false;
  };
}

export const __telemetryTestUtils = {
  reset(): void {
    queue = [];
    if (flushTimer !== null) {
      clearTimeout(flushTimer);
      flushTimer = null;
    }
    sessionId = null;
    userId = null;
    currentRequestId = null;
    listenersRegistered = false;
  },
  getQueue(): TelemetryEnvelope[] {
    return queue;
  },
  setSession(id: string): void {
    sessionId = id;
  },
};
