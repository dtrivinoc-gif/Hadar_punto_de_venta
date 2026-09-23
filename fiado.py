"""
Fiado: ventas a crédito para clientes conocidos del almacén.

La deuda se lleva por cliente, no por venta puntual: cada venta fiada se
registra en `ventas` (metodo_pago='fiado', cliente_id=<quién>), y lo que
el cliente debe es simplemente:

    deuda = suma(total de sus ventas fiadas) - suma(sus abonos)

Este archivo tiene:
  - Funciones de datos: clientes, deuda, abonos
  - DialogoSeleccionarCliente: se usa desde venta.py al cobrar "fiado"
  - WidgetFiado: la pestaña "Fiado" -- lista de clientes a la izquierda,
    detalle del cliente elegido (deuda, historial, acciones) a la derecha
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit,
    QDialog, QFormLayout, QMessageBox, QListWidget, QListWidgetItem,
    QDoubleSpinBox, QComboBox, QSplitter, QSizePolicy,
)
from PySide6.QtCore import Qt, QSize

from db import conectar
from arqueo import sesion_abierta
from tiempo import ahora_texto
from config import COLOR_ACENTO_HADAR

try:
    from cajeros import listar_cajeros
except ImportError:  # por si algún día se usa este archivo sin cajeros.py
    def listar_cajeros(solo_activos=True):
        return []


# ---------------------------------------------------------------------------
# Paleta -- mismos tonos que el resto de Hadar, más semántica de color para
# fiado: naranja = "sale plata fiada" (sube la deuda), verde = "entra plata"
# (abono, baja la deuda). Un solo lugar para tocar el color si cambia.
# ---------------------------------------------------------------------------

ACENTO = COLOR_ACENTO_HADAR       # #6366F1 -- azul aciano de Hadar
ACENTO_HOVER = "#4F46E5"
ACENTO_SUAVE = "#EEF0FE"
ROJO = "#DC2626"
ROJO_SUAVE = "#FEE2E2"
VERDE = "#16A34A"
VERDE_HOVER = "#15803D"
VERDE_SUAVE = "#DCFCE7"
NARANJA = "#D97706"
NARANJA_HOVER = "#B45309"
GRIS_TEXTO = "#1F2430"
GRIS_MUTED = "#6B7280"
BORDE = "#E5E7EB"

ESTILO_FIADO = f"""
QLineEdit#buscarCliente {{
    padding: 10px 12px;
    border: 1px solid {BORDE};
    border-radius: 8px;
    font-size: 13px;
    background: white;
}}
QLineEdit#buscarCliente:focus {{ border: 1.5px solid {ACENTO}; }}

QListWidget#listaClientes {{
    background: white;
    border: 1px solid {BORDE};
    border-radius: 10px;
    padding: 6px;
}}
QListWidget#listaClientes::item {{ border-radius: 8px; margin-bottom: 2px; }}
QListWidget#listaClientes::item:hover {{ background: #F3F4F6; }}
QListWidget#listaClientes::item:selected {{ background: {ACENTO_SUAVE}; }}

QListWidget#listaHistorial {{
    background: white;
    border: 1px solid {BORDE};
    border-radius: 10px;
    padding: 4px;
}}
QListWidget#listaHistorial::item {{ border-radius: 6px; }}

QFrame#panelDetalle {{
    background: white;
    border: 1px solid {BORDE};
    border-radius: 12px;
}}

QPushButton#botonFiar {{
    background: {NARANJA}; color: white; border: none;
    border-radius: 8px; padding: 12px 18px; font-weight: 600; font-size: 14px;
}}
QPushButton#botonFiar:hover {{ background: {NARANJA_HOVER}; }}

QPushButton#botonAbono {{
    background: {VERDE}; color: white; border: none;
    border-radius: 8px; padding: 12px 18px; font-weight: 600; font-size: 14px;
}}
QPushButton#botonAbono:hover {{ background: {VERDE_HOVER}; }}

QPushButton#botonPrimario {{
    background: {ACENTO}; color: white; border: none;
    border-radius: 8px; padding: 12px 20px; font-weight: 600; font-size: 14px;
}}
QPushButton#botonPrimario:hover {{ background: {ACENTO_HOVER}; }}

QPushButton#botonSecundario {{
    background: white; color: {GRIS_TEXTO}; border: 1px solid {BORDE};
    border-radius: 8px; padding: 9px 14px; font-weight: 600; font-size: 13px;
}}
QPushButton#botonSecundario:hover {{ background: #F3F4F6; }}
"""


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


def deuda_total_negocio() -> float:
    """Para el resumen de arriba de la pestaña: cuánto suman todas las
    deudas de fiado del negocio, sin importar de quién."""
    with conectar() as con:
        total_fiado = con.execute(
            "SELECT COALESCE(SUM(total), 0) AS suma FROM ventas WHERE metodo_pago = 'fiado' AND anulada = 0"
        ).fetchone()["suma"]
        total_abonado = con.execute(
            "SELECT COALESCE(SUM(monto), 0) AS suma FROM abonos_fiado"
        ).fetchone()["suma"]
        return total_fiado - total_abonado


def eliminar_cliente(cliente_id: int):
    """Da de baja a un cliente (no lo borra de la tabla, para no perder el
    historial de sus fiados/abonos pasados) -- solo se permite si está al
    día, para no perder de vista una deuda por accidente."""
    deuda = deuda_cliente(cliente_id)
    if deuda > 0:
        raise ValueError("No se puede eliminar: todavía debe $ {:,.0f}.".format(deuda))
    with conectar() as con:
        con.execute("UPDATE clientes SET activo = 0 WHERE id = ?", (cliente_id,))


def historial_fiado_cliente(cliente_id: int):
    """Ventas fiadas (con sus productos y quién las registró) y abonos de
    un cliente, mezclados y ordenados por fecha."""
    with conectar() as con:
        columnas_ventas = {fila["name"] for fila in con.execute("PRAGMA table_info(ventas)")}
        tiene_cajero = "cajero_id" in columnas_ventas

        if tiene_cajero:
            ventas = con.execute(
                """SELECT v.id, v.fecha_hora, v.total, c.nombre AS cajero
                   FROM ventas v LEFT JOIN cajeros c ON c.id = v.cajero_id
                   WHERE v.cliente_id = ? AND v.metodo_pago = 'fiado' AND v.anulada = 0
                   ORDER BY v.fecha_hora""",
                (cliente_id,),
            ).fetchall()
        else:
            ventas = con.execute(
                """SELECT id, fecha_hora, total, NULL AS cajero FROM ventas
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
        if v["cajero"]:
            detalle = f"{detalle}  ·  fiado por {v['cajero']}" if detalle else f"fiado por {v['cajero']}"
        movimientos.append({
            "fecha": v["fecha_hora"], "tipo": "fiado", "detalle": detalle, "monto": v["total"],
        })
    for a in abonos:
        movimientos.append({
            "fecha": a["fecha_hora"], "tipo": "abono", "detalle": a["nota"] or "", "monto": -a["monto"],
        })
    movimientos.sort(key=lambda m: m["fecha"], reverse=True)  # lo más reciente arriba
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


def registrar_fiado_directo(cliente_id: int, monto: float, nota: str = "", cajero_id=None):
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
        columnas_ventas = {fila["name"] for fila in con.execute("PRAGMA table_info(ventas)")}
        if "cajero_id" in columnas_ventas:
            cursor_venta = con.execute(
                """INSERT INTO ventas (caja_sesion_id, fecha_hora, origen, total, metodo_pago, cliente_id, cajero_id)
                   VALUES (?, ?, 'venta_negocio', ?, 'fiado', ?, ?)""",
                (sesion["id"], ahora_texto(), monto, cliente_id, cajero_id),
            )
        else:
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
# Diálogo: elegir o crear cliente (usado desde venta.py al cobrar "fiado",
# y desde WidgetFiado cuando todavía no hay nadie seleccionado)
# ---------------------------------------------------------------------------

class DialogoSeleccionarCliente(QDialog):
    """Buscar un cliente existente por nombre, o crear uno nuevo al vuelo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("¿A nombre de quién se fía?")
        self.setMinimumWidth(360)
        self.cliente_id = None

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        self.campo_buscar = QLineEdit()
        self.campo_buscar.setPlaceholderText("Escribe el nombre del cliente…")
        self.campo_buscar.setMinimumHeight(36)
        self.campo_buscar.textChanged.connect(self._buscar)
        self.campo_buscar.returnPressed.connect(self._manejar_enter)
        layout.addWidget(self.campo_buscar)

        self.lista = QListWidget()
        self.lista.itemDoubleClicked.connect(lambda _: self._confirmar_existente())
        layout.addWidget(self.lista, stretch=1)

        boton_nuevo = QPushButton("+ Cliente nuevo con este nombre")
        boton_nuevo.setObjectName("botonSecundario")
        boton_nuevo.clicked.connect(self._crear_nuevo)
        layout.addWidget(boton_nuevo)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.setObjectName("botonSecundario")
        boton_cancelar.clicked.connect(self.reject)
        boton_elegir = QPushButton("Elegir")
        boton_elegir.setObjectName("botonPrimario")
        boton_elegir.setDefault(True)
        boton_elegir.clicked.connect(self._confirmar_existente)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_elegir)
        layout.addLayout(botones)

        self.setStyleSheet(ESTILO_FIADO)
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
        directo; si no hay ninguno, ofrece crearlo con ese nombre."""
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
# Diálogos: abonar y fiar (montos), ambos ya "a nombre de" un cliente conocido
# ---------------------------------------------------------------------------

class _DialogoMonto(QDialog):
    """Base común de DialogoRegistrarAbono y DialogoFiarDirecto -- ambos son
    'cliente + monto + nota', solo cambian título, tope y color del botón."""

    def __init__(self, parent, titulo: str, nombre_cliente: str, deuda_actual: float,
                 texto_boton: str, id_boton: str, tope_monto: float, valor_inicial: float,
                 placeholder_nota: str, mostrar_cajero: bool):
        super().__init__(parent)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(320)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        etiqueta_cliente = QLabel(nombre_cliente)
        etiqueta_cliente.setStyleSheet("font-size: 15px; font-weight: 700;")
        layout.addWidget(etiqueta_cliente)

        color_deuda = ROJO if deuda_actual > 0 else VERDE
        texto_deuda = f"$ {deuda_actual:,.0f}" if deuda_actual > 0 else "Al día"
        etiqueta_deuda = QLabel(f"Debe actualmente: {texto_deuda}")
        etiqueta_deuda.setStyleSheet(f"color: {color_deuda}; font-weight: 600;")
        layout.addWidget(etiqueta_deuda)

        form = QFormLayout()
        self.campo_monto = QDoubleSpinBox()
        self.campo_monto.setMaximum(tope_monto)
        self.campo_monto.setDecimals(0)
        self.campo_monto.setPrefix("$ ")
        self.campo_monto.setMinimumHeight(32)
        self.campo_monto.setValue(valor_inicial)
        form.addRow("Monto", self.campo_monto)

        self.campo_nota = QLineEdit()
        self.campo_nota.setPlaceholderText(placeholder_nota)
        form.addRow("Nota (opcional)", self.campo_nota)

        self.combo_cajero = None
        if mostrar_cajero:
            cajeros = listar_cajeros(solo_activos=True)
            if cajeros:
                self.combo_cajero = QComboBox()
                for cajero in cajeros:
                    self.combo_cajero.addItem(cajero["nombre"], userData=cajero["id"])
                form.addRow("Registrado por", self.combo_cajero)

        layout.addLayout(form)

        botones = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.setObjectName("botonSecundario")
        boton_cancelar.clicked.connect(self.reject)
        boton_ok = QPushButton(texto_boton)
        boton_ok.setObjectName(id_boton)
        boton_ok.setDefault(True)
        boton_ok.clicked.connect(self.accept)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_ok)
        layout.addLayout(botones)

        self.setStyleSheet(ESTILO_FIADO)

        # el monto siempre parte en un valor (QDoubleSpinBox no puede quedar
        # "vacío"), así que dejamos el texto seleccionado: al empezar a
        # escribir se reemplaza solo, sin tener que borrarlo primero
        self.campo_monto.setFocus()
        self.campo_monto.lineEdit().selectAll()

    def resultado(self):
        cajero_id = self.combo_cajero.currentData() if self.combo_cajero else None
        return self.campo_monto.value(), self.campo_nota.text().strip(), cajero_id


class DialogoRegistrarAbono(_DialogoMonto):
    def __init__(self, parent, nombre_cliente: str, deuda_actual: float):
        super().__init__(
            parent, f"Abono de {nombre_cliente}", nombre_cliente, deuda_actual,
            texto_boton="Registrar abono", id_boton="botonAbono",
            tope_monto=max(deuda_actual, 1), valor_inicial=0,
            placeholder_nota="Ej: pagó la mitad", mostrar_cajero=False,
        )


class DialogoFiarDirecto(_DialogoMonto):
    def __init__(self, parent, nombre_cliente: str, deuda_actual: float):
        super().__init__(
            parent, f"Fiar a {nombre_cliente}", nombre_cliente, deuda_actual,
            texto_boton="Registrar fiado", id_boton="botonFiar",
            tope_monto=10_000_000, valor_inicial=0,
            placeholder_nota="Ej: pan y leche, o deuda anterior", mostrar_cajero=True,
        )


# ---------------------------------------------------------------------------
# Filas custom para las listas (cliente / movimiento del historial)
# ---------------------------------------------------------------------------

def _fila_cliente(cliente, on_eliminar=None) -> QWidget:
    fila = QWidget()
    layout = QHBoxLayout(fila)
    layout.setContentsMargins(10, 8, 10, 8)

    nombre = QLabel(cliente["nombre"])
    nombre.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {GRIS_TEXTO};")
    layout.addWidget(nombre, stretch=1)

    deuda = cliente["deuda"]
    badge = QLabel(f"$ {deuda:,.0f}" if deuda > 0 else "Al día")
    color_fondo, color_texto = (ROJO_SUAVE, ROJO) if deuda > 0 else (VERDE_SUAVE, VERDE)
    badge.setStyleSheet(
        f"background: {color_fondo}; color: {color_texto}; font-weight: 700; "
        f"font-size: 12px; padding: 4px 10px; border-radius: 10px;"
    )
    layout.addWidget(badge)

    if deuda <= 0 and on_eliminar is not None:
        boton_eliminar = QPushButton("×")
        boton_eliminar.setToolTip("Eliminar cliente (solo si está al día)")
        boton_eliminar.setFixedSize(24, 24)
        boton_eliminar.setStyleSheet(
            f"QPushButton {{ border: none; background: transparent; color: {GRIS_MUTED}; "
            f"font-size: 16px; font-weight: 700; }}"
            f"QPushButton:hover {{ color: {ROJO}; background: {ROJO_SUAVE}; border-radius: 12px; }}"
        )
        boton_eliminar.clicked.connect(lambda: on_eliminar(cliente["id"], cliente["nombre"]))
        layout.addWidget(boton_eliminar)

    return fila


def _fila_movimiento(m) -> QWidget:
    fila = QWidget()
    layout = QVBoxLayout(fila)
    layout.setContentsMargins(12, 8, 12, 8)
    layout.setSpacing(2)

    es_fiado = m["tipo"] == "fiado"
    color = ROJO if es_fiado else VERDE
    signo = "+" if es_fiado else "−"

    fila_superior = QHBoxLayout()
    etiqueta_tipo = QLabel("Fiado" if es_fiado else "Abono")
    etiqueta_tipo.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 12px;")
    fila_superior.addWidget(etiqueta_tipo)
    fila_superior.addStretch(1)
    etiqueta_fecha = QLabel(m["fecha"])
    etiqueta_fecha.setStyleSheet(f"color: {GRIS_MUTED}; font-size: 11px;")
    fila_superior.addWidget(etiqueta_fecha)
    layout.addLayout(fila_superior)

    etiqueta_monto = QLabel(f"{signo} $ {abs(m['monto']):,.0f}")
    etiqueta_monto.setStyleSheet(f"color: {color}; font-weight: 700; font-size: 15px;")
    layout.addWidget(etiqueta_monto)

    if m["detalle"]:
        etiqueta_detalle = QLabel(m["detalle"])
        etiqueta_detalle.setStyleSheet(f"color: {GRIS_MUTED}; font-size: 12px;")
        etiqueta_detalle.setWordWrap(True)
        layout.addWidget(etiqueta_detalle)

    return fila


# ---------------------------------------------------------------------------
# Pestaña "Fiado"
# ---------------------------------------------------------------------------

class WidgetFiado(QWidget):
    """Maestro-detalle: lista de clientes a la izquierda, deuda + historial
    + acciones del cliente elegido a la derecha."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cliente_seleccionado_id = None
        self._armar_ui()
        self.recargar()

    # -- construcción de la interfaz -------------------------------------

    def _armar_ui(self):
        self.setStyleSheet(ESTILO_FIADO)
        layout = QVBoxLayout(self)

        # -- resumen de arriba: cuánto debe el negocio en total --
        self.etiqueta_resumen = QLabel()
        self.etiqueta_resumen.setStyleSheet(f"color: {GRIS_MUTED}; font-size: 13px;")
        layout.addWidget(self.etiqueta_resumen)

        boton_anotar_fiado = QPushButton("+ Anotar fiado (cliente nuevo o existente)")
        boton_anotar_fiado.setObjectName("botonFiar")
        boton_anotar_fiado.setMinimumHeight(46)
        boton_anotar_fiado.clicked.connect(self._fiar_a_cliente_nuevo)
        layout.addWidget(boton_anotar_fiado)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, stretch=1)

        # ---------------- panel izquierdo: lista de clientes ----------------
        panel_izquierdo = QWidget()
        layout_izquierdo = QVBoxLayout(panel_izquierdo)
        layout_izquierdo.setContentsMargins(0, 0, 0, 0)

        self.campo_buscar_cliente = QLineEdit()
        self.campo_buscar_cliente.setObjectName("buscarCliente")
        self.campo_buscar_cliente.setPlaceholderText("Buscar cliente por nombre…")
        self.campo_buscar_cliente.textChanged.connect(lambda texto: self.recargar(filtro=texto))
        layout_izquierdo.addWidget(self.campo_buscar_cliente)

        self.lista_clientes = QListWidget()
        self.lista_clientes.setObjectName("listaClientes")
        self.lista_clientes.currentItemChanged.connect(self._al_cambiar_seleccion)
        layout_izquierdo.addWidget(self.lista_clientes, stretch=1)

        splitter.addWidget(panel_izquierdo)

        # ---------------- panel derecho: detalle del cliente elegido --------
        self.panel_derecho = QWidget()
        self.layout_derecho = QVBoxLayout(self.panel_derecho)

        self.etiqueta_vacio = QLabel(
            "Elige un cliente de la izquierda para ver su deuda,\n"
            "o usa \"+ Anotar fiado\" arriba para uno nuevo."
        )
        self.etiqueta_vacio.setAlignment(Qt.AlignCenter)
        self.etiqueta_vacio.setStyleSheet(f"color: {GRIS_MUTED}; font-size: 13px;")
        self.layout_derecho.addWidget(self.etiqueta_vacio, stretch=1)

        # -- encabezado del cliente elegido (nombre + deuda grande) --
        self.etiqueta_nombre_cliente = QLabel()
        self.etiqueta_nombre_cliente.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.etiqueta_nombre_cliente.hide()
        self.layout_derecho.addWidget(self.etiqueta_nombre_cliente)

        self.etiqueta_deuda_cliente = QLabel()
        self.etiqueta_deuda_cliente.setStyleSheet("font-size: 34px; font-weight: 800;")
        self.etiqueta_deuda_cliente.hide()
        self.layout_derecho.addWidget(self.etiqueta_deuda_cliente)

        fila_acciones = QHBoxLayout()
        self.boton_fiar = QPushButton("Fiar")
        self.boton_fiar.setObjectName("botonFiar")
        self.boton_fiar.setMinimumHeight(44)
        self.boton_fiar.clicked.connect(self._fiar_a_cliente_seleccionado)
        self.boton_fiar.hide()
        fila_acciones.addWidget(self.boton_fiar)

        self.boton_abono = QPushButton("Recibir abono")
        self.boton_abono.setObjectName("botonAbono")
        self.boton_abono.setMinimumHeight(44)
        self.boton_abono.clicked.connect(self._registrar_abono)
        self.boton_abono.hide()
        fila_acciones.addWidget(self.boton_abono)
        self.layout_derecho.addLayout(fila_acciones)

        self.etiqueta_historial = QLabel("Historial")
        self.etiqueta_historial.setStyleSheet("font-size: 13px; font-weight: 700; margin-top: 6px;")
        self.etiqueta_historial.hide()
        self.layout_derecho.addWidget(self.etiqueta_historial)

        self.lista_historial = QListWidget()
        self.lista_historial.setObjectName("listaHistorial")
        self.lista_historial.hide()
        self.layout_derecho.addWidget(self.lista_historial, stretch=2)

        splitter.addWidget(self.panel_derecho)
        splitter.setSizes([320, 480])

    # -- carga de datos ----------------------------------------------------

    def recargar(self, seleccionar_cliente_id=None, filtro=""):
        clientes_con_saldo = listar_clientes_con_saldo()
        deudores = sum(1 for c in clientes_con_saldo if c["deuda"] > 0)
        if deudores:
            self.etiqueta_resumen.setText(
                f"Deuda total del negocio: $ {deuda_total_negocio():,.0f}  ·  {deudores} cliente(s) con deuda"
            )
        else:
            self.etiqueta_resumen.setText("Ningún cliente tiene deuda pendiente.")

        self.lista_clientes.clear()
        item_a_seleccionar = None
        filtro_normalizado = filtro.strip().lower()
        for cliente in clientes_con_saldo:
            if filtro_normalizado and filtro_normalizado not in cliente["nombre"].lower():
                continue
            item = QListWidgetItem()
            item.setData(Qt.UserRole, cliente["id"])
            item.setData(Qt.UserRole + 1, cliente["nombre"])
            item.setData(Qt.UserRole + 2, cliente["deuda"])
            item.setSizeHint(QSize(0, 54))
            self.lista_clientes.addItem(item)
            self.lista_clientes.setItemWidget(item, _fila_cliente(cliente, on_eliminar=self._eliminar_cliente))
            if cliente["id"] == seleccionar_cliente_id:
                item_a_seleccionar = item

        if item_a_seleccionar is not None:
            self.lista_clientes.setCurrentItem(item_a_seleccionar)
        elif self.cliente_seleccionado_id is not None:
            self._mostrar_detalle_cliente(self.cliente_seleccionado_id)
        else:
            self._mostrar_estado_vacio()

    def _al_cambiar_seleccion(self, item, _anterior=None):
        if item is None:
            self.cliente_seleccionado_id = None
            self._mostrar_estado_vacio()
            return
        self._mostrar_detalle_cliente(item.data(Qt.UserRole))

    def _mostrar_estado_vacio(self):
        self.cliente_seleccionado_id = None
        self.etiqueta_vacio.show()
        for w in (self.etiqueta_nombre_cliente, self.etiqueta_deuda_cliente,
                  self.boton_fiar, self.boton_abono, self.etiqueta_historial, self.lista_historial):
            w.hide()

    def _mostrar_detalle_cliente(self, cliente_id):
        self.cliente_seleccionado_id = cliente_id
        nombre = next((c["nombre"] for c in listar_clientes() if c["id"] == cliente_id), "Cliente")
        deuda = deuda_cliente(cliente_id)

        self.etiqueta_vacio.hide()
        self.etiqueta_nombre_cliente.setText(nombre)
        self.etiqueta_nombre_cliente.show()

        if deuda > 0:
            self.etiqueta_deuda_cliente.setText(f"Debe $ {deuda:,.0f}")
            self.etiqueta_deuda_cliente.setStyleSheet(f"font-size: 34px; font-weight: 800; color: {ROJO};")
        else:
            self.etiqueta_deuda_cliente.setText("Al día")
            self.etiqueta_deuda_cliente.setStyleSheet(f"font-size: 34px; font-weight: 800; color: {VERDE};")
        self.etiqueta_deuda_cliente.show()

        self.boton_fiar.show()
        self.boton_abono.setEnabled(deuda > 0)
        self.boton_abono.show()
        self.etiqueta_historial.show()

        self.lista_historial.clear()
        movimientos = historial_fiado_cliente(cliente_id)
        if not movimientos:
            item = QListWidgetItem("Todavía no hay fiados ni abonos con este cliente.")
            item.setFlags(Qt.NoItemFlags)
            self.lista_historial.addItem(item)
        else:
            for m in movimientos:
                item = QListWidgetItem()
                item.setSizeHint(QSize(0, 68 if m["detalle"] else 50))
                self.lista_historial.addItem(item)
                self.lista_historial.setItemWidget(item, _fila_movimiento(m))
        self.lista_historial.show()

    # -- acciones ------------------------------------------------------------

    def _eliminar_cliente(self, cliente_id, nombre):
        respuesta = QMessageBox.question(
            self, "Eliminar cliente",
            f"¿Quitar a {nombre} de la lista? Esto no borra su historial pasado, "
            "solo deja de mostrarlo entre los clientes activos.",
        )
        if respuesta != QMessageBox.Yes:
            return
        try:
            eliminar_cliente(cliente_id)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo eliminar", str(error))
            return

        if self.cliente_seleccionado_id == cliente_id:
            self.cliente_seleccionado_id = None
        self.recargar(filtro=self.campo_buscar_cliente.text())

    def _registrar_abono(self):
        if self.cliente_seleccionado_id is None:
            return
        cliente_id = self.cliente_seleccionado_id
        nombre = self.etiqueta_nombre_cliente.text()
        deuda = deuda_cliente(cliente_id)
        if deuda <= 0:
            QMessageBox.information(self, "Sin deuda", f"{nombre} está al día, no tiene nada pendiente.")
            return

        dialogo = DialogoRegistrarAbono(self, nombre, deuda)
        if dialogo.exec() != QDialog.Accepted:
            return
        monto, nota, _ = dialogo.resultado()
        if monto <= 0:
            return

        try:
            registrar_abono(cliente_id, monto, nota)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo registrar el abono", str(error))
            return

        self.recargar(seleccionar_cliente_id=cliente_id, filtro=self.campo_buscar_cliente.text())

    def _fiar_a_cliente_seleccionado(self):
        if self.cliente_seleccionado_id is None:
            return
        self._fiar(self.cliente_seleccionado_id, self.etiqueta_nombre_cliente.text())

    def _fiar_a_cliente_nuevo(self):
        """Punto de entrada cuando todavía no hay nadie seleccionado (o se
        quiere fiar a alguien que no está a la vista en la lista filtrada)."""
        dialogo_cliente = DialogoSeleccionarCliente(self)
        if dialogo_cliente.exec() != QDialog.Accepted:
            return
        nombre = next((c["nombre"] for c in listar_clientes() if c["id"] == dialogo_cliente.cliente_id), "cliente")
        self._fiar(dialogo_cliente.cliente_id, nombre)

    def _fiar(self, cliente_id, nombre):
        deuda_actual = deuda_cliente(cliente_id)
        dialogo_monto = DialogoFiarDirecto(self, nombre, deuda_actual)
        if dialogo_monto.exec() != QDialog.Accepted:
            return
        monto, nota, cajero_id = dialogo_monto.resultado()
        if monto <= 0:
            return

        try:
            registrar_fiado_directo(cliente_id, monto, nota, cajero_id)
        except Exception as error:
            QMessageBox.warning(self, "No se pudo registrar el fiado", str(error))
            return

        self.recargar(seleccionar_cliente_id=cliente_id, filtro=self.campo_buscar_cliente.text())