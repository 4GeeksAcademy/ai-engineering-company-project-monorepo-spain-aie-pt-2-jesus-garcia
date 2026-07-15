import { SkipLink } from "@/components/SkipLink";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";

export default function PublicLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <SkipLink />
      <div className="min-h-screen bg-[radial-gradient(circle_at_20%_10%,rgba(249,115,22,0.25),transparent_35%),radial-gradient(circle_at_85%_12%,rgba(59,130,246,0.18),transparent_30%),linear-gradient(180deg,#020617_0%,#0f172a_60%,#111827_100%)]">
        <Header />
        <main id="main-content" tabIndex={-1}>
          {children}
        </main>
        <Footer />
      </div>
    </>
  );
}
