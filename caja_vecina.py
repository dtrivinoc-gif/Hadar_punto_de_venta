"""
Módulo de caja vecina.

Registra los movimientos de dinero de caja vecina (depósitos, retiros,
comisión que se queda el negocio) dentro de la sesión de caja abierta.
No mezcla este dinero con las ventas de productos del negocio — por eso
es una tabla aparte (movimientos_caja_vecina) en vez de usar 'ventas'.
"""

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QDoubleSpinBox, QLineEdit, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
)
from PySide6.QtGui import QColor

from db import conectar
from arqueo import sesion_abierta
from estilos import (
    ESTILO_BASE, ACENTO, VERDE, NARANJA, ROJO, GRIS_MUTED,
    seleccionar_texto_al_enfocar,
)


TIPOS_MOVIMIENTO = [
    ("deposito", "Depósito (cliente deposita)"),
    ("retiro", "Retiro (cliente retira)"),
    ("comision", "Comisión del negocio"),
]


# ---------------------------------------------------------------------------
# Acceso a datos
# ---------------------------------------------------------------------------

def listar_movimientos(sesion_id: int):
    with conectar() as con:
        cur = con.execute(
            "SELECT * FROM movimientos_caja_vecina WHERE caja_sesion_id = ? "
            "ORDER BY id DESC",
            (sesion_id,),
        )
        return cur.fetchall()


def registrar_movimiento(sesion_id: int, tipo: str, monto: float, descripcion: str = None):
    with conectar() as con:
        con.execute(
            """INSERT INTO movimientos_caja_vecina
               (caja_sesion_id, tipo, monto, descripcion)
               VALUES (?, ?, ?, ?)""",
            (sesion_id, tipo, monto, descripcion),
        )


# ---------------------------------------------------------------------------
# Diálogo para registrar un movimiento
# ---------------------------------------------------------------------------

class DialogoMovimientoCajaVecina(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Movimiento de caja vecina")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.combo_tipo = QComboBox()
        for valor, etiqueta in TIPOS_MOVIMIENTO:
            self.combo_tipo.addItem(etiqueta, userData=valor)
        form.addRow("Tipo", self.combo_tipo)

        self.campo_monto = QDoubleSpinBox()
        self.campo_monto.setMaximum(10_000_000)
        self.campo_monto.setDecimals(0)
        self.campo_monto.setPrefix("$ ")
        form.addRow("Monto", self.campo_monto)

        self.campo_descripcion = QLineEdit()
        self.campo_descripcion.setPlaceholderText("Opcional")
        form.addRow("Nota", self.campo_descripcion)

        layout.addLayout(form)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.setObjectName("botonSecundario")
        boton_cancelar.clicked.connect(self.reject)
        self.boton_ok = QPushButton("Registrar")
        self.boton_ok.setDefault(True)
        self.boton_ok.clicked.connect(self._validar_y_aceptar)
        botones.addWidget(boton_cancelar)
        botones.addWidget(self.boton_ok)
        layout.addLayout(botones)

        self.setStyleSheet(ESTILO_BASE)
        self.combo_tipo.currentIndexChanged.connect(self._actualizar_color_boton)
        self._actualizar_color_boton()
        seleccionar_texto_al_enfocar(self.campo_monto)

    def _actualizar_color_boton(self):
        """El botón de registrar cambia de color según lo que significa el
        movimiento: verde si entra plata a caja vecina (depósito), naranja
        si sale (retiro o comisión) -- mismo lenguaje que el resto del POS."""
        tipo = self.combo_tipo.currentData()
        self.boton_ok.setObjectName("botonExito" if tipo == "deposito" else "botonAdvertencia")
        self.boton_ok.style().unpolish(self.boton_ok)
        self.boton_ok.style().polish(self.boton_ok)

    def _validar_y_aceptar(self):
        if self.campo_monto.value() <= 0:
            QMessageBox.warning(self, "Monto inválido", "El monto debe ser mayor a cero.")
            return
        self.accept()

    def resultado(self):
        return (
            self.combo_tipo.currentData(),
            self.campo_monto.value(),
            self.campo_descripcion.text().strip() or None,
        )


# ---------------------------------------------------------------------------
# Pantalla de caja vecina
# ---------------------------------------------------------------------------

class WidgetCajaVecina(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._armar_ui()
        self.recargar()

    def _armar_ui(self):
        self.setStyleSheet(ESTILO_BASE)
        layout = QVBoxLayout(self)

        self.etiqueta_saldo = QLabel()
        self.etiqueta_saldo.setStyleSheet("font-size: 24px; font-weight: 800;")
        layout.addWidget(self.etiqueta_saldo)

        self.boton_agregar = QPushButton("+ Registrar movimiento")
        self.boton_agregar.setObjectName("botonPrimario")
        self.boton_agregar.setMinimumHeight(44)
        self.boton_agregar.clicked.connect(self._agregar)
        layout.addWidget(self.boton_agregar)

        self.tabla = QTableWidget(0, 4)
        self.tabla.setHorizontalHeaderLabels(["Fecha/hora", "Tipo", "Monto", "Nota"])
        self.tabla.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.tabla)

    def recargar(self):
        sesion = sesion_abierta()
        etiquetas_tipo = dict(TIPOS_MOVIMIENTO)

        if sesion is None:
            self.etiqueta_saldo.setText("No hay caja abierta.")
            self.etiqueta_saldo.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {GRIS_MUTED};")
            self.boton_agregar.setEnabled(False)
            self.tabla.setRowCount(0)
            return

        self.boton_agregar.setEnabled(True)
        self._sesion_id = sesion["id"]

        movimientos = listar_movimientos(sesion["id"])
        self.tabla.setRowCount(len(movimientos))
        saldo = sesion["monto_apertura_vecina"]
        for fila, movimiento in enumerate(movimientos):
            es_deposito = movimiento["tipo"] == "deposito"
            color = QColor(VERDE if es_deposito else NARANJA)
            signo = "+" if es_deposito else "-"

            self.tabla.setItem(fila, 0, QTableWidgetItem(movimiento["fecha_hora"]))
            self.tabla.setItem(fila, 1, QTableWidgetItem(etiquetas_tipo.get(movimiento["tipo"], movimiento["tipo"])))

            item_monto = QTableWidgetItem(f"{signo} $ {movimiento['monto']:,.0f}")
            item_monto.setForeground(color)
            self.tabla.setItem(fila, 2, item_monto)

            self.tabla.setItem(fila, 3, QTableWidgetItem(movimiento["descripcion"] or ""))

            if es_deposito:
                saldo += movimiento["monto"]
            else:  # retiro o comision, ambos restan de la caja vecina
                saldo -= movimiento["monto"]

        color_saldo = ROJO if saldo < 0 else ACENTO
        self.etiqueta_saldo.setText(f"Saldo caja vecina: $ {saldo:,.0f}")
        self.etiqueta_saldo.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {color_saldo};")

    def _agregar(self):
        sesion = sesion_abierta()
        if sesion is None:
            QMessageBox.information(self, "Caja cerrada", "Abre la caja primero, en la pestaña Arqueo.")
            return
        dialogo = DialogoMovimientoCajaVecina(self)
        if dialogo.exec() != QDialog.Accepted:
            return
        tipo, monto, descripcion = dialogo.resultado()
        registrar_movimiento(sesion["id"], tipo, monto, descripcion)
        self.recargar()