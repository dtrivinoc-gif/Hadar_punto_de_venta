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

# Nombre del negocio (se puede usar en tickets, títulos de ventana, etc.)
NOMBRE_NEGOCIO = "Negocio"


def asegurar_carpetas():
    """Crea las carpetas de datos y backups si no existen todavía."""
    os.makedirs(CARPETA_DATOS, exist_ok=True)
    os.makedirs(CARPETA_BACKUPS, exist_ok=True)
