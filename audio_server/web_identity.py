import hashlib


def derive_web_device_uuid(ip: str, user_agent: str) -> str:
    """Deriva un UUID estable para clientes web sin depender de caché/localStorage.

    Requisito del proyecto: identidad estable por IP (no por localStorage).
    Nota: si cambia la IP, cambia el UUID.

    Si la IP no está disponible, usa fallback IP+User-Agent para evitar colisión masiva.
    """
    ip = (ip or '').strip()
    user_agent = (user_agent or '').strip()

    if ip:
        raw_id = ip
    else:
        raw_id = f"{ip}|{user_agent}"

    hash_id = hashlib.sha256(raw_id.encode('utf-8')).hexdigest()[:16]
    return f"web-{hash_id}"
