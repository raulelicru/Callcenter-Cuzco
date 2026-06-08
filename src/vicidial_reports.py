"""
Generador de reportes diarios de campana GRAL (VICIdial).

Construye los tres reportes operativos a partir de los exports de VICIdial
y acumula contra los tableros del dia anterior:
  1. Tablero de Contactabilidad
  2. Control de Recontacto
  3. Tipificacion de Gestion

Reglas de negocio (definidas por el usuario / supervisor de campana):
  - Promesa de pago      = status 04 + 21 (siempre se suman ambos)
  - Status 01            = cuelga en saludo -> rechazo temprano, NO es gestion
  - Segmentacion humanos = status en {01,02,04,09,14,18,19,21}, con hoja "Por Entidad"
  - Sabado               = media jornada (8:00-12:00); se compara sabado vs sabado
  - Acumulado            = dia nuevo + historico leido del tablero del dia anterior
  - Monto comprometido   = columna reutilizada `postal_code` del export
  - Estado del deudor    = columna reutilizada `first_name` del export
"""

from __future__ import annotations

import io
import re
import unicodedata
from datetime import date, datetime
from typing import Optional

import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# REGLAS / CONSTANTES DE NEGOCIO
# ─────────────────────────────────────────────────────────────────────────────

STATUS_PROMESA_PAGO   = ["04", "21"]
STATUS_CUELGA_SALUDO  = ["01"]
STATUS_HUMANOS        = ["01", "02", "04", "09", "14", "18", "19", "21"]

STATUS_LABELS = {
    "01": "Cuelga en saludo (rechazo temprano)",
    "02": "Contacto humano - gestion",
    "04": "Promesa de pago",
    "09": "Contacto humano - gestion",
    "14": "Contacto humano - gestion",
    "18": "Contacto humano - gestion",
    "19": "Contacto humano - gestion",
    "21": "Promesa de pago",
}

# Columnas del export reutilizadas para datos que VICIdial no expone de forma nativa
COL_MONTO_COMPROMETIDO = "postal_code"
COL_ESTADO_DEUDOR      = "first_name"

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE NORMALIZACION / LECTURA
# ─────────────────────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", s.strip().lower()).strip("_")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [_norm(c) for c in df.columns]
    return df


def _find_col(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    """Busca la primera columna cuyo nombre normalizado contenga alguno de los candidatos."""
    for cand in candidates:
        cand_n = _norm(cand)
        for col in df.columns:
            if cand_n == col:
                return col
        for col in df.columns:
            if cand_n in col:
                return col
    return None


def _read_any(uploaded, **kwargs) -> pd.DataFrame:
    """Lee CSV, TXT (delimitado) o Excel detectando el separador."""
    name = getattr(uploaded, "name", "archivo").lower()
    raw = uploaded.read() if hasattr(uploaded, "read") else uploaded
    if isinstance(raw, (bytes, bytearray)):
        text_bytes = raw
    else:
        text_bytes = raw.encode("utf-8")

    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(text_bytes), **kwargs)

    text = text_bytes.decode("utf-8", errors="replace")
    sample = text[:5000]
    sep = "|" if sample.count("|") > sample.count(",") and sample.count("|") > sample.count("\t") else (
        "\t" if sample.count("\t") > sample.count(",") else ","
    )
    return pd.read_csv(io.StringIO(text), sep=sep, engine="python", on_bad_lines="skip", **kwargs)


def read_export_call_report(uploaded) -> pd.DataFrame:
    """Lee el EXPORT_CALL_REPORT (Estados = ---ALL---), el insumo principal."""
    df = _read_any(uploaded)
    df = _normalize_columns(df)
    return df


def read_amd_log(uploaded) -> pd.DataFrame:
    df = _read_any(uploaded)
    return _normalize_columns(df)


def read_vdad_stats(uploaded) -> pd.DataFrame:
    df = _read_any(uploaded)
    return _normalize_columns(df)


def read_carrier_log(uploaded) -> pd.DataFrame:
    df = _read_any(uploaded)
    return _normalize_columns(df)


def read_tablero_anterior(uploaded) -> dict[str, pd.DataFrame]:
    """Lee un tablero de salida (Excel multi-hoja) del dia anterior."""
    if uploaded is None:
        return {}
    name = getattr(uploaded, "name", "tablero").lower()
    raw = uploaded.read() if hasattr(uploaded, "read") else uploaded
    buf = io.BytesIO(raw) if isinstance(raw, (bytes, bytearray)) else io.BytesIO(raw.encode("utf-8"))
    if not name.endswith((".xlsx", ".xls")):
        return {"Hoja1": _normalize_columns(_read_any(io.BytesIO(buf.getvalue())))}
    sheets = pd.read_excel(buf, sheet_name=None)
    return sheets


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACCION DE CAMPOS CLAVE DEL EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def _status_series(df: pd.DataFrame) -> pd.Series:
    col = _find_col(df, "status", "status_code", "call_status")
    if col is None:
        return pd.Series([""] * len(df), index=df.index)
    return df[col].astype(str).str.strip().str.upper().str.zfill(2)


def enrich_export(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega columnas derivadas: status, monto comprometido, estado del deudor, flags de regla."""
    df = df.copy()
    df["_status"] = _status_series(df)

    monto_col = COL_MONTO_COMPROMETIDO if COL_MONTO_COMPROMETIDO in df.columns else _find_col(df, "monto", "amount")
    estado_col = COL_ESTADO_DEUDOR if COL_ESTADO_DEUDOR in df.columns else _find_col(df, "estado_deudor", "estado")

    df["_monto_comprometido"] = pd.to_numeric(df.get(monto_col), errors="coerce").fillna(0.0) if monto_col else 0.0
    df["_estado_deudor"]      = df[estado_col].astype(str).fillna("") if estado_col else ""

    df["_es_promesa_pago"]    = df["_status"].isin(STATUS_PROMESA_PAGO)
    df["_es_cuelga_saludo"]   = df["_status"].isin(STATUS_CUELGA_SALUDO)
    df["_es_humano"]          = df["_status"].isin(STATUS_HUMANOS)
    df["_es_gestion"]         = df["_es_humano"] & ~df["_es_cuelga_saludo"]
    df["_status_label"]       = df["_status"].map(STATUS_LABELS).fillna("Otro / no gestion")

    entidad_col = _find_col(df, "entidad", "campaign", "campaign_id", "client")
    df["_entidad"] = df[entidad_col].astype(str) if entidad_col else "GRAL"

    agente_col = _find_col(df, "agente", "user", "fullname", "agent_user")
    df["_agente"] = df[agente_col].astype(str) if agente_col else ""

    return df


# ─────────────────────────────────────────────────────────────────────────────
# CALENDARIO / MEDIA JORNADA SABADO
# ─────────────────────────────────────────────────────────────────────────────

def es_sabado(fecha: date) -> bool:
    return fecha.weekday() == 5


def jornada_label(fecha: date) -> str:
    return "Media jornada (8:00-12:00, sabado)" if es_sabado(fecha) else "Jornada completa"


# ─────────────────────────────────────────────────────────────────────────────
# REPORTE 1: TABLERO DE CONTACTABILIDAD
# ─────────────────────────────────────────────────────────────────────────────

def build_tablero_contactabilidad(export_df: pd.DataFrame, fecha: date) -> dict[str, pd.DataFrame]:
    df = export_df
    total = len(df)
    n_humanos = int(df["_es_humano"].sum())
    n_gestion = int(df["_es_gestion"].sum())
    n_cuelga_saludo = int(df["_es_cuelga_saludo"].sum())
    n_promesas = int(df["_es_promesa_pago"].sum())
    monto_comprometido = float(df.loc[df["_es_promesa_pago"], "_monto_comprometido"].sum())

    resumen = pd.DataFrame([{
        "fecha": fecha.isoformat(),
        "jornada": jornada_label(fecha),
        "total_marcaciones": total,
        "contactos_humanos": n_humanos,
        "en_gestion": n_gestion,
        "cuelga_en_saludo": n_cuelga_saludo,
        "tasa_contactabilidad_%": round(n_humanos / total * 100, 2) if total else 0.0,
        "tasa_evasion_saludo_%": round(n_cuelga_saludo / total * 100, 2) if total else 0.0,
        "promesas_pago_(04+21)": n_promesas,
        "monto_comprometido_total": round(monto_comprometido, 2),
    }])

    por_status = (
        df.groupby(["_status", "_status_label"]).size()
        .reset_index(name="contactos")
        .rename(columns={"_status": "status", "_status_label": "descripcion"})
        .sort_values("contactos", ascending=False)
    )

    por_entidad = (
        df[df["_es_humano"]]
        .groupby("_entidad")
        .agg(
            contactos_humanos=("_es_humano", "sum"),
            cuelgan=("_es_cuelga_saludo", "sum"),
            promesas=("_es_promesa_pago", "sum"),
            monto_comprometido=("_monto_comprometido", lambda s: s[df.loc[s.index, "_es_promesa_pago"]].sum()),
        )
        .reset_index()
        .rename(columns={"_entidad": "entidad"})
    )
    if len(por_entidad):
        por_entidad["evasion_%"] = (por_entidad["cuelgan"] / por_entidad["contactos_humanos"] * 100).round(2)

    detalle_cols = [c for c in df.columns if not c.startswith("_")] + [
        "_status", "_status_label", "_monto_comprometido", "_estado_deudor", "_entidad", "_agente",
    ]
    detalle = df[detalle_cols].rename(columns={
        "_status": "status", "_status_label": "descripcion_status",
        "_monto_comprometido": "monto_comprometido", "_estado_deudor": "estado_deudor",
        "_entidad": "entidad", "_agente": "agente",
    })

    return {
        "Resumen del Dia": resumen,
        "Por Status": por_status,
        "Por Entidad": por_entidad,
        "Detalle": detalle,
    }


# ─────────────────────────────────────────────────────────────────────────────
# REPORTE 2: CONTROL DE RECONTACTO
# ─────────────────────────────────────────────────────────────────────────────

def build_control_recontacto(export_df: pd.DataFrame, fecha: date) -> dict[str, pd.DataFrame]:
    df = export_df
    lead_col = _find_col(df, "lead_id", "phone_number", "deudor_id", "documento", "dni")

    if lead_col is None:
        df = df.copy()
        df["_lead_id"] = df.index.astype(str)
        lead_col = "_lead_id"

    rec = (
        df.groupby(lead_col)
        .agg(
            intentos=(lead_col, "count"),
            contactos_humanos=("_es_humano", "sum"),
            promesas=("_es_promesa_pago", "sum"),
            ultimo_status=("_status", "last"),
            ultima_descripcion=("_status_label", "last"),
            estado_deudor=("_estado_deudor", "last"),
            monto_comprometido=("_monto_comprometido", lambda s: s[df.loc[s.index, "_es_promesa_pago"]].sum()),
        )
        .reset_index()
        .rename(columns={lead_col: "deudor"})
    )
    rec["fecha"] = fecha.isoformat()
    rec["requiere_recontacto"] = (rec["contactos_humanos"] == 0) | (
        (rec["promesas"] == 0) & (rec["ultimo_status"].isin(STATUS_HUMANOS)) & (~rec["ultimo_status"].isin(STATUS_PROMESA_PAGO))
    )

    pendientes = rec[rec["requiere_recontacto"]].sort_values("intentos", ascending=False)

    resumen = pd.DataFrame([{
        "fecha": fecha.isoformat(),
        "deudores_contactados": int(len(rec)),
        "con_promesa_de_pago": int((rec["promesas"] > 0).sum()),
        "pendientes_de_recontacto": int(pendientes.shape[0]),
        "tasa_recontacto_pendiente_%": round(len(pendientes) / len(rec) * 100, 2) if len(rec) else 0.0,
    }])

    return {
        "Resumen del Dia": resumen,
        "Control por Deudor": rec,
        "Pendientes de Recontacto": pendientes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# REPORTE 3: TIPIFICACION DE GESTION
# ─────────────────────────────────────────────────────────────────────────────

def build_tipificacion_gestion(export_df: pd.DataFrame, fecha: date) -> dict[str, pd.DataFrame]:
    df = export_df

    tipificacion = (
        df.groupby(["_status", "_status_label"])
        .agg(
            casos=("_status", "count"),
            monto_comprometido=("_monto_comprometido", lambda s: s[df.loc[s.index, "_es_promesa_pago"]].sum()),
        )
        .reset_index()
        .rename(columns={"_status": "status", "_status_label": "tipificacion"})
        .sort_values("casos", ascending=False)
    )
    total_gestion = int(df["_es_gestion"].sum())
    tipificacion["%_del_total_gestion"] = (
        (tipificacion["casos"] / total_gestion * 100).round(2) if total_gestion else 0.0
    )

    promesas = df[df["_es_promesa_pago"]].copy()
    promesas_cols = [c for c in [
        _find_col(df, "lead_id", "phone_number"), "_status", "_status_label",
        "_estado_deudor", "_monto_comprometido", "_entidad", "_agente",
    ] if c is not None]
    promesas_detalle = promesas[promesas_cols].rename(columns={
        "_status": "status", "_status_label": "tipificacion",
        "_estado_deudor": "estado_deudor", "_monto_comprometido": "monto_comprometido",
        "_entidad": "entidad", "_agente": "agente",
    })

    por_estado_deudor = (
        df[df["_es_humano"]]
        .groupby("_estado_deudor")
        .agg(
            casos=("_estado_deudor", "count"),
            promesas=("_es_promesa_pago", "sum"),
            monto_comprometido=("_monto_comprometido", lambda s: s[df.loc[s.index, "_es_promesa_pago"]].sum()),
        )
        .reset_index()
        .rename(columns={"_estado_deudor": "estado_del_deudor"})
        .sort_values("casos", ascending=False)
    )

    resumen = pd.DataFrame([{
        "fecha": fecha.isoformat(),
        "total_gestionados": total_gestion,
        "promesas_pago_(04+21)": int(df["_es_promesa_pago"].sum()),
        "monto_comprometido_total": round(float(promesas["_monto_comprometido"].sum()), 2),
        "rescates_(reactivacion_tras_cuelga)": int(df["_es_cuelga_saludo"].sum() & (df["_es_humano"]).any()),
    }])

    return {
        "Resumen del Dia": resumen,
        "Tipificacion": tipificacion,
        "Promesas de Pago": promesas_detalle,
        "Por Estado del Deudor": por_estado_deudor,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ACUMULADO: combinar el dia nuevo con el historico del tablero anterior
# ─────────────────────────────────────────────────────────────────────────────

def acumular(reporte_nuevo: dict[str, pd.DataFrame], tablero_anterior: dict[str, pd.DataFrame],
             hoja_resumen: str = "Resumen del Dia", hoja_acumulado: str = "Acumulado") -> dict[str, pd.DataFrame]:
    """Agrega el resumen del dia al historico (hoja 'Acumulado') leido del tablero de ayer."""
    out = dict(reporte_nuevo)
    hist = tablero_anterior.get(hoja_acumulado)
    if hist is None:
        hist = tablero_anterior.get(hoja_resumen)

    nuevo_resumen = reporte_nuevo.get(hoja_resumen)
    if nuevo_resumen is None:
        return out

    if hist is not None and len(hist):
        hist = _normalize_columns(hist)
        nuevo_norm = nuevo_resumen.copy()
        nuevo_norm.columns = [_norm(c) for c in nuevo_norm.columns]
        common = [c for c in nuevo_norm.columns if c in hist.columns]
        acumulado = pd.concat([hist[common], nuevo_norm[common]], ignore_index=True)
        if "fecha" in acumulado.columns:
            acumulado = acumulado.drop_duplicates(subset=["fecha"], keep="last").sort_values("fecha")
    else:
        acumulado = nuevo_resumen.copy()

    out[hoja_acumulado] = acumulado.reset_index(drop=True)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTAR A EXCEL
# ─────────────────────────────────────────────────────────────────────────────

def export_report_excel(sheets: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            safe_name = str(name)[:31]
            (frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)).to_excel(
                writer, index=False, sheet_name=safe_name
            )
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# RESUMEN EJECUTIVO + ALERTAS
# ─────────────────────────────────────────────────────────────────────────────

def generar_resumen_alertas(export_df: pd.DataFrame, fecha: date,
                            tableros_ayer: dict[str, dict[str, pd.DataFrame]]) -> str:
    df = export_df
    total = len(df)
    n_humanos = int(df["_es_humano"].sum())
    n_cuelga = int(df["_es_cuelga_saludo"].sum())
    n_promesas = int(df["_es_promesa_pago"].sum())
    monto = float(df.loc[df["_es_promesa_pago"], "_monto_comprometido"].sum())

    tasa_contacto = (n_humanos / total * 100) if total else 0.0
    tasa_evasion  = (n_cuelga / total * 100) if total else 0.0

    lineas = []
    lineas.append(f"## Resumen del {fecha.strftime('%d/%m/%Y')} — {jornada_label(fecha)}")
    lineas.append(f"- Marcaciones totales: **{total:,}**")
    lineas.append(f"- Contactos humanos: **{n_humanos:,}** (tasa de contactabilidad {tasa_contacto:.1f}%)")
    lineas.append(f"- Cuelgan en saludo (status 01): **{n_cuelga:,}** (evasion temprana {tasa_evasion:.1f}%)")
    lineas.append(f"- Promesas de pago (status 04+21): **{n_promesas:,}**, monto comprometido **S/ {monto:,.2f}**")

    # Comparacion contra el dia anterior (acumulado leido del tablero de contactabilidad)
    contac_ayer = tableros_ayer.get("contactabilidad", {})
    hist = contac_ayer.get("Acumulado") or contac_ayer.get("Resumen del Dia")
    alertas = []
    if hist is not None and len(hist):
        hist_n = _normalize_columns(hist)
        if es_sabado(fecha) and "jornada" in hist_n.columns:
            hist_n = hist_n[hist_n["jornada"].astype(str).str.contains("sabado", case=False, na=False)]
            lineas.append("- Comparacion realizada **sabado vs sabado** (media jornada 8:00-12:00).")
        if len(hist_n):
            prev = hist_n.iloc[-1]
            if "tasa_contactabilidad_%" in prev and prev["tasa_contactabilidad_%"]:
                delta_contacto = tasa_contacto - float(prev["tasa_contactabilidad_%"])
                lineas.append(f"- Variacion de contactabilidad vs. periodo de referencia anterior: {delta_contacto:+.1f} pp")
                if delta_contacto <= -10:
                    alertas.append(f"**DROP de contactabilidad**: cae {abs(delta_contacto):.1f} puntos porcentuales respecto al periodo de referencia.")
            if "total_marcaciones" in prev and prev["total_marcaciones"]:
                prev_total = float(prev["total_marcaciones"])
                if prev_total and total > prev_total * 1.5:
                    alertas.append(f"**Posible sobre-marcado**: las marcaciones totales ({total:,}) crecieron mas de 50% respecto al periodo de referencia ({prev_total:,.0f}).")
            if "tasa_evasion_saludo_%" in prev and prev["tasa_evasion_saludo_%"]:
                delta_evasion = tasa_evasion - float(prev["tasa_evasion_saludo_%"])
                if delta_evasion >= 5:
                    alertas.append(f"**Aumento de evasion**: el cuelgue en saludo (status 01) sube {delta_evasion:+.1f} pp respecto al periodo de referencia.")

    if tasa_evasion >= 30:
        alertas.append(f"**Evasion alta**: {tasa_evasion:.1f}% de las marcaciones cuelgan en saludo (status 01); revisar guion / horario de marcacion.")
    if total and (n_humanos / total) < 0.10:
        alertas.append(f"**Contactabilidad baja**: solo {tasa_contacto:.1f}% de las marcaciones llegan a un humano.")

    lineas.append("")
    lineas.append("### Alertas")
    if alertas:
        for a in alertas:
            lineas.append(f"- {a}")
    else:
        lineas.append("- Sin alertas relevantes; los indicadores se mantienen dentro de rangos esperados.")

    return "\n".join(lineas)


# ─────────────────────────────────────────────────────────────────────────────
# PIPELINE COMPLETO
# ─────────────────────────────────────────────────────────────────────────────

def generar_reportes_diarios(
    export_call_report,
    fecha: date,
    amd_log=None,
    vdad_stats=None,
    tablero_contactabilidad_ayer=None,
    control_recontacto_ayer=None,
    tipificacion_gestion_ayer=None,
    _tableros_precargados: Optional[dict] = None,
):
    """Orquesta la lectura, construccion, acumulado y resumen de los 3 reportes.

    _tableros_precargados: dict opcional con claves 'contactabilidad', 'recontacto',
    'tipificacion', cada valor ya leido como dict[str, DataFrame] (para cuando la app
    carga el historial desde disco en lugar de recibir un archivo subido).
    """
    export_df = enrich_export(read_export_call_report(export_call_report))

    pre = _tableros_precargados or {}

    ayer_contac = pre.get("contactabilidad") if "contactabilidad" in pre else read_tablero_anterior(tablero_contactabilidad_ayer)
    ayer_recont = pre.get("recontacto")      if "recontacto"      in pre else read_tablero_anterior(control_recontacto_ayer)
    ayer_tipif  = pre.get("tipificacion")    if "tipificacion"     in pre else read_tablero_anterior(tipificacion_gestion_ayer)

    ayer_contac = ayer_contac or {}
    ayer_recont = ayer_recont or {}
    ayer_tipif  = ayer_tipif  or {}

    contactabilidad = acumular(build_tablero_contactabilidad(export_df, fecha), ayer_contac)
    recontacto      = acumular(build_control_recontacto(export_df, fecha), ayer_recont)
    tipificacion    = acumular(build_tipificacion_gestion(export_df, fecha), ayer_tipif)

    resumen_md = generar_resumen_alertas(export_df, fecha, {
        "contactabilidad": ayer_contac, "recontacto": ayer_recont, "tipificacion": ayer_tipif,
    })

    return {
        "contactabilidad": contactabilidad,
        "recontacto": recontacto,
        "tipificacion": tipificacion,
        "resumen_md": resumen_md,
        "export_df": export_df,
    }
