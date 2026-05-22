"""
Pipeline de Preprocesamiento de Datos
=====================================
Transforma la tabla maestra cruda en features listos para el modelo.
"""

import pandas as pd
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OrdinalEncoder
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer


# ── Definición de columnas por tipo ──────────────────────────────────────────
NUMERIC_FEATURES = [
    "dpd",
    "saldo_capital",
    "saldo_total",
    "num_cuotas_vencidas",
    "rpc_rate",
    "total_llamadas",
    "contactos_efectivos",
    "promesas_cumplidas",
    "promesas_rotas",
    "dias_ultimo_contacto",
    "edad",
    "ingreso_mensual",
    "ratio_deuda_ingreso",
]

CATEGORICAL_FEATURES = [
    "bucket_mora",
    "producto",
    "ultimo_estado_marcado",
    "genero",
    "nivel_educativo",
    "estado_laboral",
    "zona_geografica",
]

TARGET = "pago_30d"
ID_COLS = ["cliente_id", "fecha_corte"]

# Columnas a descartar (alta cardinalidad o fugas de información)
DROP_COLS = ["saldo_interes", "monto_cuota", "promesas_totales"]


class FeatureEngineer(BaseEstimator, TransformerMixin):
    """
    Genera features derivados con valor predictivo alto.
    Se aplica ANTES del ColumnTransformer.
    """

    def fit(self, X: pd.DataFrame, y=None):
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        df = X.copy()

        # Rellenar columnas opcionales que pueden no venir en el Excel del usuario
        if "promesas_totales" not in df.columns:
            df["promesas_totales"] = (
                df.get("promesas_cumplidas", pd.Series(0, index=df.index)).fillna(0) +
                df.get("promesas_rotas",     pd.Series(0, index=df.index)).fillna(0)
            )
        if "promesas_cumplidas" not in df.columns:
            df["promesas_cumplidas"] = 0
        if "promesas_rotas" not in df.columns:
            df["promesas_rotas"] = 0
        if "total_llamadas" not in df.columns:
            df["total_llamadas"] = 0
        if "contactos_efectivos" not in df.columns:
            df["contactos_efectivos"] = 0
        if "dias_ultimo_contacto" not in df.columns:
            df["dias_ultimo_contacto"] = 30
        if "ultimo_estado_marcado" not in df.columns:
            df["ultimo_estado_marcado"] = "NO_CONTESTA"

        # Promesas: ratio cumplimiento (evita division por cero)
        df["ratio_cumplimiento"] = np.where(
            df["promesas_totales"] > 0,
            df["promesas_cumplidas"] / df["promesas_totales"],
            0.0,
        )

        # Intensidad de contacto normalizada
        df["contacto_por_llamada"] = np.where(
            df["total_llamadas"] > 0,
            df["contactos_efectivos"] / df["total_llamadas"],
            0.0,
        )

        # Bandera: ultima gestion fue promesa de pago
        df["flag_ultima_promesa"] = (df["ultimo_estado_marcado"] == "RPC_PROMESA").astype(int)

        # Bandera: cliente contactado en ultimos 7 dias
        df["flag_contacto_reciente"] = (df["dias_ultimo_contacto"] <= 7).astype(int)

        # Severidad de mora (normalizada 0-1 sobre rango 0-180 dias)
        df["severidad_mora"] = np.clip(df["dpd"] / 180, 0, 1)

        return df

    def get_feature_names_out(self, input_features=None):
        return input_features


def build_preprocessor() -> ColumnTransformer:
    """
    Construye el ColumnTransformer con pipelines para cada tipo de feature.
    """
    # Features numéricos derivados también se incluyen aquí
    extended_numeric = NUMERIC_FEATURES + [
        "ratio_cumplimiento",
        "contacto_por_llamada",
        "flag_ultima_promesa",
        "flag_contacto_reciente",
        "severidad_mora",
    ]

    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, extended_numeric),
            ("cat", categorical_pipeline, CATEGORICAL_FEATURES),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )

    return preprocessor


def prepare_data(df: pd.DataFrame):
    """
    Orquesta la preparación completa del dataset.

    Returns
    -------
    X_raw : pd.DataFrame   features sin escalar (para análisis)
    y     : pd.Series      target binario
    """
    df = df.drop(columns=[c for c in DROP_COLS if c in df.columns], errors="ignore")

    engineer = FeatureEngineer()
    df = engineer.transform(df)

    feature_cols = [c for c in df.columns if c not in ID_COLS + [TARGET]]
    X_raw = df[feature_cols]
    y = df[TARGET] if TARGET in df.columns else None

    return X_raw, y
