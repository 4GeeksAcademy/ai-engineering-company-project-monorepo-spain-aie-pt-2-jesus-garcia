import Link from "next/link";
import { WelcomeCards } from "@/components/backoffice/WelcomeCards";

export default function BackofficePage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">
          Panel de Operaciones TrackFlow
        </h1>
        <p className="mt-2 text-slate-400">
          Herramientas internas para la gestión logística.
        </p>
      </div>
      <WelcomeCards />
      <div className="mt-8 flex gap-4">
        <Link
          href="/backoffice/business-logic"
          className="rounded-md bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
        >
          Explorar lógica de negocio
        </Link>
      </div>
    </div>
  );
}
