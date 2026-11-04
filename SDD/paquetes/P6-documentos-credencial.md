# P6 · Documentos y credencial digital

**Branch:** `paquete-p6-documentos` · **SQL:** `SDD/sql/18_documentos_poliza.sql` · **Depende de:** nada (P1 agrega la patente a la credencial si existe).
**Por qué (Roberto):** «mandame la póliza» es la consulta que más se repite y hoy me interrumpe a mí o a Graciela. Y cuando la policía para a un cliente, muchos no encuentran la credencial. Quiero que el cliente la pida por WhatsApp y la reciba solo, y que tenga una credencial en el celular.

## 1. Decisiones de diseño
- **No hay generación de PDF.** `00-comun.md` limita las dependencias de Python y no incluye ninguna librería de PDF. Por eso hay **dos cosas distintas**:
  1. La **póliza real** (el PDF que emite la compañía) la sube un aprobador a la póliza correspondiente; el bot la reenvía tal cual.
  2. La **credencial digital** es una página web chica, para el celular, a la que se entra por un **link con token** (sin sesión), con los datos esenciales y el teléfono de asistencia.
- **Privacidad.** La credencial es pública para quien tenga el link, así que **no muestra** saldo, prima, DNI completo ni datos de otros clientes. El token es largo e impredecible y se puede revocar.
- **Variable nueva** `PUBLIC_BASE_URL` (ej.: `https://agencia.example`): excepción a la sección 7 de `00-comun.md`; la etapa A la agrega a `SDD/plantillas/env.example` y a esa sección, con default `http://localhost:8000` en desarrollo.

## 2. Esquema (`18_documentos_poliza.sql`)
```
documentos_poliza  id, poliza_id → polizas, tipo (poliza, certificado_cobertura, otro), titulo, archivo text (ruta privada),
                   mime text, tamano int, subido_por_id → funcionarios, subido_en, activo bool default true
credenciales       id, poliza_id → polizas, token text UNIQUE (largo mínimo 32), creada_en, revocada_en null
                   UNIQUE parcial: una sola credencial no revocada por póliza
tipos_consulta     + ('documento', 'Pedido de póliza o credencial', 'bot_responde')
```

## 3. Etapa A · ORM (T4)
| ID | Criterio |
|---|---|
| AC-T4-40 | Dados `DocumentoPoliza` y `Credencial` (`related_name` `poliza.documentos` y `poliza.credenciales`), `TipoDocumentoPoliza` coincidente con el `CHECK` (AC-T4-07), `crear_catalogos()` con el tipo `documento`, el SQL 18 en `test_runner.py` (aplicable dos veces) y las fábricas `crear_documento_poliza` y `crear_credencial` (token aleatorio), entonces todo se crea sin error; un token de menos de 32 caracteres es rechazado por la base. |
| AC-T4-41 | Dadas `documentos_de_poliza(poliza_id, solo_activos=True)` y `credencial_por_token(token)` (devuelve la credencial **no revocada** con su póliza, cliente, vehículo y compañía en un número fijo de consultas, o `None`), y `PUBLIC_BASE_URL` leída en `config/settings.py` con default de desarrollo, entonces `python manage.py check` pasa sin la variable. |

## 4. Etapa B · Lógica (T3)
Archivos: `negocio/credenciales.py` y `negocio/documentos_poliza.py` (nuevos), `negocio/whatsapp.py`, `negocio/bot/` (orquestador, plantillas, guardrails).
| ID | Criterio |
|---|---|
| AC-T3-89 | Dados `obtener_o_crear_credencial(poliza_id)` (devuelve la no revocada o crea una con `secrets.token_urlsafe(32)`), `revocar_credencial(poliza_id, funcionario_id)` (aprobador; la siguiente llamada a `obtener_o_crear` genera un token nuevo) y `url_credencial(token)` (`PUBLIC_BASE_URL` + `/c/<token>/`), entonces el token nunca se repite, la póliza dada de baja no admite credencial nueva (`EstadoInvalido`) y revocar sin credencial activa es `EstadoInvalido`. |
| AC-T3-90 | Dada `datos_de_credencial(token)`, entonces devuelve `None` si el token no existe o está revocado; si existe, devuelve **solo** `{numero_poliza, estado, vigencia_desde, vigencia_hasta, tipo_seguro, cobertura, compania, asegurado (nombre y apellido), dni_enmascarado ("***678"), vehiculo (patente, marca, modelo, año) o null, conductores (solo nombres), telefono_asistencia}`; nunca saldo, prima, comisión ni DNI completo; una póliza vencida o dada de baja se devuelve con su `estado` real (nunca como vigente); el teléfono sale de `TELEFONOS_ASISTENCIA` por cobertura. |
| AC-T3-91 | Dados `subir_documento_poliza(poliza_id, funcionario_id, tipo, titulo, contenido: bytes, nombre_archivo)` y `quitar_documento_poliza(id, funcionario_id)` (baja lógica), ambos de aprobador, entonces se acepta solo PDF (empieza con `%PDF-`) o imagen válida, de hasta 10 MB, guardado con nombre aleatorio en el almacenamiento privado (como `adjuntos_siniestros.py`); título vacío, tipo inválido o contenido de otro formato es `DatosInvalidos`; un operador, `PermisoDenegado`; el nombre original nunca forma parte de la ruta. |
| AC-T3-92 | Dada una consulta `documento` («mandame la póliza», “mi credencial”, «certificado de cobertura», «no encuentro mi póliza»), entonces el bot, para un contacto con cliente, responde con `CREDENCIAL` («Tu credencial digital de {numero_poliza}{vehiculo}: {link}») por cada póliza vigente (hasta 5; con más, deriva a Graciela) y, si esa póliza tiene un documento activo de tipo `poliza`, crea además un mensaje saliente con `payload.documento`; sin pólizas vigentes responde `SIN_POLIZAS` y deriva; sin cliente, `SIN_CLIENTE` y deriva. El link va en `datos_verificados` y el host de `PUBLIC_BASE_URL` queda permitido para `evaluar_salida` sin tocar `BOT_URLS_PERMITIDAS`; cualquier otro dominio sigue alertando (AC-T3-38). |
| AC-T3-93 | Dado un mensaje saliente con `payload.documento`, cuando `enviar_pendientes` lo procesa, entonces en modo `simulado` queda `enviado` y se escribe en el log; en modo `real` sube el archivo a la API de Meta (multipart con `urllib`, timeout 10 s) y lo manda como `type: "document"` con su título como nombre; si el archivo ya no existe o la API falla, queda `fallido` con `error` descriptivo (`archivo_no_disponible` o el detalle); respeta la ventana de 24 h y R14. La red se simula en los tests. |

## 5. Etapa C · API (T2)
| ID | Criterio |
|---|---|
| AC-T2-38 | Dados `GET /c/<token>/` (devuelve `credencial.html`, sin sesión) y `GET /api/publico/credencial/<token>/` (JSON de `datos_de_credencial`, sin sesión ni CSRF), entonces un token inexistente o revocado responde `404` con el mismo cuerpo genérico en ambos casos (no revela cuál fue); las respuestas llevan `Cache-Control: no-store` y `X-Robots-Tag: noindex`; ninguna otra ruta pública expone datos. |
| AC-T2-39 | Dados `GET /api/polizas/{id}/documentos/` (cualquier funcionario), `POST /api/polizas/{id}/documentos/` (multipart, aprobador), `GET /api/documentos-poliza/{id}/archivo/` (protegido por sesión, `Content-Type` real, `Cache-Control: private, no-store`, sin rutas del servidor en el JSON), `POST /api/documentos-poliza/{id}/quitar/`, `GET /api/polizas/{id}/credencial/` (`{url}`) y `POST /api/polizas/{id}/credencial/revocar/`, entonces llaman a las funciones de AC-T3-89 a 91 y traducen los errores según AC-T2-03. |

## 6. Etapa D · Front (T1)
| ID | Criterio |
|---|---|
| AC-T1-39 | **(QA)** Dada `credencial.html` (en `/c/<token>/`), entonces se ve bien en un celular (ancho de 360 px sin scroll horizontal): estado grande y con texto (VIGENTE / VENCIDA / DADA DE BAJA, no solo color), patente, vigencia, asegurado, conductores y el teléfono de asistencia como enlace `tel:`; sin barra de navegación; un token inválido muestra «Esta credencial no está disponible» sin detalles; no carga scripts externos; los datos se muestran con `textContent`. |
| AC-T1-40 | **(QA)** Dada la ficha de cliente, entonces cada póliza permite (aprobadores) subir un documento (tipo y título), ver los existentes, quitarlos, copiar el link de la credencial y revocarlo con confirmación; los demás los ven sin botones. |
| AC-T1-41 | Dado `lib/credencial.js`, entonces `etiquetaEstadoCredencial("vigente"…)` → «VIGENTE», «VENCIDA», «DADA DE BAJA» (desconocido → «—»), `claseEstadoCredencial` → `estado-ok`/`estado-alerta` (definidas en `app.css`), y `formatearDniEnmascarado("***678")` lo devuelve tal cual (nunca intenta reconstruirlo). |

## 7. Terminado cuando
Los 12 AC con prueba, contratos actualizados (incluida `PUBLIC_BASE_URL` en `env.example` y `00-comun.md`), SQL 18 aplicado, y a mano: «mandame la póliza» por `simular_whatsapp` → link → abrir la credencial desde un celular → revocar → el link deja de andar. `SDD/entregas/P6.md`.
