import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-slate-950 px-6 text-center text-slate-100">
      <h1 className="text-5xl font-bold text-white">404</h1>
      <p className="mt-4 text-slate-400">
        No encontramos la página que buscas.
      </p>
      <Link
        href="/"
        className="mt-8 rounded-lg bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
      >
        Volver al inicio
      </Link>
    </div>
  );
}
