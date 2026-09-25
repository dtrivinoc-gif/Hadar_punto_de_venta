"""
Módulo de cajeros (vendedores).

Cada venta queda marcada con quién la hizo. La idea es que agregar un
cajero nuevo sea tan simple como agregar un producto: solo el nombre.
"""

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QCheckBox,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from db import conectar
from estilos import ESTILO_BASE, VERDE, GRIS_MUTED


# ---------------------------------------------------------------------------
# Acceso a datos
# ---------------------------------------------------------------------------

def listar_cajeros(solo_activos: bool = True):
    with conectar() as con:
        if solo_activos:
            cur = con.execute("SELECT * FROM cajeros WHERE activo = 1 ORDER BY nombre")
        else:
            cur = con.execute("SELECT * FROM cajeros ORDER BY nombre")
        return cur.fetchall()


def crear_cajero(nombre: str) -> int:
    with conectar() as con:
        cur = con.execute("INSERT INTO cajeros (nombre) VALUES (?)", (nombre.strip(),))
        return cur.lastrowid


def desactivar_cajero(cajero_id: int):
    with conectar() as con:
        con.execute("UPDATE cajeros SET activo = 0 WHERE id = ?", (cajero_id,))


def reactivar_cajero(cajero_id: int):
    with conectar() as con:
        con.execute("UPDATE cajeros SET activo = 1 WHERE id = ?", (cajero_id,))


# ---------------------------------------------------------------------------
# Diálogo de alta rápida
# ---------------------------------------------------------------------------

class DialogoCajero(QDialog):
    """Solo pide el nombre — pensado para agregar un cajero en 5 segundos
    desde la misma pantalla de venta."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cajero_id = None
        self.setWindowTitle("Agregar cajero")
        self.setMinimumWidth(280)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.campo_nombre = QLineEdit()
        self.campo_nombre.setPlaceholderText("Ej: María")
        form.addRow("Nombre", self.campo_nombre)
        layout.addLayout(form)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.setObjectName("botonSecundario")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton("Agregar")
        boton_ok.setObjectName("botonPrimario")
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self._validar_y_aceptar)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

        self.setStyleSheet(ESTILO_BASE)

    def _validar_y_aceptar(self):
        if not self.campo_nombre.text().strip():
            QMessageBox.warning(self, "Falta el nombre", "Escribe el nombre del cajero.")
            return
        self.cajero_id = crear_cajero(self.campo_nombre.text())
        self.accept()


# ---------------------------------------------------------------------------
# Pantalla de gestión (para dar de baja a alguien que ya no trabaja ahí)
# ---------------------------------------------------------------------------

class VentanaCajeros(QWidget):

    cajeros_cambiaron = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._armar_ui()
        self.recargar()

    def _armar_ui(self):
        self.setStyleSheet(ESTILO_BASE)
        layout = QVBoxLayout(self)

        barra = QHBoxLayout()
        self.checkbox_mostrar_inactivos = QCheckBox("Mostrar dados de baja")
        self.checkbox_mostrar_inactivos.stateChanged.connect(self.recargar)
        barra.addWidget(self.checkbox_mostrar_inactivos)
        barra.addStretch()

        boton_agregar = QPushButton("+ Agregar cajero")
        boton_agregar.setObjectName("botonPrimario")
        boton_agregar.clicked.connect(self._agregar)
        barra.addWidget(boton_agregar)

        self.boton_baja = QPushButton("Dar de baja")
        self.boton_baja.setObjectName("botonAdvertencia")
        self.boton_baja.clicked.connect(self._dar_de_baja)
        barra.addWidget(self.boton_baja)
        layout.addLayout(barra)

        self.tabla = QTableWidget(0, 2)
        self.tabla.setHorizontalHeaderLabels(["Nombre", "Estado"])
        self.tabla.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.tabla)

    def recargar(self):
        mostrar_inactivos = self.checkbox_mostrar_inactivos.isChecked()
        cajeros = listar_cajeros(solo_activos=not mostrar_inactivos)
        self.tabla.setRowCount(len(cajeros))
        for fila, cajero in enumerate(cajeros):
            self.tabla.setItem(fila, 0, QTableWidgetItem(cajero["nombre"]))
            item_estado = QTableWidgetItem("Activo" if cajero["activo"] else "De baja")
            item_estado.setForeground(QColor(VERDE if cajero["activo"] else GRIS_MUTED))
            self.tabla.setItem(fila, 1, item_estado)
            self.tabla.item(fila, 0).setData(Qt.UserRole, cajero["id"])

    def _fila_seleccionada_id(self):
        filas = self.tabla.selectionModel().selectedRows()
        if not filas:
            return None
        return self.tabla.item(filas[0].row(), 0).data(Qt.UserRole)

    def _agregar(self):
        dialogo = DialogoCajero(self)
        if dialogo.exec() == QDialog.Accepted:
            self.recargar()
            self.cajeros_cambiaron.emit()

    def _dar_de_baja(self):
        cajero_id = self._fila_seleccionada_id()
        if cajero_id is None:
            QMessageBox.information(self, "Selecciona un cajero", "Elige un cajero de la tabla primero.")
            return
        respuesta = QMessageBox.question(
            self, "Confirmar",
            "¿Dar de baja a este cajero? No aparecerá más en el selector de venta, "
            "pero sus ventas anteriores se conservan."
        )
        if respuesta == QMessageBox.Yes:
            desactivar_cajero(cajero_id)
            self.recargar()
            self.cajeros_cambiaron.emit()