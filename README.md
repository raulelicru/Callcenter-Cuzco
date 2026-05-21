# Sistema Predictivo de Cobranza — Call Center Cuzco

Score de Propensión al Pago basado en Machine Learning. 100% local, 0 dependencias de API externas.

## Inicio Rápido

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Entrenar modelo y generar datos de prueba
python src/main.py

# 3. Iniciar el dashboard
streamlit run dashboard/app.py
```

## Estructura del Proyecto

```
Callcenter-Cuzco/
├── src/
│   ├── data_generator.py   # Genera dataset sintético para pruebas
│   ├── preprocessing.py    # Feature engineering y preprocesamiento
│   ├── model.py            # Entrenamiento, scoring y evaluación
│   └── main.py             # Pipeline de entrenamiento completo
├── dashboard/
│   └── app.py              # Dashboard Streamlit
├── data/                   # Datos generados (gitignored)
├── models/                 # Modelos entrenados (gitignored)
├── docs/
│   └── PROPUESTA_TECNICA.md
└── requirements.txt
```

## Score Operativo

| Segmento | Score | Acción |
|----------|-------|--------|
| 🟢 ALTO | 67–100 | SMS / WhatsApp Bot / IVR |
| 🟡 MEDIO | 34–66 | Agente Humano + Marcador Predictivo |
| 🔴 BAJO | 1–33 | Especialista / Pre-Legal |

Ver `docs/PROPUESTA_TECNICA.md` para la arquitectura completa.
