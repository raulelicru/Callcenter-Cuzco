# Reportes Diarios — Campana GRAL (Call Center Cuzco)

App de Streamlit para generar los tres reportes operativos diarios de la
campana GRAL a partir de los exports de VICIdial.

## Inicio Rapido

```bash
pip install -r requirements.txt
streamlit run dashboard/app.py
```

## Como funciona

1. Sube los **6 archivos del dia**:
   - 3 frescos de VICIdial: `AST_AMD_log_report`, `AST_VDADstats` y
     `EXPORT_CALL_REPORT` (Estados = ---ALL---, el insumo principal).
   - 3 tableros de salida del dia anterior (los acumulados que regresaste):
     `Tablero_Contactabilidad_GRAL`, `Control_Recontacto_GRAL`,
     `Tipificacion_Gestion_GRAL`.
2. Presiona **Generar los 3 reportes**.
3. Descarga los tres archivos Excel actualizados y revisa el resumen de
   tendencia y alertas (DROP, sobre-marcado, evasion).

## Reglas de negocio aplicadas

- **Promesa de pago** = status `04` + `21` (siempre se suman ambos).
- **Status `01`** = cuelga en saludo (rechazo temprano), no cuenta como gestion.
- **Segmentacion de humanos** = status `01, 02, 04, 09, 14, 18, 19, 21`, con
  hoja "Por Entidad" (evasion y cuelgue por estado).
- **Sabado** = media jornada (8:00-12:00); se compara sabado contra sabado.
- El dia nuevo se agrega al **acumulado** de cada reporte leyendo el historico
  de los tableros del dia anterior.
- **Monto comprometido** = campo reutilizado `postal_code` del export.
- **Estado del deudor** = campo reutilizado `first_name` del export.

## Estructura del Proyecto

```
Callcenter-Cuzco/
├── src/
│   └── vicidial_reports.py   # Reglas de negocio y construccion de los 3 reportes
├── dashboard/
│   └── app.py                # App de Streamlit (subir archivos, generar, descargar)
└── requirements.txt
```
