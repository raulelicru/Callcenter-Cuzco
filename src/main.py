"""
Punto de Entrada Principal — Pipeline de Entrenamiento y Scoring
================================================================
Ejecutar: python src/main.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from data_generator import generate_collection_dataset
from model import train, score_portfolio
from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def run_training_pipeline():
    print("\n" + "=" * 60)
    print("   SISTEMA PREDICTIVO DE COBRANZA — ENTRENAMIENTO MVP")
    print("=" * 60)

    # 1. Generar / cargar datos
    print("\n[1/4] Generando dataset sintético...")
    df = generate_collection_dataset(n_samples=5000, seed=42)
    df.to_csv(DATA_DIR / "cartera_sintetica.csv", index=False)
    print(f"      → {len(df):,} registros | Tasa de pago: {df['pago_30d'].mean():.1%}")

    # 2. Entrenar Random Forest
    print("\n[2/4] Entrenando modelo Random Forest...")
    results = train(df, model_name="random_forest")

    # 3. Scoring de la cartera completa
    print("\n[3/4] Calculando scores para toda la cartera...")
    pipeline = results["pipeline"]
    scores = score_portfolio(df, pipeline)
    scores.to_csv(DATA_DIR / "cartera_scored.csv", index=False)

    # 4. Resumen por segmento
    print("\n[4/4] Distribución por Segmento Operativo:")
    print("-" * 55)
    resumen = (
        scores.groupby("segmento")
        .agg(
            clientes=("cliente_id", "count"),
            score_promedio=("score_operativo", "mean"),
            prob_pago_promedio=("prob_pago", "mean"),
            saldo_total=("saldo_total", "sum"),
        )
        .round(2)
    )
    resumen["pct_cartera"] = (resumen["clientes"] / len(scores) * 100).round(1)
    print(resumen.to_string())
    print("-" * 55)
    print(f"\nArchivo de scoring exportado: data/cartera_scored.csv")
    print("\n  Inicia el dashboard con: streamlit run dashboard/app.py\n")


if __name__ == "__main__":
    run_training_pipeline()
