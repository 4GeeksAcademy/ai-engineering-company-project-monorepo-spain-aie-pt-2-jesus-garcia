import { createElement } from "react";

export function LoadingSpinner({ className }: { className?: string }) {
  return createElement("div", {
    role: "status",
    "aria-label": "Cargando",
    className: `h-10 w-10 animate-spin rounded-full border-4 border-slate-600 border-t-cyan-400 ${className ?? ""}`,
  });
}