"""
Pestaña de Ajustes.

Por ahora tiene una sola cosa: corregir la hora que usa el POS, sin tocar
el reloj de Windows (ver tiempo.py para el porqué). Si más adelante se
agregan otros ajustes del negocio, este es el lugar natural para vivir.
"""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton,
    QDateTimeEdit, QGroupBox, QMessageBox,
)
from PySide6.QtCore import Qt, QTimer, QDateTime

from tiempo import ahora, desfase_actual_segundos, establecer_hora_correcta


class WidgetAjustes(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._armar_ui()
        self._actualizar_reloj_en_vivo()

        # refresca la hora mostrada cada segundo, para que se vea que corre
        self.temporizador = QTimer(self)
        self.temporizador.timeout.connect(self._actualizar_reloj_en_vivo)
        self.temporizador.start(1000)

    def _armar_ui(self):
        layout = QVBoxLayout(self)

        grupo = QGroupBox("Hora del sistema")
        layout_grupo = QVBoxLayout(grupo)

        self.etiqueta_hora_actual = QLabel()
        self.etiqueta_hora_actual.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout_grupo.addWidget(self.etiqueta_hora_actual)

        self.etiqueta_desfase = QLabel()
        self.etiqueta_desfase.setStyleSheet("color: #666;")
        layout_grupo.addWidget(self.etiqueta_desfase)

        layout_grupo.addWidget(QLabel(
            "Esta es la hora que usa el POS en cada venta, fiado y movimiento "
            "de caja. Si la ves atrasada o adelantada, corrígela abajo -- "
            "no hace falta cambiar la hora de Windows."
        ))

        form = QFormLayout()
        self.campo_hora_correcta = QDateTimeEdit()
        self.campo_hora_correcta.setDisplayFormat("dd-MM-yyyy HH:mm:ss")
        self.campo_hora_correcta.setDateTime(QDateTime.currentDateTime())
        self.campo_hora_correcta.setCalendarPopup(True)
        form.addRow("Hora real (ahora mismo)", self.campo_hora_correcta)
        layout_grupo.addLayout(form)

        fila_botones = QHBoxLayout()
        boton_ahora = QPushButton("Usar la hora actual del PC")
        boton_ahora.setToolTip("Rellena el campo con la hora del PC, por si solo necesitas quitar la corrección.")
        boton_ahora.clicked.connect(lambda: self.campo_hora_correcta.setDateTime(QDateTime.currentDateTime()))
        fila_botones.addWidget(boton_ahora)

        boton_guardar = QPushButton("Guardar hora correcta")
        boton_guardar.setMinimumHeight(40)
        boton_guardar.clicked.connect(self._guardar_correccion)
        fila_botones.addWidget(boton_guardar)

        layout_grupo.addLayout(fila_botones)
        layout.addWidget(grupo)
        layout.addStretch(1)

    def _actualizar_reloj_en_vivo(self):
        self.etiqueta_hora_actual.setText(ahora().strftime("%A %d-%m-%Y  %H:%M:%S"))
        desfase = desfase_actual_segundos()
        if desfase == 0:
            self.etiqueta_desfase.setText("Sin corrección aplicada (usa la hora del PC tal cual).")
        else:
            signo = "adelantada" if desfase > 0 else "atrasada"
            minutos = abs(desfase) // 60
            segundos = abs(desfase) % 60
            self.etiqueta_desfase.setText(
                f"Corrección activa: {minutos} min {segundos} s {signo} respecto al reloj del PC."
            )

    def _guardar_correccion(self):
        fecha_hora_correcta = self.campo_hora_correcta.dateTime().toPython()
        establecer_hora_correcta(fecha_hora_correcta)
        self._actualizar_reloj_en_vivo()
        QMessageBox.information(
            self, "Hora corregida",
            "Listo. Desde ahora todas las ventas, fiados y movimientos van a usar esta hora corregida."
        )
