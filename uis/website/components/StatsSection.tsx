export function StatsSection() {
  return (
    <section
      id="estadisticas"
      className="mx-auto max-w-6xl px-6 pb-16 md:pb-42"
    >
      <h2 className="text-3xl font-bold text-white">TrackFlow en números</h2>
      <p className="mt-2 text-slate-300">
        Datos clave extraídos del contexto operativo actual de la empresa.
      </p>
      <div className="mt-8 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <article className="rounded-2xl border border-white/10 bg-white/5 p-6">
          <p className="text-sm uppercase tracking-widest text-cyan-200">
            Empleados
          </p>
          <p className="mt-3 text-4xl font-bold text-white">130+</p>
          <p className="mt-2 text-sm text-slate-300">
            Equipo distribuido entre Los Ángeles y Zaragoza.
          </p>
        </article>
        <article className="rounded-2xl border border-white/10 bg-white/5 p-6">
          <p className="text-sm uppercase tracking-widest text-cyan-200">
            Facturación anual
          </p>
          <p className="mt-3 text-4xl font-bold text-white">EUR 9M</p>
          <p className="mt-2 text-sm text-slate-300">
            Escala actual del negocio logístico.
          </p>
        </article>
        <article className="rounded-2xl border border-white/10 bg-white/5 p-6">
          <p className="text-sm uppercase tracking-widest text-cyan-200">
            Transportistas
          </p>
          <p className="mt-3 text-4xl font-bold text-white">8</p>
          <p className="mt-2 text-sm text-slate-300">
            Red multimercado para envíos de última milla.
          </p>
        </article>
        <article className="rounded-2xl border border-white/10 bg-white/5 p-6">
          <p className="text-sm uppercase tracking-widest text-cyan-200">
            Devoluciones
          </p>
          <p className="mt-3 text-4xl font-bold text-white">18-25%</p>
          <p className="mt-2 text-sm text-slate-300">
            Rango de devolución según cliente y país.
          </p>
        </article>
      </div>
    </section>
  );
}
