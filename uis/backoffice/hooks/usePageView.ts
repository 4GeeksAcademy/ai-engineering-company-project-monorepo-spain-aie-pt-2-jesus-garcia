"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";
import { track } from "@/src/services/telemetry";

export function usePageView() {
  const pathname = usePathname();
  const previous = useRef<string | null>(null);

  useEffect(() => {
    track("page_view", {
      path: pathname,
      referrer_path: previous.current,
      app: "backoffice",
    });
    previous.current = pathname;
  }, [pathname]);
}
