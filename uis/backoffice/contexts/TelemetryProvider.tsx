"use client";

import { useEffect, type ReactNode } from "react";
import { ConsentBanner } from "@/components/telemetry/ConsentBanner";
import { usePageView } from "@/hooks/usePageView";
import { initTelemetry, track } from "@/src/services/telemetry";

export function TelemetryProvider({ children }: { children: ReactNode }) {
  usePageView();

  useEffect(() => {
    const cleanup = initTelemetry();

    const handleError = (event: ErrorEvent) => {
      track("frontend_error_uncaught", {
        error_type: "error",
        error_name: event.error?.name ?? "Error",
        error_message_sanitized: event.message,
        path: window.location.pathname,
        app: "backoffice",
      });
    };

    const handleRejection = (event: PromiseRejectionEvent) => {
      const reason = event.reason as unknown;
      let name = "UnhandledRejection";
      let message = "";
      if (typeof reason === "string") {
        message = reason;
      } else if (reason && typeof reason === "object") {
        const record = reason as { name?: unknown; message?: unknown };
        if (typeof record.name === "string") name = record.name;
        if (typeof record.message === "string") message = record.message;
      }
      track("frontend_error_uncaught", {
        error_type: "unhandledrejection",
        error_name: name,
        error_message_sanitized: message,
        path: window.location.pathname,
        app: "backoffice",
      });
    };

    window.addEventListener("error", handleError);
    window.addEventListener("unhandledrejection", handleRejection);

    return () => {
      cleanup();
      window.removeEventListener("error", handleError);
      window.removeEventListener("unhandledrejection", handleRejection);
    };
  }, []);

  return (
    <>
      {children}
      <ConsentBanner />
    </>
  );
}
