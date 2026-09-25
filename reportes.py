"""
Módulo de reportes.

Genera un resumen de un día: quién vendió y cuánto, cómo abrió y cerró
cada caja, y quién quedó fiando o abonando. A propósito NO incluye qué
productos se vendieron -- ese detalle vive en la base de datos; este
reporte es para tener un pantallazo rápido del día, no un detalle línea
por línea.
"""

import os
import tempfile

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTextEdit,
    QDateEdit, QComboBox, QFileDialog, QMessageBox, QDialog, QGroupBox,
)
from PySide6.QtCore import QDate
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter

from db import conectar
from notificaciones import disparar_envio_correo, DialogoConfiguracionCorreo, cargar_configuracion
from contactos import listar_contactos, agregar_contacto, eliminar_contacto, DialogoContacto
from estilos import ESTILO_BASE, BORDE


# ---------------------------------------------------------------------------
# Datos
# ---------------------------------------------------------------------------

def generar_reporte_dia(fecha: str) -> dict:
    """
    fecha: 'YYYY-MM-DD'. Junta todo lo necesario para el reporte de ese
    día -- sin ningún detalle de qué productos se vendieron.
    """
    with conectar() as con:
        sesiones = con.execute(
            "SELECT * FROM caja_sesion WHERE date(fecha_apertura) = ? ORDER BY id",
            (fecha,),
        ).fetchall()
        ids_sesiones = [s["id"] for s in sesiones]

        cajeros = []
        if ids_sesiones:
            marcadores = ",".join("?" for _ in ids_sesiones)
            cajeros = con.execute(
                f"""SELECT c.nombre AS nombre, COUNT(v.id) AS cantidad_ventas,
                           COALESCE(SUM(v.total), 0) AS total_vendido
                    FROM ventas v
                    JOIN cajeros c ON c.id = v.cajero_id
                    WHERE v.caja_sesion_id IN ({marcadores}) AND v.anulada = 0
                    GROUP BY c.id
                    ORDER BY total_vendido DESC""",
                ids_sesiones,
            ).fetchall()

        # clientes con CUALQUIER actividad de fiado ese día (pidieron y/o abonaron)
        clientes_con_actividad = con.execute(
            """SELECT DISTINCT cl.id, cl.nombre FROM clientes cl
               WHERE cl.id IN (
                   SELECT cliente_id FROM ventas
                   WHERE metodo_pago = 'fiado' AND date(fecha_hora) = ? AND cliente_id IS NOT NULL
                   UNION
                   SELECT cliente_id FROM abonos_fiado WHERE date(fecha_hora) = ?
               )
               ORDER BY cl.nombre""",
            (fecha, fecha),
        ).fetchall()

        fiados = []
        for cliente in clientes_con_actividad:
            pedido_hoy = con.execute(
                """SELECT COALESCE(SUM(total), 0) AS s FROM ventas
                   WHERE cliente_id = ? AND metodo_pago = 'fiado'
                     AND date(fecha_hora) = ? AND anulada = 0""",
                (cliente["id"], fecha),
            ).fetchone()["s"]
            abonado_hoy = con.execute(
                """SELECT COALESCE(SUM(monto), 0) AS s FROM abonos_fiado
                   WHERE cliente_id = ? AND date(fecha_hora) = ?""",
                (cliente["id"], fecha),
            ).fetchone()["s"]
            # deuda histórica = todo lo fiado alguna vez, menos todo lo abonado
            # alguna vez -- no solo lo de hoy
            total_fiado_historico = con.execute(
                """SELECT COALESCE(SUM(total), 0) AS s FROM ventas
                   WHERE cliente_id = ? AND metodo_pago = 'fiado' AND anulada = 0""",
                (cliente["id"],),
            ).fetchone()["s"]
            total_abonado_historico = con.execute(
                "SELECT COALESCE(SUM(monto), 0) AS s FROM abonos_fiado WHERE cliente_id = ?",
                (cliente["id"],),
            ).fetchone()["s"]
            fiados.append({
                "nombre": cliente["nombre"],
                "pedido_hoy": pedido_hoy,
                "abonado_hoy": abonado_hoy,
                "deuda_historica": total_fiado_historico - total_abonado_historico,
            })

    return {
        "fecha": fecha,
        "sesiones": [dict(s) for s in sesiones],
        "cajeros": [dict(c) for c in cajeros],
        "fiados": fiados,
    }


# ---------------------------------------------------------------------------
# Formato de texto
# ---------------------------------------------------------------------------

def formatear_reporte_texto(datos: dict, nota: str = "") -> str:
    lineas = [f"REPORTE DEL DÍA — {datos['fecha']}", "=" * 42]

    if not datos["sesiones"]:
        lineas.append("\nNo se abrió caja este día.")
    else:
        varias = len(datos["sesiones"]) > 1
        for indice, sesion in enumerate(datos["sesiones"], start=1):
            etiqueta = f" (sesión {indice})" if varias else ""

            lineas.append(f"\nCaja negocio{etiqueta}:")
            lineas.append(f"  Empezó con: $ {sesion['monto_apertura_negocio']:,.0f}")
            if sesion["cerrada"]:
                lineas.append(f"  Terminó con: $ {sesion['monto_cierre_negocio']:,.0f}")
            else:
                lineas.append("  Terminó con: (todavía abierta)")

            lineas.append(f"\nCaja vecina{etiqueta}:")
            lineas.append(f"  Empezó con: $ {sesion['monto_apertura_vecina']:,.0f}")
            if sesion["cerrada"]:
                lineas.append(f"  Terminó con: $ {sesion['monto_cierre_vecina']:,.0f}")
            else:
                lineas.append("  Terminó con: (todavía abierta)")

    lineas.append("\n" + "-" * 42)
    lineas.append("CAJEROS DEL DÍA")
    if not datos["cajeros"]:
        lineas.append("  (sin ventas registradas)")
    else:
        for cajero in datos["cajeros"]:
            lineas.append(
                f"  {cajero['nombre']}: $ {cajero['total_vendido']:,.0f} "
                f"({cajero['cantidad_ventas']} ventas)"
            )
        total_vendido = sum(c["total_vendido"] for c in datos["cajeros"])
        total_ventas = sum(c["cantidad_ventas"] for c in datos["cajeros"])
        lineas.append(f"  {'-' * 30}")
        lineas.append(f"  TOTAL VENDIDO: $ {total_vendido:,.0f} ({total_ventas} ventas)")

    lineas.append("\n" + "-" * 42)
    lineas.append("FIADO")
    if not datos["fiados"]:
        lineas.append("  (sin movimientos de fiado este día)")
    else:
        for persona in datos["fiados"]:
            partes_hoy = []
            if persona["pedido_hoy"] > 0:
                partes_hoy.append(f"pidió $ {persona['pedido_hoy']:,.0f}")
            if persona["abonado_hoy"] > 0:
                partes_hoy.append(f"abonó $ {persona['abonado_hoy']:,.0f}")
            texto_hoy = " y ".join(partes_hoy) if partes_hoy else "sin movimiento"
            lineas.append(
                f"  {persona['nombre']}: {texto_hoy} hoy "
                f"— debe en total $ {persona['deuda_historica']:,.0f}"
            )

    if nota.strip():
        lineas.append("\n" + "-" * 42)
        lineas.append("NOTA:")
        lineas.append(f"  {nota.strip()}")

    return "\n".join(lineas)


def generar_pdf_reporte(texto: str, ruta_destino: str, titulo: str = "Reporte POS"):
    """
    Convierte el texto ya formateado del reporte en un PDF, usando las
    herramientas de impresión que ya trae Qt (QTextDocument + QPrinter) --
    no hace falta agregar ninguna librería nueva al proyecto solo para esto.
    """
    import html as _html
    texto_escapado = _html.escape(texto)
    html = (
        f"<h2 style='font-family: Arial; color: #1F2430;'>{_html.escape(titulo)}</h2>"
        f"<pre style='font-family: Consolas, monospace; font-size: 11pt; "
        f"white-space: pre-wrap;'>{texto_escapado}</pre>"
    )

    documento = QTextDocument()
    documento.setHtml(html)

    impresora = QPrinter(QPrinter.HighResolution)
    impresora.setOutputFormat(QPrinter.PdfFormat)
    impresora.setOutputFileName(ruta_destino)
    documento.print_(impresora)


# ---------------------------------------------------------------------------
# Pantalla
# ---------------------------------------------------------------------------

class WidgetReportes(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ultimos_datos = None
        self._armar_ui()

    def _armar_ui(self):
        self.setStyleSheet(ESTILO_BASE)
        layout_principal = QHBoxLayout(self)

        # ---------------- columna izquierda: el reporte en sí ----------------
        columna_izquierda = QVBoxLayout()

        titulo = QLabel("Reporte del día")
        titulo.setStyleSheet("font-size: 16px; font-weight: 700;")
        columna_izquierda.addWidget(titulo)

        self.texto_reporte = QTextEdit()
        self.texto_reporte.setReadOnly(True)
        self.texto_reporte.setStyleSheet(
            f"QTextEdit {{ font-family: Consolas, monospace; font-size: 13px; "
            f"border: 1px solid {BORDE}; border-radius: 10px; background: white; }}"
        )
        self.texto_reporte.setPlaceholderText("Elige una fecha y presiona \"Generar reporte\" →")
        columna_izquierda.addWidget(self.texto_reporte, stretch=1)

        etiqueta_nota = QLabel("Nota (opcional) — algo que no quedó en el reporte automático:")
        etiqueta_nota.setStyleSheet("font-size: 12px;")
        columna_izquierda.addWidget(etiqueta_nota)

        self.campo_nota = QTextEdit()
        self.campo_nota.setPlaceholderText(
            "Ej: se rompió la balanza a las 3pm, faltó cargar una venta del turno tarde..."
        )
        self.campo_nota.setMaximumHeight(70)
        self.campo_nota.setStyleSheet(
            f"QTextEdit {{ border: 1px solid {BORDE}; border-radius: 10px; background: white; }}"
        )
        self.campo_nota.textChanged.connect(self._actualizar_texto)
        columna_izquierda.addWidget(self.campo_nota)

        layout_principal.addLayout(columna_izquierda, stretch=2)

        # ---------------- columna derecha: controles agrupados ----------------
        columna_derecha = QVBoxLayout()
        columna_derecha.setSpacing(14)

        grupo_generar = QGroupBox("Generar")
        layout_generar = QVBoxLayout(grupo_generar)
        layout_generar.addWidget(QLabel("Fecha"))
        self.selector_fecha = QDateEdit()
        self.selector_fecha.setCalendarPopup(True)
        self.selector_fecha.setDate(QDate.currentDate())
        layout_generar.addWidget(self.selector_fecha)
        boton_generar = QPushButton("Generar reporte")
        boton_generar.setObjectName("botonPrimario")
        boton_generar.setMinimumHeight(40)
        boton_generar.clicked.connect(self._generar)
        layout_generar.addWidget(boton_generar)
        columna_derecha.addWidget(grupo_generar)

        grupo_guardar = QGroupBox("Guardar")
        layout_guardar = QVBoxLayout(grupo_guardar)
        boton_guardar = QPushButton("Guardar como archivo de texto")
        boton_guardar.setObjectName("botonSecundario")
        boton_guardar.clicked.connect(self._guardar)
        layout_guardar.addWidget(boton_guardar)
        columna_derecha.addWidget(grupo_guardar)

        grupo_correo = QGroupBox("Enviar por correo")
        layout_correo = QVBoxLayout(grupo_correo)

        layout_correo.addWidget(QLabel("Destinatario"))
        self.combo_destinatario = QComboBox()
        layout_correo.addWidget(self.combo_destinatario)

        fila_contactos = QHBoxLayout()
        boton_agregar_contacto = QPushButton("+ Contacto")
        boton_agregar_contacto.setObjectName("botonSecundario")
        boton_agregar_contacto.clicked.connect(self._agregar_contacto)
        fila_contactos.addWidget(boton_agregar_contacto)

        boton_quitar_contacto = QPushButton("Quitar")
        boton_quitar_contacto.setObjectName("botonAdvertencia")
        boton_quitar_contacto.clicked.connect(self._quitar_contacto)
        fila_contactos.addWidget(boton_quitar_contacto)
        layout_correo.addLayout(fila_contactos)

        boton_enviar = QPushButton("Enviar por correo")
        boton_enviar.setObjectName("botonExito")
        boton_enviar.setMinimumHeight(40)
        boton_enviar.clicked.connect(self._enviar_por_correo)
        layout_correo.addWidget(boton_enviar)

        boton_configurar_correo = QPushButton("Configurar correo…")
        boton_configurar_correo.setObjectName("botonSecundario")
        boton_configurar_correo.clicked.connect(self._abrir_configuracion_correo)
        layout_correo.addWidget(boton_configurar_correo)

        columna_derecha.addWidget(grupo_correo)
        columna_derecha.addStretch(1)

        layout_principal.addLayout(columna_derecha, stretch=1)

        self._recargar_contactos()

    def _generar(self):
        fecha = self.selector_fecha.date().toString("yyyy-MM-dd")
        self._ultimos_datos = generar_reporte_dia(fecha)
        self._actualizar_texto()

    def _actualizar_texto(self):
        """Redibuja el reporte con los últimos datos consultados más la
        nota actual -- se llama al generar y cada vez que se edita la
        nota, sin volver a golpear la base de datos."""
        if self._ultimos_datos is None:
            return
        nota = self.campo_nota.toPlainText()
        self.texto_reporte.setPlainText(formatear_reporte_texto(self._ultimos_datos, nota))

    def _recargar_contactos(self):
        """Reconstruye el combo de contactos guardados, tratando de
        mantener el que estaba elegido (útil tras agregar uno nuevo)."""
        correo_actual = self.combo_destinatario.currentData()
        self.combo_destinatario.clear()
        for contacto in listar_contactos():
            self.combo_destinatario.addItem(
                f"{contacto['nombre']} <{contacto['correo']}>", userData=contacto["correo"]
            )
        if correo_actual is not None:
            indice = self.combo_destinatario.findData(correo_actual)
            if indice >= 0:
                self.combo_destinatario.setCurrentIndex(indice)

    def _agregar_contacto(self):
        dialogo = DialogoContacto(self)
        if dialogo.exec() != QDialog.Accepted:
            return
        nombre, correo = dialogo.resultado()
        agregar_contacto(nombre, correo)
        self._recargar_contactos()
        indice = self.combo_destinatario.findData(correo)
        if indice >= 0:
            self.combo_destinatario.setCurrentIndex(indice)

    def _quitar_contacto(self):
        indice = self.combo_destinatario.currentIndex()
        if indice < 0:
            QMessageBox.information(self, "Nada que quitar", "No hay ningún contacto seleccionado.")
            return
        nombre = self.combo_destinatario.currentText()
        respuesta = QMessageBox.question(
            self, "Confirmar", f"¿Quitar «{nombre}» de la lista de contactos?"
        )
        if respuesta == QMessageBox.Yes:
            eliminar_contacto(indice)
            self._recargar_contactos()

    def _enviar_por_correo(self):
        texto = self.texto_reporte.toPlainText().strip()
        if not texto:
            QMessageBox.information(self, "Nada que enviar", "Genera un reporte primero.")
            return

        config = cargar_configuracion()
        if not config.get("habilitado") or not config.get("contrasena_app"):
            QMessageBox.information(
                self, "Correo no configurado",
                "Primero configura el envío de correo con el botón 'Configurar correo…'."
            )
            return

        destino = self.combo_destinatario.currentData()
        if not destino:
            QMessageBox.information(
                self, "Falta el destinatario",
                "Agrega un contacto con '+ Contacto' y selecciónalo antes de enviar."
            )
            return

        fecha = self.selector_fecha.date().toString("yyyy-MM-dd")
        asunto = f"Reporte POS — {fecha}"

        ruta_pdf = os.path.join(tempfile.gettempdir(), f"reporte_pos_{fecha}.pdf")
        try:
            generar_pdf_reporte(texto, ruta_pdf, titulo=f"Reporte del día — {fecha}")
        except Exception as error:
            QMessageBox.critical(self, "Error al generar el PDF", str(error))
            return

        cuerpo = f"Se adjunta el reporte del día {fecha}."

        def _resultado(ok, error):
            if ok:
                QMessageBox.information(self, "Enviado", "El reporte se mandó por correo en PDF.")
            else:
                QMessageBox.warning(self, "No se pudo enviar", error or "Error desconocido.")

        disparar_envio_correo(
            self, destino, asunto, cuerpo, on_resultado=_resultado, ruta_adjunto=ruta_pdf
        )

    def _abrir_configuracion_correo(self):
        DialogoConfiguracionCorreo(self, parent=self).exec()

    def _guardar(self):
        if not self.texto_reporte.toPlainText().strip():
            QMessageBox.information(self, "Nada que guardar", "Genera un reporte primero.")
            return
        fecha = self.selector_fecha.date().toString("yyyy-MM-dd")
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar reporte", f"reporte_{fecha}.txt", "Texto (*.txt)"
        )
        if not ruta:
            return
        try:
            with open(ruta, "w", encoding="utf-8") as archivo:
                archivo.write(self.texto_reporte.toPlainText())
        except Exception as error:
            QMessageBox.critical(self, "Error al guardar", str(error))
            return
        QMessageBox.information(self, "Listo", f"Reporte guardado en:\n{ruta}")