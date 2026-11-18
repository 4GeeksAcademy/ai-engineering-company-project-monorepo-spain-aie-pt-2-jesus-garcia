import { describe, expect, it } from "vitest";
import {
  activeGeneration,
  applySnapshot,
  mergeCompleted,
  mergeGenerationStarted,
  mergeInterrupted,
  mergeToken,
  mergeUserMessage,
  type ChatMessage,
  type ChatSnapshot,
} from "@/lib/chat-types";

function assistant(
  overrides: Partial<ChatMessage> = {},
): ChatMessage {
  return {
    message_id: "msg_1",
    session_id: "chat_1",
    role: "assistant",
    text: "",
    status: "streaming",
    sequence: 0,
    run_id: "run-1",
    created_at: "",
    ...overrides,
  };
}

describe("chat reducer", () => {
  it("append tokens in order and ignores duplicates or older sequences", () => {
    let messages: ChatMessage[] = [];
    messages = mergeGenerationStarted(messages, {
      session_id: "chat_1",
      message_id: "msg_1",
      run_id: "run-1",
    });
    messages = mergeToken(messages, {
      session_id: "chat_1",
      message_id: "msg_1",
      token: "Hola ",
      sequence: 1,
    });
    messages = mergeToken(messages, {
      session_id: "chat_1",
      message_id: "msg_1",
      token: "pedido",
      sequence: 2,
    });
    messages = mergeToken(messages, {
      session_id: "chat_1",
      message_id: "msg_1",
      token: "DUPLICADO",
      sequence: 2,
    });
    expect(messages).toHaveLength(1);
    expect(messages[0].text).toBe("Hola pedido");
    expect(messages[0].status).toBe("streaming");
  });

  it("completes appending the missing suffix, never replacing the stream", () => {
    let messages = [assistant({ text: "Hola pedido" })];
    messages = mergeCompleted(messages, {
      session_id: "chat_1",
      message_id: "msg_1",
      text: "Hola pedido\n\n¿Quieres que lo recuerde?",
      status: "ok",
    });
    expect(messages[0].status).toBe("completed");
    expect(messages[0].text).toBe(
      "Hola pedido\n\n¿Quieres que lo recuerde?",
    );
  });

  it("keeps the displayed text when the final text diverges", () => {
    const messages = mergeCompleted(
      [assistant({ text: "Texto mostrado" })],
      {
        session_id: "chat_1",
        message_id: "msg_1",
        text: "Otro texto distinto",
        status: "ok",
      },
    );
    expect(messages[0].text).toBe("Texto mostrado");
  });

  it("replaces only when the output guard blocked the answer", () => {
    const messages = mergeCompleted(
      [assistant({ text: "contenido sensible" })],
      {
        session_id: "chat_1",
        message_id: "msg_1",
        text: "No puedo mostrar esa información.",
        status: "blocked",
        blocked: true,
      },
    );
    expect(messages[0].text).toBe("No puedo mostrar esa información.");
  });

  it("marks interrupted and preserves the partial text", () => {
    const messages = mergeInterrupted(
      [assistant({ text: "La entrega" })],
      {
        session_id: "chat_1",
        message_id: "msg_1",
        status: "interrupted",
        text: "La entrega",
        sequence: 2,
      },
    );
    expect(messages[0].status).toBe("interrupted");
    expect(messages[0].text).toBe("La entrega");
    expect(activeGeneration(messages)).toBeNull();
  });

  it("deduplicates user messages echoed by the server", () => {
    let messages = mergeUserMessage([], {
      session_id: "chat_1",
      message_id: "msg_user",
      text: "hola",
    });
    messages = mergeUserMessage(messages, {
      session_id: "chat_1",
      message_id: "msg_user",
      text: "hola",
    });
    expect(messages).toHaveLength(1);
    expect(messages[0].role).toBe("user");
  });

  it("hydrates snapshot plus active generation without losing partial text", () => {
    const snapshot: ChatSnapshot = {
      session_id: "chat_1",
      thread_id: "chat_1",
      agent_id: "first_line_cx",
      status: "active",
      messages: [assistant({ text: "parte " })],
      active_generation: {
        message_id: "msg_1",
        run_id: "run-1",
        sequence: 2,
        text: "parte visible",
      },
    };
    const messages = applySnapshot(snapshot);
    expect(messages[0].text).toBe("parte visible");
    expect(messages[0].sequence).toBe(2);
    expect(activeGeneration(messages)?.message_id).toBe("msg_1");
  });
});
