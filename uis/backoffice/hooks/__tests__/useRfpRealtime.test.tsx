import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { mergeRfpTickets, useRfpRealtime } from "@/hooks/useRfpRealtime";
import type { RfpTicketListItem } from "@/lib/rfp-types";

function ticket(
  overrides: Partial<RfpTicketListItem> = {},
): RfpTicketListItem {
  return {
    ticket_id: "t1",
    rfp_id: "RFP-2026-1",
    status: "analizando",
    pipeline_stage: "encolado",
    original_filename: "rfp.pdf",
    client_name: null,
    client_country: null,
    currency: null,
    discard_reason: null,
    error_message: null,
    created_at: "2026-11-15T10:00:00Z",
    updated_at: "2026-11-15T10:00:00Z",
    ...overrides,
  };
}

function payload(overrides: Record<string, unknown> = {}) {
  return {
    ticket_id: "t1",
    rfp_id: "RFP-2026-1",
    client_name: null,
    client_country: null,
    services_requested: [] as string[],
    currency: null,
    status: "analizando",
    created_at: "2026-11-15T10:00:00Z",
    original_filename: "rfp.pdf",
    pipeline_stage: "encolado",
    ...overrides,
  };
}

function frameText(event: string, data: unknown, id = 1): string {
  return `id: ${id}\nevent: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

function controllableStream() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(inner) {
      controller = inner;
    },
  });
  return {
    stream,
    send(text: string) {
      controller.enqueue(encoder.encode(text));
    },
  };
}

function stubStream(stream: ReadableStream<Uint8Array>) {
  const fetchMock = vi.fn(
    async () =>
      new Response(stream, {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("mergeRfpTickets", () => {
  it("deduplica por ticket_id y prefiere el snapshot autoritativo", () => {
    const snapshot = [ticket({ status: "analisis_completo" })];
    const live = new Map<string, RfpTicketListItem>([
      ["t1", ticket({ status: "analizando" })],
      [
        "t2",
        ticket({
          ticket_id: "t2",
          rfp_id: "RFP-2026-2",
          created_at: "2026-11-15T11:00:00Z",
        }),
      ],
    ]);

    const merged = mergeRfpTickets(snapshot, live);

    expect(merged.map((item) => item.ticket_id)).toEqual(["t2", "t1"]);
    expect(merged.find((item) => item.ticket_id === "t1")?.status).toBe(
      "analisis_completo",
    );
  });

  it("devuelve el snapshot intacto cuando no hay eventos en vivo", () => {
    const snapshot = [ticket()];
    expect(mergeRfpTickets(snapshot, new Map())).toEqual(snapshot);
  });
});

describe("useRfpRealtime", () => {
  it("pide el snapshot justo después de abrir el stream", async () => {
    const stream = controllableStream();
    const fetchMock = stubStream(stream.stream);
    const reload = vi.fn();

    renderHook(() =>
      useRfpRealtime({
        enabled: true,
        token: "jwt",
        snapshot: null,
        reload,
      }),
    );

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(reload).toHaveBeenCalledTimes(1));
  });

  it("notifica una sola vez por ticket y enriquece con los metadatos", async () => {
    const stream = controllableStream();
    stubStream(stream.stream);
    const reload = vi.fn();

    const { result } = renderHook(() =>
      useRfpRealtime({
        enabled: true,
        token: "jwt",
        snapshot: null,
        reload,
      }),
    );

    act(() =>
      stream.send(
        frameText("rfp_ticket_created", payload(), 1),
      ),
    );
    await waitFor(() => expect(result.current.notifications).toHaveLength(1));
    expect(result.current.notifications[0].recovered).toBe(false);
    expect(result.current.liveTickets.get("t1")?.status).toBe("analizando");

    act(() =>
      stream.send(
        frameText(
          "rfp_ticket_metadata_ready",
          payload({
            client_name: "Northline Apparel",
            client_country: "US",
            services_requested: ["warehousing", "last_mile"],
            currency: "USD",
          }),
          2,
        ),
      ),
    );
    await waitFor(() =>
      expect(result.current.notifications[0].clientName).toBe(
        "Northline Apparel",
      ),
    );
    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.notifications[0].servicesRequested).toEqual([
      "warehousing",
      "last_mile",
    ]);
    expect(result.current.liveTickets.get("t1")?.currency).toBe("USD");

    // Un evento repetido no duplica la notificación ni la fila.
    act(() => stream.send(frameText("rfp_ticket_created", payload(), 3)));
    await waitFor(() =>
      expect(result.current.liveTickets.get("t1")?.ticket_id).toBe("t1"),
    );
    expect(result.current.notifications).toHaveLength(1);
    expect(result.current.liveTickets.size).toBe(1);
  });

  it("recupera los tickets perdidos tras una caída sin duplicar los ya vistos", async () => {
    const stream = controllableStream();
    stubStream(stream.stream);
    const reload = vi.fn();
    const known = ticket();

    const { result, rerender } = renderHook(
      ({ snapshot }: { snapshot: RfpTicketListItem[] | null }) =>
        useRfpRealtime({
          enabled: true,
          token: "jwt",
          snapshot,
          reload,
        }),
      { initialProps: { snapshot: [known] as RfpTicketListItem[] | null } },
    );

    // El servidor descartó cola durante la caída: pide reconciliación.
    act(() => stream.send(frameText("stream_lagged", { dropped: 2 }, 5)));
    await waitFor(() => expect(reload).toHaveBeenCalled());

    // Snapshot tras reconectar: aparece el ticket que llegó desconectados.
    const missed = ticket({
      ticket_id: "t2",
      rfp_id: "RFP-2026-2",
      client_name: "Luna Cosmetics",
      created_at: "2026-11-15T11:00:00Z",
    });
    rerender({ snapshot: [missed, known] });

    await waitFor(() => expect(result.current.notifications).toHaveLength(1));
    expect(result.current.notifications[0].ticketId).toBe("t2");
    expect(result.current.notifications[0].recovered).toBe(true);

    // Un nuevo snapshot con los mismos ids no vuelve a notificar.
    rerender({ snapshot: [missed, known] });
    expect(result.current.notifications).toHaveLength(1);
  });
});
