"""
Exportación de datos del POS.

Dos maneras de sacar los datos, para dos necesidades distintas:

  1. Copiar la base de datos completa (.db) — sirve como respaldo o para
     que otra persona (ej. otro programador) la abra directo con SQLite.
  2. Exportar a Excel (.xlsx) con varias hojas — pensado específicamente
     para cargarlo en Hadar, con el mismo espíritu del export de varias
     hojas que ya usa pos_simulador.
"""

import shutil
from datetime import datetime

import pandas as pd
from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel, QFileDialog, QMessageBox

from config import RUTA_BASE_DATOS
from db import conectar


# ---------------------------------------------------------------------------
# Lógica de exportación
# ---------------------------------------------------------------------------

def copiar_base_datos(ruta_destino: str):
    """Copia el archivo .db tal cual está. La forma más simple y directa
    de sacar TODOS los datos sin transformar nada."""
    shutil.copy2(RUTA_BASE_DATOS, ruta_destino)


TABLAS_A_EXPORTAR = [
    ("Ventas", "SELECT * FROM ventas"),
    ("Detalle_Venta", "SELECT * FROM detalle_venta"),
    ("Productos", "SELECT * FROM productos"),
    ("Cajeros", "SELECT * FROM cajeros"),
    ("Clientes", "SELECT * FROM clientes"),
    ("Abonos_Fiado", "SELECT * FROM abonos_fiado"),
    ("Caja_Sesion", "SELECT * FROM caja_sesion"),
    ("Movimientos_Caja_Vecina", "SELECT * FROM movimientos_caja_vecina"),
]


def exportar_a_excel(ruta_destino: str):
    """
    Genera un Excel con una hoja por tabla, listo para cargar en Hadar.
    Cada hoja es una tabla plana (sin joins), para que Hadar pueda armar
    sus propias relaciones con el módulo de ontología.
    """
    with conectar() as con:
        with pd.ExcelWriter(ruta_destino, engine="openpyxl") as escritor:
            for nombre_hoja, consulta in TABLAS_A_EXPORTAR:
                dataframe = pd.read_sql_query(consulta, con)
                dataframe.to_excel(escritor, sheet_name=nombre_hoja, index=False)


def nombre_archivo_sugerido(extension: str) -> str:
    marca_tiempo = datetime.now().strftime("%Y-%m-%d_%H%M")
    return f"pos_export_{marca_tiempo}.{extension}"


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------

class WidgetExportar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "Exporta los datos del POS para respaldarlos o para cargarlos en Hadar."
        ))

        boton_excel = QPushButton("Exportar a Excel (para Hadar)")
        boton_excel.setMinimumHeight(44)
        boton_excel.clicked.connect(self._exportar_excel)
        layout.addWidget(boton_excel)

        boton_db = QPushButton("Copiar base de datos completa (.db)")
        boton_db.setMinimumHeight(44)
        boton_db.clicked.connect(self._copiar_db)
        layout.addWidget(boton_db)

        layout.addStretch()

    def _exportar_excel(self):
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar a Excel",
            nombre_archivo_sugerido("xlsx"),
            "Excel (*.xlsx)"
        )
        if not ruta:
            return
        try:
            exportar_a_excel(ruta)
        except Exception as error:
            QMessageBox.critical(self, "Error al exportar", str(error))
            return
        QMessageBox.information(self, "Listo", f"Datos exportados a:\n{ruta}")

    def _copiar_db(self):
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Copiar base de datos",
            nombre_archivo_sugerido("db"),
            "Base de datos SQLite (*.db)"
        )
        if not ruta:
            return
        try:
            copiar_base_datos(ruta)
        except Exception as error:
            QMessageBox.critical(self, "Error al copiar", str(error))
            return
        QMessageBox.information(self, "Listo", f"Base de datos copiada a:\n{ruta}")
