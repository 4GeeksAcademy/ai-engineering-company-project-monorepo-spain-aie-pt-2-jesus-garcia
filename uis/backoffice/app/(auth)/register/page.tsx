import { RegisterForm } from "@/components/auth/RegisterForm";

export default function RegisterPage() {
  return (
    <section>
      <h1 className="mb-6 text-center text-2xl font-bold text-white">
        Crear cuenta
      </h1>
      <RegisterForm />
    </section>
  );
}
