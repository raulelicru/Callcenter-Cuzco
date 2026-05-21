# Sistema Predictivo de Cobranza — Propuesta Técnica

**Call Center Cuzco | Versión 1.0**

---

## Resumen Ejecutivo

Desarrollar un **Score Propio de Propensión al Pago (Propensity to Pay)** que reemplaza la asignación manual de carteras por una priorización algorítmica. El sistema clasifica a cada deudor en un score del **1 al 100** según su probabilidad real de pagar en los próximos 30 días, permitiendo al call center enfocar sus recursos humanos en los segmentos de mayor retorno.

**Resultado esperado:** Reducción del costo por recuperación entre 20–35% y aumento de la tasa de contacto efectivo (RPC) en 15–25 puntos porcentuales dentro de los primeros 3 meses.

---

## 1. Arquitectura de Datos — Tabla Maestra

La tabla maestra (`tb_cartera_maestro`) es el insumo central del modelo. Se actualiza diariamente desde el core bancario / sistema de gestión de cobranza.

### 1.1 Esquema de la Tabla

```sql
CREATE TABLE tb_cartera_maestro (
    -- ── IDENTIFICADORES ──────────────────────────────────────────
    cliente_id          VARCHAR(20)     NOT NULL,
    fecha_corte         DATE            NOT NULL,

    -- ── DATOS DE LA CUENTA / DEUDA ────────────────────────────────
    dpd                 INTEGER,        -- Days Past Due (días en mora)
    bucket_mora         VARCHAR(5),     -- B1 (1-30d), B2 (31-60d), B3 (61-90d), B4 (>90d)
    saldo_capital       DECIMAL(12,2),  -- Capital vencido
    saldo_interes       DECIMAL(12,2),  -- Intereses acumulados
    saldo_total         DECIMAL(12,2),  -- Capital + intereses + gastos
    num_cuotas_vencidas INTEGER,        -- Número de cuotas impagas
    monto_cuota         DECIMAL(10,2),  -- Monto de la cuota mensual
    producto            VARCHAR(50),    -- Tipo de crédito

    -- ── HISTORIAL DE GESTIÓN DEL CALL CENTER ─────────────────────
    rpc_rate            DECIMAL(5,4),   -- Right Party Contact: contactos efectivos / llamadas totales
    total_llamadas      INTEGER,        -- Llamadas intentadas en los últimos 90 días
    contactos_efectivos INTEGER,        -- Llamadas donde se habló con el titular
    promesas_totales    INTEGER,        -- Compromisos de pago generados
    promesas_cumplidas  INTEGER,        -- Compromisos honrados
    promesas_rotas      INTEGER,        -- Compromisos incumplidos
    dias_ultimo_contacto INTEGER,       -- Días desde el último RPC exitoso
    ultimo_estado_marcado VARCHAR(30),  -- RPC_PROMESA | RPC_RECHAZO | NO_CONTESTA | BUZÓN | COLGÓ

    -- ── DATOS SOCIODEMOGRÁFICOS ───────────────────────────────────
    edad                INTEGER,
    genero              CHAR(1),        -- M / F
    nivel_educativo     VARCHAR(20),
    estado_laboral      VARCHAR(20),    -- Dependiente | Independiente | Desempleado | Jubilado
    ingreso_mensual     DECIMAL(10,2),  -- Ingreso declarado o imputado
    ratio_deuda_ingreso DECIMAL(6,4),   -- saldo_total / (ingreso_mensual * 12)
    zona_geografica     VARCHAR(50),

    -- ── TARGET (para entrenamiento) ───────────────────────────────
    pago_30d            SMALLINT,       -- 1 = realizó pago en ventana de 30 días, 0 = no pagó

    PRIMARY KEY (cliente_id, fecha_corte)
);
```

### 1.2 Variables por Importancia Predictiva (Estimado)

| Rank | Variable | Grupo | Razón |
|------|----------|-------|-------|
| 1 | `rpc_rate` | Gestión CC | Proxy directo de accesibilidad del deudor |
| 2 | `dpd` | Deuda | A mayor mora, menor intención/capacidad de pago |
| 3 | `promesas_cumplidas` | Gestión CC | Historial de comportamiento de pago |
| 4 | `ultimo_estado_marcado` | Gestión CC | El estado más reciente define la intención actual |
| 5 | `ratio_deuda_ingreso` | Sociodem. | Capacidad real de pago |
| 6 | `dias_ultimo_contacto` | Gestión CC | Recencia del contacto |
| 7 | `estado_laboral` | Sociodem. | Estabilidad del flujo de ingresos |
| 8 | `bucket_mora` | Deuda | Segmentación estándar de cobranza |

---

## 2. Metodología del Modelo de Machine Learning

### 2.1 Selección de Algoritmo

Se implementa una estrategia de **dos modelos complementarios**:

| Modelo | Propósito | Ventaja | Cuándo Usar |
|--------|-----------|---------|-------------|
| **Regresión Logística** | Explicabilidad regulatoria | Coeficientes interpretables, rápido | Auditorías, presentaciones a dirección |
| **Random Forest / XGBoost** | Máxima precisión predictiva | Captura relaciones no lineales | Scoring operativo diario |

> **Decisión MVP:** Random Forest con `n_estimators=300`. Balanceo de clases con `class_weight="balanced"` dado que la tasa de pago histórica es típicamente 25–40% (clase desbalanceada).

### 2.2 Definición de la Variable Objetivo (Target)

```
Target = 1  →  El cliente realizó AL MENOS UN pago dentro de los 30 días 
               posteriores a la fecha de corte.
Target = 0  →  El cliente NO realizó ningún pago en esa ventana.
```

La ventana de 30 días es el estándar operativo del call center (ciclo mensual de gestión). Se puede parametrizar a 15 o 60 días según la estrategia de cobranza.

### 2.3 Transformación de Probabilidad a Score Operativo

El modelo genera `P(pago)` ∈ [0, 1]. La transformación a Score 1–100 sigue:

```
                  P(i) - P_p1
Score(i) = ─────────────────────── × 99 + 1
               P_p99 - P_p1
```

Donde `P_p1` y `P_p99` son los percentiles 1 y 99 de la distribución, lo que:
- **Elimina outliers** en los extremos sin recortar información
- **Distribuye el score** uniformemente en toda la escala 1–100
- **Estabiliza** el score entre ejecuciones diarias

### 2.4 Métricas de Evaluación

| Métrica | Umbral Mínimo Aceptable | Por Qué |
|---------|------------------------|---------|
| **AUC-ROC** | ≥ 0.72 | Mide capacidad discriminante global |
| **Average Precision** | ≥ 0.55 | Relevante con clases desbalanceadas |
| **Lift en Decil 1** | ≥ 2.5x | Los top-10% deben pagar 2.5× más que la media |
| **KS Statistic** | ≥ 0.35 | Separación entre distribuciones de pagadores/no-pagadores |

---

## 3. Estrategia Operativa — Matriz de Segmentación

```
┌─────────────┬───────────┬──────────────────────────────────────┬──────────────────────────────────────┬─────────────────┐
│  Segmento   │   Score   │           Canal / Acción             │           Objetivo                   │  Costo Unitario │
├─────────────┼───────────┼──────────────────────────────────────┼──────────────────────────────────────┼─────────────────┤
│  🟢 ALTO    │  67 – 100 │ SMS automatizado, WhatsApp Bot,      │ Recuperación masiva, bajo costo.     │ S/ 0.05–0.30    │
│             │           │ IVR de autopago, email               │ El cliente ya tiene intención.       │ por contacto    │
├─────────────┼───────────┼──────────────────────────────────────┼──────────────────────────────────────┼─────────────────┤
│  🟡 MEDIO   │  34 – 66  │ Marcador Predictivo + Agente         │ Negociación activa, planes de pago,  │ S/ 1.50–4.00    │
│             │           │ Humano. Prioridad en el dialer.      │ acuerdos de refinanciamiento.        │ por contacto    │
│             │           │ Llamada outbound estructurada.       │ FOCO PRINCIPAL del call center.      │                 │
├─────────────┼───────────┼──────────────────────────────────────┼──────────────────────────────────────┼─────────────────┤
│  🔴 BAJO    │   1 – 33  │ Agente Especialista Senior,          │ Acuerdo de quita/condonación,        │ S/ 8.00–25.00   │
│             │           │ Derivación a Agencia Externa,        │ venta de cartera, inicio de proceso  │ por gestión     │
│             │           │ Notificación Pre-Legal               │ judicial. Última instancia.          │ especializada   │
└─────────────┴───────────┴──────────────────────────────────────┴──────────────────────────────────────┴─────────────────┘
```

### 3.1 Lógica de Re-Segmentación Dinámica

El score se recalcula **diariamente**. Un cliente puede ascender o descender de segmento según:
- Nueva promesa de pago registrada → Score sube
- Promesa rota → Score baja
- Días adicionales sin contacto → Score baja gradualmente
- Pago parcial registrado → Score sube significativamente

---

## 4. Arquitectura del Sistema (Componentes)

```
┌─────────────────────────────────────────────────────────────────┐
│                    CALL CENTER CUZCO                            │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Core        │    │  Tabla       │    │  Motor de        │  │
│  │  Bancario /  │───▶│  Maestra     │───▶│  Scoring         │  │
│  │  CRM         │    │  (PostgreSQL)│    │  (Python/sklearn)│  │
│  └──────────────┘    └──────────────┘    └────────┬─────────┘  │
│                                                   │            │
│  ┌──────────────────────────────────────────────  ▼  ────────┐ │
│  │              Dashboard Streamlit                          │ │
│  │   KPIs │ Distribución de Score │ Análisis │ Export Dialer │ │
│  └─────────────────────────────────────────────────────────┘  │
│                            │                                   │
│                            ▼                                   │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  Dialer      │    │  Canal       │    │  Reporte         │  │
│  │  Predictivo  │    │  Digital     │    │  Dirección       │  │
│  │  (Segmento   │    │  (SMS/WA)    │    │  (Excel/PDF)     │  │
│  │   MEDIO)     │    │  (Seg.ALTO)  │    │                  │  │
│  └──────────────┘    └──────────────┘    └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Roadmap de Implementación

| Fase | Duración | Hitos |
|------|----------|-------|
| **Fase 1 — MVP** | Semanas 1–3 | Dataset histórico limpio, modelo baseline, dashboard básico |
| **Fase 2 — Validación** | Semanas 4–6 | A/B test: cartera con score vs. asignación manual, medición de KPIs |
| **Fase 3 — Producción** | Semanas 7–10 | Integración con dialer, ejecución automática diaria, alertas |
| **Fase 4 — Optimización** | Mes 4+ | XGBoost, features de bureau crediticio, modelo de contactabilidad separado |

---

## 6. ROI Estimado

| Concepto | Situación Actual | Con Score Predictivo | Ahorro/Mejora |
|----------|-----------------|---------------------|---------------|
| Llamadas por recuperación | 100% de la cartera | 40% (MEDIO) | -60% en costo de marcado |
| Tasa de Contacto Efectivo | ~30% | ~48% (MEDIO priorizado) | +18 p.p. |
| Costo por sol recuperado | S/ 0.18 | S/ 0.11 | -39% |
| Cartera derivada a agencia | 100% BAJO manual | Sólo Score < 25 | Decisión basada en dato |

> Asumiendo cartera activa de 10,000 cuentas y costo promedio de operación de S/ 2.50/contacto.

---

## 7. Stack Tecnológico (100% Open Source, Servidor Local)

| Capa | Tecnología | Costo |
|------|-----------|-------|
| Lenguaje | Python 3.11+ | Gratuito |
| ML / Modelado | scikit-learn, XGBoost | Gratuito |
| Dashboard | Streamlit | Gratuito |
| Visualización | Plotly | Gratuito |
| Base de Datos | PostgreSQL / SQLite | Gratuito |
| Servidor | Hardware existente (≥8GB RAM) | S/ 0/mes en API |
| Orquestación | Cron job + scripts Python | Gratuito |

**Costo de APIs externas reemplazadas: S/ 0/mes** (vs. alternativas SaaS que cobran S/ 2,000–8,000/mes por scoring crediticio externo).
