"""
Entrenamiento y Scoring del Modelo Predictivo de Cobranza
==========================================================
MVP con Random Forest + transformación de probabilidad a Score 1-100.
"""

import numpy as np
import pandas as pd
import joblib
import os
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import (
    roc_auc_score,
    classification_report,
    confusion_matrix,
    average_precision_score,
)

from preprocessing import FeatureEngineer, build_preprocessor, CATEGORICAL_FEATURES

MODELS_DIR = Path("models")
MODELS_DIR.mkdir(exist_ok=True)


# ── Configuración de modelos disponibles ─────────────────────────────────────
MODEL_REGISTRY = {
    "random_forest": RandomForestClassifier(
        n_estimators=300,
        max_depth=12,
        min_samples_leaf=20,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1,
    ),
    "logistic_regression": LogisticRegression(
        C=0.5,
        class_weight="balanced",
        solver="lbfgs",
        max_iter=1000,
        random_state=42,
    ),
}


def build_full_pipeline(model_name: str = "random_forest") -> Pipeline:
    """
    Ensambla el pipeline completo:
    FeatureEngineer → Preprocessor → Classifier
    """
    clf = MODEL_REGISTRY[model_name]
    preprocessor = build_preprocessor()

    pipeline = Pipeline([
        ("feature_engineering", FeatureEngineer()),
        ("preprocessor", preprocessor),
        ("classifier", clf),
    ])
    return pipeline


def train(
    df: pd.DataFrame,
    model_name: str = "random_forest",
    test_size: float = 0.20,
) -> dict:
    """
    Entrena el modelo y devuelve métricas de evaluación.

    Parameters
    ----------
    df         : DataFrame con la tabla maestra completa
    model_name : 'random_forest' | 'logistic_regression'
    test_size  : proporción del set de prueba

    Returns
    -------
    results : dict con pipeline entrenado y métricas
    """
    from preprocessing import TARGET, ID_COLS, prepare_data

    feature_cols = [c for c in df.columns if c not in ID_COLS + [TARGET, "saldo_interes", "monto_cuota"]]
    X = df[feature_cols]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, stratify=y, random_state=42
    )

    pipeline = build_full_pipeline(model_name)

    # ── Validación cruzada (evaluación robusta) ───────────────────────────────
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_auc = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring="roc_auc", n_jobs=-1)

    # ── Entrenamiento final ───────────────────────────────────────────────────
    pipeline.fit(X_train, y_train)

    # ── Evaluación en test ────────────────────────────────────────────────────
    y_prob = pipeline.predict_proba(X_test)[:, 1]
    y_pred = pipeline.predict(X_test)

    metrics = {
        "model_name": model_name,
        "cv_auc_mean": cv_auc.mean(),
        "cv_auc_std": cv_auc.std(),
        "test_auc_roc": roc_auc_score(y_test, y_prob),
        "test_avg_precision": average_precision_score(y_test, y_prob),
        "classification_report": classification_report(y_test, y_pred),
        "confusion_matrix": confusion_matrix(y_test, y_pred),
    }

    print("=" * 60)
    print(f"  MODELO: {model_name.upper()}")
    print("=" * 60)
    print(f"  CV AUC-ROC (5-fold): {metrics['cv_auc_mean']:.4f} ± {metrics['cv_auc_std']:.4f}")
    print(f"  Test AUC-ROC       : {metrics['test_auc_roc']:.4f}")
    print(f"  Test Avg Precision : {metrics['test_avg_precision']:.4f}")
    print("\n  Classification Report:")
    print(metrics["classification_report"])

    # ── Importancia de features (Random Forest) ───────────────────────────────
    if model_name == "random_forest":
        feature_importances = _extract_feature_importance(pipeline)
        metrics["feature_importances"] = feature_importances
        print("  Top 10 Features por Importancia:")
        print(feature_importances.head(10).to_string(index=False))

    # ── Persistencia del modelo ───────────────────────────────────────────────
    model_path = MODELS_DIR / f"pipeline_{model_name}.pkl"
    joblib.dump(pipeline, model_path)
    print(f"\n  Modelo guardado en: {model_path}")

    metrics["pipeline"] = pipeline
    return metrics


def _extract_feature_importance(pipeline: Pipeline) -> pd.DataFrame:
    """Extrae la importancia de features del Random Forest."""
    preprocessor = pipeline.named_steps["preprocessor"]
    classifier = pipeline.named_steps["classifier"]

    try:
        feature_names = preprocessor.get_feature_names_out()
    except Exception:
        feature_names = [f"feature_{i}" for i in range(len(classifier.feature_importances_))]

    importances = pd.DataFrame({
        "feature": feature_names,
        "importance": classifier.feature_importances_,
    }).sort_values("importance", ascending=False).reset_index(drop=True)

    return importances


def score_portfolio(
    df: pd.DataFrame,
    pipeline: Pipeline,
    score_min: int = 1,
    score_max: int = 100,
) -> pd.DataFrame:
    """
    Aplica el modelo a la cartera y calcula el Score Operativo.

    Transformación: probabilidad (0-1) → Score (1-100)
    Usa MinMax sobre los percentiles 1-99 para mayor robustez frente a outliers.

    Parameters
    ----------
    df         : DataFrame con la cartera a puntuar (sin necesidad de columna target)
    pipeline   : Pipeline entrenado
    score_min  : límite inferior del score operativo
    score_max  : límite superior del score operativo
    """
    from preprocessing import TARGET, ID_COLS

    id_data = df[["cliente_id"]].copy() if "cliente_id" in df.columns else pd.DataFrame()

    feature_cols = [
        c for c in df.columns
        if c not in ["cliente_id", "fecha_corte", TARGET, "saldo_interes", "monto_cuota"]
    ]
    X = df[feature_cols]

    # Probabilidad de pago
    prob_pago = pipeline.predict_proba(X)[:, 1]

    # Transformación robusta MinMax con percentiles
    p1, p99 = np.percentile(prob_pago, 1), np.percentile(prob_pago, 99)
    prob_clipped = np.clip(prob_pago, p1, p99)
    score_raw = (prob_clipped - p1) / (p99 - p1 + 1e-9)
    score_operativo = np.round(score_raw * (score_max - score_min) + score_min).astype(int)
    score_operativo = np.clip(score_operativo, score_min, score_max)

    # Segmentación operativa
    segmento = pd.cut(
        score_operativo,
        bins=[0, 33, 66, 100],
        labels=["BAJO", "MEDIO", "ALTO"],
        include_lowest=True,
    )

    estrategia_map = {
        "ALTO": "SMS / WhatsApp Automatizado / Bot",
        "MEDIO": "Agente Humano — Marcador Predictivo",
        "BAJO": "Especialista / Agencia Externa / Pre-Legal",
    }
    prioridad_map = {"ALTO": 3, "MEDIO": 2, "BAJO": 1}

    resultado = id_data.copy()
    resultado["prob_pago"] = np.round(prob_pago, 4)
    resultado["score_operativo"] = score_operativo
    resultado["segmento"] = segmento.astype(str)
    resultado["estrategia"] = resultado["segmento"].map(estrategia_map)
    resultado["prioridad_dialer"] = resultado["segmento"].map(prioridad_map)

    # Re-adjuntar columnas de negocio útiles para el export al Dialer
    for col in ["dpd", "saldo_total", "bucket_mora", "rpc_rate", "ultimo_estado_marcado"]:
        if col in df.columns:
            resultado[col] = df[col].values

    return resultado.sort_values("score_operativo", ascending=False).reset_index(drop=True)


def load_pipeline(model_name: str = "random_forest") -> Pipeline:
    """Carga un pipeline previamente entrenado desde disco."""
    model_path = MODELS_DIR / f"pipeline_{model_name}.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"Modelo no encontrado en {model_path}. Ejecuta train() primero.")
    return joblib.load(model_path)
