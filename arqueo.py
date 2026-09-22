"""
Apertura y cierre de caja (arqueo).

Acá vive la sesión de caja "de verdad": se abre con montos contados a mano,
durante el día se van sumando ventas y movimientos de caja vecina, y al
cerrar se compara lo que "debería haber" (esperado, calculado) contra lo
que la cajera cuenta físicamente (contado), mostrando la diferencia.

Importante: el arqueo de efectivo solo considera ventas pagadas en
efectivo (metodo_pago = 'efectivo'). Las ventas con débito/crédito/
transferencia no mueven el dinero físico de la caja.
"""

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QDoubleSpinBox, QPushButton, QLabel, QMessageBox, QGroupBox,
)
from PySide6.QtCore import Signal

from db import conectar


# ---------------------------------------------------------------------------
# Acceso a datos / lógica
# ---------------------------------------------------------------------------

def sesion_abierta():
    """Devuelve la fila de caja_sesion abierta actualmente, o None si no hay ninguna."""
    with conectar() as con:
        cur = con.execute(
            "SELECT * FROM caja_sesion WHERE cerrada = 0 ORDER BY id DESC LIMIT 1"
        )
        return cur.fetchone()


def abrir_caja(monto_negocio: float, monto_vecina: float) -> int:
    """Abre una caja nueva. Falla si ya hay una abierta (hay que cerrarla primero)."""
    if sesion_abierta() is not None:
        raise ValueError("Ya hay una caja abierta. Ciérrala antes de abrir una nueva.")
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO caja_sesion (monto_apertura_negocio, monto_apertura_vecina) "
            "VALUES (?, ?)",
            (monto_negocio, monto_vecina),
        )
        return cur.lastrowid


def calcular_esperado(sesion_id: int):
    """
    Calcula cuánto efectivo debería haber en cada caja, sumando el monto de
    apertura más los movimientos de la sesión:

    - Caja negocio: apertura + ventas en efectivo con origen 'venta_negocio'
    - Caja vecina:  apertura + ventas en efectivo con origen 'caja_vecina'
                     + depósitos - retiros - comisión
    """
    with conectar() as con:
        sesion = con.execute(
            "SELECT * FROM caja_sesion WHERE id = ?", (sesion_id,)
        ).fetchone()

        def _sumar_ventas(origen):
            fila = con.execute(
                """SELECT COALESCE(SUM(total), 0) AS s FROM ventas
                   WHERE caja_sesion_id = ? AND origen = ?
                     AND metodo_pago = 'efectivo' AND anulada = 0""",
                (sesion_id, origen),
            ).fetchone()
            return fila["s"]

        def _sumar_movimientos(tipo):
            fila = con.execute(
                """SELECT COALESCE(SUM(monto), 0) AS s FROM movimientos_caja_vecina
                   WHERE caja_sesion_id = ? AND tipo = ?""",
                (sesion_id, tipo),
            ).fetchone()
            return fila["s"]

        efectivo_negocio = _sumar_ventas("venta_negocio")
        efectivo_vecina_ventas = _sumar_ventas("caja_vecina")
        depositos = _sumar_movimientos("deposito")
        retiros = _sumar_movimientos("retiro")
        comisiones = _sumar_movimientos("comision")

    esperado_negocio = sesion["monto_apertura_negocio"] + efectivo_negocio
    esperado_vecina = (
        sesion["monto_apertura_vecina"] + efectivo_vecina_ventas
        + depositos - retiros - comisiones
    )
    return esperado_negocio, esperado_vecina


def cerrar_caja(sesion_id: int, monto_contado_negocio: float, monto_contado_vecina: float) -> dict:
    """Cierra la sesión y devuelve un resumen con esperado, contado y diferencia."""
    esperado_negocio, esperado_vecina = calcular_esperado(sesion_id)

    with conectar() as con:
        con.execute(
            """UPDATE caja_sesion
               SET fecha_cierre = datetime('now', 'localtime'),
                   monto_cierre_negocio = ?, monto_cierre_vecina = ?, cerrada = 1
               WHERE id = ?""",
            (monto_contado_negocio, monto_contado_vecina, sesion_id),
        )

    return {
        "esperado_negocio": esperado_negocio,
        "esperado_vecina": esperado_vecina,
        "contado_negocio": monto_contado_negocio,
        "contado_vecina": monto_contado_vecina,
        "diferencia_negocio": monto_contado_negocio - esperado_negocio,
        "diferencia_vecina": monto_contado_vecina - esperado_vecina,
    }


# ---------------------------------------------------------------------------
# Diálogos
# ---------------------------------------------------------------------------

class DialogoAperturaCaja(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Abrir caja")
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.campo_negocio = QDoubleSpinBox()
        self.campo_negocio.setMaximum(10_000_000)
        self.campo_negocio.setDecimals(0)
        self.campo_negocio.setPrefix("$ ")
        form.addRow("Monto inicial negocio", self.campo_negocio)

        self.campo_vecina = QDoubleSpinBox()
        self.campo_vecina.setMaximum(10_000_000)
        self.campo_vecina.setDecimals(0)
        self.campo_vecina.setPrefix("$ ")
        form.addRow("Monto inicial caja vecina", self.campo_vecina)

        layout.addLayout(form)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton("Abrir caja")
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self.accept)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

    def montos(self):
        return self.campo_negocio.value(), self.campo_vecina.value()


class DialogoCierreCaja(QDialog):

    def __init__(self, parent, sesion_id: int):
        super().__init__(parent)
        self.sesion_id = sesion_id
        self.setWindowTitle("Cerrar caja")
        self.setMinimumWidth(360)

        esperado_negocio, esperado_vecina = calcular_esperado(sesion_id)
        self.esperado_negocio = esperado_negocio
        self.esperado_vecina = esperado_vecina

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(f"Esperado en caja negocio: $ {esperado_negocio:,.0f}"))
        self.campo_contado_negocio = QDoubleSpinBox()
        self.campo_contado_negocio.setMaximum(10_000_000)
        self.campo_contado_negocio.setDecimals(0)
        self.campo_contado_negocio.setPrefix("$ ")
        self.campo_contado_negocio.setValue(esperado_negocio)
        layout.addWidget(self.campo_contado_negocio)

        layout.addWidget(QLabel(f"Esperado en caja vecina: $ {esperado_vecina:,.0f}"))
        self.campo_contado_vecina = QDoubleSpinBox()
        self.campo_contado_vecina.setMaximum(10_000_000)
        self.campo_contado_vecina.setDecimals(0)
        self.campo_contado_vecina.setPrefix("$ ")
        self.campo_contado_vecina.setValue(esperado_vecina)
        layout.addWidget(self.campo_contado_vecina)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton("Cerrar caja")
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self.accept)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

    def montos_contados(self):
        return self.campo_contado_negocio.value(), self.campo_contado_vecina.value()


# ---------------------------------------------------------------------------
# Pantalla de arqueo
# ---------------------------------------------------------------------------

class WidgetArqueo(QWidget):
    """Muestra el estado de la caja actual y permite abrirla o cerrarla."""

    # se emite al abrir o cerrar caja, para que otras pantallas (venta,
    # caja vecina) se actualicen
    caja_cambio = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._armar_ui()
        self.recargar()

    def _armar_ui(self):
        layout = QVBoxLayout(self)

        grupo = QGroupBox("Estado de caja")
        layout_grupo = QVBoxLayout(grupo)
        self.etiqueta_estado = QLabel()
        layout_grupo.addWidget(self.etiqueta_estado)
        layout.addWidget(grupo)

        botones = QHBoxLayout()
        self.boton_abrir = QPushButton("Abrir caja")
        self.boton_abrir.clicked.connect(self._abrir)
        botones.addWidget(self.boton_abrir)

        self.boton_cerrar = QPushButton("Cerrar caja")
        self.boton_cerrar.clicked.connect(self._cerrar)
        botones.addWidget(self.boton_cerrar)
        layout.addLayout(botones)

        layout.addStretch()

    def recargar(self):
        sesion = sesion_abierta()
        if sesion is None:
            self.etiqueta_estado.setText("No hay caja abierta. Ábrela para empezar a vender.")
            self.boton_abrir.setEnabled(True)
            self.boton_cerrar.setEnabled(False)
        else:
            esperado_negocio, esperado_vecina = calcular_esperado(sesion["id"])
            self.etiqueta_estado.setText(
                f"Caja abierta desde {sesion['fecha_apertura']}\n"
                f"Apertura negocio: $ {sesion['monto_apertura_negocio']:,.0f}  |  "
                f"Esperado ahora: $ {esperado_negocio:,.0f}\n"
                f"Apertura caja vecina: $ {sesion['monto_apertura_vecina']:,.0f}  |  "
                f"Esperado ahora: $ {esperado_vecina:,.0f}"
            )
            self.boton_abrir.setEnabled(False)
            self.boton_cerrar.setEnabled(True)

    def _abrir(self):
        dialogo = DialogoAperturaCaja(self)
        if dialogo.exec() != QDialog.Accepted:
            return
        monto_negocio, monto_vecina = dialogo.montos()
        abrir_caja(monto_negocio, monto_vecina)
        self.recargar()
        self.caja_cambio.emit()

    def _cerrar(self):
        sesion = sesion_abierta()
        if sesion is None:
            return
        dialogo = DialogoCierreCaja(self, sesion["id"])
        if dialogo.exec() != QDialog.Accepted:
            return
        contado_negocio, contado_vecina = dialogo.montos_contados()
        resumen = cerrar_caja(sesion["id"], contado_negocio, contado_vecina)

        mensaje = (
            f"Negocio — esperado $ {resumen['esperado_negocio']:,.0f}, "
            f"contado $ {resumen['contado_negocio']:,.0f}, "
            f"diferencia $ {resumen['diferencia_negocio']:,.0f}\n\n"
            f"Caja vecina — esperado $ {resumen['esperado_vecina']:,.0f}, "
            f"contado $ {resumen['contado_vecina']:,.0f}, "
            f"diferencia $ {resumen['diferencia_vecina']:,.0f}"
        )
        QMessageBox.information(self, "Caja cerrada", mensaje)
        self.recargar()
        self.caja_cambio.emit()
