import Image from "next/image";
import Link from "next/link";

export default function AuthLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[radial-gradient(circle_at_20%_10%,rgba(249,115,22,0.25),transparent_35%),radial-gradient(circle_at_85%_12%,rgba(59,130,246,0.18),transparent_30%),linear-gradient(180deg,#020617_0%,#0f172a_60%,#111827_100%)] px-4">
      <div className="w-full max-w-md">
        <Link href="/" className="mb-8 flex items-center justify-center gap-3">
          <Image
            src="/logo.png"
            alt="TrackFlow"
            width={56}
            height={56}
            className="object-contain"
          />
          <span className="border-b-2 border-orange-500 text-2xl font-bold uppercase italic tracking-wide text-white">
            TrackFlow
          </span>
        </Link>
        <div className="rounded-xl border border-white/10 bg-slate-900/60 p-8 backdrop-blur">
          {children}
        </div>
      </div>
    </div>
  );
}
