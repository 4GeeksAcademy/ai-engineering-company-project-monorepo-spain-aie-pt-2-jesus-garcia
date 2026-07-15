import { ApplicationForm } from "@/components/application/ApplicationForm";

export default function ApplicationPage() {
  return (
    <section className="mx-auto max-w-4xl px-6 py-12">
      <div className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-2xl shadow-slate-900/40 sm:p-8">
        <div className="mb-8">
          <p className="inline-flex rounded-md border border-cyan-300/40 bg-cyan-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
            ÚNETE A TRACKFLOW
          </p>
          <h1 className="mt-4 text-3xl font-bold text-white sm:text-4xl">
            Formulario de Aplicación
          </h1>
          <p className="mt-3 text-slate-300">
            Comparte tu perfil y tu propuesta para ayudar a modernizar
            operaciones logísticas entre Estados Unidos y España.
          </p>
        </div>
        <ApplicationForm />
      </div>
    </section>
  );
}
