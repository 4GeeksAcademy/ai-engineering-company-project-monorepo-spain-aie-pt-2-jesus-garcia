"use client";

import { RFP_STATUS_LABELS, RFP_STATUS_STYLES, type RfpStatus } from "@/lib/rfp-types";

export function RfpStatusBadge({ status }: { status: RfpStatus }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${RFP_STATUS_STYLES[status]}`}
    >
      {RFP_STATUS_LABELS[status]}
    </span>
  );
}
