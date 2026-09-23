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
    QDoubleSpinBox, QPushButton, QLabel, QMessageBox, QGroupBox, QFrame,
)
from PySide6.QtCore import Signal, Qt

from db import conectar
from estilos import (
    ESTILO_BASE, VERDE, VERDE_SUAVE, ROJO,
    GRIS_MUTED, BORDE, badge_estado, seleccionar_texto_al_enfocar,
)


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
        boton_cancelar.setObjectName("botonSecundario")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton("Abrir caja")
        boton_ok.setObjectName("botonPrimario")
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self.accept)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

        self.setStyleSheet(ESTILO_BASE)
        seleccionar_texto_al_enfocar(self.campo_negocio)

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
        boton_cancelar.setObjectName("botonSecundario")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton("Cerrar caja")
        boton_ok.setObjectName("botonAdvertencia")
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self.accept)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

        self.setStyleSheet(ESTILO_BASE)

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
        self.setStyleSheet(ESTILO_BASE)
        layout = QVBoxLayout(self)

        grupo = QGroupBox("Estado de caja")
        layout_grupo = QVBoxLayout(grupo)

        self.etiqueta_badge = QLabel()
        self.etiqueta_badge.setAlignment(Qt.AlignLeft)
        layout_grupo.addWidget(self.etiqueta_badge)

        self.etiqueta_desde = QLabel()
        self.etiqueta_desde.setStyleSheet(f"color: {GRIS_MUTED}; font-size: 12px;")
        layout_grupo.addWidget(self.etiqueta_desde)

        tarjetas = QHBoxLayout()
        self.tarjeta_negocio = self._crear_tarjeta_caja("Caja negocio")
        self.tarjeta_vecina = self._crear_tarjeta_caja("Caja vecina")
        tarjetas.addWidget(self.tarjeta_negocio["marco"])
        tarjetas.addWidget(self.tarjeta_vecina["marco"])
        layout_grupo.addLayout(tarjetas)

        layout.addWidget(grupo)

        botones = QHBoxLayout()
        self.boton_abrir = QPushButton("Abrir caja")
        self.boton_abrir.setObjectName("botonPrimario")
        self.boton_abrir.setMinimumHeight(44)
        self.boton_abrir.clicked.connect(self._abrir)
        botones.addWidget(self.boton_abrir)

        self.boton_cerrar = QPushButton("Cerrar caja")
        self.boton_cerrar.setObjectName("botonAdvertencia")
        self.boton_cerrar.setMinimumHeight(44)
        self.boton_cerrar.clicked.connect(self._cerrar)
        botones.addWidget(self.boton_cerrar)
        layout.addLayout(botones)

        layout.addStretch()

    def _crear_tarjeta_caja(self, titulo: str) -> dict:
        """Tarjeta con borde redondeado mostrando apertura + esperado de
        una caja (negocio o vecina). Devuelve las etiquetas para poder
        actualizarlas después desde recargar()."""
        marco = QFrame()
        marco.setStyleSheet(f"QFrame {{ background: #F8F9FC; border: 1px solid {BORDE}; border-radius: 10px; }}")
        layout_tarjeta = QVBoxLayout(marco)

        etiqueta_titulo = QLabel(titulo)
        etiqueta_titulo.setStyleSheet(f"color: {GRIS_MUTED}; font-size: 12px; font-weight: 700; border: none;")
        layout_tarjeta.addWidget(etiqueta_titulo)

        etiqueta_apertura = QLabel()
        etiqueta_apertura.setStyleSheet("font-size: 12px; border: none;")
        layout_tarjeta.addWidget(etiqueta_apertura)

        etiqueta_esperado = QLabel()
        etiqueta_esperado.setStyleSheet("font-size: 20px; font-weight: 800; border: none;")
        layout_tarjeta.addWidget(etiqueta_esperado)

        return {
            "marco": marco, "apertura": etiqueta_apertura, "esperado": etiqueta_esperado,
        }

    def recargar(self):
        sesion = sesion_abierta()
        if sesion is None:
            self.etiqueta_badge.setText("Caja cerrada")
            self.etiqueta_badge.setStyleSheet(badge_estado("Caja cerrada", "#F1F2F6", GRIS_MUTED))
            self.etiqueta_desde.setText("Ábrela para empezar a vender.")
            for tarjeta in (self.tarjeta_negocio, self.tarjeta_vecina):
                tarjeta["apertura"].setText("—")
                tarjeta["esperado"].setText("$ 0")
            self.boton_abrir.setEnabled(True)
            self.boton_cerrar.setEnabled(False)
        else:
            esperado_negocio, esperado_vecina = calcular_esperado(sesion["id"])

            self.etiqueta_badge.setText("Caja abierta")
            self.etiqueta_badge.setStyleSheet(badge_estado("Caja abierta", VERDE_SUAVE, VERDE))
            self.etiqueta_desde.setText(f"Desde {sesion['fecha_apertura']}")

            self.tarjeta_negocio["apertura"].setText(
                f"Apertura: $ {sesion['monto_apertura_negocio']:,.0f}"
            )
            self.tarjeta_negocio["esperado"].setText(f"$ {esperado_negocio:,.0f}")

            self.tarjeta_vecina["apertura"].setText(
                f"Apertura: $ {sesion['monto_apertura_vecina']:,.0f}"
            )
            self.tarjeta_vecina["esperado"].setText(f"$ {esperado_vecina:,.0f}")

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

    @staticmethod
    def _linea_diferencia(etiqueta: str, resumen: dict, sufijo: str) -> str:
        """Una línea del resumen de cierre, con la diferencia en verde si
        sobra o cuadra exacto, y en rojo si falta plata."""
        diferencia = resumen[f"diferencia_{sufijo}"]
        color = VERDE if diferencia >= 0 else ROJO
        texto_diferencia = f"cuadra exacto" if diferencia == 0 else (
            f"sobran $ {diferencia:,.0f}" if diferencia > 0 else f"faltan $ {abs(diferencia):,.0f}"
        )
        return (
            f"<b>{etiqueta}</b> — esperado $ {resumen[f'esperado_{sufijo}']:,.0f}, "
            f"contado $ {resumen[f'contado_{sufijo}']:,.0f}<br>"
            f"<span style='color:{color}; font-weight:700;'>{texto_diferencia}</span>"
        )

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
            self._linea_diferencia("Negocio", resumen, "negocio")
            + "<br><br>"
            + self._linea_diferencia("Caja vecina", resumen, "vecina")
        )
        cuadro = QMessageBox(self)
        cuadro.setWindowTitle("Caja cerrada")
        cuadro.setTextFormat(Qt.RichText)
        cuadro.setText(mensaje)
        cuadro.exec()

        self.recargar()
        self.caja_cambio.emit()