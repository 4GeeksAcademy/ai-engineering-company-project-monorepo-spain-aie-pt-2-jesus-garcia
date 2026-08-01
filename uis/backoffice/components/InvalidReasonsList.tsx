import { describeReason } from "@/lib/types";

export function InvalidReasonsList({ reasons }: { reasons: Record<string, number> }) {
  const entries = Object.entries(reasons);

  if (entries.length === 0) {
    return (
      <div className="rounded-xl border border-emerald-400/20 bg-emerald-500/10 p-5">
        <p className="text-sm font-medium text-emerald-300">
          Sin registros inválidos — todos los registros son válidos.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-amber-400/20 bg-amber-500/10 p-5">
      <h3 className="text-lg font-semibold text-amber-300">
        Registros inválidos detectados
      </h3>
      <p className="mt-1 text-sm text-slate-300">
        El archivo contiene registros que fueron excluidos del análisis principal:
      </p>
      <ul className="mt-3 space-y-1.5">
        {entries.map(([key, count]) => (
          <li key={key} className="flex items-center justify-between text-sm">
            <span className="text-slate-300">{describeReason(key)}</span>
            <span className="font-semibold text-amber-300">{count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
