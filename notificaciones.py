"""
Envío de reportes por correo.

Mismo patrón que notificaciones.py de Hadar: una cuenta de Gmail dedicada
como remitente, con "contraseña de aplicación" (no la contraseña normal
de la cuenta -- se genera en myaccount.google.com con la verificación en
2 pasos activada). El envío corre en un hilo aparte para no trabar la
ventana del POS mientras se conecta a Gmail.

A diferencia de la versión de Hadar (que arma el mensaje a partir de una
regla de alarma), acá se manda un asunto y un cuerpo directos -- el texto
del reporte que ya armó reportes.py.
"""

import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QVBoxLayout, QLabel, QLineEdit, QCheckBox,
    QPushButton, QMessageBox,
)

from config import CARPETA_DATOS

CORREO_REMITENTE_POR_DEFECTO = "hadar.notificaciones@gmail.com"
SERVIDOR_SMTP = "smtp.gmail.com"
PUERTO_SMTP = 587


def ruta_config_correo():
    return os.path.join(CARPETA_DATOS, "pos_correo_config.json")


def cargar_configuracion():
    ruta = ruta_config_correo()
    config_por_defecto = {
        "habilitado": False,
        "correo_remitente": CORREO_REMITENTE_POR_DEFECTO,
        "contrasena_app": "",
        "correo_destino_predeterminado": "",
        # a diferencia de Hadar: acá se agrega la opción de mandar el
        # reporte solo cuando se cierra la caja, sin que nadie tenga que
        # acordarse de apretar "Enviar por correo" a mano
        "enviar_automatico_al_cerrar_caja": False,
    }
    if not os.path.exists(ruta):
        return config_por_defecto
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            guardado = json.load(f)
        config_por_defecto.update(guardado)
        return config_por_defecto
    except (json.JSONDecodeError, OSError):
        return config_por_defecto


def guardar_configuracion(config):
    os.makedirs(CARPETA_DATOS, exist_ok=True)
    with open(ruta_config_correo(), "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _enviar_smtp(config, destinatario, asunto, cuerpo, ruta_adjunto=None):
    if ruta_adjunto:
        mensaje = MIMEMultipart()
        mensaje.attach(MIMEText(cuerpo, "plain", "utf-8"))
        with open(ruta_adjunto, "rb") as archivo:
            adjunto = MIMEApplication(archivo.read(), _subtype="pdf")
        adjunto.add_header(
            "Content-Disposition", "attachment", filename=os.path.basename(ruta_adjunto)
        )
        mensaje.attach(adjunto)
    else:
        mensaje = MIMEText(cuerpo, "plain", "utf-8")

    mensaje["Subject"] = asunto
    mensaje["From"] = config["correo_remitente"]
    mensaje["To"] = destinatario

    with smtplib.SMTP(SERVIDOR_SMTP, PUERTO_SMTP, timeout=15) as servidor:
        servidor.starttls()
        servidor.login(config["correo_remitente"], config["contrasena_app"])
        servidor.sendmail(config["correo_remitente"], [destinatario], mensaje.as_string())


class CorreoWorker(QObject):
    """Manda un único correo. Vive en su propio QThread -- ver
    disparar_envio_correo() más abajo."""
    resultado = Signal(bool, str)

    def __init__(self, config, destinatario, asunto, cuerpo, ruta_adjunto=None):
        super().__init__()
        self.config = config
        self.destinatario = destinatario
        self.asunto = asunto
        self.cuerpo = cuerpo
        self.ruta_adjunto = ruta_adjunto

    def run(self):
        try:
            _enviar_smtp(self.config, self.destinatario, self.asunto, self.cuerpo, self.ruta_adjunto)
            self.resultado.emit(True, "")
        except Exception as exc:
            self.resultado.emit(False, str(exc))


class _PuenteResultado(QObject):
    """Puente para que el callback de resultado se ejecute siempre en el
    hilo principal. Sin esto, conectar la señal directamente a una
    función común hace que Qt la ejecute en el hilo de envío --
    territorio inestable para tocar la interfaz."""
    listo = Signal(bool, str)

    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self.listo.connect(self._ejecutar)

    def _ejecutar(self, ok, error):
        if self._callback:
            self._callback(ok, error)


def disparar_envio_correo(host, destinatario, asunto, cuerpo, on_resultado=None,
                           verificar_habilitado=True, ruta_adjunto=None):
    """Manda un correo en un hilo aparte. `ruta_adjunto`, si se pasa, es la
    ruta a un archivo (ej. un PDF) que se adjunta al correo.

    `host` es cualquier objeto Qt que se mantenga vivo mientras el POS
    esté abierto (la pantalla de Reportes o Arqueo sirven) -- necesita
    poder colgarle una lista `_hilos_correo`, donde se guarda una
    referencia al hilo mientras dura el envío; si no se guarda en algún
    lado, Python los destruye a mitad de camino y el correo nunca sale.

    `verificar_habilitado=False` se usa para el botón "correo de prueba":
    ahí queremos poder probar la contraseña ANTES de decidir activar el
    interruptor de verdad.
    """
    if not hasattr(host, "_hilos_correo"):
        host._hilos_correo = []

    config = cargar_configuracion()
    if (verificar_habilitado and not config.get("habilitado")) or not config.get("contrasena_app"):
        if on_resultado:
            on_resultado(False, "Notificaciones por correo no configuradas.")
        return

    hilo = QThread()
    worker = CorreoWorker(config, destinatario, asunto, cuerpo, ruta_adjunto)
    worker.moveToThread(hilo)
    hilo.started.connect(worker.run)

    puente = _PuenteResultado(on_resultado) if on_resultado else None

    def _al_terminar(ok, error):
        if puente is not None:
            puente.listo.emit(ok, error)
        hilo.quit()

    worker.resultado.connect(_al_terminar)
    worker.resultado.connect(worker.deleteLater)
    hilo.finished.connect(hilo.deleteLater)

    referencia = (hilo, worker, puente)

    def _liberar():
        if referencia in host._hilos_correo:
            host._hilos_correo.remove(referencia)

    hilo.finished.connect(_liberar)

    host._hilos_correo.append(referencia)
    hilo.start()


def enviar_reporte_por_correo(host, fecha_texto, cuerpo_reporte, on_resultado=None,
                               verificar_habilitado=True, ruta_adjunto=None):
    """Atajo para el caso de uso de reportes.py / arqueo.py: arma el
    asunto solo y manda al correo destino predeterminado guardado en la
    configuración."""
    config = cargar_configuracion()
    destino = config.get("correo_destino_predeterminado")
    if not destino:
        if on_resultado:
            on_resultado(False, "No hay correo de destino configurado.")
        return
    asunto = f"Reporte POS — {fecha_texto}"
    disparar_envio_correo(host, destino, asunto, cuerpo_reporte, on_resultado,
                           verificar_habilitado, ruta_adjunto)


# ----------------------------------------------------------------------------
# Diálogo de configuración
# ----------------------------------------------------------------------------

class DialogoConfiguracionCorreo(QDialog):
    """Configurar la cuenta que manda los reportes y el correo de destino.
    Se guarda en un archivo local (pos_correo_config.json), no en el
    código -- así la contraseña de aplicación no queda pegada en ningún
    archivo que se comparta o se suba a GitHub."""

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.setWindowTitle("Configurar envío de reportes por correo")
        self.setMinimumWidth(420)
        config = cargar_configuracion()

        layout = QVBoxLayout(self)

        self.checkbox_habilitado = QCheckBox("Permitir el envío de reportes por correo")
        self.checkbox_habilitado.setChecked(config.get("habilitado", False))
        layout.addWidget(self.checkbox_habilitado)

        self.checkbox_automatico = QCheckBox(
            "Enviar el reporte del día automáticamente al cerrar la caja"
        )
        self.checkbox_automatico.setChecked(config.get("enviar_automatico_al_cerrar_caja", False))
        layout.addWidget(self.checkbox_automatico)

        layout.addWidget(QLabel("Correo remitente (la cuenta que manda los reportes):"))
        self.remitente_edit = QLineEdit(config.get("correo_remitente", CORREO_REMITENTE_POR_DEFECTO))
        layout.addWidget(self.remitente_edit)

        layout.addWidget(QLabel(
            "Contraseña de aplicación de Gmail\n"
            "(no es tu contraseña normal -- se genera en myaccount.google.com,\n"
            "con la verificación en 2 pasos activada primero):"
        ))
        self.contrasena_edit = QLineEdit(config.get("contrasena_app", ""))
        self.contrasena_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.contrasena_edit)

        layout.addWidget(QLabel("Correo de destino (a quién le llega el reporte):"))
        self.destino_edit = QLineEdit(config.get("correo_destino_predeterminado", ""))
        self.destino_edit.setPlaceholderText("dueno-del-negocio@ejemplo.com")
        layout.addWidget(self.destino_edit)

        self.btn_probar = QPushButton("Guardar y enviar correo de prueba")
        self.btn_probar.clicked.connect(self._enviar_prueba)
        layout.addWidget(self.btn_probar)

        botones = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        botones.accepted.connect(self._guardar_y_aceptar)
        botones.rejected.connect(self.reject)
        layout.addWidget(botones)

    def _config_actual(self):
        return {
            "habilitado": self.checkbox_habilitado.isChecked(),
            "enviar_automatico_al_cerrar_caja": self.checkbox_automatico.isChecked(),
            "correo_remitente": self.remitente_edit.text().strip() or CORREO_REMITENTE_POR_DEFECTO,
            "contrasena_app": self.contrasena_edit.text().strip(),
            "correo_destino_predeterminado": self.destino_edit.text().strip(),
        }

    def _enviar_prueba(self):
        destino = self.destino_edit.text().strip()
        if not destino:
            QMessageBox.information(self, "Falta el correo", "Completá el correo de destino primero.")
            return
        if not self.contrasena_edit.text().strip():
            QMessageBox.information(self, "Falta la contraseña", "Completá la contraseña de aplicación primero.")
            return

        guardar_configuracion(self._config_actual())
        self.btn_probar.setEnabled(False)
        self.btn_probar.setText("Enviando...")

        def _resultado(ok, error):
            self.btn_probar.setEnabled(True)
            self.btn_probar.setText("Guardar y enviar correo de prueba")
            if ok:
                QMessageBox.information(self, "Listo", "Correo de prueba enviado. Revisá tu bandeja de entrada.")
            else:
                QMessageBox.warning(self, "No se pudo enviar", error or "Error desconocido.")

        disparar_envio_correo(
            self.host, destino, "Prueba de configuración — POS",
            "Si recibiste esto, la configuración de correo del POS funciona.",
            on_resultado=_resultado, verificar_habilitado=False,
        )

    def _guardar_y_aceptar(self):
        guardar_configuracion(self._config_actual())
        self.accept()