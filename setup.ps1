# ============================================================
#  SETUP COMPLETO — Sistema Predictivo de Cobranza
#  Ejecutar: .\setup.ps1
# ============================================================

$PROJECT = "$env:USERPROFILE\Documents\CallcenterCuzco"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   INSTALANDO Sistema Predictivo de Cobranza" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Crear carpetas ────────────────────────────────────────────
Write-Host "[1/6] Creando estructura de carpetas..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path "$PROJECT\src"      | Out-Null
New-Item -ItemType Directory -Force -Path "$PROJECT\dashboard" | Out-Null
New-Item -ItemType Directory -Force -Path "$PROJECT\data"     | Out-Null
New-Item -ItemType Directory -Force -Path "$PROJECT\models"   | Out-Null
New-Item -ItemType Directory -Force -Path "$PROJECT\docs"     | Out-Null
Write-Host "      OK: $PROJECT" -ForegroundColor Green

# ── requirements.txt ─────────────────────────────────────────
Write-Host "[2/6] Creando archivos del sistema..." -ForegroundColor Yellow

@"
pandas>=2.0.0
numpy>=1.24.0
scikit-learn>=1.3.0
xgboost>=2.0.0
streamlit>=1.28.0
plotly>=5.17.0
joblib>=1.3.0
openpyxl>=3.1.0
xlrd>=2.0.1
"@ | Set-Content "$PROJECT\requirements.txt" -Encoding UTF8

# ── src/data_generator.py ────────────────────────────────────
@'
import numpy as np
import pandas as pd
from datetime import datetime

def generate_collection_dataset(n_samples=5000, seed=42):
    np.random.seed(seed)
    n = n_samples
    ids = [f"CLI-{str(i).zfill(6)}" for i in range(1, n+1)]
    dpd = np.random.choice([15,30,45,60,90,120,150,180], size=n, p=[0.18,0.20,0.17,0.15,0.12,0.09,0.05,0.04])
    bucket_map = {15:"B1",30:"B1",45:"B2",60:"B2",90:"B3",120:"B3",150:"B4",180:"B4"}
    bucket_mora = [bucket_map[d] for d in dpd]
    saldo_capital = np.round(np.random.lognormal(mean=8.5,sigma=1.2,size=n).clip(500,150000),2)
    saldo_interes = np.round(saldo_capital*np.random.uniform(0.05,0.40,size=n),2)
    saldo_total = saldo_capital + saldo_interes
    num_cuotas_vencidas = np.maximum(1,(dpd//30).astype(int))
    monto_cuota = np.round(saldo_capital/np.random.randint(6,48,size=n),2)
    producto = np.random.choice(["Credito Personal","Tarjeta de Credito","Prestamo Vehicular","Microcredito"],size=n,p=[0.35,0.30,0.15,0.20])
    rpc_base = np.where(dpd<=30,0.55,np.where(dpd<=90,0.35,0.18))
    rpc_rate = np.clip(rpc_base+np.random.normal(0,0.08,size=n),0.0,1.0)
    total_llamadas = np.random.randint(1,25,size=n)
    contactos_efectivos = np.round(rpc_rate*total_llamadas).astype(int)
    promesas_totales = np.random.randint(0,5,size=n)
    promesas_cumplidas = np.minimum(promesas_totales,np.random.binomial(promesas_totales,p=np.where(dpd<=60,0.6,0.25)))
    promesas_rotas = promesas_totales - promesas_cumplidas
    dias_ultimo_contacto = np.random.randint(0,45,size=n)
    ultimo_estado_marcado = np.random.choice(["RPC_PROMESA","RPC_RECHAZO","NO_CONTESTA","BUZON","NUMERO_INVALIDO","COLGO"],size=n,p=[0.18,0.22,0.30,0.12,0.08,0.10])
    edad = np.random.randint(22,72,size=n)
    genero = np.random.choice(["M","F"],size=n,p=[0.55,0.45])
    nivel_educativo = np.random.choice(["Primaria","Secundaria","Tecnico","Universidad","Posgrado"],size=n,p=[0.08,0.25,0.30,0.30,0.07])
    estado_laboral = np.random.choice(["Dependiente","Independiente","Desempleado","Jubilado"],size=n,p=[0.50,0.25,0.15,0.10])
    ingreso_mensual = np.round(np.random.lognormal(mean=7.8,sigma=0.6,size=n).clip(800,25000),2)
    ratio_deuda_ingreso = np.round(saldo_total/(ingreso_mensual*12),4)
    zona_geografica = np.random.choice(["Lima","Arequipa","Cusco","Trujillo","Piura","Iquitos"],size=n,p=[0.40,0.15,0.12,0.13,0.10,0.10])
    logit = (2.5 - 0.03*dpd + 3.0*rpc_rate + 0.4*promesas_cumplidas - 0.5*promesas_rotas
             - 0.02*dias_ultimo_contacto + np.where(ultimo_estado_marcado=="RPC_PROMESA",1.2,0)
             + np.where(ultimo_estado_marcado=="RPC_RECHAZO",-0.8,0)
             + np.where(estado_laboral=="Dependiente",0.5,0)
             + np.where(estado_laboral=="Desempleado",-1.0,0)
             - 1.5*ratio_deuda_ingreso + np.random.normal(0,0.5,size=n))
    prob_pago = 1/(1+np.exp(-logit))
    pago_realizado = np.random.binomial(1,prob_pago)
    return pd.DataFrame({
        "cliente_id":ids,"fecha_corte":datetime.today().strftime("%Y-%m-%d"),
        "dpd":dpd,"bucket_mora":bucket_mora,"saldo_capital":saldo_capital,
        "saldo_interes":saldo_interes,"saldo_total":saldo_total,
        "num_cuotas_vencidas":num_cuotas_vencidas,"monto_cuota":monto_cuota,"producto":producto,
        "rpc_rate":np.round(rpc_rate,4),"total_llamadas":total_llamadas,
        "contactos_efectivos":contactos_efectivos,"promesas_totales":promesas_totales,
        "promesas_cumplidas":promesas_cumplidas,"promesas_rotas":promesas_rotas,
        "dias_ultimo_contacto":dias_ultimo_contacto,"ultimo_estado_marcado":ultimo_estado_marcado,
        "edad":edad,"genero":genero,"nivel_educativo":nivel_educativo,
        "estado_laboral":estado_laboral,"ingreso_mensual":ingreso_mensual,
        "ratio_deuda_ingreso":ratio_deuda_ingreso,"zona_geografica":zona_geografica,
        "pago_30d":pago_realizado,
    })

if __name__ == "__main__":
    df = generate_collection_dataset()
    df.to_csv("data/cartera_sintetica.csv", index=False)
    print(f"Dataset: {len(df)} registros | Tasa pago: {df['pago_30d'].mean():.1%}")
'@ | Set-Content "$PROJECT\src\data_generator.py" -Encoding UTF8

# ── src/preprocessing.py ─────────────────────────────────────
@'
import pandas as pd
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler, OrdinalEncoder
from sklearn.impute import SimpleImputer
from sklearn.compose import ColumnTransformer

NUMERIC_FEATURES = ["dpd","saldo_capital","saldo_total","num_cuotas_vencidas","rpc_rate",
    "total_llamadas","contactos_efectivos","promesas_cumplidas","promesas_rotas",
    "dias_ultimo_contacto","edad","ingreso_mensual","ratio_deuda_ingreso",
    "ratio_cumplimiento","contacto_por_llamada","flag_ultima_promesa",
    "flag_contacto_reciente","severidad_mora"]
CATEGORICAL_FEATURES = ["bucket_mora","producto","ultimo_estado_marcado","genero",
    "nivel_educativo","estado_laboral","zona_geografica"]
TARGET = "pago_30d"
ID_COLS = ["cliente_id","fecha_corte"]

class FeatureEngineer(BaseEstimator, TransformerMixin):
    def fit(self, X, y=None): return self
    def transform(self, X):
        df = X.copy()
        df["ratio_cumplimiento"] = np.where(df.get("promesas_totales", pd.Series([0]*len(df))) > 0,
            df.get("promesas_cumplidas", 0) / df.get("promesas_totales", pd.Series([1]*len(df))), 0.0)
        df["contacto_por_llamada"] = np.where(df.get("total_llamadas", pd.Series([0]*len(df))) > 0,
            df.get("contactos_efectivos", 0) / df.get("total_llamadas", pd.Series([1]*len(df))), 0.0)
        df["flag_ultima_promesa"] = (df.get("ultimo_estado_marcado", "") == "RPC_PROMESA").astype(int) if "ultimo_estado_marcado" in df.columns else 0
        df["flag_contacto_reciente"] = (df.get("dias_ultimo_contacto", 99) <= 7).astype(int) if "dias_ultimo_contacto" in df.columns else 0
        df["severidad_mora"] = np.clip(df.get("dpd", 0) / 180, 0, 1) if "dpd" in df.columns else 0
        return df

def build_preprocessor():
    numeric_pipeline = Pipeline([("imputer",SimpleImputer(strategy="median")),("scaler",StandardScaler())])
    categorical_pipeline = Pipeline([("imputer",SimpleImputer(strategy="most_frequent")),
        ("encoder",OrdinalEncoder(handle_unknown="use_encoded_value",unknown_value=-1))])
    return ColumnTransformer(
        transformers=[("num",numeric_pipeline,NUMERIC_FEATURES),("cat",categorical_pipeline,CATEGORICAL_FEATURES)],
        remainder="drop", verbose_feature_names_out=False)
'@ | Set-Content "$PROJECT\src\preprocessing.py" -Encoding UTF8

# ── src/model.py ─────────────────────────────────────────────
@'
import numpy as np
import pandas as pd
import joblib
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.metrics import roc_auc_score, classification_report, average_precision_score
from preprocessing import FeatureEngineer, build_preprocessor

MODELS_DIR = Path("models")
MODELS_DIR.mkdir(exist_ok=True)
TARGET = "pago_30d"
ID_COLS = ["cliente_id","fecha_corte"]
DROP_COLS = ["saldo_interes","monto_cuota","pago_30d","cliente_id","fecha_corte"]

ESTRATEGIAS = {
    "ALTO":  {"canal":"WhatsApp / SMS / Email / IVR","accion":"Recordatorio digital con link de pago","oferta":"2 cuotas sin interes adicional","frecuencia":"Max 2 contactos/semana"},
    "MEDIO": {"canal":"Marcador Predictivo + Agente","accion":"Negociacion script ACED + registro PTP","oferta":"Plan 3-6 cuotas / Condonacion intereses","frecuencia":"Max 3 intentos/dia"},
    "BAJO":  {"canal":"Especialista / Notaria / Agencia","accion":"Skip tracing + Carta notarial + Settlement","oferta":"Descuento 20-40% en deuda total","frecuencia":"Gestion semanal especializada"},
}

def build_pipeline():
    clf = RandomForestClassifier(n_estimators=300,max_depth=12,min_samples_leaf=20,
        class_weight="balanced",random_state=42,n_jobs=-1)
    return Pipeline([("feature_engineering",FeatureEngineer()),("preprocessor",build_preprocessor()),("classifier",clf)])

def train(df, model_name="random_forest", test_size=0.20):
    feature_cols = [c for c in df.columns if c not in ID_COLS + [TARGET,"saldo_interes","monto_cuota"]]
    X, y = df[feature_cols], df[TARGET]
    X_train,X_test,y_train,y_test = train_test_split(X,y,test_size=test_size,stratify=y,random_state=42)
    pipeline = build_pipeline()
    cv = StratifiedKFold(n_splits=5,shuffle=True,random_state=42)
    cv_auc = cross_val_score(pipeline,X_train,y_train,cv=cv,scoring="roc_auc",n_jobs=-1)
    pipeline.fit(X_train,y_train)
    y_prob = pipeline.predict_proba(X_test)[:,1]
    y_pred = pipeline.predict(X_test)
    print("="*55)
    print(f"  CV AUC-ROC: {cv_auc.mean():.4f} +/- {cv_auc.std():.4f}")
    print(f"  Test AUC-ROC: {roc_auc_score(y_test,y_prob):.4f}")
    print(f"  Avg Precision: {average_precision_score(y_test,y_prob):.4f}")
    print(classification_report(y_test,y_pred))
    joblib.dump(pipeline, MODELS_DIR/"pipeline_random_forest.pkl")
    print(f"  Modelo guardado.")
    return {"pipeline":pipeline,"cv_auc":cv_auc.mean()}

def score_portfolio(df, pipeline, score_min=1, score_max=100):
    DROP = ["cliente_id","fecha_corte",TARGET,"saldo_interes","monto_cuota"]
    id_data = df[["cliente_id"]].copy() if "cliente_id" in df.columns else pd.DataFrame()
    # Asegurar columnas requeridas
    from preprocessing import NUMERIC_FEATURES, CATEGORICAL_FEATURES
    for col in NUMERIC_FEATURES:
        if col not in df.columns: df[col] = np.nan
    for col in CATEGORICAL_FEATURES:
        if col not in df.columns: df[col] = "DESCONOCIDO"
    if "promesas_totales" not in df.columns: df["promesas_totales"] = 0
    X = df[[c for c in df.columns if c not in DROP]]
    prob = pipeline.predict_proba(X)[:,1]
    p1,p99 = np.percentile(prob,1),np.percentile(prob,99)
    score_raw = np.clip((prob-p1)/(p99-p1+1e-9),0,1)
    score_op = np.clip(np.round(score_raw*(score_max-score_min)+score_min).astype(int),score_min,score_max)
    segmento = pd.cut(score_op,bins=[0,33,66,100],labels=["BAJO","MEDIO","ALTO"],include_lowest=True).astype(str)
    resultado = id_data.copy()
    resultado["prob_pago"] = np.round(prob,4)
    resultado["score_operativo"] = score_op
    resultado["segmento"] = segmento
    resultado["estrategia"] = segmento.map({s:ESTRATEGIAS[s]["canal"] for s in ESTRATEGIAS})
    resultado["estrategia_canal"] = segmento.map({s:ESTRATEGIAS[s]["canal"] for s in ESTRATEGIAS})
    resultado["estrategia_accion"] = segmento.map({s:ESTRATEGIAS[s]["accion"] for s in ESTRATEGIAS})
    resultado["estrategia_oferta"] = segmento.map({s:ESTRATEGIAS[s]["oferta"] for s in ESTRATEGIAS})
    resultado["frecuencia_contacto"] = segmento.map({s:ESTRATEGIAS[s]["frecuencia"] for s in ESTRATEGIAS})
    resultado["prioridad_dialer"] = segmento.map({"ALTO":3,"MEDIO":2,"BAJO":1})
    for col in ["dpd","saldo_total","bucket_mora","rpc_rate","ultimo_estado_marcado"]:
        if col in df.columns: resultado[col] = df[col].values
    return resultado.sort_values("score_operativo",ascending=False).reset_index(drop=True)

def load_pipeline():
    p = MODELS_DIR/"pipeline_random_forest.pkl"
    if not p.exists(): raise FileNotFoundError("Modelo no encontrado. Ejecuta main.py primero.")
    return joblib.load(p)
'@ | Set-Content "$PROJECT\src\model.py" -Encoding UTF8

# ── src/database.py ──────────────────────────────────────────
@'
import sqlite3, pandas as pd
from pathlib import Path
from datetime import datetime

DB_PATH = Path("data/callcenter.db")
DB_PATH.parent.mkdir(exist_ok=True)

def get_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS clientes (
            cliente_id TEXT PRIMARY KEY, score_operativo INTEGER, segmento TEXT,
            prob_pago REAL, dpd INTEGER, bucket_mora TEXT, saldo_total REAL,
            rpc_rate REAL, ultimo_estado_marcado TEXT, estrategia_canal TEXT,
            estrategia_accion TEXT, estrategia_oferta TEXT,
            veces_procesado INTEGER DEFAULT 1, fecha_primera_carga TEXT, fecha_ultima_carga TEXT);
        CREATE TABLE IF NOT EXISTS historial_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id TEXT,
            score_operativo INTEGER, segmento TEXT, prob_pago REAL,
            dpd INTEGER, saldo_total REAL, fecha_score TEXT, carga_id INTEGER);
        CREATE TABLE IF NOT EXISTS cargas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT, filename TEXT,
            total_registros INTEGER, registros_nuevos INTEGER,
            registros_actualizados INTEGER, fecha_carga TEXT);
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            nombre TEXT NOT NULL, email TEXT, rol TEXT NOT NULL,
            password_hash TEXT NOT NULL, activo INTEGER DEFAULT 1,
            fecha_creacion TEXT DEFAULT (date('now')));
    """)
    conn.commit(); conn.close()

def get_clientes_by_ids(ids):
    if not ids: return pd.DataFrame()
    conn = get_connection()
    ph = ",".join("?"*len(ids))
    df = pd.read_sql_query(f"SELECT * FROM clientes WHERE cliente_id IN ({ph})", conn, params=ids)
    conn.close(); return df

def upsert_clientes_batch(df, carga_id):
    conn = get_connection(); cursor = conn.cursor()
    today = datetime.today().strftime("%Y-%m-%d")
    ids = df["cliente_id"].tolist()
    ph = ",".join("?"*len(ids))
    cursor.execute(f"SELECT cliente_id,veces_procesado,fecha_primera_carga FROM clientes WHERE cliente_id IN ({ph})", ids)
    existing = {row["cliente_id"]: row for row in cursor.fetchall()}
    nuevos = actualizados = 0
    for _, row in df.iterrows():
        cid = row["cliente_id"]
        vals = (int(row.get("score_operativo",0)), str(row.get("segmento","")),
                float(row.get("prob_pago",0)), int(row.get("dpd",0) or 0),
                str(row.get("bucket_mora","")), float(row.get("saldo_total",0) or 0),
                float(row.get("rpc_rate",0) or 0), str(row.get("ultimo_estado_marcado","")),
                str(row.get("estrategia_canal","")), str(row.get("estrategia_accion","")),
                str(row.get("estrategia_oferta","")))
        if cid in existing:
            cursor.execute("UPDATE clientes SET score_operativo=?,segmento=?,prob_pago=?,dpd=?,bucket_mora=?,saldo_total=?,rpc_rate=?,ultimo_estado_marcado=?,estrategia_canal=?,estrategia_accion=?,estrategia_oferta=?,veces_procesado=?,fecha_ultima_carga=? WHERE cliente_id=?",
                (*vals, existing[cid]["veces_procesado"]+1, today, cid))
            actualizados += 1
        else:
            cursor.execute("INSERT OR IGNORE INTO clientes (cliente_id,score_operativo,segmento,prob_pago,dpd,bucket_mora,saldo_total,rpc_rate,ultimo_estado_marcado,estrategia_canal,estrategia_accion,estrategia_oferta,veces_procesado,fecha_primera_carga,fecha_ultima_carga) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
                (cid,*vals,today,today))
            nuevos += 1
        cursor.execute("INSERT INTO historial_scores (cliente_id,score_operativo,segmento,prob_pago,dpd,saldo_total,fecha_score,carga_id) VALUES (?,?,?,?,?,?,?,?)",
            (cid,int(row.get("score_operativo",0)),str(row.get("segmento","")),float(row.get("prob_pago",0)),int(row.get("dpd",0) or 0),float(row.get("saldo_total",0) or 0),today,carga_id))
    conn.commit(); conn.close()
    return {"nuevos":nuevos,"actualizados":actualizados}

def log_carga(usuario, filename, total, nuevos, actualizados):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO cargas (usuario,filename,total_registros,registros_nuevos,registros_actualizados,fecha_carga) VALUES (?,?,?,?,?,?)",
        (usuario,filename,total,nuevos,actualizados,datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    cid = cursor.lastrowid; conn.commit(); conn.close(); return cid

def get_cargas_historico():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM cargas ORDER BY fecha_carga DESC LIMIT 100", conn)
    conn.close(); return df

def get_metricas_globales():
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) as n FROM clientes")
    total = cursor.fetchone()["n"]
    cursor.execute("SELECT segmento,COUNT(*) as n,AVG(score_operativo) as avg_s,SUM(saldo_total) as saldo FROM clientes GROUP BY segmento")
    por_segmento = {r["segmento"]:{"count":r["n"],"avg_score":round(r["avg_s"] or 0,1),"saldo":round(r["saldo"] or 0,2)} for r in cursor.fetchall()}
    cursor.execute("SELECT AVG(score_operativo) as s,AVG(prob_pago) as p FROM clientes")
    row = cursor.fetchone()
    cursor.execute("SELECT SUM(saldo_total) as s FROM clientes")
    saldo = cursor.fetchone()["s"] or 0
    cursor.execute("SELECT COUNT(*) as n FROM cargas")
    total_cargas = cursor.fetchone()["n"]
    conn.close()
    return {"total_clientes":total,"por_segmento":por_segmento,
            "avg_score":round(row["s"] or 0,1),"avg_prob_pago":round((row["p"] or 0)*100,1),
            "saldo_total":saldo,"total_cargas":total_cargas}

def get_all_clientes_df(limit=50000):
    conn = get_connection()
    df = pd.read_sql_query(f"SELECT * FROM clientes ORDER BY score_operativo DESC LIMIT {limit}", conn)
    conn.close(); return df
'@ | Set-Content "$PROJECT\src\database.py" -Encoding UTF8

# ── src/auth.py ──────────────────────────────────────────────
@'
import hashlib, os, sqlite3, pandas as pd
from database import get_connection

def hash_password(password):
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
    return salt.hex()+":"+key.hex()

def verify_password(password, stored):
    try:
        salt_hex, key_hex = stored.split(":")
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200000)
        return key.hex() == key_hex
    except: return False

def authenticate(username, password):
    conn = get_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM usuarios WHERE username=? AND activo=1", (username.strip().lower(),))
    user = cursor.fetchone(); conn.close()
    if user and verify_password(password, user["password_hash"]):
        return {"username":user["username"],"nombre":user["nombre"],"email":user["email"],"rol":user["rol"]}
    return None

def create_user(username, password, nombre, email, rol):
    if rol not in ("admin","colaborador"): return False,"Rol invalido."
    if len(password) < 6: return False,"Password minimo 6 caracteres."
    try:
        conn = get_connection(); cursor = conn.cursor()
        cursor.execute("INSERT INTO usuarios (username,nombre,email,rol,password_hash) VALUES (?,?,?,?,?)",
            (username.strip().lower(),nombre,email,rol,hash_password(password)))
        conn.commit(); conn.close(); return True,f"Usuario '{username}' creado."
    except sqlite3.IntegrityError: return False,f"Usuario '{username}' ya existe."

def get_all_users():
    conn = get_connection()
    df = pd.read_sql_query("SELECT id,username,nombre,email,rol,activo,fecha_creacion FROM usuarios ORDER BY id", conn)
    conn.close(); return df

def toggle_user_status(username):
    try:
        conn = get_connection()
        conn.execute("UPDATE usuarios SET activo=CASE WHEN activo=1 THEN 0 ELSE 1 END WHERE username=?", (username,))
        conn.commit(); conn.close(); return True
    except: return False

def update_password(username, new_password):
    if len(new_password) < 6: return False,"Minimo 6 caracteres."
    try:
        conn = get_connection()
        conn.execute("UPDATE usuarios SET password_hash=? WHERE username=?", (hash_password(new_password),username))
        conn.commit(); conn.close(); return True,"Contrasena actualizada."
    except Exception as e: return False,str(e)
'@ | Set-Content "$PROJECT\src\auth.py" -Encoding UTF8

# ── src/setup_db.py ──────────────────────────────────────────
@'
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from database import init_db
from auth import create_user

USUARIOS = [
    dict(username="admin",       password="Admin2024!", nombre="Administrador", email="admin@callcenter.com",  rol="admin"),
    dict(username="supervisor",  password="Super2024!", nombre="Supervisor",    email="super@callcenter.com",  rol="admin"),
    dict(username="colaborador", password="Colab2024!", nombre="Colaborador",   email="colab@callcenter.com",  rol="colaborador"),
]

def setup():
    print("Inicializando base de datos..."); init_db(); print("  OK: tablas creadas")
    print("Creando usuarios...")
    for u in USUARIOS:
        ok,msg = create_user(**u)
        print(f"  {'OK' if ok else 'YA EXISTE'}: {u['username']} ({u['rol']}) | Pass: {u['password']}")
    print("\nCredenciales:")
    print("  admin        / Admin2024!   (Admin)")
    print("  supervisor   / Super2024!   (Admin)")
    print("  colaborador  / Colab2024!   (Colaborador)")

if __name__ == "__main__": setup()
'@ | Set-Content "$PROJECT\src\setup_db.py" -Encoding UTF8

# ── src/main.py ──────────────────────────────────────────────
@'
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from data_generator import generate_collection_dataset
from model import train, score_portfolio
from database import init_db
from setup_db import setup
from pathlib import Path

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

def run():
    print("\n"+"="*55)
    print("  SISTEMA PREDICTIVO DE COBRANZA — SETUP COMPLETO")
    print("="*55)
    print("\n[1/4] Inicializando BD y usuarios..."); setup()
    print("\n[2/4] Generando datos de prueba...")
    df = generate_collection_dataset(5000, 42)
    df.to_csv(DATA_DIR/"cartera_sintetica.csv", index=False)
    print(f"      {len(df):,} registros | Tasa pago: {df['pago_30d'].mean():.1%}")
    print("\n[3/4] Entrenando modelo..."); results = train(df)
    print("\n[4/4] Calculando scores...")
    scores = score_portfolio(df, results["pipeline"])
    scores.to_csv(DATA_DIR/"cartera_scored.csv", index=False)
    resumen = scores.groupby("segmento").agg(clientes=("cliente_id","count"),score_prom=("score_operativo","mean")).round(1)
    resumen["pct"] = (resumen["clientes"]/len(scores)*100).round(1)
    print(resumen.to_string())
    print("\n"+"="*55)
    print("  LISTO. Ejecuta: streamlit run dashboard/app.py")
    print("="*55+"\n")

if __name__ == "__main__": run()
'@ | Set-Content "$PROJECT\src\main.py" -Encoding UTF8

# ── dashboard/app.py ─────────────────────────────────────────
@'
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import joblib, io
from pathlib import Path
from datetime import datetime
from database import init_db, get_clientes_by_ids, upsert_clientes_batch, log_carga, get_cargas_historico, get_metricas_globales, get_all_clientes_df
from auth import authenticate, create_user, get_all_users, toggle_user_status, update_password

st.set_page_config(page_title="Score de Cobranza", page_icon="📊", layout="wide")
MODELS_DIR = Path("models")
COLORES = {"ALTO":"#27ae60","MEDIO":"#f39c12","BAJO":"#e74c3c"}
ESTRATEGIAS = {
    "ALTO":  {"canal":"WhatsApp / SMS / Email / IVR","accion":"Recordatorio digital con link de pago automatico","oferta":"2 cuotas sin interes adicional","frecuencia":"Max 2 contactos/semana","kpis":"Conversion >= 20% | Costo S/ 0.10-0.30","script":"Hola [Nombre], tienes un saldo de S/[monto]. Pagalo aqui: [link]","ref":"Hoist Finance / Interbank — Digital First"},
    "MEDIO": {"canal":"Marcador Predictivo + Agente Humano","accion":"Negociacion script ACED + registro PTP","oferta":"Plan 3-6 cuotas / Condonacion intereses moratorios","frecuencia":"Max 3 intentos/dia | 9-11am y 6-8pm L-V","kpis":"RPC >= 45% | PTP >= 30% | Kept PTP >= 65%","script":"ACED: Acknowledge → Create urgency → Empathize → Deal. Oferta: 'Puedo condonar intereses si paga capital hoy.'","ref":"FICO TRIAD / COFACE / Encore Capital"},
    "BAJO":  {"canal":"Especialista Senior / Notaria / Agencia Externa","accion":"Skip tracing + Carta notarial + Oferta settlement","oferta":"Descuento 20-40% en deuda total si paga contado","frecuencia":"Gestion semanal especializada","kpis":"Skip tracing >= 25% | Settlement >= 15% | Recovery >= 8%","script":"'Notificamos que de no regularizar S/[monto] en 15 dias, iniciaremos proceso judicial y registro SBS/Equifax.'","ref":"Intrum / Portfolio Recovery Associates"},
}

@st.cache_resource
def load_model():
    p = MODELS_DIR/"pipeline_random_forest.pkl"
    return joblib.load(p) if p.exists() else None

def score_df(df_raw, pipeline):
    from model import score_portfolio
    df_s = score_portfolio(df_raw, pipeline)
    for k in ["canal","accion","oferta","frecuencia"]:
        df_s[f"estrategia_{k}"] = df_s["segmento"].map(lambda s,k=k: ESTRATEGIAS.get(s,{}).get(k,""))
    return df_s

def process_upload(df_raw, pipeline, usuario, filename):
    if "cliente_id" not in df_raw.columns:
        posibles = [c for c in df_raw.columns if "id" in c.lower() or "cliente" in c.lower()]
        df_raw = df_raw.rename(columns={posibles[0]:"cliente_id"}) if posibles else df_raw
        if "cliente_id" not in df_raw.columns:
            df_raw.insert(0,"cliente_id",[f"CLI-{i:06d}" for i in range(1,len(df_raw)+1)])
    ids = df_raw["cliente_id"].astype(str).tolist()
    df_ex = get_clientes_by_ids(ids)
    ids_conocidos = set(df_ex["cliente_id"].tolist()) if len(df_ex)>0 else set()
    n_conocidos = sum(1 for i in ids if i in ids_conocidos)
    n_nuevos = len(ids)-n_conocidos
    df_scored = score_df(df_raw, pipeline)
    df_scored["es_nuevo"] = ~df_scored["cliente_id"].isin(ids_conocidos)
    df_scored["estado_carga"] = df_scored["es_nuevo"].map({True:"Nuevo","False":"Actualizado",False:"Actualizado"})
    carga_id = log_carga(usuario, filename, len(df_scored), n_nuevos, n_conocidos)
    upsert_clientes_batch(df_scored, carga_id)
    return df_scored, {"total":len(df_scored),"nuevos":n_nuevos,"conocidos":n_conocidos}

def export_excel(df):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Cartera Completa")
        for seg in ["ALTO","MEDIO","BAJO"]:
            sub = df[df["segmento"]==seg]
            if len(sub)>0: sub.to_excel(w, index=False, sheet_name=f"Seg {seg}")
        resumen = df.groupby("segmento").agg(clientes=("cliente_id","count"),score_prom=("score_operativo","mean"),prob_prom=("prob_pago","mean"),saldo=("saldo_total","sum")).round(2)
        resumen.to_excel(w, sheet_name="Resumen Ejecutivo")
        guia = pd.DataFrame([{"Segmento":s,"Canal":ESTRATEGIAS[s]["canal"],"Accion":ESTRATEGIAS[s]["accion"],"Oferta":ESTRATEGIAS[s]["oferta"],"KPIs":ESTRATEGIAS[s]["kpis"]} for s in ["ALTO","MEDIO","BAJO"]])
        guia.to_excel(w, index=False, sheet_name="Guia Estrategias")
    return buf.getvalue()

def show_login():
    init_db()
    _,col,_ = st.columns([1,1.2,1])
    with col:
        st.markdown("## 📊 Sistema de Cobranza")
        st.markdown("**Call Center Cuzco** — Score Predictivo")
        st.divider()
        with st.form("login"):
            user = st.text_input("Usuario")
            pwd = st.text_input("Contrasena", type="password")
            ok = st.form_submit_button("Ingresar", use_container_width=True, type="primary")
        if ok:
            u = authenticate(user, pwd)
            if u: st.session_state["user"]=u; st.session_state["page"]="inicio"; st.rerun()
            else: st.error("Usuario o contrasena incorrectos.")

def show_sidebar():
    u = st.session_state["user"]
    with st.sidebar:
        st.markdown(f"### {u['nombre']}")
        st.caption("Admin" if u["rol"]=="admin" else "Colaborador")
        st.divider()
        pages = {"inicio":"🏠 Inicio","cargar":"📤 Cargar Cartera","analisis":"📊 Analisis","historial":"📋 Historial","estrategias":"🎯 Estrategias"}
        if u["rol"]=="admin": pages["admin"]="⚙️ Panel Admin"
        cur = st.session_state.get("page","inicio")
        for k,label in pages.items():
            if st.button(label, use_container_width=True, type="primary" if cur==k else "secondary"):
                st.session_state["page"]=k; st.rerun()
        st.divider()
        if st.button("🚪 Salir", use_container_width=True): st.session_state.clear(); st.rerun()

def page_inicio():
    st.title("🏠 Inicio")
    m = get_metricas_globales()
    if m["total_clientes"]==0: st.info("BD vacia. Ve a Cargar Cartera."); return
    seg = m["por_segmento"]
    total = m["total_clientes"]
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Total en BD", f"{total:,}")
    c2.metric("Score Promedio", m["avg_score"])
    c3.metric("ALTO",  f"{seg.get('ALTO',{}).get('count',0):,}")
    c4.metric("MEDIO", f"{seg.get('MEDIO',{}).get('count',0):,}")
    c5.metric("BAJO",  f"{seg.get('BAJO',{}).get('count',0):,}")
    st.divider()
    df_db = get_all_clientes_df(5000)
    c1,c2 = st.columns(2)
    with c1:
        st.subheader("Composicion por Segmento")
        data = {"Segmento":list(seg.keys()),"Clientes":[v["count"] for v in seg.values()]}
        fig = px.pie(data,values="Clientes",names="Segmento",color="Segmento",color_discrete_map=COLORES,hole=0.45,template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        st.subheader("Distribucion de Score")
        if len(df_db)>0:
            fig2 = px.histogram(df_db,x="score_operativo",nbins=40,color="segmento",color_discrete_map=COLORES,template="plotly_dark")
            st.plotly_chart(fig2, use_container_width=True)
    st.subheader("Ultimas Cargas")
    df_c = get_cargas_historico()
    if len(df_c)>0: st.dataframe(df_c.head(8), hide_index=True, use_container_width=True)

def page_cargar():
    st.title("📤 Cargar Cartera")
    pipeline = load_model()
    if pipeline is None: st.error("Modelo no encontrado. Ejecuta: python src/main.py"); return
    uploaded = st.file_uploader("Selecciona archivo de cartera", type=["xlsx","xls","csv"])
    if uploaded is None: st.info("Sube tu Excel o CSV. El sistema detecta automaticamente clientes conocidos vs nuevos."); return
    try:
        df_raw = pd.read_csv(uploaded) if uploaded.name.lower().endswith(".csv") else pd.read_excel(uploaded)
    except Exception as e: st.error(f"Error leyendo archivo: {e}"); return
    st.success(f"Archivo: {uploaded.name} | {len(df_raw):,} registros")
    with st.expander("Vista previa"): st.dataframe(df_raw.head(5), use_container_width=True)
    if st.button("🚀 Procesar y Calcular Scores", type="primary", use_container_width=True):
        with st.spinner(f"Procesando {len(df_raw):,} cuentas..."):
            prog = st.progress(0,"Verificando en BD...")
            try:
                prog.progress(30,"Calculando scores..."); df_r, stats = process_upload(df_raw, pipeline, st.session_state["user"]["username"], uploaded.name); prog.progress(100,"Listo!")
            except Exception as e: st.error(f"Error: {e}"); import traceback; st.code(traceback.format_exc()); return
        st.divider()
        c1,c2,c3 = st.columns(3)
        c1.metric("Total Procesado", f"{stats['total']:,}")
        c2.metric("Ya en BD (actualizados)", f"{stats['conocidos']:,}")
        c3.metric("Clientes Nuevos", f"{stats['nuevos']:,}")
        sc = df_r["segmento"].value_counts()
        ca,cm,cb = st.columns(3)
        ca.metric("ALTO",  f"{sc.get('ALTO',0):,}")
        cm.metric("MEDIO", f"{sc.get('MEDIO',0):,}")
        cb.metric("BAJO",  f"{sc.get('BAJO',0):,}")
        st.divider()
        cols = [c for c in ["cliente_id","score_operativo","segmento","prob_pago","estrategia_canal","estrategia_oferta","dpd","saldo_total","estado_carga"] if c in df_r.columns]
        st.dataframe(df_r[cols].head(300), hide_index=True, use_container_width=True, column_config={"score_operativo":st.column_config.ProgressColumn("Score",min_value=1,max_value=100),"prob_pago":st.column_config.NumberColumn("Prob Pago",format="%.1%")})
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        d1,d2 = st.columns(2)
        with d1: st.download_button("⬇️ Excel Completo (4 hojas)", export_excel(df_r), f"cartera_{ts}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary", use_container_width=True)
        with d2:
            buf=io.StringIO(); df_r.to_csv(buf,index=False)
            st.download_button("⬇️ CSV para Dialer", buf.getvalue(), f"dialer_{ts}.csv", "text/csv", use_container_width=True)

def page_analisis():
    st.title("📊 Analisis de Cartera")
    df = get_all_clientes_df(20000)
    if len(df)==0: st.info("Carga tu primera cartera."); return
    segs = st.multiselect("Segmentos",["ALTO","MEDIO","BAJO"],default=["ALTO","MEDIO","BAJO"])
    df = df[df["segmento"].isin(segs)]
    c1,c2 = st.columns(2)
    with c1:
        st.subheader("Score vs DPD")
        if "dpd" in df.columns:
            fig = px.scatter(df.sample(min(1500,len(df))),x="dpd",y="score_operativo",color="segmento",color_discrete_map=COLORES,opacity=0.6,template="plotly_dark")
            st.plotly_chart(fig,use_container_width=True)
    with c2:
        st.subheader("RPC por Segmento")
        if "rpc_rate" in df.columns:
            fig2 = px.box(df,x="segmento",y="rpc_rate",color="segmento",color_discrete_map=COLORES,template="plotly_dark")
            fig2.update_layout(showlegend=False); st.plotly_chart(fig2,use_container_width=True)
    if "saldo_total" in df.columns:
        st.subheader("Saldo por Segmento")
        s = df.groupby("segmento")["saldo_total"].sum().reset_index()
        fig3 = px.bar(s,x="segmento",y="saldo_total",color="segmento",color_discrete_map=COLORES,text_auto=".3s",template="plotly_dark")
        fig3.update_layout(showlegend=False); st.plotly_chart(fig3,use_container_width=True)

def page_historial():
    st.title("📋 Historial de Cargas")
    df = get_cargas_historico()
    if len(df)==0: st.info("Sin cargas registradas."); return
    c1,c2,c3 = st.columns(3)
    c1.metric("Total Cargas",f"{len(df):,}")
    c2.metric("Total Procesados",f"{df['total_registros'].sum():,}")
    c3.metric("Clientes Nuevos",f"{df['registros_nuevos'].sum():,}")
    st.divider(); st.dataframe(df,hide_index=True,use_container_width=True)

def page_estrategias():
    st.title("🎯 Estrategias de Cobranza — Clase Mundial")
    st.caption("Basadas en Hoist Finance, Encore Capital, FICO TRIAD, COFACE, Intrum.")
    for seg,color in [("ALTO","#27ae60"),("MEDIO","#f39c12"),("BAJO","#e74c3c")]:
        e = ESTRATEGIAS[seg]
        rng = {"ALTO":"67-100","MEDIO":"34-66","BAJO":"1-33"}[seg]
        st.markdown(f"<div style='border-left:5px solid {color};padding:12px 16px;background:#1a1a2e;border-radius:8px;margin-bottom:16px'><h3 style='color:{color};margin:0'>Segmento {seg} | Score {rng}</h3></div>",unsafe_allow_html=True)
        c1,c2 = st.columns(2)
        with c1:
            st.markdown(f"**Canal:** {e['canal']}")
            st.markdown(f"**Accion:** {e['accion']}")
            st.markdown(f"**Oferta:** {e['oferta']}")
            st.markdown(f"**Frecuencia:** {e['frecuencia']}")
        with c2:
            st.markdown(f"**KPIs:** {e['kpis']}")
            st.markdown(f"**Referencia:** {e['ref']}")
        with st.expander(f"Script / Guion — {seg}"): st.info(e["script"])
        st.divider()

def page_admin():
    if st.session_state["user"]["rol"]!="admin": st.error("Solo Administradores."); return
    st.title("⚙️ Panel de Administracion")
    t1,t2,t3 = st.tabs(["Usuarios","Crear Usuario","Cambiar Contrasena"])
    with t1:
        df_u = get_all_users(); st.dataframe(df_u,hide_index=True,use_container_width=True)
        st.subheader("Activar / Desactivar")
        cur = st.session_state["user"]["username"]
        ops = [u for u in df_u["username"].tolist() if u!=cur]
        if ops:
            sel = st.selectbox("Usuario",ops)
            if st.button(f"Cambiar estado de '{sel}'"): toggle_user_status(sel); st.success("Cambiado."); st.rerun()
    with t2:
        st.subheader("Nuevo Usuario")
        with st.form("nuevo"):
            c1,c2 = st.columns(2)
            nu = c1.text_input("Username"); nn = c2.text_input("Nombre")
            ne = c1.text_input("Email"); nr = c2.selectbox("Rol",["colaborador","admin"])
            np_ = st.text_input("Contrasena",type="password"); nc = st.text_input("Confirmar",type="password")
            if st.form_submit_button("Crear",type="primary"):
                if np_!=nc: st.error("Contrasenas no coinciden.")
                else:
                    ok,msg = create_user(nu,np_,nn,ne,nr)
                    (st.success if ok else st.error)(msg)
    with t3:
        st.subheader("Cambiar Contrasena")
        df_u2 = get_all_users()
        with st.form("pass"):
            us = st.selectbox("Usuario",df_u2["username"].tolist())
            p1 = st.text_input("Nueva contrasena",type="password"); p2 = st.text_input("Confirmar",type="password")
            if st.form_submit_button("Actualizar",type="primary"):
                if p1!=p2: st.error("No coinciden.")
                else:
                    ok,msg = update_password(us,p1)
                    (st.success if ok else st.error)(msg)

def main():
    init_db()
    if "user" not in st.session_state: show_login(); return
    show_sidebar()
    routes = {"inicio":page_inicio,"cargar":page_cargar,"analisis":page_analisis,"historial":page_historial,"estrategias":page_estrategias,"admin":page_admin}
    routes.get(st.session_state.get("page","inicio"), page_inicio)()

if __name__ == "__main__": main()
'@ | Set-Content "$PROJECT\dashboard\app.py" -Encoding UTF8

Write-Host "      OK: todos los archivos creados" -ForegroundColor Green

# ── Instalar dependencias ─────────────────────────────────────
Write-Host ""
Write-Host "[3/6] Instalando dependencias Python..." -ForegroundColor Yellow
Set-Location $PROJECT
pip install -r requirements.txt --quiet
Write-Host "      OK: dependencias instaladas" -ForegroundColor Green

# ── Entrenar modelo ───────────────────────────────────────────
Write-Host ""
Write-Host "[4/6] Entrenando modelo y configurando base de datos..." -ForegroundColor Yellow
python src/main.py

# ── Lanzar dashboard ──────────────────────────────────────────
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  SISTEMA LISTO" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Usuarios:" -ForegroundColor White
Write-Host "  admin       / Admin2024!  (Admin)" -ForegroundColor Cyan
Write-Host "  supervisor  / Super2024!  (Admin)" -ForegroundColor Cyan
Write-Host "  colaborador / Colab2024!  (Colaborador)" -ForegroundColor Cyan
Write-Host ""
Write-Host "[5/6] Abriendo dashboard en el navegador..." -ForegroundColor Yellow
Write-Host ""
streamlit run dashboard/app.py
