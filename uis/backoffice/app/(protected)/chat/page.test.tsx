import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  sockets: [] as Array<{
    options: {
      onEvent: (event: { event: string; data: unknown }) => void;
      onStatus: (status: string, detail?: { attempt?: number }) => void;
    };
    sent: Array<{ type: string; text?: string; newInput?: string | null }>;
  }>,
  apiRequest: vi.fn(),
  friendlyError: vi.fn((error: unknown) => String(error)),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ token: "jwt", user: { id: "1", role: "admin" } }),
}));

vi.mock("@/lib/api", () => ({
  apiRequest: mocks.apiRequest,
  friendlyError: mocks.friendlyError,
}));

vi.mock("@/lib/chat-socket", () => ({
  ChatSocket: class {
    options: unknown;
    sent: Array<{ type: string; text?: string; newInput?: string | null }> = [];
    started = false;
    constructor(options: unknown) {
      this.options = options;
      mocks.sockets.push(this as never);
    }
    start() {
      this.started = true;
    }
    stop() {
      this.started = false;
    }
    isOpen() {
      return true;
    }
    sendUserMessage(text: string) {
      this.sent.push({ type: "user", text });
      return true;
    }
    sendInterrupt(newInput: string | null) {
      this.sent.push({ type: "interrupt", newInput });
      return true;
    }
  },
}));

import ChatPage from "@/app/(protected)/chat/page";

function snapshot(messages: unknown[] = [], active: unknown = null) {
  return {
    event: "session_snapshot",
    data: {
      session_id: "chat_1",
      thread_id: "chat_1",
      agent_id: "first_line_cx",
      status: active ? "active" : "active",
      messages,
      active_generation: active,
    },
  };
}

async function renderChat() {
  render(<ChatPage />);
  await waitFor(() => expect(mocks.sockets).toHaveLength(1));
  const socket = mocks.sockets[0];
  act(() => {
    socket.options.onStatus("open");
    socket.options.onEvent(snapshot());
  });
  return socket;
}

beforeEach(() => {
  mocks.sockets.length = 0;
  mocks.apiRequest.mockReset();
  mocks.apiRequest.mockResolvedValue({
    session_id: "chat_1",
    thread_id: "chat_1",
    agent_id: "first_line_cx",
    user_id: "1",
    client_id: null,
    status: "active",
    created_at: "2026-11-16T00:00:00Z",
  });
  window.localStorage.clear();
  window.history.replaceState({}, "", "/chat");
});

describe("ChatPage", () => {
  it("creates the session and sends the first message over the socket", async () => {
    const socket = await renderChat();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText("Mensaje"), "¿Dónde está mi pedido?");
    await user.click(screen.getByRole("button", { name: "Enviar" }));

    expect(mocks.apiRequest).toHaveBeenCalledWith(
      "/api/chat/sessions",
      expect.objectContaining({ method: "POST", token: "jwt" }),
    );
    expect(socket.sent).toEqual([
      { type: "user", text: "¿Dónde está mi pedido?" },
    ]);
    expect(
      window.localStorage.getItem("trackflow_chat_session"),
    ).toBe("chat_1");
  });

  it("renders tokens live, interrupts and shows the redirected new turn", async () => {
    const socket = await renderChat();
    const user = userEvent.setup();

    act(() => {
      socket.options.onEvent({
        event: "user_message",
        data: {
          session_id: "chat_1",
          message_id: "msg_user_1",
          text: "rastrea mi pedido",
        },
      });
      socket.options.onEvent({
        event: "generation_started",
        data: {
          session_id: "chat_1",
          message_id: "msg_old",
          run_id: "run_old",
        },
      });
      socket.options.onEvent({
        event: "token_chunk",
        data: {
          session_id: "chat_1",
          message_id: "msg_old",
          token: "Estoy ",
          sequence: 1,
        },
      });
      socket.options.onEvent({
        event: "token_chunk",
        data: {
          session_id: "chat_1",
          message_id: "msg_old",
          token: "rastreando",
          sequence: 2,
        },
      });
    });

    expect(screen.getByText(/Estoy rastreando/)).toBeInTheDocument();
    expect(screen.getByTestId("streaming-cursor")).toBeInTheDocument();

    await user.type(
      screen.getByLabelText("Mensaje"),
      "espera, quiero una devolución",
    );
    await user.click(
      screen.getByRole("button", { name: "Interrumpir y enviar" }),
    );
    expect(socket.sent.at(-1)).toEqual({
      type: "interrupt",
      newInput: "espera, quiero una devolución",
    });

    act(() => {
      socket.options.onEvent({
        event: "interrupt_requested",
        data: { session_id: "chat_1", message_id: "msg_old" },
      });
      socket.options.onEvent({
        event: "generation_interrupted",
        data: {
          session_id: "chat_1",
          message_id: "msg_old",
          status: "interrupted",
          text: "Estoy rastreando",
          sequence: 2,
        },
      });
      socket.options.onEvent({
        event: "user_message",
        data: {
          session_id: "chat_1",
          message_id: "msg_user_2",
          text: "espera, quiero una devolución",
        },
      });
      socket.options.onEvent({
        event: "generation_started",
        data: {
          session_id: "chat_1",
          message_id: "msg_new",
          run_id: "run_new",
        },
      });
      socket.options.onEvent({
        event: "token_chunk",
        data: {
          session_id: "chat_1",
          message_id: "msg_new",
          token: "Puedo ayudarte con la devolución",
          sequence: 1,
        },
      });
      socket.options.onEvent({
        event: "generation_completed",
        data: {
          session_id: "chat_1",
          message_id: "msg_new",
          status: "ok",
          text: "Puedo ayudarte con la devolución",
        },
      });
    });

    expect(screen.getByTestId("interrupted-badge")).toBeInTheDocument();
    expect(screen.getByText("Estoy rastreando")).toBeInTheDocument();
    expect(
      screen.getByText("Puedo ayudarte con la devolución"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("streaming-cursor")).not.toBeInTheDocument();
  });
});
