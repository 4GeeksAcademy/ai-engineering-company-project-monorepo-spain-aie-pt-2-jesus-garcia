import { sampleData } from "@repo/types/models";
import {
  filterShipments,
  filterInventory,
  filterReturns,
} from "@repo/utils/filters";
import {
  countByCategory,
  sumBy,
  averageBy,
  maxBy,
  minBy,
} from "@repo/utils/transformations";

export default function BusinessLogicPage() {
  const { shipments, inventory, returns, carrierPerformance } = sampleData;

  const urgentShipments = filterShipments(shipments, { priority: "urgent" });
  const esReturns = filterReturns(returns, { country: "ES" });
  const lowStock = filterInventory(inventory, { lowStock: true });

  const shipmentsByCarrier = countByCategory(shipments, (s) => s.carrier);
  const shipmentsByStatus = countByCategory(shipments, (s) => s.status);
  const totalWeight = sumBy(shipments, (s) => s.weightKg);
  const avgWeight = averageBy(shipments, (s) => s.weightKg);
  const avgCost = averageBy(carrierPerformance, (c) => c.avgCostPerKgEur);
  const mostExpensive = maxBy(carrierPerformance, (c) => c.avgCostPerKgEur);
  const cheapest = minBy(carrierPerformance, (c) => c.avgCostPerKgEur);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Lógica de negocio</h1>
        <p className="mt-2 text-slate-400">
          Resultados de filtros, agregaciones y transformaciones sobre los datos
          de TrackFlow (importados desde <code className="rounded bg-white/5 px-1.5 py-0.5 text-cyan-300">src/</code>).
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <MetricCard
          title="Envíos urgentes"
          value={urgentShipments.length}
          subtitle={`de ${shipments.length} totales`}
        />
        <MetricCard
          title="Devoluciones en España"
          value={esReturns.length}
          subtitle={`de ${returns.length} totales`}
        />
        <MetricCard
          title="SKU con stock bajo"
          value={lowStock.length}
          subtitle={`de ${inventory.length} evaluados`}
        />
        <MetricCard
          title="Peso total"
          value={`${totalWeight} kg`}
          subtitle={`promedio ${avgWeight?.toFixed(1)} kg`}
        />
        <MetricCard
          title="Coste promedio carriers"
          value={`${avgCost?.toFixed(2)} €/kg`}
          subtitle={
            mostExpensive && cheapest
              ? `máx: ${mostExpensive.value} (${mostExpensive.item.carrier}) · mín: ${cheapest.value} (${cheapest.item.carrier})`
              : undefined
          }
        />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <DataTable
          title="Envíos por transportista"
          headers={["Transportista", "Cantidad"]}
          rows={Object.entries(shipmentsByCarrier)}
        />
        <DataTable
          title="Envíos por estado"
          headers={["Estado", "Cantidad"]}
          rows={Object.entries(shipmentsByStatus)}
        />
      </div>

      <div className="mt-8">
        <h2 className="mb-4 text-xl font-semibold text-white">
          Datos de ejemplo (sampleData)
        </h2>
        <div className="overflow-x-auto rounded-xl border border-white/10">
          <pre className="max-h-96 overflow-y-auto p-4 text-xs text-slate-300">
            {JSON.stringify(sampleData, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
}

function MetricCard({
  title,
  value,
  subtitle,
}: {
  title: string;
  value: string | number;
  subtitle?: string;
}) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-5">
      <p className="text-sm text-slate-400">{title}</p>
      <p className="mt-1 text-2xl font-bold text-white">{value}</p>
      {subtitle && <p className="mt-1 text-xs text-slate-500">{subtitle}</p>}
    </div>
  );
}

function DataTable({
  title,
  headers,
  rows,
}: {
  title: string;
  headers: string[];
  rows: [string, unknown][];
}) {
  return (
    <div>
      <h3 className="mb-3 text-lg font-semibold text-white">{title}</h3>
      <div className="overflow-hidden rounded-xl border border-white/10">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-white/10 bg-white/5 text-xs font-semibold uppercase tracking-wider text-slate-400">
              {headers.map((h) => (
                <th key={h} className="px-4 py-3">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([key, val]) => (
              <tr key={key} className="border-b border-white/5 last:border-0">
                <td className="px-4 py-2.5 text-slate-200">{key}</td>
                <td className="px-4 py-2.5 text-slate-400">
                  {String(val)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
