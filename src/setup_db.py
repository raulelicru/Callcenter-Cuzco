"""
Inicialización del Sistema
===========================
Ejecutar UNA SOLA VEZ antes de lanzar el dashboard:
    python src/setup_db.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import init_db
from auth import create_user

USUARIOS_DEFAULT = [
    dict(username="admin",       password="Admin2024!",  nombre="Administrador",    email="admin@callcenter.com",       rol="admin"),
    dict(username="supervisor",  password="Super2024!",  nombre="Supervisor",       email="supervisor@callcenter.com",  rol="admin"),
    dict(username="colaborador", password="Colab2024!",  nombre="Colaborador",      email="colab@callcenter.com",       rol="colaborador"),
]


def setup():
    print("\n" + "=" * 55)
    print("  INICIALIZACIÓN — Sistema Predictivo de Cobranza")
    print("=" * 55)

    print("\n[1/2] Creando base de datos y tablas...")
    init_db()
    print("      ✓ Base de datos lista en data/callcenter.db")

    print("\n[2/2] Creando usuarios por defecto...")
    for u in USUARIOS_DEFAULT:
        ok, msg = create_user(**u)
        icon = "✓" if ok else "⚠"
        print(f"      {icon} {u['username']:15s} ({u['rol']:12s}) | Pass: {u['password']} — {msg}")

    print("\n" + "=" * 55)
    print("  CREDENCIALES DE ACCESO")
    print("=" * 55)
    print("  Usuario         Contraseña     Rol")
    print("  admin           Admin2024!     Administrador")
    print("  supervisor      Super2024!     Administrador")
    print("  colaborador     Colab2024!     Colaborador")
    print("=" * 55)
    print("\n  Inicia el sistema con:")
    print("  streamlit run dashboard/app.py\n")


if __name__ == "__main__":
    setup()
