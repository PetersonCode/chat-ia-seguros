# Sistema de Atención al Cliente con Bot IA y Panel de Supervisión para Agencia de Seguros

**Caso 8 – Seguros Castaño**

Sistema que automatiza la atención al cliente de una agencia de seguros mediante un asistente de IA conectado a WhatsApp, con un panel web en tiempo real para que los asesores supervisen las conversaciones y tomen el control cuando sea necesario.

---

## Integrantes

- Juan Ignacio Morana
- Sebastian Damonte
- Daniel Peterson
- Agustin Stele

---

## Descripción del proyecto

El objetivo es resolver los problemas actuales de atención al cliente y gestión operativa de la agencia, permitiendo atención simultánea y 24/7, recepción ordenada de siniestros y derivación inmediata a un humano ante situaciones urgentes.

## Alcance (MVP 1)

- **Conexión oficial con WhatsApp API:** línea corporativa que habilita la atención simultánea sin depender de teléfonos físicos y previene bloqueos de cuenta.
- **Asistente de IA (RAG):** bot entrenado de forma restringida con la documentación y pólizas de la agencia para cotizar seguros, explicar coberturas y responder consultas 24/7 sin inventar información.
- **Recepción y tipificación de siniestros:** flujo guiado por la IA para que el cliente reporte incidentes y envíe fotografías (DNI, cédula, daños del vehículo) directamente por el chat.
- **Motor de interrupción automática (Human Handoff):** semáforo y detección de palabras clave de urgencia (ej. "choque", "hospital", "robo") que pausa la IA al instante y emite una alerta al equipo humano.
- **Panel de supervisión (CRM) en tiempo real:** plataforma web con login exclusivo para asesores, donde pueden ver todas las conversaciones activas y tomar el control manual de los chats.

## Stack tecnológico

| Capa | Tecnología |
|------|------------|
| Backend | Python + Django |
| Base de datos | SQL Server (conector `mssql-django`) |
| Frontend | HTML + plantillas de Django |
| Estilos | Bootstrap |
| Interactividad | JavaScript |
| Mensajería | WhatsApp Business API (Meta) |
| IA | Modelo de lenguaje con RAG sobre pólizas y condiciones |

## Modelo de datos

La base de datos relacional vincula clientes, pólizas, vehículos, siniestros, conversaciones y registros de auditoría. Las entidades principales son:

- **Cliente**, **Póliza**, **Vehículo** y **Siniestro**, con sus tablas de tipo (`Tipo_Cobertura`, `Tipo_Vehiculo`).
- **Caso**: núcleo de la atención, asociado a un cliente, un empleado, un tipo de consulta, un estado y un resultado. Registra si requiere intervención humana o si es un incidente de seguridad.
- **Mensaje**: cada mensaje intercambiado dentro de un caso.
- **Operación IA** y **Tipo Operación**: acciones críticas realizadas por la IA, con estado de autorización y empleado que autoriza.
- **Empleado** y **Rol**: usuarios del panel y sus permisos.
- Tablas auxiliares: `Tipo_Consulta`, `Estado_Caso`, `Resultado`.

> Podés agregar el diagrama entidad-relación en `docs/` y referenciarlo así: `![Modelo de datos](docs/der.png)`

## Instalación y ejecución

> ⚠️ Ajustar los nombres de archivos, variables y comandos según cómo quedó armado el repositorio.

### Requisitos

- Python 3.10 o superior
- SQL Server (con el driver ODBC correspondiente instalado)
- Cuenta de WhatsApp Business API (Meta)
- Credenciales del proveedor de IA

### Pasos

```bash
# 1. Clonar el repositorio
git clone <URL_DEL_REPOSITORIO>
cd <NOMBRE_DEL_REPOSITORIO>

# 2. Crear y activar el entorno virtual
python -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno (ver sección siguiente)
cp .env.example .env

# 5. Aplicar migraciones
python manage.py migrate

# 6. Crear un usuario administrador
python manage.py createsuperuser

# 7. Levantar el servidor
python manage.py runserver
```

El panel queda disponible en `http://127.0.0.1:8000/`.

### Variables de entorno

```env
SECRET_KEY=
DEBUG=True

# Base de datos
DB_NAME=
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=

# WhatsApp API (Meta)
WHATSAPP_TOKEN=
WHATSAPP_PHONE_ID=
WHATSAPP_VERIFY_TOKEN=

# Inteligencia Artificial
AI_API_KEY=
```

## Cronograma

El desarrollo está planificado en 3 sprints, con una duración total de 6 semanas y 270 horas de esfuerzo (incluye un 20% de buffer de contingencia).

| Sprint | Semanas | Objetivos |
|--------|---------|-----------|
| 1 | 1–2 | Configuración de la cuenta oficial de WhatsApp API, diseño de la base de datos, setup de servidores y maquetado inicial del panel de supervisión. |
| 2 | 3–4 | Integración del modelo de IA, procesamiento de pólizas y condiciones, flujo de recepción de siniestros y archivos adjuntos. |
| 3 | 5–6 | Botón de toma de control (Human Handoff), pruebas de estrés, testing de derivación de mensajes y pase a producción. |

## Estructura del proyecto

> Completar con la estructura real del repositorio.

```
.
├── manage.py
├── requirements.txt
├── .env.example
├── docs/
└── <apps de Django>/
```
