import { ResetPasswordForm } from "@/components/auth/ResetPasswordForm";

export default async function ResetPasswordPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return (
    <section>
      <h1 className="mb-6 text-center text-2xl font-bold text-white">
        Restablecer contraseña
      </h1>
      <ResetPasswordForm initialToken={token} />
    </section>
  );
}
