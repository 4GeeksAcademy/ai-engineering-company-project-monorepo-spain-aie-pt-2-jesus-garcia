const departments = [
  {
    name: "Operaciones de Almacén",
    head: "Ana Whitfield",
    desc: "Gestión de inventario en tiempo real entre Los Ángeles y Zaragoza.",
  },
  {
    name: "Última Milla y Transportistas",
    head: "Carlos Vega",
    desc: "Coordinación de 8 transportistas en EE.UU. y España.",
  },
  {
    name: "Logística Inversa",
    head: "Sofía Ramos",
    desc: "Gestión de devoluciones con criterios de autoaprobación.",
  },
  {
    name: "Experiencia del Cliente",
    head: "Valentina Cruz",
    desc: "Soporte multicanal para marcas y consumidores finales.",
  },
  {
    name: "Comercial y Clientes",
    head: "Miguel Torres",
    desc: "Retención y crecimiento de la cartera de clientes.",
  },
  {
    name: "Dirección Ejecutiva",
    head: "Thomas Harry",
    desc: "Visión estratégica y reporting consolidado.",
  },
];

export function WelcomeCards() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {departments.map((dept) => (
        <article
          key={dept.name}
          className="rounded-xl border border-white/10 bg-white/5 p-5 transition hover:border-cyan-400/30"
        >
          <h3 className="font-semibold text-white">{dept.name}</h3>
          <p className="mt-1 text-xs text-cyan-300/80">{dept.head}</p>
          <p className="mt-2 text-sm text-slate-400">{dept.desc}</p>
        </article>
      ))}
    </div>
  );
}
