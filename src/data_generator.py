"""
Generador de Dataset Sintético de Cobranza
==========================================
Crea datos realistas para pruebas del modelo de score predictivo.
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate_collection_dataset(n_samples: int = 5000, seed: int = 42) -> pd.DataFrame:
    """
    Genera un dataset sintético que simula la cartera de un call center de cobranza.

    Variables diseñadas con correlaciones realistas:
    - DPD alto → mayor probabilidad de no pago
    - RPC alto → mayor probabilidad de pago
    - Promesas cumplidas previas → mayor probabilidad de pago
    """
    np.random.seed(seed)
    n = n_samples

    # ── 1. IDENTIFICADORES ───────────────────────────────────────────────────
    ids = [f"CLI-{str(i).zfill(6)}" for i in range(1, n + 1)]

    # ── 2. DATOS DE LA CUENTA / DEUDA ────────────────────────────────────────
    dpd = np.random.choice(
        [15, 30, 45, 60, 90, 120, 150, 180],
        size=n,
        p=[0.18, 0.20, 0.17, 0.15, 0.12, 0.09, 0.05, 0.04],
    )

    bucket_map = {15: "B1", 30: "B1", 45: "B2", 60: "B2", 90: "B3", 120: "B3", 150: "B4", 180: "B4"}
    bucket_mora = [bucket_map[d] for d in dpd]

    saldo_capital = np.round(
        np.random.lognormal(mean=8.5, sigma=1.2, size=n).clip(500, 150_000), 2
    )
    saldo_interes = np.round(saldo_capital * np.random.uniform(0.05, 0.40, size=n), 2)
    saldo_total = saldo_capital + saldo_interes

    num_cuotas_vencidas = np.maximum(1, (dpd // 30).astype(int))
    monto_cuota = np.round(saldo_capital / np.random.randint(6, 48, size=n), 2)

    producto = np.random.choice(
        ["Crédito Personal", "Tarjeta de Crédito", "Préstamo Vehicular", "Microcrédito"],
        size=n,
        p=[0.35, 0.30, 0.15, 0.20],
    )

    # ── 3. HISTORIAL DE GESTIÓN DEL CALL CENTER ───────────────────────────────
    # RPC: Right Party Contact — más alto en cuentas recientes
    rpc_base = np.where(dpd <= 30, 0.55, np.where(dpd <= 90, 0.35, 0.18))
    rpc_rate = np.clip(rpc_base + np.random.normal(0, 0.08, size=n), 0.0, 1.0)

    total_llamadas = np.random.randint(1, 25, size=n)
    contactos_efectivos = np.round(rpc_rate * total_llamadas).astype(int)

    promesas_totales = np.random.randint(0, 5, size=n)
    promesas_cumplidas = np.minimum(
        promesas_totales,
        np.random.binomial(promesas_totales, p=np.where(dpd <= 60, 0.6, 0.25)),
    )
    promesas_rotas = promesas_totales - promesas_cumplidas

    dias_ultimo_contacto = np.random.randint(0, 45, size=n)

    ultimo_estado_marcado = np.random.choice(
        ["RPC_PROMESA", "RPC_RECHAZO", "NO_CONTESTA", "BUZÓN", "NÚMERO_INVÁLIDO", "COLGÓ"],
        size=n,
        p=[0.18, 0.22, 0.30, 0.12, 0.08, 0.10],
    )

    # ── 4. DATOS SOCIODEMOGRÁFICOS ────────────────────────────────────────────
    edad = np.random.randint(22, 72, size=n)
    genero = np.random.choice(["M", "F"], size=n, p=[0.55, 0.45])

    nivel_educativo = np.random.choice(
        ["Primaria", "Secundaria", "Técnico", "Universidad", "Posgrado"],
        size=n,
        p=[0.08, 0.25, 0.30, 0.30, 0.07],
    )

    estado_laboral = np.random.choice(
        ["Dependiente", "Independiente", "Desempleado", "Jubilado"],
        size=n,
        p=[0.50, 0.25, 0.15, 0.10],
    )

    ingreso_mensual = np.round(
        np.random.lognormal(mean=7.8, sigma=0.6, size=n).clip(800, 25_000), 2
    )
    ratio_deuda_ingreso = np.round(saldo_total / (ingreso_mensual * 12), 4)

    zona_geografica = np.random.choice(
        ["Lima", "Arequipa", "Cusco", "Trujillo", "Piura", "Iquitos"],
        size=n,
        p=[0.40, 0.15, 0.12, 0.13, 0.10, 0.10],
    )

    # ── 5. TARGET: PAGÓ EN LOS PRÓXIMOS 30 DÍAS ───────────────────────────────
    # Probabilidad base influenciada por variables clave
    logit = (
        2.5
        - 0.03 * dpd
        + 3.0 * rpc_rate
        + 0.4 * promesas_cumplidas
        - 0.5 * promesas_rotas
        - 0.02 * dias_ultimo_contacto
        + np.where(ultimo_estado_marcado == "RPC_PROMESA", 1.2, 0)
        + np.where(ultimo_estado_marcado == "RPC_RECHAZO", -0.8, 0)
        + np.where(estado_laboral == "Dependiente", 0.5, 0)
        + np.where(estado_laboral == "Desempleado", -1.0, 0)
        - 1.5 * ratio_deuda_ingreso
        + np.random.normal(0, 0.5, size=n)
    )
    prob_pago = 1 / (1 + np.exp(-logit))
    pago_realizado = np.random.binomial(1, prob_pago)

    # ── 6. ENSAMBLADO DEL DATAFRAME ───────────────────────────────────────────
    df = pd.DataFrame({
        # Identificadores
        "cliente_id": ids,
        "fecha_corte": datetime.today().strftime("%Y-%m-%d"),
        # Cuenta / Deuda
        "dpd": dpd,
        "bucket_mora": bucket_mora,
        "saldo_capital": saldo_capital,
        "saldo_interes": saldo_interes,
        "saldo_total": saldo_total,
        "num_cuotas_vencidas": num_cuotas_vencidas,
        "monto_cuota": monto_cuota,
        "producto": producto,
        # Gestión Call Center
        "rpc_rate": np.round(rpc_rate, 4),
        "total_llamadas": total_llamadas,
        "contactos_efectivos": contactos_efectivos,
        "promesas_totales": promesas_totales,
        "promesas_cumplidas": promesas_cumplidas,
        "promesas_rotas": promesas_rotas,
        "dias_ultimo_contacto": dias_ultimo_contacto,
        "ultimo_estado_marcado": ultimo_estado_marcado,
        # Sociodemográficos
        "edad": edad,
        "genero": genero,
        "nivel_educativo": nivel_educativo,
        "estado_laboral": estado_laboral,
        "ingreso_mensual": ingreso_mensual,
        "ratio_deuda_ingreso": ratio_deuda_ingreso,
        "zona_geografica": zona_geografica,
        # Target
        "pago_30d": pago_realizado,
    })

    return df


if __name__ == "__main__":
    df = generate_collection_dataset(n_samples=5000)
    df.to_csv("data/cartera_sintetica.csv", index=False)
    print(f"Dataset generado: {df.shape[0]} registros | Tasa de pago: {df['pago_30d'].mean():.1%}")
    print(df.head(3).to_string())
