"""
Fiado: ventas a crédito para clientes conocidos del almacén.

La deuda se lleva por cliente, no por venta puntual: cada venta fiada se
registra en `ventas` (metodo_pago='fiado', cliente_id=<quién>), y lo que
el cliente debe es simplemente:

    deuda = suma(total de sus ventas fiadas) - suma(sus abonos)

Este archivo tiene:
  - Funciones de datos: clientes, deuda, abonos
  - DialogoSeleccionarCliente: se usa desde venta.py al cobrar "fiado"
  - WidgetFiado: la pestaña "Fiado" con el listado de clientes y su deuda
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QDialog, QFormLayout, QMessageBox, QListWidget, QListWidgetItem,
    QDoubleSpinBox, QTextEdit,
)
from PySide6.QtCore import Qt

from db import conectar
from arqueo import sesion_abierta
from tiempo import ahora_texto


# ---------------------------------------------------------------------------
# Funciones de datos
# ---------------------------------------------------------------------------

def listar_clientes(solo_activos: bool = True):
    with conectar() as con:
        if solo_activos:
            filas = con.execute(
                "SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre"
            ).fetchall()
        else:
            filas = con.execute("SELECT * FROM clientes ORDER BY nombre").fetchall()
        return [dict(fila) for fila in filas]


def buscar_clientes(texto: str):
    """Búsqueda simple por nombre, para el diálogo de selección al fiar."""
    with conectar() as con:
        filas = con.execute(
            "SELECT * FROM clientes WHERE activo = 1 AND nombre LIKE ? ORDER BY nombre",
            (f"%{texto}%",),
        ).fetchall()
        return [dict(fila) for fila in filas]


def crear_cliente(nombre: str, telefono: str = "", notas: str = "") -> int:
    with conectar() as con:
        cursor = con.execute(
            "INSERT INTO clientes (nombre, telefono, notas) VALUES (?, ?, ?)",
            (nombre.strip(), telefono.strip(), notas.strip()),
        )
        return cursor.lastrowid


def deuda_cliente(cliente_id: int) -> float:
    with conectar() as con:
        total_fiado = con.execute(
            """SELECT COALESCE(SUM(total), 0) AS suma FROM ventas
               WHERE cliente_id = ? AND metodo_pago = 'fiado' AND anulada = 0""",
            (cliente_id,),
        ).fetchone()["suma"]
        total_abonado = con.execute(
            "SELECT COALESCE(SUM(monto), 0) AS suma FROM abonos_fiado WHERE cliente_id = ?",
            (cliente_id,),
        ).fetchone()["suma"]
        return total_fiado - total_abonado


def listar_clientes_con_saldo(solo_deudores: bool = False):
    """Todos los clientes activos junto con lo que deben (puede ser $0).
    Ordenados por deuda descendente y, a igual deuda, por nombre.
    Si solo_deudores=True, se filtran los que están al día."""
    resultado = []
    for cliente in listar_clientes(solo_activos=True):
        deuda = deuda_cliente(cliente["id"])
        if solo_deudores and deuda <= 0:
            continue
        cliente["deuda"] = deuda
        resultado.append(cliente)
    resultado.sort(key=lambda c: (-c["deuda"], c["nombre"]))
    return resultado


def historial_fiado_cliente(cliente_id: int):
    """Ventas fiadas (con sus productos) y abonos de un cliente, mezclados
    y ordenados por fecha, para que el dueño pueda ver el detalle completo."""
    with conectar() as con:
        ventas = con.execute(
            """SELECT id, fecha_hora, total FROM ventas
               WHERE cliente_id = ? AND metodo_pago = 'fiado' AND anulada = 0
               ORDER BY fecha_hora""",
            (cliente_id,),
        ).fetchall()
        abonos = con.execute(
            "SELECT fecha_hora, monto, nota FROM abonos_fiado WHERE cliente_id = ? ORDER BY fecha_hora",
            (cliente_id,),
        ).fetchall()

        productos_por_venta = {}
        for venta in ventas:
            filas = con.execute(
                "SELECT nombre_producto, cantidad FROM detalle_venta WHERE venta_id = ?",
                (venta["id"],),
            ).fetchall()
            productos_por_venta[venta["id"]] = [dict(f) for f in filas]

    movimientos = []
    for v in ventas:
        productos = productos_por_venta[v["id"]]
        detalle = ", ".join(
            p["nombre_producto"] if p["cantidad"] == 1 else f"{p['nombre_producto']} (x{p['cantidad']:g})"
            for p in productos
        )
        movimientos.append({
            "fecha": v["fecha_hora"], "tipo": "Venta fiada", "detalle": detalle, "monto": v["total"],
        })
    for a in abonos:
        tipo = "Abono" + (f" ({a['nota']})" if a["nota"] else "")
        movimientos.append({"fecha": a["fecha_hora"], "tipo": tipo, "detalle": "", "monto": -a["monto"]})
    movimientos.sort(key=lambda m: m["fecha"])
    return movimientos


def registrar_abono(cliente_id: int, monto: float, nota: str = ""):
    """Registra un pago del cliente contra su deuda acumulada.

    IMPORTANTE (pendiente): este dinero entra físicamente a la caja, así
    que arqueo.py debería sumarlo al efectivo esperado de la sesión -- hoy
    no tengo ese archivo, así que este gancho queda listo pero no conectado.
    """
    sesion = sesion_abierta()
    if sesion is None:
        raise ValueError("No hay una caja abierta; abre la caja antes de registrar un abono.")

    with conectar() as con:
        con.execute(
            """INSERT INTO abonos_fiado (cliente_id, caja_sesion_id, fecha_hora, monto, nota)
               VALUES (?, ?, ?, ?, ?)""",
            (cliente_id, sesion["id"], ahora_texto(), monto, nota.strip()),
        )


def registrar_fiado_directo(cliente_id: int, monto: float, nota: str = ""):
    """Registra una deuda de fiado sin pasar por el carrito de Venta.

    Sirve para dos casos: cargar una deuda que el cliente ya traía de antes
    de usar el sistema, o un fiado informal que no corresponde a productos
    del catálogo (ej. "le presté $5.000"). Queda guardado igual que
    cualquier otra venta fiada (misma tabla `ventas`), con una única línea
    de detalle, así que cuenta igual para la deuda total del cliente.
    """
    sesion = sesion_abierta()
    if sesion is None:
        raise ValueError("No hay una caja abierta; abre la caja antes de registrar un fiado.")

    with conectar() as con:
        cursor_venta = con.execute(
            """INSERT INTO ventas (caja_sesion_id, fecha_hora, origen, total, metodo_pago, cliente_id)
               VALUES (?, ?, 'venta_negocio', ?, 'fiado', ?)""",
            (sesion["id"], ahora_texto(), monto, cliente_id),
        )
        venta_id = cursor_venta.lastrowid
        con.execute(
            """INSERT INTO detalle_venta
               (venta_id, producto_id, nombre_producto, cantidad, precio_unitario, subtotal, es_venta_libre)
               VALUES (?, NULL, ?, 1, ?, ?, 1)""",
            (venta_id, nota.strip() or "Fiado directo", monto, monto),
        )


# ---------------------------------------------------------------------------
# Diálogo: elegir o crear cliente (usado desde venta.py al cobrar "fiado")
# ---------------------------------------------------------------------------

class DialogoSeleccionarCliente(QDialog):
    """Buscar un cliente existente por nombre, o crear uno nuevo al vuelo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("¿A nombre de quién se fía?")
        self.setMinimumWidth(340)
        self.cliente_id = None

        layout = QVBoxLayout(self)

        self.campo_buscar = QLineEdit()
        self.campo_buscar.setPlaceholderText("Escribe el nombre del cliente…")
        self.campo_buscar.textChanged.connect(self._buscar)
        self.campo_buscar.returnPressed.connect(self._manejar_enter)
        layout.addWidget(self.campo_buscar)

        self.lista = QListWidget()
        self.lista.itemDoubleClicked.connect(lambda _: self._confirmar_existente())
        layout.addWidget(self.lista, stretch=1)

        boton_nuevo = QPushButton("+ Cliente nuevo con este nombre")
        boton_nuevo.clicked.connect(self._crear_nuevo)
        layout.addWidget(boton_nuevo)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        boton_elegir = QPushButton("Elegir")
        boton_elegir.setDefault(True)
        boton_elegir.clicked.connect(self._confirmar_existente)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_elegir)
        layout.addLayout(botones)

        self._buscar("")

    def _buscar(self, texto):
        self.lista.clear()
        clientes = buscar_clientes(texto) if texto.strip() else listar_clientes()
        for cliente in clientes:
            item = QListWidgetItem(cliente["nombre"])
            item.setData(Qt.UserRole, cliente["id"])
            self.lista.addItem(item)

    def _manejar_enter(self):
        """Enter en el campo de búsqueda: si hay un solo resultado, lo elige
        directo; si no hay ninguno, ofrece crearlo con ese nombre. Con varios
        resultados no hace nada -- ahí el usuario elige a mano cuál es."""
        if self.lista.count() == 1:
            self.lista.setCurrentRow(0)
            self._confirmar_existente()
        elif self.lista.count() == 0 and self.campo_buscar.text().strip():
            self._crear_nuevo()

    def _confirmar_existente(self):
        item = self.lista.currentItem()
        if item is None:
            QMessageBox.information(self, "Elige un cliente", "Selecciona un cliente de la lista, o crea uno nuevo.")
            return
        self.cliente_id = item.data(Qt.UserRole)
        self.accept()

    def _crear_nuevo(self):
        nombre = self.campo_buscar.text().strip()
        if not nombre:
            QMessageBox.information(self, "Falta el nombre", "Escribe el nombre del cliente arriba primero.")
            return
        self.cliente_id = crear_cliente(nombre)
        self.accept()


# ---------------------------------------------------------------------------
# Pestaña "Fiado"
# ---------------------------------------------------------------------------

class DialogoRegistrarAbono(QDialog):
    def __init__(self, parent, nombre_cliente: str, deuda_actual: float):
        super().__init__(parent)
        self.setWindowTitle(f"Abono de {nombre_cliente}")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Debe actualmente", QLabel(f"$ {deuda_actual:,.0f}"))

        self.campo_monto = QDoubleSpinBox()
        self.campo_monto.setMaximum(deuda_actual)
        self.campo_monto.setDecimals(0)
        self.campo_monto.setPrefix("$ ")
        self.campo_monto.setValue(deuda_actual)
        form.addRow("Monto que paga", self.campo_monto)

        self.campo_nota = QLineEdit()
        self.campo_nota.setPlaceholderText("Opcional")
        form.addRow("Nota", self.campo_nota)

        layout.addLayout(form)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton("Registrar abono")
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self.accept)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

    def resultado(self):
        return self.campo_monto.value(), self.campo_nota.text().strip()


class DialogoFiarDirecto(QDialog):
    """Fiar un monto libre, sin pasar por el carrito de Venta."""

    def __init__(self, parent, nombre_cliente: str, deuda_actual: float):
        super().__init__(parent)
        self.setWindowTitle(f"Fiar a {nombre_cliente}")
        layout = QVBoxLayout(self)
        form = QFormLayout()

        form.addRow("Debe actualmente", QLabel(f"$ {deuda_actual:,.0f}"))

        self.campo_monto = QDoubleSpinBox()
        self.campo_monto.setMaximum(10_000_000)
        self.campo_monto.setDecimals(0)
        self.campo_monto.setPrefix("$ ")
        form.addRow("Monto a fiar", self.campo_monto)

        self.campo_nota = QLineEdit()
        self.campo_nota.setPlaceholderText("Ej: pan y leche, o deuda anterior")
        form.addRow("¿Por qué es? (opcional)", self.campo_nota)

        layout.addLayout(form)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton("Registrar fiado")
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self.accept)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

    def resultado(self):
        return self.campo_monto.value(), self.campo_nota.text().strip()


class WidgetFiado(QWidget):
    """Pestaña principal de fiado: quién debe, cuánto, y registrar abonos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._armar_ui()
        self.recargar()

    def _armar_ui(self):
        layout = QVBoxLayout(self)

        titulo = QLabel("Clientes")
        titulo.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(titulo)

        self.campo_buscar_cliente = QLineEdit()
        self.campo_buscar_cliente.setPlaceholderText("Buscar cliente por nombre…")
        self.campo_buscar_cliente.textChanged.connect(lambda texto: self.recargar(filtro=texto))
        layout.addWidget(self.campo_buscar_cliente)

        self.lista_clientes = QListWidget()
        self.lista_clientes.currentItemChanged.connect(self._mostrar_historial)
        layout.addWidget(self.lista_clientes, stretch=1)

        self.texto_historial = QTextEdit()
        self.texto_historial.setReadOnly(True)
        self.texto_historial.setPlaceholderText("Selecciona un cliente para ver su historial de fiado y abonos.")
        layout.addWidget(self.texto_historial, stretch=1)

        fila_botones = QHBoxLayout()
        boton_fiar_directo = QPushButton("Fiar directo (sin carrito)")
        boton_fiar_directo.setMinimumHeight(44)
        boton_fiar_directo.clicked.connect(self._fiar_directo)
        fila_botones.addWidget(boton_fiar_directo)

        boton_abono = QPushButton("Registrar abono")
        boton_abono.setMinimumHeight(44)
        boton_abono.clicked.connect(self._registrar_abono)
        fila_botones.addWidget(boton_abono)

        boton_nuevo_cliente = QPushButton("+ Nuevo cliente")
        boton_nuevo_cliente.clicked.connect(self._nuevo_cliente)
        fila_botones.addWidget(boton_nuevo_cliente)

        layout.addLayout(fila_botones)

    def recargar(self, seleccionar_cliente_id=None, filtro=""):
        self.lista_clientes.clear()
        item_a_seleccionar = None
        filtro = filtro.strip().lower()
        for cliente in listar_clientes_con_saldo():
            if filtro and filtro not in cliente["nombre"].lower():
                continue
            texto_deuda = f"$ {cliente['deuda']:,.0f}" if cliente["deuda"] > 0 else "al día"
            item = QListWidgetItem(f"{cliente['nombre']} — {texto_deuda}")
            item.setData(Qt.UserRole, cliente["id"])
            item.setData(Qt.UserRole + 1, cliente["nombre"])
            item.setData(Qt.UserRole + 2, cliente["deuda"])
            self.lista_clientes.addItem(item)
            if cliente["id"] == seleccionar_cliente_id:
                item_a_seleccionar = item

        if item_a_seleccionar is not None:
            self.lista_clientes.setCurrentItem(item_a_seleccionar)
        else:
            self.texto_historial.clear()

    def _mostrar_historial(self, item, _anterior=None):
        if item is None:
            self.texto_historial.clear()
            return
        cliente_id = item.data(Qt.UserRole)
        movimientos = historial_fiado_cliente(cliente_id)
        lineas = []
        for m in movimientos:
            lineas.append(f"{m['fecha']}  —  {m['tipo']}  —  $ {m['monto']:,.0f}")
            if m.get("detalle"):
                lineas.append(f"        {m['detalle']}")
        self.texto_historial.setPlainText("\n".join(lineas) or "Sin movimientos.")

    def _registrar_abono(self):
        item = self.lista_clientes.currentItem()
        if item is None:
            QMessageBox.information(self, "Elige un cliente", "Selecciona un cliente de la lista primero.")
            return
        cliente_id = item.data(Qt.UserRole)
        nombre = item.data(Qt.UserRole + 1)
        deuda = item.data(Qt.UserRole + 2)

        dialogo = DialogoRegistrarAbono(self, nombre, deuda)
        if dialogo.exec() != QDialog.Accepted:
            return
        monto, nota = dialogo.resultado()
        if monto <= 0:
            return

        try:
            registrar_abono(cliente_id, monto, nota)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo registrar", str(error))
            return

        self.recargar(seleccionar_cliente_id=cliente_id, filtro=self.campo_buscar_cliente.text())

    def _fiar_directo(self):
        dialogo_cliente = DialogoSeleccionarCliente(self)
        dialogo_cliente.setWindowTitle("¿A nombre de quién se fía?")
        if dialogo_cliente.exec() != QDialog.Accepted:
            return
        cliente_id = dialogo_cliente.cliente_id

        nombre = next((c["nombre"] for c in listar_clientes() if c["id"] == cliente_id), "cliente")
        deuda_actual = deuda_cliente(cliente_id)

        dialogo_monto = DialogoFiarDirecto(self, nombre, deuda_actual)
        if dialogo_monto.exec() != QDialog.Accepted:
            return
        monto, nota = dialogo_monto.resultado()
        if monto <= 0:
            return

        try:
            registrar_fiado_directo(cliente_id, monto, nota)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo registrar", str(error))
            return

        self.recargar(seleccionar_cliente_id=cliente_id, filtro=self.campo_buscar_cliente.text())

    def _nuevo_cliente(self):
        dialogo = DialogoSeleccionarCliente(self)
        dialogo.setWindowTitle("Nuevo cliente")
        dialogo.campo_buscar.setPlaceholderText("Nombre del cliente nuevo…")
        if dialogo.exec() == QDialog.Accepted:
            self.recargar(seleccionar_cliente_id=dialogo.cliente_id)