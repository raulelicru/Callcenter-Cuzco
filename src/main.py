"""
Pipeline de Entrenamiento del Modelo
=====================================
Ejecutar: python src/main.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from data_generator import generate_collection_dataset
from model import train, score_portfolio
from database import init_db
from setup_db import setup
from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)


def run_training_pipeline():
    print("\n" + "=" * 60)
    print("   SISTEMA PREDICTIVO DE COBRANZA — SETUP COMPLETO")
    print("=" * 60)

    # 1. Inicializar base de datos y usuarios
    print("\n[1/5] Inicializando base de datos y usuarios...")
    setup()

    # 2. Generar datos sintéticos
    print("\n[2/5] Generando dataset sintético de entrenamiento...")
    df = generate_collection_dataset(n_samples=5000, seed=42)
    df.to_csv(DATA_DIR / "cartera_sintetica.csv", index=False)
    print(f"      → {len(df):,} registros | Tasa de pago: {df['pago_30d'].mean():.1%}")

    # 3. Entrenar modelo
    print("\n[3/5] Entrenando modelo Random Forest...")
    results = train(df, model_name="random_forest")

    # 4. Score de cartera de prueba
    print("\n[4/5] Calculando scores para cartera sintética...")
    pipeline = results["pipeline"]
    scores = score_portfolio(df, pipeline)
    scores.to_csv(DATA_DIR / "cartera_scored.csv", index=False)

    # 5. Resumen
    print("\n[5/5] Distribución por Segmento Operativo:")
    print("-" * 60)
    resumen = (
        scores.groupby("segmento")
        .agg(
            clientes=("cliente_id", "count"),
            score_promedio=("score_operativo", "mean"),
            prob_pago_promedio=("prob_pago", "mean"),
        ).round(2)
    )
    resumen["pct_cartera"] = (resumen["clientes"] / len(scores) * 100).round(1)
    print(resumen.to_string())
    print("-" * 60)

    print("\n" + "=" * 60)
    print("  SISTEMA LISTO. Ejecuta el dashboard con:")
    print("  streamlit run dashboard/app.py")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    run_training_pipeline()
