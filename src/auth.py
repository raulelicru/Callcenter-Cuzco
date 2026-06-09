"""
Autenticacion de Usuarios — multi-empresa
"""
import hashlib
import os
import pandas as pd
from database import get_client


def hash_password(password: str) -> str:
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt.hex() + ":" + key.hex()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":")
        key = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 200_000
        )
        return key.hex() == key_hex
    except Exception:
        return False


def authenticate(username: str, password: str, empresa_id: int = 1):
    try:
        client = get_client()
        resp = (
            client.table("usuarios")
            .select("*")
            .eq("username", username.strip().lower())
            .eq("empresa_id", empresa_id)
            .eq("activo", 1)
            .maybe_single()
            .execute()
        )
        user = resp.data if hasattr(resp, "data") else None
        if user and verify_password(password, user["password_hash"]):
            return {
                "username":  user["username"],
                "nombre":    user["nombre"],
                "email":     user["email"],
                "rol":       user["rol"],
                "empresa_id": empresa_id,
            }
        return None
    except Exception:
        return None


def create_user(username: str, password: str, nombre: str, email: str,
                rol: str, empresa_id: int = 1):
    if rol not in ("admin", "colaborador"):
        return False, "Rol invalido."
    try:
        client = get_client()
        client.table("usuarios").insert({
            "empresa_id":    empresa_id,
            "username":      username.strip().lower(),
            "nombre":        nombre,
            "email":         email,
            "rol":           rol,
            "password_hash": hash_password(password),
            "activo":        1,
        }).execute()
        return True, f"Usuario '{username}' creado."
    except Exception as e:
        return False, str(e)


def get_all_users(empresa_id: int = 1) -> pd.DataFrame:
    client = get_client()
    resp = (
        client.table("usuarios")
        .select("id, username, nombre, email, rol, activo, fecha_creacion")
        .eq("empresa_id", empresa_id)
        .order("username")
        .execute()
    )
    return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()


def toggle_user_status(username: str, empresa_id: int = 1):
    client = get_client()
    resp = (
        client.table("usuarios")
        .select("activo")
        .eq("username", username)
        .eq("empresa_id", empresa_id)
        .maybe_single()
        .execute()
    )
    if resp.data:
        new_status = 0 if resp.data["activo"] else 1
        client.table("usuarios").update({"activo": new_status}) \
            .eq("username", username).eq("empresa_id", empresa_id).execute()


def update_password(username: str, new_password: str, empresa_id: int = 1):
    try:
        client = get_client()
        client.table("usuarios").update({"password_hash": hash_password(new_password)}) \
            .eq("username", username).eq("empresa_id", empresa_id).execute()
        return True, "Contrasena actualizada."
    except Exception as e:
        return False, str(e)
