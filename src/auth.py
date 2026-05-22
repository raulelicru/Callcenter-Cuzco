"""
Autenticacion de Usuarios — PostgreSQL
"""

import hashlib
import os
import pandas as pd
from database import get_connection


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex() + ":" + key.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":")
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200_000)
        return key.hex() == key_hex
    except Exception:
        return False


def authenticate(username: str, password: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM usuarios WHERE username=%s AND activo=1", (username.strip().lower(),))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if user and verify_password(password, user["password_hash"]):
        return {"username": user["username"], "nombre": user["nombre"],
                "email": user["email"], "rol": user["rol"]}
    return None


def create_user(username: str, password: str, nombre: str, email: str, rol: str):
    if rol not in ("admin", "colaborador"):
        return False, "Rol invalido."
    if len(password) < 6:
        return False, "Password minimo 6 caracteres."
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO usuarios (username,nombre,email,rol,password_hash) VALUES (%s,%s,%s,%s,%s)",
            (username.strip().lower(), nombre, email, rol, hash_password(password))
        )
        conn.commit()
        cur.close()
        conn.close()
        return True, f"Usuario '{username}' creado."
    except Exception as e:
        err = str(e)
        if "unique" in err.lower() or "UniqueViolation" in err:
            return False, f"El usuario '{username}' ya existe."
        return False, err


def get_all_users() -> pd.DataFrame:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id,username,nombre,email,rol,activo,fecha_creacion FROM usuarios ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def toggle_user_status(username: str) -> bool:
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "UPDATE usuarios SET activo = CASE WHEN activo=1 THEN 0 ELSE 1 END WHERE username=%s",
            (username,)
        )
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception:
        return False


def update_password(username: str, new_password: str):
    if len(new_password) < 6:
        return False, "Minimo 6 caracteres."
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE usuarios SET password_hash=%s WHERE username=%s",
                    (hash_password(new_password), username))
        conn.commit()
        cur.close()
        conn.close()
        return True, "Contrasena actualizada."
    except Exception as e:
        return False, str(e)
