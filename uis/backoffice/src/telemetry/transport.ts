import {
  DEFAULT_TELEMETRY_ENDPOINT,
  MAX_SEND_RETRIES,
  RETRY_BASE_DELAY_MS,
  type TelemetryEnvelope,
} from "@shared/telemetry/schema";
import { getConsent } from "./consent";
import { getTelemetryEnvironment } from "./environment";

export function getTelemetryEndpoint(): string {
  const fromEnv = process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT;
  return fromEnv && fromEnv.length > 0 ? fromEnv : DEFAULT_TELEMETRY_ENDPOINT;
}

function getAppVersion(): string {
  return process.env.NEXT_PUBLIC_APP_VERSION ?? "unknown";
}

export function buildTelemetryHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-Telemetry-Environment": getTelemetryEnvironment(),
    "X-Telemetry-Consent": getConsent(),
    "X-Telemetry-App-Version": getAppVersion(),
  };
}

export function buildBeaconUrl(endpoint: string): string {
  const params = new URLSearchParams({
    environment: getTelemetryEnvironment(),
    consent: getConsent(),
    app_version: getAppVersion(),
  });
  const separator = endpoint.includes("?") ? "&" : "?";
  return `${endpoint}${separator}${params.toString()}`;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export interface SendBatchOptions {
  beacon?: boolean;
}

export async function sendTelemetryBatch(
  events: TelemetryEnvelope[],
  options: SendBatchOptions = {},
): Promise<boolean> {
  const endpoint = getTelemetryEndpoint();
  const body = JSON.stringify({ events });

  if (
    options.beacon &&
    typeof navigator !== "undefined" &&
    typeof navigator.sendBeacon === "function"
  ) {
    const blob = new Blob([body], { type: "application/json" });
    return navigator.sendBeacon(buildBeaconUrl(endpoint), blob);
  }

  for (let attempt = 0; attempt <= MAX_SEND_RETRIES; attempt += 1) {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: buildTelemetryHeaders(),
        body,
        keepalive: true,
      });
      if (response.ok) return true;
    } catch {
      // network error — retry below
    }
    if (attempt < MAX_SEND_RETRIES) {
      await delay(RETRY_BASE_DELAY_MS * 2 ** attempt);
    }
  }
  return false;
}
