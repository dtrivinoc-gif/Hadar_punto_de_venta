"""
Capa de base de datos del POS.

Todo lo que toca la base de datos vive acá. El resto de los módulos
(productos.py, venta.py, caja_vecina.py, arqueo.py, fiado.py, cajeros.py)
siguen usando `conectar()` exactamente igual que siempre -- no tuvieron
que cambiar ni una línea para esto.

NOVEDAD: si config.USAR_TURSO está activado, `conectar()` entrega una
conexión que lee y escribe LOCAL (rápido, funciona sin internet) pero
que se puede sincronizar con Turso Cloud llamando a push()/pull() --
eso lo hace sincronizacion.py, no este archivo.

OJO CON EL MODO: existen dos formas de usar Turso desde Python:
  - "Embedded Replicas" (paquete `libsql`): lee local, pero ESCRIBE
    directo a la nube -- si no hay internet, no se puede vender. NO es
    lo que se usa acá.
  - "Turso Sync" (paquete `pyturso`, módulo `turso.sync`): lee Y escribe
    siempre local; vos decidís cuándo mandar (push) o traer (pull)
    cambios. Es la que se usa en este archivo, a propósito, porque el
    POS tiene que poder seguir vendiendo sin internet.

IMPORTANTE -- esto no se probó contra una base de Turso real (este
entorno no tiene acceso a internet). Antes de usarlo con el negocio de
verdad, hay que probarlo con una base de Turso de prueba y revisar en
particular:
  1. Que `con.row_factory = sqlite3.Row` funcione igual que con sqlite3
     puro (para que `fila["nombre"]` siga funcionando en todos los
     otros archivos, tal cual están hoy).
  2. Que los varios `con.execute(...)` seguidos dentro de un mismo
     `with conectar() as con:` (ver venta.py: inserta la venta y
     después cada línea de detalle_venta) se comporten como una
     transacción, igual que con sqlite3.
Si algo de esto no calza, avisame el error exacto y lo ajustamos.
"""

import sqlite3
from contextlib import contextmanager

from config import (
    RUTA_BASE_DATOS, asegurar_carpetas,
    USAR_TURSO, TURSO_DATABASE_URL, TURSO_AUTH_TOKEN,
)

# Conexión única y persistente a Turso (si USAR_TURSO está activo).
# A propósito NO se abre una conexión nueva por cada consulta, como sí
# se hace con sqlite3 más abajo: turso.sync está pensado para abrirse
# una vez al arrancar el programa y reusarse durante toda la sesión,
# sincronizando de fondo -- abrir/cerrar todo el tiempo sería lento y
# no es el uso que la propia documentación de Turso recomienda.
_conexion_turso = None


def _obtener_conexion_turso():
    global _conexion_turso
    if _conexion_turso is None:
        import turso.sync  # se importa acá adentro para que el POS ni
                            # siquiera necesite tener el paquete instalado
                            # cuando USAR_TURSO está en False

        _conexion_turso = turso.sync.connect(
            RUTA_BASE_DATOS,
            remote_url=TURSO_DATABASE_URL,
            auth_token=TURSO_AUTH_TOKEN,
            # False = el POS puede arrancar sin internet, incluso la
            # primera vez -- no espera poder "bajar" nada de la nube
            # para funcionar.
            bootstrap_if_empty=False,
        )
        try:
            _conexion_turso.row_factory = sqlite3.Row
        except Exception:
            # Si turso.sync no soporta este atributo, seguimos igual --
            # pero entonces `fila["nombre"]` va a fallar en los demás
            # archivos y hay que adaptar esas consultas a fila[0], fila[1]...
            pass
        try:
            _conexion_turso.execute("PRAGMA foreign_keys = ON")
        except Exception:
            pass
    return _conexion_turso


def cerrar_conexion_turso():
    """Cierra la conexión persistente a Turso, si estaba abierta.
    Llamar UNA vez, al salir del programa (ver run_pos.py)."""
    global _conexion_turso
    if _conexion_turso is not None:
        try:
            _conexion_turso.close()
        except Exception:
            pass
        _conexion_turso = None


@contextmanager
def conectar():
    """
    Entrega una conexión a la base de datos, con foreign keys activadas
    y row_factory configurado para que las filas se puedan leer como
    diccionarios (fila["nombre"] en vez de fila[2]).

    Uso (igual que siempre, en todos los demás archivos):
        with conectar() as con:
            con.execute(...)
    """
    asegurar_carpetas()

    if USAR_TURSO:
        con = _obtener_conexion_turso()
        try:
            yield con
            con.commit()
        except Exception:
            try:
                con.rollback()
            except Exception:
                pass
            raise
        # a propósito NO se cierra acá -- es la conexión compartida de
        # todo el programa (ver _obtener_conexion_turso arriba)
    else:
        con = sqlite3.connect(RUTA_BASE_DATOS)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


# ---------------------------------------------------------------------------
# Esquema
# ---------------------------------------------------------------------------

ESQUEMA = """
-- Productos catalogados (incluye los que se venden sueltos: dulces,
-- verduras, cigarros, pan, etc.)
CREATE TABLE IF NOT EXISTS productos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,
    precio          REAL NOT NULL DEFAULT 0,
    tipo_venta      TEXT NOT NULL DEFAULT 'unidad'
                        CHECK (tipo_venta IN ('unidad', 'variable', 'peso')),
    categoria       TEXT NOT NULL DEFAULT 'General',
    codigo_barra    TEXT,
    codigo_plu      TEXT,
    activo          INTEGER NOT NULL DEFAULT 1,
    creado_en       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS caja_sesion (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_apertura          TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    monto_apertura_negocio  REAL NOT NULL DEFAULT 0,
    monto_apertura_vecina   REAL NOT NULL DEFAULT 0,
    fecha_cierre            TEXT,
    monto_cierre_negocio    REAL,
    monto_cierre_vecina     REAL,
    cerrada                 INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cajeros (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,
    activo          INTEGER NOT NULL DEFAULT 1,
    creado_en       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS ventas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    caja_sesion_id  INTEGER NOT NULL REFERENCES caja_sesion(id),
    cajero_id       INTEGER REFERENCES cajeros(id),
    fecha_hora      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    origen          TEXT NOT NULL DEFAULT 'venta_negocio'
                        CHECK (origen IN ('venta_negocio', 'caja_vecina')),
    total           REAL NOT NULL DEFAULT 0,
    metodo_pago     TEXT NOT NULL DEFAULT 'efectivo'
                        CHECK (metodo_pago IN ('efectivo', 'debito', 'credito', 'transferencia', 'fiado')),
    anulada         INTEGER NOT NULL DEFAULT 0,
    cliente_id      INTEGER REFERENCES clientes(id)
);

CREATE TABLE IF NOT EXISTS detalle_venta (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id        INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id     INTEGER REFERENCES productos(id),
    nombre_producto TEXT NOT NULL,
    cantidad        REAL NOT NULL DEFAULT 1,
    precio_unitario REAL NOT NULL DEFAULT 0,
    subtotal        REAL NOT NULL DEFAULT 0,
    es_venta_libre  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS movimientos_caja_vecina (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    caja_sesion_id  INTEGER NOT NULL REFERENCES caja_sesion(id),
    fecha_hora      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    tipo            TEXT NOT NULL CHECK (tipo IN ('deposito', 'retiro', 'comision')),
    monto           REAL NOT NULL,
    descripcion     TEXT
);

CREATE TABLE IF NOT EXISTS clientes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre          TEXT NOT NULL,
    telefono        TEXT,
    notas           TEXT,
    activo          INTEGER NOT NULL DEFAULT 1,
    creado_en       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS abonos_fiado (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id      INTEGER NOT NULL REFERENCES clientes(id),
    caja_sesion_id  INTEGER NOT NULL REFERENCES caja_sesion(id),
    fecha_hora      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    monto           REAL NOT NULL,
    nota            TEXT
);

CREATE INDEX IF NOT EXISTS idx_ventas_caja_sesion ON ventas(caja_sesion_id);
CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente_id);
CREATE INDEX IF NOT EXISTS idx_ventas_cajero ON ventas(cajero_id);
CREATE INDEX IF NOT EXISTS idx_detalle_venta_venta ON detalle_venta(venta_id);
CREATE INDEX IF NOT EXISTS idx_movimientos_caja_sesion ON movimientos_caja_vecina(caja_sesion_id);
CREATE INDEX IF NOT EXISTS idx_productos_activo ON productos(activo);
CREATE INDEX IF NOT EXISTS idx_abonos_cliente ON abonos_fiado(cliente_id);

CREATE TABLE IF NOT EXISTS configuracion_reloj (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    desfase_segundos    INTEGER NOT NULL DEFAULT 0
);
"""


def _migrar_ventas_agregar_fiado(con):
    """
    Instalaciones que ya tenían la tabla `ventas` de antes del fiado no
    tienen la columna cliente_id ni 'fiado' en el CHECK de metodo_pago.
    SQLite permite agregar columnas con ALTER TABLE, pero no modificar un
    CHECK existente -- para eso hay que reconstruir la tabla.

    IMPORTANTE: al usar ALTER TABLE ... RENAME TO, SQLite reescribe
    automáticamente las cláusulas REFERENCES de OTRAS tablas que apunten a
    la tabla renombrada (acá, detalle_venta.venta_id apuntaba a "ventas").
    Sin 'PRAGMA legacy_alter_table = ON', esa reescritura queda pegada
    apuntando a "ventas_old" para siempre, aunque después se cree una
    tabla "ventas" nueva -- y cualquier operación sobre detalle_venta
    empieza a fallar con "no such table: main.ventas_old" en cuanto SQLite
    intenta validar esa referencia. legacy_alter_table = ON evita que
    SQLite toque el texto de las otras tablas durante el rename.

    Esta función es segura de llamar siempre: si ya está migrada, no hace
    nada. Si la tabla ventas se acaba de crear con el ESQUEMA de arriba
    (instalación nueva), tampoco hace nada porque ya viene con todo.
    """
    fila = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='ventas'"
    ).fetchone()
    if fila is None or "'fiado'" in fila["sql"]:
        return  # no existe todavía (se creará con el esquema nuevo) o ya migrada

    con.execute("PRAGMA legacy_alter_table = ON")
    con.execute("PRAGMA foreign_keys = OFF")
    con.executescript("""
        ALTER TABLE ventas RENAME TO ventas_old;

        CREATE TABLE ventas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            caja_sesion_id  INTEGER NOT NULL REFERENCES caja_sesion(id),
            fecha_hora      TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            origen          TEXT NOT NULL DEFAULT 'venta_negocio'
                                CHECK (origen IN ('venta_negocio', 'caja_vecina')),
            total           REAL NOT NULL DEFAULT 0,
            metodo_pago     TEXT NOT NULL DEFAULT 'efectivo'
                                CHECK (metodo_pago IN ('efectivo', 'debito', 'credito', 'transferencia', 'fiado')),
            anulada         INTEGER NOT NULL DEFAULT 0,
            cliente_id      INTEGER REFERENCES clientes(id)
        );

        INSERT INTO ventas (id, caja_sesion_id, fecha_hora, origen, total, metodo_pago, anulada, cliente_id)
        SELECT id, caja_sesion_id, fecha_hora, origen, total, metodo_pago, anulada, NULL
        FROM ventas_old;

        DROP TABLE ventas_old;

        CREATE INDEX IF NOT EXISTS idx_ventas_caja_sesion ON ventas(caja_sesion_id);
        CREATE INDEX IF NOT EXISTS idx_ventas_cliente ON ventas(cliente_id);
    """)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA legacy_alter_table = OFF")


def _reparar_referencia_ventas_old(con):
    """
    Repara el daño que causaba una versión anterior de la migración de
    arriba (antes de tener 'PRAGMA legacy_alter_table = ON'): detalle_venta
    quedó con su columna venta_id apuntando a "ventas_old" en vez de
    "ventas", porque esa tabla ya no existe.

    Detecta el daño mirando el esquema guardado de detalle_venta, y si lo
    encuentra, reconstruye la tabla con la referencia correcta -- sin
    perder ninguna fila. Si la base nunca tuvo el bug (instalaciones
    nuevas, o esta reparación ya se hizo antes), no hace nada.
    """
    fila = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='detalle_venta'"
    ).fetchone()
    if fila is None or "ventas_old" not in fila["sql"]:
        return  # no existe todavía, o no está dañada

    con.execute("PRAGMA legacy_alter_table = ON")
    con.execute("PRAGMA foreign_keys = OFF")
    con.executescript("""
        ALTER TABLE detalle_venta RENAME TO detalle_venta_old;

        CREATE TABLE detalle_venta (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            venta_id        INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
            producto_id     INTEGER REFERENCES productos(id),
            nombre_producto TEXT NOT NULL,
            cantidad        REAL NOT NULL DEFAULT 1,
            precio_unitario REAL NOT NULL DEFAULT 0,
            subtotal        REAL NOT NULL DEFAULT 0,
            es_venta_libre  INTEGER NOT NULL DEFAULT 0
        );

        INSERT INTO detalle_venta (id, venta_id, producto_id, nombre_producto, cantidad, precio_unitario, subtotal, es_venta_libre)
        SELECT id, venta_id, producto_id, nombre_producto, cantidad, precio_unitario, subtotal, es_venta_libre
        FROM detalle_venta_old;

        DROP TABLE detalle_venta_old;

        CREATE INDEX IF NOT EXISTS idx_detalle_venta_venta ON detalle_venta(venta_id);
    """)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA legacy_alter_table = OFF")


def _migrar_columnas_faltantes(con):
    tabla_existe = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ventas'"
    ).fetchone()
    if tabla_existe is None:
        return

    columnas_ventas = {fila["name"] for fila in con.execute("PRAGMA table_info(ventas)")}
    if "cajero_id" not in columnas_ventas:
        con.execute("ALTER TABLE ventas ADD COLUMN cajero_id INTEGER REFERENCES cajeros(id)")


def inicializar_base_datos():
    with conectar() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS clientes (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre          TEXT NOT NULL,
                telefono        TEXT,
                notas           TEXT,
                activo          INTEGER NOT NULL DEFAULT 1,
                creado_en       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
            CREATE TABLE IF NOT EXISTS cajeros (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre          TEXT NOT NULL,
                activo          INTEGER NOT NULL DEFAULT 1,
                creado_en       TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            );
        """)
        _migrar_ventas_agregar_fiado(con)
        _reparar_referencia_ventas_old(con)
        _migrar_columnas_faltantes(con)
        con.executescript(ESQUEMA)
        con.execute(
            "INSERT OR IGNORE INTO configuracion_reloj (id, desfase_segundos) VALUES (1, 0)"
        )


if __name__ == "__main__":
    inicializar_base_datos()
    print(f"Base de datos lista en: {RUTA_BASE_DATOS}")