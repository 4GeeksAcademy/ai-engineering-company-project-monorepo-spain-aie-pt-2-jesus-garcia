"use client";

import { AuthProvider } from "@/contexts/AuthContext";
import { TelemetryProvider } from "@/contexts/TelemetryProvider";
import type { ReactNode } from "react";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <TelemetryProvider>
      <AuthProvider>{children}</AuthProvider>
    </TelemetryProvider>
  );
}
