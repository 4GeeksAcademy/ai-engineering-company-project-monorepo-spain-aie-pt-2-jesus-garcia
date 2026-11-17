import { describe, expect, it, vi } from "vitest";
import {
  ChatSocket,
  chatSocketUrl,
  type ChatSocketStatus,
  type WebSocketLike,
} from "@/lib/chat-socket";
import type { ChatEvent } from "@/lib/chat-types";

class FakeSocket implements WebSocketLike {
  readyState = 0;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  sent: string[] = [];
  closedWith: number | null = null;

  constructor(public readonly url: string) {}

  send(data: string): void {
    this.sent.push(data);
  }

  close(code = 1000): void {
    this.closedWith = code;
    this.readyState = 3;
    this.onclose?.({ code, reason: "" } as CloseEvent);
  }

  open(): void {
    this.readyState = 1;
    this.onopen?.(new Event("open"));
  }

  message(payload: unknown): void {
    this.onmessage?.({
      data: JSON.stringify(payload),
    } as MessageEvent);
  }

  serverClose(code: number, reason = ""): void {
    this.readyState = 3;
    this.onclose?.({ code, reason } as CloseEvent);
  }
}

function setup() {
  const sockets: FakeSocket[] = [];
  const scheduled: Array<() => void> = [];
  const events: ChatEvent[] = [];
  const statuses: Array<[ChatSocketStatus, unknown]> = [];
  const client = new ChatSocket({
    sessionId: "chat_1",
    token: "jwt",
    url: "ws://api/chat/ws?session_id=chat_1&token=jwt",
    inactivityTimeoutMs: 0,
    createSocket: (url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket;
    },
    schedule: (callback) => {
      scheduled.push(callback);
      return scheduled.length;
    },
    clearSchedule: () => undefined,
    onEvent: (event) => events.push(event),
    onStatus: (status, detail) => statuses.push([status, detail]),
    onAuthError: () => statuses.push(["unauthorized", { auth: true }]),
  });
  return { client, sockets, scheduled, events, statuses };
}

describe("ChatSocket", () => {
  it("derives the ws url from NEXT_PUBLIC_API_URL or localhost", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.trackflow.test");
    expect(chatSocketUrl("chat_1", "jwt")).toBe(
      "wss://api.trackflow.test/chat/ws?session_id=chat_1&token=jwt",
    );

    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    expect(chatSocketUrl("chat_1", "jwt")).toBe(
      "ws://localhost:8000/chat/ws?session_id=chat_1&token=jwt",
    );
    vi.unstubAllEnvs();
  });

  it("dispatches snapshot events and answers application pings", () => {
    const { client, sockets, events } = setup();
    client.start();
    sockets[0].open();
    sockets[0].message({
      event: "session_snapshot",
      data: { session_id: "chat_1", messages: [] },
    });
    sockets[0].message({ event: "ping", data: {} });

    expect(events.map((event) => event.event)).toEqual(["session_snapshot"]);
    expect(JSON.parse(sockets[0].sent[0])).toEqual({
      event: "pong",
      data: { session_id: "chat_1" },
    });
    client.stop();
  });

  it("reconnects with progressive backoff and the same session url", () => {
    const { client, sockets, scheduled } = setup();
    client.start();
    sockets[0].open();
    sockets[0].serverClose(1006, "network");

    expect(scheduled).toHaveLength(1);
    scheduled.shift()?.();
    expect(sockets).toHaveLength(2);
    expect(sockets[1].url).toBe(sockets[0].url);
    client.stop();
  });

  it("does not retry on authentication close codes", () => {
    const { client, sockets, scheduled, statuses } = setup();
    client.start();
    sockets[0].open();
    sockets[0].serverClose(4401, "expired");

    expect(scheduled).toHaveLength(0);
    expect(statuses.some(([status]) => status === "unauthorized")).toBe(true);
    client.stop();
  });

  it("sends user and interrupt commands only when open", () => {
    const { client, sockets } = setup();
    expect(client.sendUserMessage("hola")).toBe(false);
    client.start();
    sockets[0].open();

    expect(client.sendUserMessage("hola")).toBe(true);
    expect(client.sendInterrupt("mejor una devolución")).toBe(true);
    expect(JSON.parse(sockets[0].sent[0])).toEqual({
      event: "user_message",
      data: { session_id: "chat_1", text: "hola" },
    });
    expect(JSON.parse(sockets[0].sent[1])).toEqual({
      event: "interrupt_requested",
      data: {
        session_id: "chat_1",
        new_input: "mejor una devolución",
      },
    });
    client.stop();
  });
});
