import { LoginForm } from "@/components/auth/LoginForm";

export default function LoginPage() {
  return (
    <section>
      <h1 className="mb-6 text-center text-2xl font-bold text-white">
        Iniciar sesión
      </h1>
      <LoginForm />
    </section>
  );
}
