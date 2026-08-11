"use client";

import { useEffect, useState } from "react";
import Image from "next/image";

interface LoaderProps {
  onComplete?: () => void;
}

export function Loader({ onComplete }: LoaderProps) {
  const [phase, setPhase] = useState<"reveal" | "fade" | "done">("reveal");

  useEffect(() => {
    const revealTimer = setTimeout(() => setPhase("fade"), 800);
    const fadeTimer = setTimeout(() => setPhase("done"), 1300);

    return () => {
      clearTimeout(revealTimer);
      clearTimeout(fadeTimer);
    };
  }, []);

  useEffect(() => {
    if (phase === "done" && onComplete) {
      onComplete();
    }
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
