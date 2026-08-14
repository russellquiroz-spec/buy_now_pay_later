"""Aviso por correo cuando la corrida del pipeline BNPL no termina bien.

Es lo mas simple que funciona en esta VM: SMTP autenticado sobre TLS contra el Workspace
de rabbitmx.com. No hace falta instalar un servidor de correo local (la VM no tiene uno),
ni un servicio nuevo, ni permisos extra de AWS: una libreria estandar y un secreto.

Si falta configuracion NO lanza: un fallo del aviso no puede convertirse en un segundo
fallo del pipeline, solo deja un WARNING en el log.

Configuracion, en .env.bnpl_pipeline en la raiz del repo (ya gitignoreado por `.env.*`):

    BNPL_SMTP_HOST=smtp.gmail.com
    BNPL_SMTP_PORT=587
    BNPL_SMTP_USER=<cuenta que envia>
    BNPL_SMTP_PASSWORD=<app password de 16 caracteres, NO la contrasena de la cuenta>
    BNPL_ALERTA_PARA=russell.quiroz@rabbitmx.com,<quien mas deba enterarse>
"""
import os
import smtplib
import socket
from email.message import EmailMessage
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ARCHIVO_ENV = BASE_DIR / ".env.bnpl_pipeline"
COLA_LINEAS = 60


def _cargar_env() -> None:
    """Lee el .env propio del pipeline. Se lee aqui y no en los .env de las librerias
    internas, que son compartidos con los otros proyectos de la VM."""
    if not ARCHIVO_ENV.exists():
        return
    for linea in ARCHIVO_ENV.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        os.environ.setdefault(clave.strip(), valor.strip())


def _cola_del_log(archivo: Path) -> str:
    try:
        return "\n".join(archivo.read_text(encoding="utf-8").splitlines()[-COLA_LINEAS:])
    except Exception:
        return "(no se pudo leer el log)"


def avisar_fallo(resultado: str, archivo_log: Path, log) -> None:
    _cargar_env()
    destinos = [d.strip() for d in os.environ.get("BNPL_ALERTA_PARA", "").split(",") if d.strip()]
    host = os.environ.get("BNPL_SMTP_HOST")
    usuario = os.environ.get("BNPL_SMTP_USER")
    clave = os.environ.get("BNPL_SMTP_PASSWORD")

    if not (destinos and host and usuario and clave):
        log.warning(
            "Aviso por correo sin configurar (falta %s): este fallo no se le avisa a nadie.",
            ARCHIVO_ENV.name,
        )
        return

    msg = EmailMessage()
    msg["Subject"] = f"[BNPL] pipeline {resultado} en {socket.gethostname()}"
    msg["From"] = usuario
    msg["To"] = ", ".join(destinos)
    msg.set_content(
        f"El pipeline BNPL termino con resultado '{resultado}'.\n\n"
        f"Log completo en la VM: {archivo_log}\n\n"
        f"Ultimas {COLA_LINEAS} lineas:\n\n{_cola_del_log(archivo_log)}\n"
    )

    try:
        with smtplib.SMTP(host, int(os.environ.get("BNPL_SMTP_PORT", 587)), timeout=30) as smtp:
            smtp.starttls()
            smtp.login(usuario, clave)
            smtp.send_message(msg)
        log.info("Aviso de fallo enviado a %s", ", ".join(destinos))
    except Exception as exc:  # noqa: BLE001 - avisar nunca debe tumbar la corrida
        log.warning("No se pudo enviar el aviso de fallo: %s", exc)
