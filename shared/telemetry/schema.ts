export const SCHEMA_VERSION = "1.0.0";

export const BATCH_SIZE = 20;
export const FLUSH_INTERVAL_MS = 10_000;
export const MAX_SEND_RETRIES = 3;
export const RETRY_BASE_DELAY_MS = 1_000;
export const DEFAULT_TELEMETRY_ENDPOINT = "/api/telemetry/events";

export type TelemetrySource = "frontend" | "backend";
export type TelemetryApp = "backoffice" | "website";
export type TelemetryEnvironment = "production" | "development" | "test";

export interface TelemetryEnvelope {
  event_id: string;
  timestamp: string;
  session_id: string;
  user_id: string | null;
  event_type: string;
  schema_version: string;
  request_id: string | null;
  source: TelemetrySource;
  app: TelemetryApp;
  properties: Record<string, unknown>;
}
