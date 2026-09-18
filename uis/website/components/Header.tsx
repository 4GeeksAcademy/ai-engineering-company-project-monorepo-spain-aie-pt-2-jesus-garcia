import Link from "next/link";
import Image from "next/image";

const BACKOFFICE_URL = process.env.NEXT_PUBLIC_BACKOFFICE_URL ?? "http://localhost:3001";

export function Header() {
  return (
    <header className="sticky top-0 z-20 border-b border-white/10 bg-slate-950/70 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
        <Link
          href="/"
          aria-label="Ir al inicio de TrackFlow"
          className="flex items-center gap-3"
        >
          <Image
            src="/logo.png"
            alt="Logo de TrackFlow"
            width={48}
            height={48}
            className="object-contain"
          />
          <span className="border-b-2 border-orange-500 text-xl font-bold uppercase italic tracking-wide">
            TrackFlow
          </span>
        </Link>
        <nav aria-label="Navegacion principal" className="flex items-center gap-4">
          <Link
            href={`${BACKOFFICE_URL}/login`}
            className="text-sm font-semibold text-slate-300 transition hover:text-orange-300"
          >
            Iniciar Sesión
          </Link>
          <Link
            href="/application"
            className="rounded-md border border-orange-400/60 px-4 py-2 text-sm font-semibold text-orange-300 transition hover:bg-orange-500 hover:text-slate-950"
          >
            Aplicar ahora
          </Link>
        </nav>
      </div>
    </header>
  );
}
