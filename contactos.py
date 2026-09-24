"""
Libreta de contactos para el envío de reportes.

Guarda pares (nombre, correo) en un archivo local -- así, al mandar un
reporte, la cajera elige de una lista en vez de escribir el correo a
mano cada vez (evita errores de tipeo y ahorra tiempo).

Esto es independiente de la configuración de notificaciones.py: ahí se
guarda el correo REMITENTE (la cuenta que manda) y el destino por
defecto del envío automático al cerrar caja; acá se guardan los posibles
DESTINATARIOS entre los que elegir al mandar un reporte a mano.
"""

import json
import os

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QMessageBox,
)

from config import CARPETA_DATOS


def ruta_contactos():
    return os.path.join(CARPETA_DATOS, "pos_contactos.json")


def listar_contactos():
    """Devuelve una lista de dicts {"nombre":..., "correo":...}, en el
    orden en que se agregaron."""
    ruta = ruta_contactos()
    if not os.path.exists(ruta):
        return []
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _guardar_contactos(lista):
    os.makedirs(CARPETA_DATOS, exist_ok=True)
    with open(ruta_contactos(), "w", encoding="utf-8") as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)


def agregar_contacto(nombre: str, correo: str):
    contactos = listar_contactos()
    contactos.append({"nombre": nombre.strip(), "correo": correo.strip()})
    _guardar_contactos(contactos)


def eliminar_contacto(indice: int):
    contactos = listar_contactos()
    if 0 <= indice < len(contactos):
        contactos.pop(indice)
        _guardar_contactos(contactos)


# ---------------------------------------------------------------------------
# Diálogo para agregar un contacto
# ---------------------------------------------------------------------------

class DialogoContacto(QDialog):
    """Alta rápida de un contacto: solo nombre y correo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agregar contacto")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("Ej: Don Pedro (dueño)")
        form.addRow("Nombre", self.campo_nombre)

        self.campo_correo = QLineEdit()
        self.campo_correo.setPlaceholderText("correo@ejemplo.com")
        form.addRow("Correo", self.campo_correo)

        layout.addLayout(form)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton("Guardar")
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self._validar_y_aceptar)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

    def _validar_y_aceptar(self):
        nombre = self.campo_nombre.text().strip()
        correo = self.campo_correo.text().strip()
        if not nombre or not correo:
            QMessageBox.warning(self, "Faltan datos", "Completa el nombre y el correo.")
            return
        if "@" not in correo or "." not in correo.split("@")[-1]:
            QMessageBox.warning(self, "Correo inválido", "Revisa el correo ingresado.")
            return
        self.accept()

    def resultado(self):
        return self.campo_nombre.text().strip(), self.campo_correo.text().strip()
