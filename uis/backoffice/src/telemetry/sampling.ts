import { getEventDefinition } from "@shared/telemetry/catalog";

export function getGlobalSampleRate(): number {
  const raw = process.env.NEXT_PUBLIC_TELEMETRY_SAMPLE_RATE;
  const parsed = raw === undefined || raw === "" ? NaN : Number(raw);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 1) return 1;
  return parsed;
}

export function getSampleRate(eventType: string): number {
  const definition = getEventDefinition(eventType);
  const base = definition ? definition.sampleRate : 1;
  return base * getGlobalSampleRate();
}

function hash(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function shouldSample(eventType: string, sessionId: string): boolean {
  const definition = getEventDefinition(eventType);
  if (!definition || !definition.highFrequency) return true;
  const rate = getSampleRate(eventType);
  if (rate >= 1) return true;
  if (rate <= 0) return false;
  const bucket = hash(`${sessionId}:${eventType}`) / 0xffffffff;
  return bucket < rate;
}
