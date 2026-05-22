"""
Autenticacion de Usuarios — Supabase via HTTPS
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


def authenticate(username: str, password: str):
    client = get_client()
    resp = (
        client.table("usuarios")
        .select("*")
        .eq("username", username.strip().lower())
        .eq("activo", 1)
        .maybe_single()
        .execute()
    )
    user = resp.data
    if user and verify_password(password, user["password_hash"]):
        return {
            "username": user["username"],
            "nombre":   user["nombre"],
            "email":    user["email"],
            "rol":      user["rol"],
        }
    return None


def create_user(username: str, password: str, nombre: str, email: str, rol: str):
    if rol not in ("admin", "colaborador"):
        return False, "Rol invalido."
    if len(password) < 6:
        return False, "Password minimo 6 caracteres."
    try:
        client = get_client()
        client.table("usuarios").insert({
            "username":      username.strip().lower(),
            "nombre":        nombre,
            "email":         email,
            "rol":           rol,
            "password_hash": hash_password(password),
        }).execute()
        return True, f"Usuario '{username}' creado."
    except Exception as e:
        err = str(e)
        if "duplicate" in err.lower() or "unique" in err.lower() or "23505" in err:
            return False, f"El usuario '{username}' ya existe."
        return False, err


def get_all_users() -> pd.DataFrame:
    client = get_client()
    resp = (
        client.table("usuarios")
        .select("id,username,nombre,email,rol,activo,fecha_creacion")
        .order("id")
        .execute()
    )
    return pd.DataFrame(resp.data) if resp.data else pd.DataFrame()


def toggle_user_status(username: str) -> bool:
    try:
        client = get_client()
        resp = (
            client.table("usuarios")
            .select("activo")
            .eq("username", username)
            .single()
            .execute()
        )
        current = resp.data["activo"]
        client.table("usuarios").update({"activo": 0 if current else 1}).eq("username", username).execute()
        return True
    except Exception:
        return False


def update_password(username: str, new_password: str):
    if len(new_password) < 6:
        return False, "Minimo 6 caracteres."
    try:
        client = get_client()
        client.table("usuarios").update(
            {"password_hash": hash_password(new_password)}
        ).eq("username", username).execute()
        return True, "Contrasena actualizada."
    except Exception as e:
        return False, str(e)
