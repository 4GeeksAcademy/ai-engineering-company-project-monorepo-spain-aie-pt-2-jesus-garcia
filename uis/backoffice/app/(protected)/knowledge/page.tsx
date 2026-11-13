"use client";

import { type FormEvent, useState } from "react";
import { LoadingSpinner } from "@shared/components/LoadingSpinner";
import { useAuth } from "@/contexts/AuthContext";
import { friendlyError } from "@/lib/api";
import { askKnowledge } from "@/lib/knowledge-api";

const SUGGESTIONS = [
  "¿Cuál es la ventana de devolución estándar?",
  "¿Qué transportista cubre mejor las zonas rurales de Aragón?",
  "¿Cómo afecta Black Friday al SLA de entrega?",
  "¿Puede un account manager ofrecer un descuento de almacenamiento?",
];

export default function KnowledgePage() {
  const { token } = useAuth();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) {
      setError("Escribe una pregunta para consultar la base de conocimiento.");
      return;
    }

    setLoading(true);
    setError(null);
    setAnswer(null);

    try {
      const response = await askKnowledge(trimmed, token);
      if (!response.answer?.trim()) {
        setError(
          "El asistente devolvió una respuesta vacía. Inténtalo de nuevo.",
        );
        return;
      }
      setAnswer(response.answer);
    } catch (err) {
      setError(friendlyError(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <header className="mb-8">
        <h1 className="text-3xl font-bold text-white">Asistente comercial</h1>
        <p className="mt-2 text-sm text-slate-300">
          Consulta la base de conocimiento de TrackFlow con la voz de un
          vendedor: SLA, devoluciones, transportistas y tarifas de
          almacenamiento.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="rounded-xl border border-white/10 bg-white/5 p-5"
      >
        <label
          htmlFor="knowledge-question"
          className="block text-sm font-medium text-slate-200"
        >
          Pregunta
        </label>
        <textarea
          id="knowledge-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={3}
          maxLength={2000}
          disabled={loading}
          placeholder="Ej. ¿Qué SLA tenemos para envíos express en España?"
          className="mt-2 w-full resize-y rounded-lg border border-white/10 bg-slate-800 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-500 focus:outline-none disabled:opacity-60"
        />
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <p className="text-xs text-slate-500">
            Respuestas basadas solo en la documentación indexada de TrackFlow.
          </p>
          <button
            type="submit"
            disabled={loading}
            className="rounded-lg bg-cyan-600 px-5 py-2 text-sm font-medium text-white transition hover:bg-cyan-500 disabled:opacity-50"
          >
            {loading ? "Consultando…" : "Consultar"}
          </button>
        </div>
      </form>

      <section aria-label="Preguntas sugeridas" className="mt-5">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
          Preguntas frecuentes
        </p>
        <div className="flex flex-wrap gap-2">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={loading}
              onClick={() => setQuestion(suggestion)}
              className="rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300 transition hover:border-cyan-500/40 hover:text-white disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </section>

      {loading && (
        <section
          aria-label="Consultando la base de conocimiento"
          className="mt-8 flex items-center gap-4 rounded-xl border border-white/10 bg-white/5 p-5"
        >
          <LoadingSpinner className="h-8 w-8" />
          <div>
            <p className="text-sm font-medium text-white">Consultando…</p>
            <p className="mt-1 text-sm text-slate-400">
              Buscando en la base de conocimiento y redactando la respuesta.
            </p>
          </div>
        </section>
      )}

      {error && (
        <div
          role="alert"
          className="mt-8 rounded-xl border border-rose-400/20 bg-rose-500/10 p-5"
        >
          <p className="text-sm font-medium text-rose-300">{error}</p>
          <p className="mt-2 text-sm text-slate-400">
            No se ha generado ninguna respuesta. Puedes corregir la pregunta o
            volver a intentarlo.
          </p>
        </div>
      )}

      {answer && !loading && (
        <section
          aria-label="Respuesta del asistente"
          className="mt-8 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-6"
        >
          <p className="text-xs font-semibold uppercase tracking-wide text-cyan-300">
            Respuesta
          </p>
          <p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-100">
            {answer}
          </p>
        </section>
      )}
    </>
  );
}
