import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import {
  track,
  flushTelemetry,
  initTelemetry,
  startTelemetrySession,
  setTelemetryUserId,
  clearTelemetrySession,
  beginTelemetryRequest,
  __telemetryTestUtils,
} from "../telemetry";
import { setConsent, __resetConsentForTests } from "../../telemetry/consent";
import { sendTelemetryBatch } from "../../telemetry/transport";
import { sanitizeString, sanitizeProperties } from "../../telemetry/sanitize";
import { applyAllowlist } from "../../telemetry/allowlist";
import { shouldSample } from "../../telemetry/sampling";

function fetchMock() {
  return vi.fn().mockResolvedValue({ ok: true });
}

let fetchSpy: ReturnType<typeof fetchMock>;

beforeEach(() => {
  fetchSpy = fetchMock();
  global.fetch = fetchSpy as unknown as typeof fetch;
  Object.defineProperty(navigator, "sendBeacon", {
    configurable: true,
    value: vi.fn().mockReturnValue(true),
  });
  __telemetryTestUtils.reset();
  __resetConsentForTests();
  process.env.NEXT_PUBLIC_TELEMETRY_ENABLED = "true";
  delete process.env.NEXT_PUBLIC_TELEMETRY_SAMPLE_RATE;
  setConsent("granted");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  clearTelemetrySession();
});

describe("track — envelope injection", () => {
  it("injects the full envelope without the caller passing envelope fields", () => {
    __telemetryTestUtils.setSession("session-1");
    setTelemetryUserId("user-7");
    const requestId = beginTelemetryRequest();

    track("login_failed", { failure_reason: "invalid_credentials" });

    const [event] = __telemetryTestUtils.getQueue();
    expect(event).toMatchObject({
      session_id: "session-1",
      user_id: "user-7",
      event_type: "login_failed",
      schema_version: "1.0.0",
      request_id: requestId,
      source: "frontend",
      app: "backoffice",
    });
    expect(event.event_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(new Date(event.timestamp).toISOString()).toBe(event.timestamp);
  });

  it("defaults user_id and request_id to null", () => {
    track("login_failed", { failure_reason: "invalid_credentials" });
    const [event] = __telemetryTestUtils.getQueue();
    expect(event.user_id).toBeNull();
    expect(event.request_id).toBeNull();
  });

  it("ignores unknown event types (closed enum)", () => {
    track("not_a_real_event", { foo: "bar" });
    expect(__telemetryTestUtils.getQueue()).toHaveLength(0);
  });
});

describe("batch + debounce", () => {
  it("flushes immediately when the queue reaches 20 events", async () => {
    for (let i = 0; i < 20; i += 1) {
      track("login_failed", { failure_reason: "invalid_credentials" });
    }
    expect(__telemetryTestUtils.getQueue()).toHaveLength(0);
    await vi.waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(1));
    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body.events).toHaveLength(20);
  });

  it("flushes after the 10s debounce window", async () => {
    vi.useFakeTimers();
    track("login_failed", { failure_reason: "invalid_credentials" });
    expect(__telemetryTestUtils.getQueue()).toHaveLength(1);

    await vi.advanceTimersByTimeAsync(10_000);

    expect(__telemetryTestUtils.getQueue()).toHaveLength(0);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("uses sendBeacon when the tab becomes hidden", async () => {
    initTelemetry();
    track("login_failed", { failure_reason: "invalid_credentials" });

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    });
    document.dispatchEvent(new Event("visibilitychange"));

    expect(navigator.sendBeacon).toHaveBeenCalledTimes(1);
    expect(__telemetryTestUtils.getQueue()).toHaveLength(0);
  });
});

describe("retries with exponential backoff", () => {
  it("retries 3 times then discards the batch on persistent failure", async () => {
    vi.useFakeTimers();
    const failingFetch = vi.fn().mockRejectedValue(new Error("network down"));
    global.fetch = failingFetch as unknown as typeof fetch;

    const promise = sendTelemetryBatch([
      {
        event_id: "id",
        timestamp: "2026-01-01T00:00:00.000Z",
        session_id: "s",
        user_id: null,
        event_type: "login_failed",
        schema_version: "1.0.0",
        request_id: null,
        source: "frontend",
        app: "backoffice",
        properties: {},
      },
    ]);

    await vi.runAllTimersAsync();
    const result = await promise;

    expect(result).toBe(false);
    expect(failingFetch).toHaveBeenCalledTimes(4);
  });
});

describe("barrier — consent", () => {
  it("drops analytics events when consent is denied", () => {
    setConsent("denied");
    track("page_view", { path: "/inventory", app: "backoffice" });
    expect(__telemetryTestUtils.getQueue()).toHaveLength(0);
  });

  it("keeps security events even when consent is denied", () => {
    setConsent("denied");
    track("login_failed", { failure_reason: "invalid_credentials" });
    expect(__telemetryTestUtils.getQueue()).toHaveLength(1);
  });
});

describe("barrier — environment separation", () => {
  it("does not emit when outside production without the enable flag", () => {
    process.env.NEXT_PUBLIC_TELEMETRY_ENABLED = "false";
    track("login_failed", { failure_reason: "invalid_credentials" });
    expect(__telemetryTestUtils.getQueue()).toHaveLength(0);
  });
});

describe("barrier — sampling", () => {
  it("drops high-frequency events at rate 0 and keeps regular events", () => {
    process.env.NEXT_PUBLIC_TELEMETRY_SAMPLE_RATE = "0";
    expect(shouldSample("page_view", "session-1")).toBe(false);
    expect(shouldSample("login_failed", "session-1")).toBe(true);
  });

  it("is deterministic per session", () => {
    process.env.NEXT_PUBLIC_TELEMETRY_SAMPLE_RATE = "0.5";
    const first = shouldSample("page_view", "session-x");
    const second = shouldSample("page_view", "session-x");
    expect(first).toBe(second);
  });
});

describe("barrier — allowlist + cleaning", () => {
  it("keeps only approved keys", () => {
    const filtered = applyAllowlist("login_failed", {
      failure_reason: "invalid_credentials",
      secret_key: "leak",
      email: "a@b.com",
    });
    expect(filtered).toEqual({ failure_reason: "invalid_credentials" });
  });

  it("redacts PII and drops sensitive keys", () => {
    const cleaned = sanitizeProperties({
      note: "contact me at ana@trackflow.com",
      password: "hunter2",
      nested: { token: "abc", ok: 1 },
    });
    expect(cleaned.note).toBe("contact me at [redacted-email]");
    expect(cleaned).not.toHaveProperty("password");
    expect(cleaned.nested).toEqual({ ok: 1 });
  });

  it("truncates long strings", () => {
    const long = "x".repeat(500);
    expect(sanitizeString(long)).toHaveLength(300);
  });

  it("drops disallowed keys end-to-end through track()", () => {
    track("login_failed", {
      failure_reason: "invalid_credentials",
      leaked: "should-not-appear",
    });
    const [event] = __telemetryTestUtils.getQueue();
    expect(event.properties).toEqual({ failure_reason: "invalid_credentials" });
  });
});

describe("session lifecycle", () => {
  it("regenerates the session id on startTelemetrySession", () => {
    const first = startTelemetrySession();
    const second = startTelemetrySession();
    expect(first).not.toBe(second);
  });

  it("flushTelemetry is a no-op when the queue is empty", async () => {
    await flushTelemetry();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
