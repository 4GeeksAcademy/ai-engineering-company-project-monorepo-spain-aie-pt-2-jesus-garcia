import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";

export default function ForgotPasswordPage() {
  return (
    <section>
      <h1 className="mb-6 text-center text-2xl font-bold text-white">
        Recuperar contraseña
      </h1>
      <ForgotPasswordForm />
    </section>
  );
}
