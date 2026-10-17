const MAX_STRING_LENGTH = 300;

const SENSITIVE_KEYS = new Set([
  "password",
  "new_password",
  "current_password",
  "hashed_password",
  "token",
  "access_token",
  "refresh_token",
  "authorization",
  "secret",
  "api_key",
  "jwt",
]);

const EMAIL_RE = /[\w.+-]+@[\w-]+\.[\w.-]+/g;
const JWT_RE = /\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g;
const URL_RE = /https?:\/\/[^\s"'<>]+/g;
const PHONE_RE = /(\+\d[\d\s().-]{6,}\d)|(\b\d{2,4}[\s.-]\d{2,4}[\s.-]\d{2,4}\b)/g;

export function sanitizeString(value: string): string {
  const cleaned = value
    .replace(JWT_RE, "[redacted-token]")
    .replace(EMAIL_RE, "[redacted-email]")
    .replace(URL_RE, "[redacted-url]")
    .replace(PHONE_RE, "[redacted-phone]");
  return cleaned.length > MAX_STRING_LENGTH
    ? cleaned.slice(0, MAX_STRING_LENGTH)
    : cleaned;
}

export function sanitizeValue(value: unknown): unknown {
  if (typeof value === "string") return sanitizeString(value);
  if (Array.isArray(value)) return value.map(sanitizeValue);
  if (value !== null && typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      if (SENSITIVE_KEYS.has(key.toLowerCase())) continue;
      result[key] = sanitizeValue(nested);
    }
    return result;
  }
  return value;
}

export function sanitizeProperties(properties: Record<string, unknown>): Record<string, unknown> {
  return sanitizeValue(properties) as Record<string, unknown>;
}
