"use client";

import { useSyncExternalStore } from "react";
import { getConsent, setConsent, subscribeConsent } from "@/src/telemetry/consent";

export function ConsentBanner() {
  const status = useSyncExternalStore(subscribeConsent, getConsent, () => "unset");

  if (status !== "unset") return null;

  return (
    <div
      role="dialog"
      aria-label="Consentimiento de analítica"
      className="fixed inset-x-4 bottom-4 z-50 mx-auto flex max-w-3xl flex-col gap-3 rounded-xl border border-white/10 bg-slate-900/95 p-4 shadow-xl backdrop-blur sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="text-sm text-slate-300">
        Usamos telemetría anónima para mejorar el backoffice de TrackFlow. Puedes aceptar o
        rechazar el seguimiento analítico; los eventos de seguridad y operativos se registran
        igualmente.
      </p>
      <div className="flex shrink-0 gap-2">
        <button
          type="button"
          onClick={() => setConsent("denied")}
          className="rounded-lg px-4 py-2 text-sm text-slate-300 transition hover:bg-white/5 hover:text-white"
        >
          Rechazar
        </button>
        <button
          type="button"
          onClick={() => setConsent("granted")}
          className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-cyan-500"
        >
          Aceptar
        </button>
      </div>
    </div>
  );
}
