import Link from "next/link";

export function CTASection() {
  return (
    <section className="mx-auto max-w-6xl px-6 pb-16 md:pb-42">
      <div className="rounded-3xl border border-orange-300/30 bg-gradient-to-r from-orange-500/20 via-orange-300/10 to-amber-300/20 p-8">
        <div className="flex flex-col items-start justify-between gap-6 lg:flex-row lg:items-center">
          <div>
            <h2 className="text-2xl font-bold text-white">
              Da el siguiente paso con TrackFlow Tech
            </h2>
            <p className="mt-2 max-w-2xl text-slate-200">
              Forma parte de la unidad que está modernizando una operación
              logística internacional. Crea soluciones reales con impacto en
              miles de envíos.
            </p>
          </div>
          <Link
            href="/application"
            className="rounded-md bg-white px-6 py-3 font-semibold text-slate-900 transition hover:bg-slate-100"
          >
            Ir al formulario de aplicación
          </Link>
        </div>
      </div>
    </section>
  );
}
