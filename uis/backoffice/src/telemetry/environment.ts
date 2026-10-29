import type { TelemetryEnvironment } from "@shared/telemetry/schema";

export function getTelemetryEnvironment(): TelemetryEnvironment {
  const explicit = process.env.NEXT_PUBLIC_APP_ENV ?? process.env.NODE_ENV;
  if (explicit === "production") return "production";
  if (explicit === "test") return "test";
  return "development";
}

export function isTelemetryTransportEnabled(): boolean {
  if (process.env.NEXT_PUBLIC_TELEMETRY_ENABLED === "true") return true;
  return getTelemetryEnvironment() === "production";
}
