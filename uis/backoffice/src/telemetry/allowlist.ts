import { getEventDefinition } from "@shared/telemetry/catalog";

export function isKnownEvent(eventType: string): boolean {
  return getEventDefinition(eventType) !== undefined;
}

export function applyAllowlist(
  eventType: string,
  properties: Record<string, unknown>,
): Record<string, unknown> {
  const definition = getEventDefinition(eventType);
  if (!definition) return {};
  const allowed = new Set(definition.allowlist);
  const result: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(properties)) {
    if (allowed.has(key)) result[key] = value;
  }
  return result;
}

export function getMissingRequiredProperties(
  eventType: string,
  properties: Record<string, unknown>,
): string[] {
  const definition = getEventDefinition(eventType);
  if (!definition) return [];
  return definition.requiredProperties.filter((key) => properties[key] === undefined);
}
