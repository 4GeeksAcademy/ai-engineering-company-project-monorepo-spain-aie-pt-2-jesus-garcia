export function Footer() {
  return (
    <footer className="border-t border-white/10 bg-slate-950/60">
      <div className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-10 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xl font-bold text-white">
            <span className="border-b-2 border-orange-500 uppercase italic">
              TrackFlow
            </span>
          </p>
          <p className="mt-2 max-w-md text-slate-300">
            Soluciones logísticas de última milla para marcas que necesitan
            escalar con confianza.
          </p>
        </div>
        <div className="text-slate-300">
          <p className="font-semibold text-white">Contacto</p>
          <p className="mt-2">
            Email:{" "}
            <a
              href="mailto:contacto@trackflow.com"
              className="decoration-cyan-300/70 underline underline-offset-2 hover:text-cyan-200"
            >
              contacto@trackflow.com
            </a>
          </p>
          <p>
            Teléfono:{" "}
            <a
              href="tel:+34900123456"
              className="decoration-cyan-300/70 underline underline-offset-2 hover:text-cyan-200"
            >
              +34 900 123 456
            </a>
          </p>
          <p>Oficinas: Los Ángeles y Zaragoza</p>
        </div>
      </div>
    </footer>
  );
}
