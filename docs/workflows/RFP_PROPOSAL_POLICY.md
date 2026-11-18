# Política de propuesta económica — TrackFlow

Documento interno que concreta lo que el briefing del Hito 9 exige pero no
cifra. Es la fuente de los valores deterministas de
`data/pipelines/rfp_proposal/policy.py` y del evaluador de cumplimiento.

> **Validación pendiente:** Miguel Torres (Director Comercial) debe confirmar
> los porcentajes de descuento por volumen antes de usar la propuesta con un
> cliente real. Las tarifas base y las condiciones operativas sí están
> publicadas en `docs/company-knowledge-base/`.

## 1. Reglas que vienen del briefing

Fuente: `docs/workflows/MILESTONE_9.md` §5 y §2.3.

| `rule_id` | Regla | Origen |
| --- | --- | --- |
| `BRIEFING-5.1-CURRENCY` | USD para operación en EE. UU.; EUR para España, según `client_country` | §5 |
| `BRIEFING-5.2-SLA-90` | La propuesta debe indicar el SLA de entrega a tiempo (%) | §5 + `trackflow-sla-delivery.es.md` |
| `BRIEFING-5.3-RETURNS-48H` | Prohibido prometer devoluciones en menos de 48 h | §5 |
| `BRIEFING-5.4-VOLUME-DISCOUNTS` | La propuesta debe incluir tabla de descuentos por volumen | §5 |
| `BRIEFING-5.5-CARRIER-RATES-CONFIDENTIAL` | Prohibido revelar tarifas negociadas con transportistas | §5 |
| `BRIEFING-2.3-NO-INVENTED-FIGURES` | No inventar pallets/SKUs/pedidos/capacidades | §2.3 |
| `BRIEFING-2.1-FORMAT-<DEPT>` | Bloques mínimos de cada sección | §2.1 |

Valores canónicos aplicados:

- SLA de entrega a tiempo comprometido: **90 % mensual por país**.
- Procesamiento de devoluciones: **mínimo 48 h** (nunca se promete menos).
- Ventana estándar de devolución: **30 días** desde la entrega.
- Almacenamiento: **18 USD/m³/mes** (Los Ángeles) y **16 EUR/m³/mes**
  (Zaragoza); 30 días de gracia; 150 % de la tarifa a partir del día 181.
- Preferencial de almacenamiento: a partir de **50 m³/mes**, negociado con
  Miguel Torres.
- Entrega: estándar 3–5 días hábiles; express 24–48 h en zonas metropolitanas;
  internacional 7–12 días hábiles (aduanas).
- Compensación por incumplimiento de SLA: 5 % de la tarifa mensual del país
  tras dos meses consecutivos por debajo del 90 %.
- Alta demanda declarada (Black Friday, Navidad, rebajas de enero): hasta un
  40 % adicional en los tiempos.

## 2. Tabla de descuentos por volumen

Tramos sobre el volumen mensual de pedidos del cliente. Se aplican al
almacenamiento y a la tarifa de última milla ofrecida al cliente (nunca a una
tarifa por transportista).

| Pedidos/mes | Descuento | Nota |
| --- | --- | --- |
| 0 – 1.999 | 0 % | Tarifa estándar publicada |
| 2.000 – 4.999 | 3 % | Requiere aprobación de Miguel Torres |
| 5.000 – 9.999 | 6 % | Requiere aprobación de Miguel Torres |
| 10.000+ | 10 % | Requiere aprobación de Miguel Torres |

La tabla se publica siempre, aunque el volumen no conste en la RFP; en ese caso
el generador añade una pregunta abierta para confirmarlo. Nunca se estima el
volumen del cliente.

## 3. Precios no publicados

La base de conocimiento no publica coste por envío, coste por devolución,
coste por pallet/SKU ni tiempo de onboarding. Estos conceptos se muestran como
`pendiente_confirmacion` con su responsable (Carlos Vega, Sofía Ramos o Ana
Whitfield) y una pregunta abierta. El generador **no los estima**.

## 4. Formato mínimo por departamento

| Departamento | Bloques obligatorios (§2.1) |
| --- | --- |
| `warehouse` | capacidad, coste de almacenamiento, onboarding, descuentos, SLA |
| `lastmile` | transportistas por destino, coste por envío, SLA, descuentos |
| `reverse` | proceso de devolución, coste, tiempo (≥ 48 h), descuentos, SLA |
