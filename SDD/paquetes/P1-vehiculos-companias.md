# P1 · Vehículos y compañías

**Branch:** `paquete-p1-vehiculos` · **SQL:** `SDD/sql/13_vehiculos_companias.sql` · **Depende de:** nada.
**Por qué (Roberto):** hoy el bien asegurado es un texto libre. No puedo buscar «la camioneta de Pérez» ni la patente, y no sé qué compañía emite cada póliza ni cuánto me deja. Es la base de renovaciones, cotizaciones, credencial y reporte de comisiones.

## 1. Esquema (`13_vehiculos_companias.sql`)
```
companias   id, nombre (único sin distinguir mayúsculas), comision_pct numeric(5,2) default 0 (0 a 100), activa bool default true
vehiculos   id, cliente_id → clientes, patente (única, mayúsculas sin espacios), marca, modelo, anio smallint,
            uso (particular, comercial, remis_taxi, carga; default particular), chasis null, valor_asegurado numeric(12,2) null,
            activo bool default true, creado_en
polizas     + vehiculo_id → vehiculos null, + compania_id → companias null, + comision_pct numeric(5,2) null (0 a 100)
```
- CHECK de patente: `^([A-Z]{3}[0-9]{3}|[A-Z]{2}[0-9]{3}[A-Z]{2}|[0-9]{3}[A-Z]{3}|[A-Z][0-9]{3}[A-Z]{3})$` (auto viejo, auto nuevo, moto vieja, moto nueva).
- `anio` entre 1950 y el año actual + 1. `marca` y `modelo` no vacíos.
- `polizas.bien_asegurado` **se conserva** (las pólizas viejas no se tocan).

## 2. Etapa A · ORM (T4)
Archivos: `datos/` y `config/test_runner.py`. Pegarle a la IA `SDD/contratos/modelos.md` y el SQL.
| ID | Criterio |
|---|---|
| AC-T4-29 | Dados `Compania`, `Vehiculo` y los campos nuevos de `Poliza` (`vehiculo`, `compania`, `comision_pct`), entonces son `managed = False` con los `related_name` `cliente.vehiculos` y `compania.polizas`; `UsoVehiculo` (`TextChoices`) coincide exactamente con el `CHECK` de la base (como AC-T4-07); el SQL 13 está en la lista de `test_runner.py` y puede aplicarse dos veces seguidas sin error. |
| AC-T4-30 | Dado `limpieza.normalizar_patente`, entonces `'ab 123 cd'` y `'AB-123-CD'` → `'AB123CD'`; `' abc123 '` → `'ABC123'`; `'123 abc'` → `'123ABC'`; `'A123BCD'` válida; `'AB12'`, `'ABCD123'` o vacío → `ValueError`. |
| AC-T4-31 | Dadas las consultas nuevas, entonces `vehiculo_por_patente(patente)` (normaliza y devuelve el objeto o `None`), `vehiculos_de(cliente_id, solo_activos=True)`, `listar_companias(solo_activas=True)` (por nombre); `buscar_clientes(q)` encuentra también por patente (si `normalizar_patente(q)` funciona busca la patente exacta antes de caer en nombre o apellido); `detalle_poliza` y `detalle_cliente` traen vehículo y compañía sin pasar de 5 consultas (`assertNumQueries`); fábricas `crear_compania` y `crear_vehiculo` con valores únicos. |

## 3. Etapa B · Lógica (T3)
Archivos: `negocio/` (módulos nuevos `vehiculos.py` y `companias.py`; `polizas.py` y `bot/orquestador.py`/`plantillas.py` para lo que se indica). Aprobador = `puede_aprobar`.
| ID | Criterio |
|---|---|
| AC-T3-57 | Dado `alta_vehiculo(cliente_id, patente, marca, modelo, anio, uso="particular", chasis=None, valor_asegurado=None, funcionario_id)` por un aprobador, entonces crea el vehículo con la patente normalizada; son `DatosInvalidos` una patente repetida o inválida, un año fuera de rango, marca o modelo vacíos, un valor asegurado ≤ 0 y un cliente inactivo; un operador recibe `PermisoDenegado`; cliente inexistente, `NoEncontrado`. |
| AC-T3-58 | Dados `modificar_vehiculo(id, …)` y `dar_de_baja_vehiculo(id)`, entonces el primero actualiza solo lo recibido (la patente propia no cuenta como repetida); la baja es lógica y es `EstadoInvalido` si el vehículo tiene una póliza vigente; ambos exigen aprobador. |
| AC-T3-59 | Dados `alta_compania(nombre, comision_pct, funcionario_id)`, `modificar_compania` y `desactivar_compania`, entonces el nombre es único sin distinguir mayúsculas ni espacios, la comisión va de 0 a 100, y desactivar una compañía no toca las pólizas que ya la usan; las tres exigen aprobador. |
| AC-T3-60 | Dado `alta_poliza` (de `negocio/polizas.py`), cuando recibe `vehiculo_id` y `compania_id` opcionales, entonces el vehículo debe ser del cliente de la póliza (si no, `DatosInvalidos`), la compañía debe estar activa, `comision_pct` de la póliza toma la de la compañía en ese momento (o la que se pase), y si no se pasó `bien_asegurado` se completa con `"<marca> <modelo> <año> (<patente>)"`. Sin vehículo ni compañía, `alta_poliza` se comporta como antes. |
| AC-T3-61 | Dada la plantilla `VENCIMIENTO`, entonces cada línea agrega ` · <patente>` solo cuando la póliza tiene vehículo; el golden set no cambia (sus pólizas no tienen vehículo). La patente va en `datos_verificados`. |

## 4. Etapa C · API (T2)
Archivos: `api/`. Pegarle `contratos/servicios.md` (con lo que dejó la etapa B).
| ID | Criterio |
|---|---|
| AC-T2-26 | Dados `GET /api/vehiculos/?cliente=N` (cualquier funcionario), `POST /api/vehiculos/`, `PATCH /api/vehiculos/{id}/` y `POST /api/vehiculos/{id}/baja/` (aprobador), entonces devuelven `vehiculo` `{id, cliente, patente, marca, modelo, anio, uso, chasis, valor_asegurado, activo}`; los errores siguen AC-T2-03 (patente repetida → 400, baja con póliza vigente → 409); `PUT`/`DELETE` → 405. |
| AC-T2-27 | Dados `GET /api/companias/?activas=1` (cualquier funcionario), `POST /api/companias/` y `PATCH /api/companias/{id}/` (aprobador), entonces devuelven `compania` `{id, nombre, comision_pct, activa}`. |
| AC-T2-28 | Dados `cliente_detalle` y `poliza_detalle`, entonces incluyen `vehiculos` / `vehiculo`, `compania` y `comision_pct`; **`comision_pct` es `null` para un operador** (la comisión es información del dueño); `GET /api/clientes/?q=ab123cd` encuentra al dueño por patente; la ruta `/panel/companias/` está en la lista blanca de páginas. |

## 5. Etapa D · Front (T1)
Archivos: `frontend/`, `SDD/qa/T1.md`. Pegarle `contratos/api.md`.
| ID | Criterio |
|---|---|
| AC-T1-24 | Dado `lib/patente.js`, entonces `normalizarPatente('ab 123 cd')` → `'AB123CD'` y `patenteValida` acepta los 4 formatos de AC-T4-30 y rechaza `'AB12'`; sirve solo para avisar en el formulario, la validación real es del back (R17). |
| AC-T1-25 | **(QA)** Dada `/panel/cliente/?id=N`, entonces hay una sección «Vehículos» (patente, marca, modelo, año, uso) con alta, edición y baja para aprobadores; cada póliza muestra su vehículo y compañía; el 409 por póliza vigente se muestra con el mensaje de la API; en `/panel/clientes/` buscar una patente (con o sin espacios) encuentra al dueño. Diego no ve la comisión. |
| AC-T1-26 | **(QA)** Dada `/panel/companias/`, entonces hay una tabla de compañías (nombre, comisión, estado) con alta, edición y activar/desactivar solo para aprobadores. |

## 6. Terminado cuando
Los 14 AC con prueba, contratos actualizados, SQL 13 aplicado a la base real por una persona, y `SDD/entregas/P1.md` completo.
