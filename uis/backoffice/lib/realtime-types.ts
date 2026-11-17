import type { RfpStatus } from "./rfp-types";

/** Campos del briefing para un ticket de RFP (sin sobre anidado). */
export interface RfpTicketEventPayload {
  ticket_id: string;
  rfp_id: string;
  client_name: string | null;
  client_country: string | null;
  services_requested: string[];
  currency: string | null;
  status: RfpStatus;
  created_at: string;
  original_filename: string;
  pipeline_stage: string | null;
}

export interface SlaAlertRecipient {
  name: string;
  role: string;
}

/** Evento `sla_threshold_alert` (SLA de entrega < 90 % por país). */
export interface SlaThresholdAlertPayload {
  alert_id: string;
  metric: string;
  country: string;
  warehouse: string | null;
  week_start: string;
  threshold_pct: number;
  on_time_pct: number | null;
  total_shipments: number;
  on_time_shipments: number;
  breached: boolean;
  recipients: SlaAlertRecipient[];
  detected_at: string | null;
}

export const RFP_TICKET_CREATED = "rfp_ticket_created";
export const RFP_TICKET_METADATA_READY = "rfp_ticket_metadata_ready";
export const SLA_THRESHOLD_ALERT = "sla_threshold_alert";
export const STREAM_LAGGED = "stream_lagged";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function parseRfpTicketEvent(
  raw: string,
): RfpTicketEventPayload | null {
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value)) return null;
    if (typeof value.ticket_id !== "string") return null;
    if (typeof value.rfp_id !== "string") return null;
    const services = Array.isArray(value.services_requested)
      ? value.services_requested.filter(
          (item): item is string => typeof item === "string",
        )
      : [];
    return {
      ticket_id: value.ticket_id,
      rfp_id: value.rfp_id,
      client_name:
        typeof value.client_name === "string" ? value.client_name : null,
      client_country:
        typeof value.client_country === "string" ? value.client_country : null,
      services_requested: services,
      currency: typeof value.currency === "string" ? value.currency : null,
      status: (typeof value.status === "string"
        ? value.status
        : "analizando") as RfpStatus,
      created_at:
        typeof value.created_at === "string" ? value.created_at : "",
      original_filename:
        typeof value.original_filename === "string"
          ? value.original_filename
          : "",
      pipeline_stage:
        typeof value.pipeline_stage === "string" ? value.pipeline_stage : null,
    };
  } catch {
    return null;
  }
}

export function parseSlaAlert(raw: string): SlaThresholdAlertPayload | null {
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value)) return null;
    if (typeof value.alert_id !== "string") return null;
    if (typeof value.country !== "string") return null;
    const recipients = Array.isArray(value.recipients)
      ? value.recipients
          .filter(isRecord)
          .map((item) => ({
            name: typeof item.name === "string" ? item.name : "",
            role: typeof item.role === "string" ? item.role : "",
          }))
          .filter((item) => item.name !== "")
      : [];
    const onTime =
      typeof value.on_time_pct === "number" ? value.on_time_pct : null;
    return {
      alert_id: value.alert_id,
      metric:
        typeof value.metric === "string"
          ? value.metric
          : "on_time_delivery_pct",
      country: value.country,
      warehouse:
        typeof value.warehouse === "string" ? value.warehouse : null,
      week_start:
        typeof value.week_start === "string" ? value.week_start : "",
      threshold_pct:
        typeof value.threshold_pct === "number" ? value.threshold_pct : 90,
      on_time_pct: onTime,
      total_shipments:
        typeof value.total_shipments === "number" ? value.total_shipments : 0,
      on_time_shipments:
        typeof value.on_time_shipments === "number"
          ? value.on_time_shipments
          : 0,
      breached: value.breached === true,
      recipients,
      detected_at:
        typeof value.detected_at === "string" ? value.detected_at : null,
    };
  } catch {
    return null;
  }
}
