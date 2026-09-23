"""
Configuración central del POS.

Acá se define dónde vive la base de datos y dónde se guardan los respaldos.
Mantener esto en un solo lugar facilita cambiarlo sin tocar el resto del código
(por ejemplo, si el negocio quiere mover la carpeta a otro disco).
"""

import os
import sys


def _carpeta_base() -> str:
    """
    Devuelve la carpeta donde vive el ejecutable (o el script, en desarrollo).
    Cuando esto se empaquete con PyInstaller, sys.executable apunta al .exe;
    en desarrollo normal, usamos la carpeta del proyecto.
    """
    if getattr(sys, "frozen", False):
        # Corriendo como .exe empaquetado con PyInstaller
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CARPETA_BASE = _carpeta_base()

# Carpeta donde vive la base de datos. Fija y predecible, para poder
# respaldarla o copiarla a mano si hace falta.
CARPETA_DATOS = os.path.join(CARPETA_BASE, "datos")
RUTA_BASE_DATOS = os.path.join(CARPETA_DATOS, "pos.db")

# Carpeta donde se guardan los respaldos automáticos/manuales
CARPETA_BACKUPS = os.path.join(CARPETA_BASE, "backups")

# Nombre de la app (marca), independiente del nombre del negocio que la usa
NOMBRE_APP = "POS by Hadar"

# Nombre del negocio (se puede usar en tickets, títulos de ventana, etc.)
NOMBRE_NEGOCIO = "Negocio"

# Color de acento de la marca Hadar (mismo azul aciano que Hadar Analytics),
# centralizado acá para no repetir el hex en cada archivo de interfaz
COLOR_ACENTO_HADAR = "#6366F1"


def asegurar_carpetas():
    """Crea las carpetas de datos y backups si no existen todavía."""
    os.makedirs(CARPETA_DATOS, exist_ok=True)
    os.makedirs(CARPETA_BACKUPS, exist_ok=True)


# --- Sincronización con Turso (nube) -----------------------------------
#
# USAR_TURSO empieza en False a propósito: el POS sigue funcionando IGUAL
# que hoy, con sqlite3 puro, hasta que se active después de probarlo con
# una base de Turso de prueba.
#
# La URL y el token NUNCA se escriben acá adentro ni se suben a GitHub --
# se leen de variables de entorno, así el .exe compilado no lleva ninguna
# contraseña adentro. Se configuran una vez en el PC de cada negocio
# (Panel de control > Variables de entorno en Windows, o un archivo .env
# si más adelante se agrega python-dotenv).

# En False: el POS funciona exactamente igual que hoy (sqlite3 local,
# sin nube, sin depender de internet para nada). Cambiar a True solo
# después de haber probado la conexión con una base de Turso de prueba.
USAR_TURSO = os.environ.get("POS_USAR_TURSO", "0") == "1"

# URL de la base de Turso de ESTE negocio (una distinta por negocio).
# Ejemplo: "libsql://mi-negocio-usuario.turso.io"
TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL", "")

# Token de autenticación de esa base (se genera en el panel de Turso,
# nunca se comparte ni se sube a GitHub).
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

# Cada cuánto se intenta sincronizar con la nube mientras el POS está
# abierto, en milisegundos. 60 segundos es razonable para un negocio
# chico -- no hay necesidad de que sea "en vivo al segundo".
INTERVALO_SINCRONIZACION_MS = 60_000