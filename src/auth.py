"""
Autenticación de Usuarios
==========================
Hashing con PBKDF2-HMAC-SHA256 (estándar seguro, sin dependencias externas).
"""

import hashlib
import os
import pandas as pd
from database import get_connection


def hash_password(password: str) -> str:
    """Genera hash seguro con salt aleatorio."""
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex() + ":" + key.hex()


def verify_password(password: str, stored: str) -> bool:
    """Verifica contraseña contra hash almacenado."""
    try:
        salt_hex, key_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
        return key.hex() == key_hex
    except Exception:
        return False


def authenticate(username: str, password: str) -> dict | None:
    """Retorna datos del usuario si las credenciales son correctas, None si no."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM usuarios WHERE username=? AND activo=1",
        (username.strip().lower(),),
    )
    user = cursor.fetchone()
    conn.close()

    if user and verify_password(password, user["password_hash"]):
        return {
            "username": user["username"],
            "nombre": user["nombre"],
            "email": user["email"],
            "rol": user["rol"],
        }
    return None


def create_user(username: str, password: str, nombre: str, email: str, rol: str) -> tuple[bool, str]:
    """
    Crea nuevo usuario. Retorna (éxito, mensaje).
    """
    import sqlite3
    if rol not in ("admin", "colaborador"):
        return False, "Rol inválido. Usa 'admin' o 'colaborador'."
    if len(password) < 6:
        return False, "La contraseña debe tener al menos 6 caracteres."
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO usuarios (username, nombre, email, rol, password_hash)
            VALUES (?,?,?,?,?)
        """, (username.strip().lower(), nombre, email, rol, hash_password(password)))
        conn.commit()
        conn.close()
        return True, f"Usuario '{username}' creado correctamente."
    except sqlite3.IntegrityError:
        return False, f"El usuario '{username}' ya existe."


def get_all_users() -> pd.DataFrame:
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT id, username, nombre, email, rol, activo, fecha_creacion FROM usuarios ORDER BY id",
        conn,
    )
    conn.close()
    return df


def toggle_user_status(username: str) -> bool:
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE usuarios SET activo = CASE WHEN activo=1 THEN 0 ELSE 1 END WHERE username=?",
            (username,),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def update_password(username: str, new_password: str) -> tuple[bool, str]:
    if len(new_password) < 6:
        return False, "La contraseña debe tener al menos 6 caracteres."
    try:
        conn = get_connection()
        conn.execute(
            "UPDATE usuarios SET password_hash=? WHERE username=?",
            (hash_password(new_password), username),
        )
        conn.commit()
        conn.close()
        return True, "Contraseña actualizada correctamente."
    except Exception as e:
        return False, str(e)
