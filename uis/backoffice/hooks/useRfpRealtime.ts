"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { RfpStatus, RfpTicketListItem } from "@/lib/rfp-types";
import {
  RFP_TICKET_CREATED,
  RFP_TICKET_METADATA_READY,
  STREAM_LAGGED,
  parseRfpTicketEvent,
  type RfpTicketEventPayload,
} from "@/lib/realtime-types";
import type { SseFrame } from "@/lib/sse";
import { useRealtimeStream } from "./useRealtimeStream";

export const MAX_LIVE_NOTIFICATIONS = 5;

export interface RfpLiveNotification {
  ticketId: string;
  rfpId: string;
  clientName: string | null;
  clientCountry: string | null;
  servicesRequested: string[];
  status: RfpStatus;
  receivedAt: string;
  recovered: boolean;
}

/**
 * Estrategia de recuperación (documentada en el PR):
 *
 * 1. Al abrir —y en cada reconexión— el stream se adjunta **antes** de pedir
 *    el snapshot REST (`reload`). Así ningún evento puede caer en el hueco.
 * 2. El snapshot es autoritativo: `mergeRfpTickets` deduplica por
 *    `ticket_id`, prefiriendo la fila del snapshot frente a la copia en vivo.
 * 3. `Last-Event-ID` pide además el replay corto del servidor.
 * 4. Un ticket que aparece en el snapshot tras una reconexión se notifica una
 *    sola vez como "recuperado". `notifiedRef` evita repetir el aviso.
 */

export function payloadToTicketRow(
  payload: RfpTicketEventPayload,
): RfpTicketListItem {
  return {
    ticket_id: payload.ticket_id,
    rfp_id: payload.rfp_id,
    status: payload.status,
    pipeline_stage: payload.pipeline_stage,
    original_filename: payload.original_filename,
    client_name: payload.client_name,
    client_country: payload.client_country,
    currency: payload.currency,
    discard_reason: null,
    error_message: null,
    created_at: payload.created_at,
    updated_at: payload.created_at,
  };
}

/** Snapshot autoritativo + tickets llegados por SSE que aún no están en él. */
export function mergeRfpTickets(
  snapshot: readonly RfpTicketListItem[],
  live: ReadonlyMap<string, RfpTicketListItem>,
): RfpTicketListItem[] {
  if (live.size === 0) return [...snapshot];
  const byId = new Map(snapshot.map((ticket) => [ticket.ticket_id, ticket]));
  const missing = [...live.values()]
    .filter((ticket) => !byId.has(ticket.ticket_id))
    .sort((a, b) => b.created_at.localeCompare(a.created_at));
  return [...missing, ...byId.values()];
}

function notificationFromRow(
  row: RfpTicketListItem,
  recovered: boolean,
): RfpLiveNotification {
  return {
    ticketId: row.ticket_id,
    rfpId: row.rfp_id,
    clientName: row.client_name,
    clientCountry: row.client_country,
    servicesRequested: [],
    status: row.status,
    receivedAt: new Date().toISOString(),
    recovered,
  };
}

interface UseRfpRealtimeOptions {
  enabled: boolean;
  token: string | null;
  snapshot: RfpTicketListItem[] | null;
  reload: () => void;
}

export function useRfpRealtime({
  enabled,
  token,
  snapshot,
  reload,
}: UseRfpRealtimeOptions) {
  const [liveTickets, setLiveTickets] = useState<
    Map<string, RfpTicketListItem>
  >(() => new Map());
  const [notifications, setNotifications] = useState<RfpLiveNotification[]>([]);

  const liveRef = useRef(new Map<string, RfpTicketListItem>());
  const notifiedRef = useRef(new Set<string>());
  const knownIdsRef = useRef<Set<string> | null>(null);
  const recoveringRef = useRef(false);
  const reloadRef = useRef(reload);

  useEffect(() => {
    reloadRef.current = reload;
  }, [reload]);

  const upsertNotification = useCallback(
    (payload: RfpTicketEventPayload, recovered: boolean) => {
      const alreadyNotified = notifiedRef.current.has(payload.ticket_id);
      notifiedRef.current.add(payload.ticket_id);
      setNotifications((prev) => {
        const current = prev.find(
          (item) => item.ticketId === payload.ticket_id,
        );
        // El usuario la descartó: el enriquecimiento no la resucita.
        if (!current && alreadyNotified) return prev;

        const next: RfpLiveNotification = {
          ticketId: payload.ticket_id,
          rfpId: payload.rfp_id,
          clientName: payload.client_name ?? current?.clientName ?? null,
          clientCountry:
            payload.client_country ?? current?.clientCountry ?? null,
          servicesRequested: payload.services_requested.length
            ? payload.services_requested
            : (current?.servicesRequested ?? []),
          status: payload.status,
          receivedAt: current?.receivedAt ?? new Date().toISOString(),
          recovered: current?.recovered ?? recovered,
        };
        const rest = prev.filter(
          (item) => item.ticketId !== payload.ticket_id,
        );
        return [next, ...rest].slice(0, MAX_LIVE_NOTIFICATIONS);
      });
    },
    [],
  );

  // Recuperación: al volver el stream, el snapshot siguiente revela los
  // tickets que llegaron durante la caída (notificación "recuperado").
  useEffect(() => {
    if (!snapshot) return;
    const known = knownIdsRef.current;
    if (known === null) {
      knownIdsRef.current = new Set(snapshot.map((ticket) => ticket.ticket_id));
      return;
    }

    const added = snapshot.filter((ticket) => !known.has(ticket.ticket_id));
    for (const ticket of added) known.add(ticket.ticket_id);

    if (!recoveringRef.current) return;
    recoveringRef.current = false;
    if (added.length === 0) return;

    const recovered = added.filter(
      (ticket) => !notifiedRef.current.has(ticket.ticket_id),
    );
    for (const ticket of recovered) notifiedRef.current.add(ticket.ticket_id);
    if (recovered.length === 0) return;

    setNotifications((prev) =>
      [
        ...recovered.map((ticket) => notificationFromRow(ticket, true)),
        ...prev,
      ].slice(0, MAX_LIVE_NOTIFICATIONS),
    );
  }, [snapshot]);

  const handleFrame = useCallback(
    (frame: SseFrame) => {
      if (frame.event === STREAM_LAGGED) {
        recoveringRef.current = true;
        reloadRef.current();
        return;
      }
      if (
        frame.event !== RFP_TICKET_CREATED &&
        frame.event !== RFP_TICKET_METADATA_READY
      ) {
        return;
      }

      const payload = parseRfpTicketEvent(frame.data);
      if (!payload) return;

      const row = payloadToTicketRow(payload);
      liveRef.current.set(row.ticket_id, row);
      setLiveTickets(new Map(liveRef.current));
      upsertNotification(payload, false);
    },
    [upsertNotification],
  );

  const handleOpen = useCallback(({ reconnected }: { reconnected: boolean }) => {
    if (reconnected) recoveringRef.current = true;
    // Snapshot después de adjuntar el stream: cierra la ventana de pérdida
    // entre la carga inicial y el primer evento, y reconcilia tras la caída.
    reloadRef.current();
  }, []);

  const stream = useRealtimeStream({
    enabled,
    token,
    onEvent: handleFrame,
    onOpen: handleOpen,
  });

  const dismiss = useCallback((ticketId: string) => {
    setNotifications((prev) =>
      prev.filter((item) => item.ticketId !== ticketId),
    );
  }, []);

  const clear = useCallback(() => setNotifications([]), []);

  return {
    ...stream,
    liveTickets,
    notifications,
    dismiss,
    clear,
  };
}
