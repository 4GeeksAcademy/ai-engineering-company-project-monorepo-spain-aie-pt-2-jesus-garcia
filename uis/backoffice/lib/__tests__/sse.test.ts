import { describe, expect, it, vi } from "vitest";
import {
  RealtimeClient,
  SseParser,
  backoffDelay,
  type SseFrame,
} from "@/lib/sse";

function streamFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

describe("SseParser", () => {
  it("parsea frames partidos entre chunks y descarta comentarios", () => {
    const parser = new SseParser();
    expect(parser.push(": keep-alive\n\n")).toEqual([]);

    expect(parser.push("retry: 3000\n\n")).toEqual([
      { id: null, event: "message", data: "", retry: 3000 },
    ]);

    const head = parser.push(
      'id: 7\nevent: rfp_ticket_created\ndata: {"ticket_id":"t1"}',
    );
    expect(head).toEqual([]);
    expect(parser.push("\n\n")).toEqual([
      {
        id: "7",
        event: "rfp_ticket_created",
        data: '{"ticket_id":"t1"}',
        retry: null,
      },
    ]);
  });

  it("normaliza CRLF y une data multilínea", () => {
    const parser = new SseParser();
    const frames = parser.push(
      'event: rfp_ticket_created\r\ndata: {"ticket_id":\r\ndata:  "t1"}\r\n\r\n',
    );
    expect(frames).toHaveLength(1);
    expect(frames[0].event).toBe("rfp_ticket_created");
    expect(frames[0].data).toBe('{"ticket_id":\n "t1"}');
  });

  it("tolera un CR final partido entre chunks (CRLF completo)", () => {
    const parser = new SseParser();
    expect(parser.push("event: rfp_ticket_created\r")).toEqual([]);
    const frames = parser.push('\ndata: {"ticket_id":"t1"}\r\n\r\n');
    expect(frames).toHaveLength(1);
    expect(frames[0].event).toBe("rfp_ticket_created");
    expect(frames[0].data).toBe('{"ticket_id":"t1"}');
  });
});

describe("backoffDelay", () => {
  it("crece de forma exponencial hasta el tope de 30 s", () => {
    const random = () => 0.5;
    expect([0, 1, 2, 3, 4, 5, 6].map((attempt) => backoffDelay(attempt, {}, random))).toEqual([
      1000, 2000, 4000, 8000, 16000, 30000, 30000,
    ]);
  });

  it("aplica jitter de ±20 %", () => {
    expect(backoffDelay(0, {}, () => 0)).toBe(800);
    expect(backoffDelay(0, {}, () => 1)).toBe(1200);
    expect(backoffDelay(0, { jitter: 0 }, () => 0)).toBe(1000);
  });
});

describe("RealtimeClient", () => {
  it("consume el stream, reconecta con backoff y reenvía Last-Event-ID", async () => {
    const scheduled: Array<{ callback: () => void; ms: number }> = [];
    const requests: Headers[] = [];
    const events: SseFrame[] = [];

    const fetchImpl = vi.fn(async (_url: string, init?: RequestInit) => {
      requests.push(new Headers(init?.headers));
      return new Response(
        streamFrom([
          'id: 7\nevent: rfp_ticket_created\ndata: {"ticket_id":"t1"}\n\n',
        ]),
        {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        },
      );
    });

    const client = new RealtimeClient({
      url: "/api/realtime/stream",
      getToken: () => "jwt-token",
      onEvent: (frame) => events.push(frame),
      fetchImpl: fetchImpl as unknown as typeof fetch,
      schedule: (callback, ms) => {
        scheduled.push({ callback, ms });
        return scheduled.length;
      },
      clearSchedule: vi.fn(),
      random: () => 0.5,
    });

    client.start();

    await vi.waitFor(() => expect(scheduled).toHaveLength(1));
    expect(scheduled[0].ms).toBe(1000);
    expect(events).toHaveLength(1);
    expect(events[0].event).toBe("rfp_ticket_created");
    expect(events[0].data).toContain("t1");
    expect(requests[0].get("Authorization")).toBe("Bearer jwt-token");

    // El backoff no debe arrastrarse: al abrir de nuevo vuelve a 1 s.
    scheduled[0].callback();
    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(2));
    expect(requests[1].get("Last-Event-ID")).toBe("7");
    expect(requests[1].get("Authorization")).toBe("Bearer jwt-token");

    client.stop();
  });

  it("detecta una conexión muda por inactividad y entra en backoff", async () => {
    const scheduled: Array<{ callback: () => void; ms: number }> = [];

    const stream = new ReadableStream<Uint8Array>({
      start() {
        // Nunca envía chunks: simula un proxy que no propaga el cierre.
      },
    });

    const client = new RealtimeClient({
      url: "/api/realtime/stream",
      getToken: () => "jwt-token",
      onEvent: vi.fn(),
      fetchImpl: (async () =>
        new Response(stream, {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        })) as unknown as typeof fetch,
      schedule: (callback, ms) => {
        scheduled.push({ callback, ms });
        return scheduled.length;
      },
      clearSchedule: vi.fn(),
      random: () => 0.5,
      inactivityTimeoutMs: 25,
    });

    client.start();
    await vi.waitFor(() => expect(scheduled).toHaveLength(1), {
      timeout: 1000,
    });
    expect(scheduled[0].ms).toBe(1000);
    client.stop();
  });

  it("no reintenta cuando el JWT no es válido (401)", async () => {
    const scheduled: Array<{ callback: () => void; ms: number }> = [];
    const statuses: string[] = [];

    const client = new RealtimeClient({
      url: "/api/realtime/stream",
      getToken: () => "expired",
      onEvent: vi.fn(),
      onStatus: (status) => statuses.push(status),
      fetchImpl: (async () =>
        new Response("no autorizado", { status: 401 })) as unknown as typeof fetch,
      schedule: (callback, ms) => {
        scheduled.push({ callback, ms });
        return scheduled.length;
      },
      clearSchedule: vi.fn(),
    });

    client.start();
    await vi.waitFor(() => expect(statuses).toContain("unauthorized"));
    expect(scheduled).toHaveLength(0);
  });
});
