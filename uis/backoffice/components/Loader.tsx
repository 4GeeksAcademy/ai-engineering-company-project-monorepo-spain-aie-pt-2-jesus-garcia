"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";

interface LoaderProps {
  onComplete?: () => void;
  /**
   * Cómo abandona la pantalla el overlay al terminar la animación:
   * - "auto": se desvanece y desaparece (por defecto).
   * - "hold": se queda opaco hasta que el componente se desmonta, para tapar
   *   la pantalla mientras la navegación al destino está en curso.
   */
  exit?: "auto" | "hold";
}

const REVEAL_MS = 800;
const FADE_MS = 500;
// Red de seguridad: si la navegación nunca llega a completarse, no dejamos al
// usuario atrapado detrás del overlay.
const HOLD_TIMEOUT_MS = 6000;

type Phase = "reveal" | "fade" | "hold" | "done";

export function Loader({ onComplete, exit = "auto" }: LoaderProps) {
  const hold = exit === "hold";
  const [phase, setPhase] = useState<Phase>("reveal");
  const completed = useRef(false);

  // Al terminar la cortinilla del logo pasamos a la siguiente fase: seguir
  // tapando la pantalla ("hold") o desvanecernos ("fade").
  useEffect(() => {
    const timer = setTimeout(() => setPhase(hold ? "hold" : "fade"), REVEAL_MS);
    return () => clearTimeout(timer);
  }, [hold]);

  // Desvanecimiento y salida final, tanto en modo "auto" como cuando salta la
  // red de seguridad del modo "hold".
  useEffect(() => {
    if (phase !== "fade") return;
    const timer = setTimeout(() => setPhase("done"), FADE_MS);
    return () => clearTimeout(timer);
  }, [phase]);

  useEffect(() => {
    if (!hold || phase !== "hold") return;
    const timer = setTimeout(() => setPhase("fade"), HOLD_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [hold, phase]);

  useEffect(() => {
    if (completed.current) return;
    if (phase !== "hold" && phase !== "done") return;
    completed.current = true;
    onComplete?.();
  }, [phase, onComplete]);

  if (phase === "done") return null;

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center bg-slate-950 transition-opacity duration-500 ${
        phase === "fade" ? "opacity-0" : "opacity-100"
      }`}
    >
      <div className="relative h-32 w-32 overflow-hidden">
        <Image
          src="/logo.png"
          alt="TrackFlow"
          width={128}
          height={128}
          className="absolute inset-0 object-contain"
        />
        <div
          className="absolute inset-0 transition-[clip-path] duration-[800ms] ease-out"
          style={{
            clipPath:
              phase === "reveal" ? "inset(0)" : "inset(0 0 100% 0)",
          }}
        >
          <Image
            src="/logo.png"
            alt=""
            width={128}
            height={128}
            className="object-contain"
            style={{ filter: "grayscale(100%)" }}
          />
        </div>
      </div>
    </div>
  );
}
