export function TimelineSection() {
  const steps = [
    {
      title: "Recepción del pedido",
      description: "El pedido se recibe, valida y enruta al almacén correcto.",
    },
    {
      title: "Picking y empaquetado",
      description:
        "Se prepara el SKU y se empaqueta según los requisitos de la marca.",
    },
    {
      title: "Asignación de transportista",
      description:
        "Se selecciona el carrier más adecuado por destino, coste y urgencia.",
    },
    {
      title: "Tracking y entrega",
      description: "El envío se monitoriza hasta la entrega final al cliente.",
    },
    {
      title: "Gestión de devolución",
      description:
        "Si aplica, se procesa la logística inversa para cerrar el ciclo.",
    },
  ];

  return (
    <section className="mx-auto max-w-6xl px-6 pb-20">
      <h2 className="text-3xl font-bold text-white">
        ¿Cómo llega un paquete a destino?
      </h2>
      <p className="mt-2 text-slate-300">
        Proceso operativo simplificado de extremo a extremo.
      </p>
      <ol className="mt-8 space-y-6 border-l border-orange-300/40 pl-6">
        {steps.map((step, i) => (
          <li key={i} className="relative">
            <span
              aria-hidden="true"
              className="absolute -left-[34px] top-1 inline-flex h-4 w-4 rounded-md bg-orange-400 ring-4 ring-orange-400/20"
            />
            <h3 className="text-lg font-semibold text-white">
              {i + 1}. {step.title}
            </h3>
            <p className="mt-1 text-slate-300">{step.description}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
