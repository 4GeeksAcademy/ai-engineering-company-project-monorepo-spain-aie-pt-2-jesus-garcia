export type ConsentStatus = "granted" | "denied" | "unset";

const CONSENT_KEY = "trackflow_analytics_consent";

const listeners = new Set<(status: ConsentStatus) => void>();

let memory: ConsentStatus | null = null;

export function getConsent(): ConsentStatus {
  if (memory !== null) return memory;
  if (typeof window === "undefined") return "unset";
  try {
    const stored = window.localStorage.getItem(CONSENT_KEY);
    memory = stored === "granted" || stored === "denied" ? stored : "unset";
  } catch {
    memory = "unset";
  }
  return memory;
}

export function setConsent(status: ConsentStatus): void {
  memory = status;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(CONSENT_KEY, status);
    } catch {
      // storage unavailable (private mode) — keep in-memory only
    }
  }
  listeners.forEach((listener) => listener(status));
}

export function isAnalyticsAllowed(): boolean {
  return getConsent() === "granted";
}

export function subscribeConsent(listener: (status: ConsentStatus) => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function __resetConsentForTests(): void {
  memory = null;
  listeners.clear();
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(CONSENT_KEY);
    } catch {
      // ignore
    }
  }
}
