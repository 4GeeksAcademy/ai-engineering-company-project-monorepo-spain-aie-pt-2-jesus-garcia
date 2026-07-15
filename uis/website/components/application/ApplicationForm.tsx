"use client";

import { useState, type FormEvent } from "react";

type StepData = Record<string, string | boolean>;

export function ApplicationForm() {
  const [currentStep, setCurrentStep] = useState(1);
  const [formData, setFormData] = useState<StepData>({});
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  function collectStep(step: number): StepData {
    const container =
      step === 1
        ? document.getElementById("step-1")
        : step === 2
          ? document.getElementById("step-2")
          : document.getElementById("step-3");
    if (!container) return {};
    const inputs = container.querySelectorAll<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>(
      "input, select, textarea",
    );
    const data: StepData = {};
    inputs.forEach((input) => {
      const name = input.id || input.name;
      if (!name) return;
      if (input instanceof HTMLInputElement && input.type === "checkbox") {
        data[name] = input.checked;
      } else if (input instanceof HTMLInputElement && input.type === "radio") {
        if (input.checked) data[name] = input.value;
      } else data[name] = input.value;
    });
    return data;
  }

  function validateStep(step: number): boolean {
    const container =
      step === 1
        ? document.getElementById("step-1")
        : step === 2
          ? document.getElementById("step-2")
          : document.getElementById("step-3");
    if (!container) return false;

    const required = container.querySelectorAll<HTMLElement>("[required]");
    let valid = true;
    let firstMsg = "Revisa los campos obligatorios del paso actual antes de continuar.";

    required.forEach((el) => {
      if (el instanceof HTMLInputElement && el.type === "radio") {
        const group = container.querySelectorAll<HTMLInputElement>(
          `input[name="${el.name}"]`,
        );
        if (!Array.from(group).some((r) => r.checked)) {
          valid = false;
          group.forEach((r) => r.setAttribute("aria-invalid", "true"));
        }
        return;
      }
      if (el instanceof HTMLInputElement && el.type === "checkbox") {
        if (!el.checked) {
          valid = false;
          el.setAttribute("aria-invalid", "true");
        }
        return;
      }
      if (el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) {
        if (!el.value.trim()) {
          valid = false;
          el.setAttribute("aria-invalid", "true");
          return;
        }
        if (el.type === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(el.value.trim())) {
          valid = false;
          el.setAttribute("aria-invalid", "true");
          if (firstMsg === "Revisa los campos obligatorios del paso actual antes de continuar.") {
            firstMsg = "Introduce un email válido.";
          }
          return;
        }
        if (el.type === "tel") {
          const digits = el.value.replace(/\D/g, "");
          if (digits.length < 7 || digits.length > 15) {
            valid = false;
            el.setAttribute("aria-invalid", "true");
            if (firstMsg === "Revisa los campos obligatorios del paso actual antes de continuar.") {
              firstMsg = "Introduce un teléfono válido (7-15 dígitos).";
            }
          }
        }
      }
    });

    if (step === 3) {
      const checkboxes = container.querySelectorAll<HTMLInputElement>(
        'input[type="checkbox"]',
      );
      if (!Array.from(checkboxes).some((c) => c.checked)) {
        valid = false;
        checkboxes.forEach((c) => c.setAttribute("aria-invalid", "true"));
        firstMsg = "Selecciona al menos un reto prioritario.";
      }
    }

    setError(valid ? null : firstMsg);
    return valid;
  }

  function clearErrors() {
    setError(null);
    document.querySelectorAll("[aria-invalid]").forEach((el) =>
      el.removeAttribute("aria-invalid"),
    );
  }

  function goToStep(step: number) {
    clearErrors();
    setCurrentStep(step);
    setSuccess(false);
  }

  function handleNext() {
    if (!validateStep(currentStep)) return;
    setFormData((prev) => ({ ...prev, ...collectStep(currentStep) }));
    goToStep(currentStep + 1);
  }

  function handlePrev() {
    setFormData((prev) => ({ ...prev, ...collectStep(currentStep) }));
    goToStep(currentStep - 1);
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validateStep(currentStep)) return;
    const allData = { ...formData, ...collectStep(currentStep) };
    console.log("Enviando datos del formulario:", allData);
    setSuccess(true);
    setCurrentStep(1);
    setFormData({});
    setError(null);
  }

  return (
    <form id="application-form" onSubmit={handleSubmit} noValidate>
      <div className="mb-6 flex items-center justify-between rounded-xl border border-white/10 bg-slate-900/40 px-4 py-3 text-sm text-slate-300">
        <span>Paso {currentStep} de 3</span>
      </div>

      <div className="space-y-6">
        {currentStep === 1 && (
          <section id="step-1" className="space-y-4">
            <h2 className="text-xl font-semibold text-white">
              Paso 1 · Datos personales
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Nombre completo" id="fullName" required />
              <Field label="Email profesional" id="email" type="email" required />
              <Field label="Teléfono" id="phone" type="tel" required />
              <Field label="Ciudad de residencia" id="city" required />
              <SelectField
                label="País principal de trabajo"
                id="country"
                options={[
                  { value: "ES", label: "España" },
                  { value: "US", label: "Estados Unidos" },
                  { value: "MIXED", label: "Ambos mercados" },
                ]}
                required
              />
              <Field label="Años de experiencia" id="experienceYears" type="number" min={0} max={40} required />
            </div>
          </section>
        )}

        {currentStep === 2 && (
          <section id="step-2" className="space-y-4">
            <h2 className="text-xl font-semibold text-white">
              Paso 2 · Enfoque en TrackFlow
            </h2>
            <div className="grid gap-4 sm:grid-cols-2">
              <SelectField
                label="Área objetivo"
                id="department"
                options={[
                  { value: "warehouse-ops", label: "Operaciones de almacén" },
                  { value: "last-mile", label: "Última milla y transportistas" },
                  { value: "reverse-logistics", label: "Logística inversa" },
                  { value: "cx", label: "Experiencia del cliente" },
                  { value: "commercial", label: "Comercial y relación con clientes" },
                  { value: "technology", label: "Tecnología" },
                  { value: "executive", label: "Dirección ejecutiva" },
                ]}
                required
              />
              <SelectField
                label="Perfil operativo"
                id="roleProfile"
                options={[
                  { value: "route-planning", label: "Planificación y optimización de rutas" },
                  { value: "warehouse-systems", label: "Sistemas de almacén (WMS)" },
                  { value: "transport-network", label: "Gestión de red de transportistas" },
                  { value: "tracking-operations", label: "Seguimiento y control operativo (TMS)" },
                  { value: "logistics-analytics", label: "Analítica y mejora continua logística" },
                ]}
                required
              />
              <Field label="Fecha de inicio disponible" id="availabilityDate" type="date" required />
              <SelectField
                label="Nivel de inglés"
                id="englishLevel"
                options={[
                  { value: "basic", label: "Básico" },
                  { value: "intermediate", label: "Intermedio" },
                  { value: "advanced", label: "Avanzado" },
                  { value: "bilingual", label: "Bilingüe" },
                ]}
                required
              />
            </div>
            <fieldset>
              <legend className="text-sm font-semibold text-slate-200">
                Modalidad preferida *
              </legend>
              <div className="mt-2 flex flex-wrap gap-4 text-sm text-slate-200">
                {["remote", "hybrid", "onsite"].map((mode) => (
                  <label key={mode} className="inline-flex items-center gap-2">
                    <input
                      id={`workMode${mode.charAt(0).toUpperCase() + mode.slice(1)}`}
                      type="radio"
                      name="workMode"
                      value={mode}
                      required
                    />
                    {mode === "remote"
                      ? "Remoto"
                      : mode === "hybrid"
                        ? "Híbrido"
                        : "Presencial"}
                  </label>
                ))}
              </div>
            </fieldset>
          </section>
        )}

        {currentStep === 3 && (
          <section id="step-3" className="space-y-4">
            <h2 className="text-xl font-semibold text-white">
              Paso 3 · Experiencia, condiciones y cierre
            </h2>
            <fieldset>
              <legend className="text-sm font-semibold text-slate-200">
                ¿Qué reto quieres priorizar? *
              </legend>
              <div className="mt-2 grid gap-2 text-sm text-slate-200 sm:grid-cols-2">
                {[
                  { id: "focusInventory", label: "Reducir errores de inventario y preparación de pedidos" },
                  { id: "focusTracking", label: "Mejorar visibilidad y trazabilidad de envíos" },
                  { id: "focusReturns", label: "Agilizar gestión de devoluciones y reclamaciones" },
                  { id: "focusCx", label: "Mejorar comunicación con clientes en incidencias" },
                  { id: "focusCarrierOptimization", label: "Optimizar asignación de rutas y transportistas" },
                  { id: "focusExecutiveDashboard", label: "Incrementar puntualidad de entregas (OTD)" },
                ].map((chk) => (
                  <label key={chk.id} className="inline-flex items-center gap-2">
                    <input id={chk.id} type="checkbox" />
                    {chk.label}
                  </label>
                ))}
              </div>
            </fieldset>

            <TextAreaField label="Experiencia operativa y herramientas que dominas" id="techStack" required />
            <TextAreaField label="Resumen de propuesta (max 400 caracteres)" id="proposalSummary" maxLength={400} required />

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Perfil profesional (LinkedIn o similar) (URL)" id="portfolioUrl" type="url" required />
              <Field label="CV (URL)" id="cvUrl" type="url" required />
            </div>

            <SelectField
              label="Rango salarial esperado (EUR bruto anual)"
              id="salaryRange"
              options={[
                { value: "30k-40k", label: "30k - 40k" },
                { value: "40k-50k", label: "40k - 50k" },
                { value: "50k-65k", label: "50k - 65k" },
                { value: "65k+", label: "65k+" },
              ]}
              required
            />

            <SelectField
              label="Disponibilidad para turnos y picos de demanda"
              id="shiftAvailability"
              options={[
                { value: "full", label: "Disponible en cualquier turno" },
                { value: "business-hours", label: "Solo horario laboral" },
                { value: "weekends", label: "Incluye fines de semana puntuales" },
              ]}
              required
            />

            <TextAreaField label="Comentarios adicionales" id="additionalComments" />

            <div className="space-y-2 text-sm text-slate-200">
              <label className="inline-flex items-center gap-2">
                <input id="acceptPolicy" type="checkbox" required />
                Acepto la política de privacidad y el tratamiento de datos. *
              </label>
              <label className="inline-flex items-center gap-2">
                <input id="acceptUpdates" type="checkbox" />
                Quiero recibir novedades sobre vacantes y operaciones de TrackFlow.
              </label>
            </div>
          </section>
        )}
      </div>

      {error && (
        <p
          className="mt-6 rounded-md border border-red-300/30 bg-red-500/10 px-4 py-3 text-sm text-red-200"
          role="alert"
        >
          {error}
        </p>
      )}

      {success && (
        <p
          className="mt-6 rounded-md border border-emerald-300/30 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-200"
          role="status"
        >
          Aplicación enviada correctamente. Gracias por postular a TrackFlow.
        </p>
      )}

      <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          onClick={handlePrev}
          className={`rounded-md border border-slate-400/40 px-5 py-2.5 text-sm font-semibold text-slate-100 transition hover:border-cyan-300 hover:text-cyan-200 ${
            currentStep === 1 ? "invisible" : ""
          }`}
        >
          Anterior
        </button>
        <div className="flex gap-3">
          {currentStep < 3 && (
            <button
              type="button"
              onClick={handleNext}
              className="rounded-md bg-orange-500 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-orange-400"
            >
              Siguiente
            </button>
          )}
          {currentStep === 3 && (
            <button
              type="submit"
              className="rounded-md bg-cyan-400 px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
            >
              Enviar aplicación
            </button>
          )}
        </div>
      </div>
    </form>
  );
}

function Field({
  label,
  id,
  type = "text",
  required,
  min,
  max,
}: {
  label: string;
  id: string;
  type?: string;
  required?: boolean;
  min?: number;
  max?: number;
}) {
  return (
    <label className="block text-sm text-slate-200" htmlFor={id}>
      {label} {required && <span className="text-red-400">*</span>}
      <input
        id={id}
        name={id}
        type={type}
        required={required}
        min={min}
        max={max}
        className="mt-2 w-full rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300"
      />
    </label>
  );
}

function SelectField({
  label,
  id,
  options,
  required,
}: {
  label: string;
  id: string;
  options: { value: string; label: string }[];
  required?: boolean;
}) {
  return (
    <label className="block text-sm text-slate-200" htmlFor={id}>
      {label} {required && <span className="text-red-400">*</span>}
      <select
        id={id}
        name={id}
        required={required}
        className="mt-2 w-full rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300"
      >
        <option value="">Selecciona una opción</option>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function TextAreaField({
  label,
  id,
  required,
  maxLength,
}: {
  label: string;
  id: string;
  required?: boolean;
  maxLength?: number;
}) {
  return (
    <label className="block text-sm text-slate-200" htmlFor={id}>
      {label} {required && <span className="text-red-400">*</span>}
      <textarea
        id={id}
        name={id}
        rows={3}
        required={required}
        maxLength={maxLength}
        className="mt-2 w-full rounded-md border border-white/20 bg-slate-900/60 px-3 py-2 text-slate-100 outline-none focus:border-cyan-300"
      />
    </label>
  );
}
