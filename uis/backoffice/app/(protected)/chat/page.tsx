"use client";

import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useAuth } from "@/contexts/AuthContext";
import { apiRequest, friendlyError } from "@/lib/api";
import { ChatSocket, type ChatSocketStatus } from "@/lib/chat-socket";
import {
  activeGeneration,
  applySnapshot,
  mergeCompleted,
  mergeGenerationStarted,
  mergeInterrupted,
  mergeToken,
  mergeUserMessage,
  type ChatErrorData,
  type ChatEvent,
  type ChatMessage,
  type ChatSession,
  type ChatSnapshot,
  type GenerationCompletedData,
  type GenerationInterruptedData,
  type GenerationStartedData,
  type TokenChunkData,
  type UserMessageData,
} from "@/lib/chat-types";

const SESSION_KEY = "trackflow_chat_session";

export default function ChatPage() {
  const { token } = useAuth();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<ChatSocketStatus>("idle");
  const [statusDetail, setStatusDetail] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const socketRef = useRef<ChatSocket | null>(null);

  const streamingMessage = useMemo(() => activeGeneration(messages), [messages]);
  const isStreaming = streamingMessage !== null;

  const storeSession = useCallback((id: string) => {
    setSessionId(id);
    setMessages([]);
    setHydrated(false);
    setError(null);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(SESSION_KEY, id);
      const url = new URL(window.location.href);
      url.searchParams.set("session", id);
      window.history.replaceState({}, "", url.toString());
    }
  }, []);

  const createSession = useCallback(async () => {
    if (!token) return;
    setCreating(true);
    setError(null);
    try {
      const session = await apiRequest<ChatSession>("/api/chat/sessions", {
        method: "POST",
        body: JSON.stringify({}),
        token,
      });
      storeSession(session.session_id);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setCreating(false);
    }
  }, [storeSession, token]);

  // Resolver la sesión: URL > localStorage > crear una nueva.
  useEffect(() => {
    if (!token || sessionId) return;
    let cancelled = false;
    async function resolveSession() {
      const fromUrl =
        typeof window !== "undefined"
          ? new URLSearchParams(window.location.search).get("session")
          : null;
      const stored =
        typeof window !== "undefined"
          ? window.localStorage.getItem(SESSION_KEY)
          : null;
      const candidate = fromUrl || stored;
      if (candidate) {
        if (!cancelled) storeSession(candidate);
        return;
      }
      await createSession();
    }
    void resolveSession();
    return () => {
      cancelled = true;
    };
  }, [createSession, sessionId, storeSession, token]);

  const handleEvent = useCallback((event: ChatEvent) => {
    const data = event.data as Record<string, unknown> | undefined;
    switch (event.event) {
      case "session_snapshot": {
        const snapshot = data as unknown as ChatSnapshot;
        setMessages(applySnapshot(snapshot));
        setHydrated(true);
        return;
      }
      case "user_message": {
        const payload = data as unknown as UserMessageData;
        setMessages((current) => mergeUserMessage(current, payload));
        return;
      }
      case "generation_started": {
        const payload = data as unknown as GenerationStartedData;
        setMessages((current) => mergeGenerationStarted(current, payload));
        return;
      }
      case "token_chunk": {
        const payload = data as unknown as TokenChunkData;
        setMessages((current) => mergeToken(current, payload));
        return;
      }
      case "generation_interrupted": {
        const payload = data as unknown as GenerationInterruptedData;
        setMessages((current) => mergeInterrupted(current, payload));
        return;
      }
      case "generation_completed": {
        const payload = data as unknown as GenerationCompletedData;
        setMessages((current) => mergeCompleted(current, payload));
        return;
      }
      case "error": {
        const payload = data as unknown as ChatErrorData;
        setError(payload.message || "El chat devolvió un error.");
        return;
      }
      default:
        return;
    }
  }, []);

  // Conexión WebSocket ligada a la sesión y al JWT.
  useEffect(() => {
    if (!token || !sessionId) return;
    const socket = new ChatSocket({
      sessionId,
      token,
      onEvent: handleEvent,
      onStatus: (next, detail) => {
        setStatus(next);
        if (next === "reconnecting" && detail?.attempt) {
          setStatusDetail(
            `Reconectando (intento ${detail.attempt}${
              detail.delayMs ? ` en ${Math.round(detail.delayMs / 1000)} s` : ""
            })…`,
          );
        } else if (next === "open") {
          setStatusDetail(null);
          setError(null);
        } else if (next === "unauthorized") {
          setStatusDetail(
            "La sesión ya no es válida. Crea una conversación nueva.",
          );
        } else {
          setStatusDetail(null);
        }
      },
      onAuthError: () => {
        setError("La autenticación del chat caducó. Vuelve a iniciar sesión.");
      },
    });
    socketRef.current = socket;
    socket.start();
    return () => {
      socket.stop();
      socketRef.current = null;
    };
  }, [handleEvent, sessionId, token]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft.trim();
    if (!text) return;
    const socket = socketRef.current;
    if (!socket || !socket.isOpen()) {
      setError("La conexión aún no está lista. Espera un momento.");
      return;
    }
    const sent = isStreaming
      ? socket.sendInterrupt(text)
      : socket.sendUserMessage(text);
    if (!sent) {
      setError("No se pudo enviar el mensaje. Inténtalo de nuevo.");
      return;
    }
    setError(null);
    setDraft("");
  }

  function handleStop() {
    const socket = socketRef.current;
    if (!socket) return;
    if (!socket.sendInterrupt(null)) {
      setError("No se pudo detener la respuesta. Inténtalo de nuevo.");
    }
  }

  const connected = status === "open";
  const connectionLabel = connected
    ? "En vivo"
    : status === "reconnecting"
      ? "Reconectando…"
      : status === "unauthorized"
        ? "Sin autorización"
        : status === "connecting" || creating
          ? "Conectando…"
          : "Desconectado";

  return (
    <>
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Chat de soporte</h1>
          <p className="mt-2 max-w-2xl text-sm text-slate-300">
            First-line CX agent de TrackFlow. La respuesta se transmite token a
            token y puedes interrumpirla para redirigir la conversación.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            data-testid="chat-connection"
            className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium ${
              connected
                ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-300"
                : "border-amber-400/30 bg-amber-500/10 text-amber-200"
            }`}
          >
            <span
              className={`size-2 rounded-full ${
                connected ? "bg-emerald-400" : "bg-amber-400"
              }`}
              aria-hidden
            />
            {connectionLabel}
          </span>
          <button
            type="button"
            onClick={() => void createSession()}
            disabled={creating}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-200 transition hover:border-cyan-500/40 hover:text-white disabled:opacity-50"
          >
            Nueva conversación
          </button>
        </div>
      </header>

      {statusDetail && (
        <p className="mb-4 text-xs text-amber-200" role="status">
          {statusDetail}
        </p>
      )}

      {error && (
        <div
          role="alert"
          className="mb-4 rounded-xl border border-rose-400/20 bg-rose-500/10 p-4"
        >
          <p className="text-sm font-medium text-rose-300">{error}</p>
        </div>
      )}

      <section
        aria-label="Conversación"
        className="flex min-h-[420px] flex-col rounded-xl border border-white/10 bg-white/5"
      >
        <div
          role="log"
          aria-live="polite"
          aria-relevant="additions text"
          className="flex-1 space-y-4 overflow-y-auto p-5"
        >
          {!hydrated && sessionId && (
            <p className="text-sm text-slate-400">Restaurando conversación…</p>
          )}
          {hydrated && messages.length === 0 && (
            <div className="rounded-lg border border-white/10 bg-slate-900/40 p-4 text-sm text-slate-300">
              <p className="font-medium text-white">Empieza una conversación</p>
              <p className="mt-1">
                Prueba con «¿Dónde está mi pedido?», «Quiero hacer una
                devolución» o «¿Cuánto tarda una entrega estándar en España?».
              </p>
            </div>
          )}
          {messages.map((message) => {
            const streaming =
              message.role === "assistant" && message.status === "streaming";
            const interrupted = message.status === "interrupted";
            return (
              <article
                key={message.message_id}
                data-testid={`chat-message-${message.role}`}
                className={`flex ${
                  message.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[85%] rounded-xl px-4 py-3 text-sm leading-6 ${
                    message.role === "user"
                      ? "bg-cyan-600 text-white"
                      : interrupted
                        ? "border border-amber-400/30 bg-amber-500/10 text-slate-100"
                        : "border border-white/10 bg-slate-900/70 text-slate-100"
                  }`}
                >
                  {message.role === "assistant" && (
                    <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
                      First-line CX
                      {interrupted && (
                        <span
                          data-testid="interrupted-badge"
                          className="ml-2 rounded-full bg-amber-500/20 px-2 py-0.5 text-amber-200"
                        >
                          Interrumpido
                        </span>
                      )}
                    </p>
                  )}
                  <p className="whitespace-pre-wrap">
                    {message.text}
                    {streaming && (
                      <span
                        aria-hidden
                        data-testid="streaming-cursor"
                        className="ml-0.5 inline-block animate-pulse"
                      >
                        ▍
                      </span>
                    )}
                  </p>
                </div>
              </article>
            );
          })}
        </div>

        <form
          onSubmit={handleSubmit}
          className="border-t border-white/10 p-4"
        >
          <label
            htmlFor="chat-input"
            className="block text-xs font-semibold uppercase tracking-wide text-slate-400"
          >
            Mensaje
          </label>
          <textarea
            id="chat-input"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={2}
            maxLength={4000}
            placeholder={
              isStreaming
                ? "Escribe para interrumpir y redirigir la respuesta…"
                : "Escribe tu consulta…"
            }
            className="mt-2 w-full resize-y rounded-lg border border-white/10 bg-slate-800 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none"
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-slate-500">
              {isStreaming
                ? "El agente está respondiendo. Enviar un mensaje aborta la generación actual y abre un turno nuevo."
                : "La conversación se rehidrata si se cae la conexión."}
            </p>
            <div className="flex items-center gap-2">
              {isStreaming && (
                <button
                  type="button"
                  onClick={handleStop}
                  className="rounded-lg border border-amber-400/30 bg-amber-500/10 px-4 py-2 text-sm font-medium text-amber-200 transition hover:bg-amber-500/20"
                >
                  Detener
                </button>
              )}
              <button
                type="submit"
                disabled={!draft.trim() || !connected}
                className="rounded-lg bg-cyan-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:opacity-50"
              >
                {isStreaming ? "Interrumpir y enviar" : "Enviar"}
              </button>
            </div>
          </div>
        </form>
      </section>
    </>
  );
}
