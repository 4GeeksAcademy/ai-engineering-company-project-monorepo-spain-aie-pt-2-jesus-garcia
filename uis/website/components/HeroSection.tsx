import Link from "next/link";
import Image from "next/image";

export function HeroSection() {
  return (
    <section className="mx-auto max-w-6xl px-6 pb-20 pt-16 md:pb-42 lg:pt-24">
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <div>
          <p className="mb-4 inline-flex rounded-md border border-cyan-300/40 bg-cyan-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">
            Logística inteligente para e-commerce
          </p>
          <h1 className="text-4xl font-bold leading-tight text-white sm:text-5xl lg:text-6xl">
            De almacén a puerta, con control total en tiempo real.
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-300">
            TrackFlow conecta inventario, transporte y devoluciones para que las
            marcas escalen sin fricción. Operamos en Estados Unidos y España con
            una propuesta centrada en velocidad, trazabilidad y automatización.
          </p>
          <div className="mt-8 flex flex-wrap gap-4">
            <Link
              href="#estadisticas"
              className="rounded-md bg-orange-500 px-6 py-3 font-semibold text-slate-950 transition hover:bg-orange-400"
            >
              Ver más
            </Link>
            <Link
              href="/application"
              className="rounded-md border border-slate-400/40 px-6 py-3 font-semibold text-slate-100 transition hover:border-cyan-300 hover:text-cyan-200"
            >
              Comenzar aplicación
            </Link>
          </div>
        </div>
        <div className="relative">
          <div className="absolute -inset-4 -z-10 rounded-3xl bg-gradient-to-tr from-orange-500/30 via-amber-300/10 to-cyan-500/20 blur-2xl" />
          <div className="max-w-md rounded-3xl border border-white/10 bg-white/5 shadow-2xl shadow-orange-900/20">
            <Image
              src="/truck-hero.jpg"
              alt="Camion de TrackFlow"
              width={500}
              height={350}
              className="w-full max-w-md rounded-3xl object-cover"
            />
          </div>
        </div>
      </div>
    </section>
  );
}
