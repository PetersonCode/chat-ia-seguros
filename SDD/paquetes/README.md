# Paquetes de funcionalidad nueva (P1 a P9)

Roberto pidió ampliar el sistema más allá de atender a quien ya es cliente: **vender, renovar y cobrar**. Cada paquete es una funcionalidad completa, de la base al front, pensada para que **una persona la haga en un chat nuevo**.

> **Restricción de esta tanda: nada usa plantillas de Meta (se cobran).** Todo es texto libre, que WhatsApp solo admite hasta 24 h después del último mensaje del cliente. Un aviso sale entonces por tres caminos: automático (ventana abierta), oportunista (cuando el cliente escribe) o **manual** (lista «Para contactar» con el texto armado). Detalle en [P2](P2-motor-avisos.md). Consecuencia práctica: la mayoría de los avisos (renovación, cuota, cumpleaños, seguimiento) los termina mandando una persona; el sistema decide *a quién*, *cuándo* y *qué decir*.

## Cómo se diferencia de las tareas T1 a T4
| | T1 a T4 (SDD original) | Paquetes P1 a P9 |
|---|---|---|
| Unidad | una **capa** (ORM, lógica, API, front) | una **funcionalidad** que cruza las 4 capas |
| Quién | 4 personas, 1 capa cada una | **una** persona o chat por paquete |
| Branch | `tarea-N-…` | `paquete-pN-nombre` |
| R1 (solo tu carpeta) | rige | **se relaja**: el paquete toca `datos/`, `negocio/`, `api/` y `frontend/`, **pero en orden y por etapa**: A (ORM) → B (lógica) → C (API) → D (front). Cada etapa usa solo el contrato de la anterior. |
| Criterios | `AC-Tn-xx` en `T*-*.md` | `AC-Tn-xx` **dentro del paquete**, con la numeración ya reservada: no chocan entre paquetes |

Todo lo demás de `00-comun.md` rige igual: R2 (la spec manda), R3 (una etapa por vez), R4 (tests primero), R11 a R14 (el bot no ejecuta, el LLM no es fuente de datos, todo se guarda, solo se envía `pendiente_envio`) y R15 a R17 (front sin `innerHTML`, todo por `api.js`).

## Los paquetes
Orden recomendado (cada uno usa los anteriores de su columna *Depende de*):

| Paquete | Qué le da a Roberto | Depende de | SQL | AC T4 | AC T3 | AC T2 | AC T1 |
|---|---|---|---|---|---|---|---|
| [**P1** · Vehículos y compañías](P1-vehiculos-companias.md) | Buscar por patente; saber qué compañía emite cada póliza y cuánta comisión deja | — | `13` | 29–31 | 57–61 | 26–28 | 24–26 |
| [**P2** · Motor de avisos](P2-motor-avisos.md) | La base para avisar al cliente sin bombardearlo y respetando su baja: automático, oportunista o lista «Para contactar» | — | `14` | 32–33 | 62–67 | 29–30 | 27–29 |
| [**P3** · Renovaciones](P3-renovaciones.md) | Lista de pólizas por vencer, avisos a 60/30/7 días, renovar con un clic | P2 (P1 opcional) | `15` | 34–35 | 68–73 | 31–32 | 30–31 |
| [**P4** · Cobranza y mora](P4-cobranza-mora.md) | Recordatorios de cuota, lista de morosos, datos de pago y comprobantes por WhatsApp | P2 | `16` | 36–37 | 74–80 | 33–35 | 32–34 |
| [**P5** · Embudo de interesados y cotizaciones](P5-embudo-interesados.md) | Tablero de venta nueva con dueño y próximo contacto, seguimiento automático, comparador de compañías | P1, P2, P3 | `17` | 38–39 | 81–88 | 36–37 | 35–38 |
| [**P6** · Documentos y credencial digital](P6-documentos-credencial.md) | El cliente pide «mi póliza» y la recibe solo; credencial en el celular | P1 (opcional) | `18` | 40–41 | 89–93 | 38–39 | 39–41 |
| [**P7** · Siniestros ampliados](P7-siniestros-ampliados.md) | Checklist por tipo, semáforo de parados, avisos de estado, talleres | P2 | `19` | 42–43 | 94–99 | 40–41 | 42–44 |
| [**P8** · Panel del día, equipo y reporte mensual](P8-panel-equipo-reportes.md) | Una pantalla de arranque, tareas y notas internas, reporte con comisión | P3, P4, P5, P7 | `20` | 44–45 | 100–102 | 42–44 | 45–48 |
| [**P9** · Fidelización](P9-fidelizacion.md) | Cumpleaños, referidos, venta cruzada, encuesta post-siniestro | P2, P4, P5, P7 | `21` | 46–47 | 103–108 | 45–47 | 49–51 |

P1 y P2 son independientes: se pueden hacer a la vez en dos chats. P6 también puede ir en cualquier momento después de P1.

## Reglas comunes a todos los paquetes
1. **Esquema (excepción documentada a R8).** Cada paquete tiene su incremento `SDD/sql/NN_*.sql`, como ya pasó con `05` a `12`: idempotente (`IF NOT EXISTS`, `ON CONFLICT`), dentro de `BEGIN; … COMMIT;`, con cabecera que dice de qué archivo depende. Lo escribe la etapa A, lo agrega a la lista de `config/test_runner.py` y **una sola persona lo aplica a la base real** antes de probar a mano. Nadie corre `makemigrations`.
2. **Los números de SQL son únicos por paquete** (13 a 21). Si dos paquetes se hacen a la vez no se pisan; si uno necesita una columna de otro, lo dice su sección *Depende de*.
3. **Contratos.** Al terminar cada etapa se agregan los modelos, funciones y endpoints nuevos a `SDD/contratos/modelos.md`, `servicios.md` y `api.md`. La etapa siguiente trabaja **solo** contra eso (R5).
4. **Páginas nuevas.** Cada página del front lleva: su ruta en la lista blanca de `api/paginas.py` (etapa C, como AC-T2-21), su `.html` + `.js` en `frontend/` (etapa D), un enlace en `nav.js` y la fila en `SDD/qa/T1.md`.
5. **Avisos.** Todo mensaje que el sistema inicia pasa por el motor de P2: texto fijo + datos de la base (R12), `evaluar_salida` (R13), y respeta `acepta_avisos`. Nada usa plantillas de Meta ni manda por su cuenta fuera de la ventana de 24 h: lo que no puede salir queda en «Para contactar».
6. **Acciones contractuales.** Lo que cambia el contrato de un cliente (renovar, dar de baja, agregar conductor) sigue pasando por `AccionPendiente` y aprobador (R11).
7. **Datos ficticios** (R10). Los tests usan las fábricas de T4; cada paquete agrega las suyas.
8. **Entrega.** Al terminar: `python SDD/verificar.py T1` a `T4` sin faltantes *de los AC del paquete*, y `SDD/entregas/Pn.md` (plantilla `_plantilla.md`, cambiando `Tn` por `Pn`).

## Cómo pedirle un paquete a un chat
Una sesión nueva **por etapa**. Pegar, en este orden: `SDD/00-comun.md`, este `README.md`, el archivo del paquete, y los contratos que su etapa indica. Mensaje de arranque:

```
Seguí 00-comun.md y SDD/paquetes/README.md al pie de la letra.
Vamos a hacer el paquete P<N>, ETAPA <A|B|C|D>.
Antes de escribir código respondé solo: (1) qué AC cubre la etapa, (2) qué archivos vas a crear o
modificar, (3) dudas o contradicciones. Esperá mi OK.
```

Etapa A = ORM y esquema · B = lógica · C = API · D = front. No saltear el orden: B lee el contrato de A, C el de B, D el de C.

## Cómo comprobar
```bash
python manage.py test datos negocio api   # las tres suites de Python
npm test                                   # JavaScript (sin argumentos)
python SDD/verificar.py T3                 # cada AC con su test; ahora también lee SDD/paquetes/
```
