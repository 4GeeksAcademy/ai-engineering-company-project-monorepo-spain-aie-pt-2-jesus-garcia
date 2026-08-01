export function BreakdownCard({
  title,
  items,
  labels,
}: {
  title: string;
  items: Record<string, number>;
  labels: Record<string, string>;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5">
      <h3 className="mb-3 text-lg font-semibold text-white">{title}</h3>
      <ul className="space-y-2">
        {Object.entries(items).map(([key, value]) => (
          <li key={key} className="flex items-center justify-between">
            <span className="text-sm text-slate-300">{labels[key] ?? key}</span>
            <span className="text-sm font-semibold text-cyan-300">{value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
