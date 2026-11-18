/**
 * Tipos y reducer del chat en tiempo real.
 *
 * El reducer es append-only para los tokens: el texto que ya se mostró no se
 * reemplaza al completar. Solo una respuesta bloqueada por el output guard
 * puede sustituirse por el mensaje seguro (corrección de seguridad).
 */

export type ChatSessionStatus = "active" | "interrupted" | "closed";
export type ChatMessageStatus =
  | "streaming"
  | "completed"
  | "interrupted"
  | "failed";

export interface ChatSession {
  session_id: string;
  thread_id: string;
  agent_id: string;
  user_id: string;
  client_id: string | null;
  status: ChatSessionStatus;
  created_at: string;
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  role: "user" | "assistant";
  text: string;
  status: ChatMessageStatus;
  sequence: number;
  run_id?: string | null;
  created_at: string;
}

export interface ActiveGeneration {
  message_id: string;
  run_id: string;
  sequence: number;
  text: string;
}

export interface ChatSnapshot {
  session_id: string;
  thread_id: string;
  agent_id: string;
  status: ChatSessionStatus;
  messages: ChatMessage[];
  active_generation: ActiveGeneration | null;
}

export interface TokenChunkData {
  session_id: string;
  message_id: string;
  run_id?: string;
  token: string;
  sequence: number;
}

export interface InterruptRequestedData {
  session_id: string;
  message_id?: string | null;
  new_input?: string;
}

export interface GenerationInterruptedData {
  session_id: string;
  message_id: string;
  run_id?: string;
  status: "interrupted";
  text?: string;
  sequence?: number;
}

export interface GenerationCompletedData {
  session_id: string;
  message_id: string;
  run_id?: string;
  status?: string;
  blocked?: boolean;
  text: string;
  sequence?: number;
}

export interface UserMessageData {
  session_id: string;
  message_id: string;
  text: string;
}

export interface GenerationStartedData {
  session_id: string;
  message_id: string;
  run_id?: string;
}

export interface ChatErrorData {
  session_id: string;
  code: string;
  message: string;
}

export interface ChatEvent {
  event: string;
  data: unknown;
}

function assistantPlaceholder(
  sessionId: string,
  messageId: string,
  runId?: string | null,
): ChatMessage {
  return {
    message_id: messageId,
    session_id: sessionId,
    role: "assistant",
    text: "",
    status: "streaming",
    sequence: 0,
    run_id: runId ?? null,
    created_at: "",
  };
}

export function mergeUserMessage(
  messages: ChatMessage[],
  data: UserMessageData,
): ChatMessage[] {
  if (messages.some((item) => item.message_id === data.message_id)) {
    return messages;
  }
  return [
    ...messages,
    {
      message_id: data.message_id,
      session_id: data.session_id,
      role: "user",
      text: data.text,
      status: "completed",
      sequence: 0,
      created_at: "",
    },
  ];
}

export function mergeGenerationStarted(
  messages: ChatMessage[],
  data: GenerationStartedData,
): ChatMessage[] {
  if (messages.some((item) => item.message_id === data.message_id)) {
    return messages;
  }
  return [
    ...messages,
    assistantPlaceholder(data.session_id, data.message_id, data.run_id),
  ];
}

export function mergeToken(
  messages: ChatMessage[],
  data: TokenChunkData,
): ChatMessage[] {
  const index = messages.findIndex(
    (item) => item.message_id === data.message_id,
  );
  if (index === -1) {
    const placeholder = assistantPlaceholder(
      data.session_id,
      data.message_id,
      data.run_id,
    );
    return [
      ...messages,
      {
        ...placeholder,
        text: data.token,
        sequence: data.sequence,
      },
    ];
  }
  const current = messages[index];
  if (current.status !== "streaming") return messages;
  if (data.sequence <= current.sequence) return messages;
  const next = [...messages];
  next[index] = {
    ...current,
    text: current.text + data.token,
    sequence: data.sequence,
    run_id: data.run_id ?? current.run_id,
  };
  return next;
}

export function mergeInterrupted(
  messages: ChatMessage[],
  data: GenerationInterruptedData,
): ChatMessage[] {
  const index = messages.findIndex(
    (item) => item.message_id === data.message_id,
  );
  if (index === -1) {
    const placeholder = assistantPlaceholder(
      data.session_id,
      data.message_id,
    );
    return [
      ...messages,
      {
        ...placeholder,
        text: data.text ?? "",
        status: "interrupted",
        sequence: data.sequence ?? 0,
      },
    ];
  }
  const current = messages[index];
  const next = [...messages];
  next[index] = {
    ...current,
    text: data.text ?? current.text,
    status: "interrupted",
    sequence: Math.max(current.sequence, data.sequence ?? 0),
  };
  return next;
}

export function mergeCompleted(
  messages: ChatMessage[],
  data: GenerationCompletedData,
): ChatMessage[] {
  const index = messages.findIndex(
    (item) => item.message_id === data.message_id,
  );
  const failed = data.status === "error" || data.status === "invalid_question";
  if (index === -1) {
    const placeholder = assistantPlaceholder(
      data.session_id,
      data.message_id,
      data.run_id,
    );
    return [
      ...messages,
      {
        ...placeholder,
        text: data.text,
        status: failed ? "failed" : "completed",
      },
    ];
  }
  const current = messages[index];
  let text = current.text;
  if (data.blocked) {
    // Única excepción al append-only: el guardrail bloqueó el contenido.
    text = data.text;
  } else if (data.text.startsWith(current.text)) {
    // Añade el sufijo que no se emitió como token (p. ej. pregunta de memoria).
    text = data.text;
  } else if (!current.text.startsWith(data.text)) {
    // Divergencia no bloqueante: se conserva lo ya mostrado.
    text = current.text;
  }
  const next = [...messages];
  next[index] = {
    ...current,
    text,
    status: failed ? "failed" : "completed",
    sequence: Math.max(current.sequence, data.sequence ?? 0),
  };
  return next;
}

export function activeGeneration(
  messages: ChatMessage[],
): ChatMessage | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    if (
      messages[index].role === "assistant" &&
      messages[index].status === "streaming"
    ) {
      return messages[index];
    }
  }
  return null;
}

export function applySnapshot(snapshot: ChatSnapshot): ChatMessage[] {
  const messages = [...snapshot.messages];
  const active = snapshot.active_generation;
  if (active) {
    const index = messages.findIndex(
      (item) => item.message_id === active.message_id,
    );
    if (index === -1) {
      messages.push({
        ...assistantPlaceholder(
          snapshot.session_id,
          active.message_id,
          active.run_id,
        ),
        text: active.text,
        sequence: active.sequence,
      });
    } else {
      const current = messages[index];
      messages[index] = {
        ...current,
        text: active.text.startsWith(current.text)
          ? active.text
          : current.text,
        sequence: Math.max(current.sequence, active.sequence),
      };
    }
  }
  return messages;
}
