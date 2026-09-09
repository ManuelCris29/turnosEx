# -*- coding: utf-8 -*-
"""Genera docs/pdf/Auditoria_Costos_AWS.docx

Auditoria de costos AWS de AppTurnos/SWALP, con precios verificados
en calculator.aws (us-east-1, on-demand) el 2026-09-07, y ElastiCache
verificado contra la AWS Price List Bulk API (catalogo 20260903183902).

Regenerar:  python scripts/generar_auditoria_costos_aws.py
"""
from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor, Inches

FECHA = "7 de septiembre de 2026"
TRM = 4050
SALIDA = r"C:\appTurnos\AppTurnosExplora\docs\pdf\Auditoria_Costos_AWS.docx"

doc = Document()

# --- estilo base -----------------------------------------------------------
normal = doc.styles["Normal"]
normal.font.name = "Calibri"
normal.font.size = Pt(10.5)


def h(texto, nivel=1):
    p = doc.add_heading(texto, level=nivel)
    for run in p.runs:
        run.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)
    return p


def parrafo(texto, negrita=False, cursiva=False):
    p = doc.add_paragraph()
    r = p.add_run(texto)
    r.bold = negrita
    r.italic = cursiva
    return p


def vinetas(items):
    for it in items:
        doc.add_paragraph(it, style="List Bullet")


def tabla(cabeceras, filas, anchos=None, resaltar_ultima=False):
    t = doc.add_table(rows=1, cols=len(cabeceras))
    t.style = "Light Grid Accent 1"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, texto in enumerate(cabeceras):
        celda = t.rows[0].cells[i]
        celda.text = ""
        run = celda.paragraphs[0].add_run(texto)
        run.bold = True
    for fila in filas:
        celdas = t.add_row().cells
        for i, valor in enumerate(fila):
            celdas[i].text = ""
            run = celdas[i].paragraphs[0].add_run(str(valor))
            if i > 0:
                celdas[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    if resaltar_ultima:
        for celda in t.rows[-1].cells:
            for p in celda.paragraphs:
                for run in p.runs:
                    run.bold = True
    if anchos:
        for fila in t.rows:
            for i, ancho in enumerate(anchos):
                fila.cells[i].width = Inches(ancho)
    doc.add_paragraph()
    return t


# --- portada ---------------------------------------------------------------
titulo = doc.add_heading("Auditoría de costos AWS — AppTurnos / SWALP", level=0)
for run in titulo.runs:
    run.font.color.rgb = RGBColor(0x1F, 0x38, 0x64)

parrafo(f"Fecha de la auditoría: {FECHA}", negrita=True)
parrafo("Región: us-east-1 (Norte de Virginia) · Modelo: on-demand")
parrafo(
    "Precios verificados uno a uno en la calculadora oficial de AWS "
    "(https://calculator.aws) y, para ElastiCache, contra la AWS Price List Bulk API. "
    "Ninguna cifra proviene de comparativas de terceros."
)
parrafo(f"Tasa de cambio usada: {TRM:,} COP/USD".replace(",", "."))
parrafo("Presupuesto tope del proyecto: 150.000 COP/mes")

doc.add_paragraph()

# --- 1. Resumen ejecutivo --------------------------------------------------
h("1. Resumen ejecutivo", 1)

parrafo(
    "Esta auditoría nace de una alarma: una estimación de costos de AWS que circulaba "
    "parecía indicar que el proyecto costaría mucho más de lo presupuestado. "
    "La conclusión es que la alarma era infundada, y por una razón concreta."
)

h("1.1 La estimación de terceros no contenía ningún precio", 2)
parrafo(
    "Se revisó la conversación completa que originó la alarma. Consta de dos preguntas: "
    "«qué es AWS Well-Architected» y «dame un ejemplo con Django en EC2 y RDS». "
    "La respuesta es una guía genérica de los seis pilares del marco Well-Architected. "
    "No aparece ni una sola cifra en dólares en toda la conversación."
)
parrafo(
    "Lo que genera el sobrecosto no es un cálculo: es la arquitectura que esa guía recomienda "
    "por defecto, que es la plantilla de libro de texto y no está dimensionada para "
    "300 usuarios y 30 solicitudes al día.",
)

h("1.2 Cifras finales", 2)
tabla(
    ["Escenario", "USD/mes", "Con IVA 19 %", "COP/mes"],
    [
        ["Arquitectura del proyecto (t4g.micro)", "26,96", "32,08", "≈ 130.000"],
        ["Arquitectura genérica Well-Architected", "112,31", "133,65", "≈ 541.000"],
        ["Diferencia", "+85,35", "+101,57", "≈ +411.000"],
    ],
    anchos=[3.0, 1.1, 1.1, 1.3],
    resaltar_ultima=True,
)
parrafo(
    "La arquitectura genérica cuesta 4,2 veces más y se sale del presupuesto por un factor "
    "de 3,6. La arquitectura del proyecto cabe dentro del techo de 150.000 COP/mes.",
    negrita=True,
)

doc.add_page_break()

# --- 2. Verificación del presupuesto ---------------------------------------
h("2. Verificación del presupuesto del proyecto", 1)
parrafo(
    "Se reconstruyó la estimación completa en calculator.aws, servicio por servicio, "
    "para contrastarla contra el documento «arquitectura-aws-rds-recomendada.md». "
    "Todos los precios coinciden."
)

tabla(
    ["Recurso", "Documento", "Calculadora AWS", "Precio unitario"],
    [
        ["EC2 t4g.micro (2 vCPU, 1 GiB)", "6,13", "6,13", "0,0084 USD/h"],
        ["Disco EC2 — EBS gp3 20 GB", "1,60", "1,60", "0,08 USD/GB-mes"],
        ["RDS db.t4g.micro MySQL Single-AZ", "11,68", "11,68", "0,016 USD/h"],
        ["Almacenamiento RDS gp3 20 GB", "2,30", "2,30", "0,115 USD/GB-mes"],
        ["IPv4 pública (1 Elastic IP)", "3,65", "3,65", "0,005 USD/h"],
        ["Amazon SES (6.000 correos/mes)", "0,60", "0,60", "0,10 USD/1.000"],
        ["Subtotal verificado", "25,96", "25,96", "—"],
    ],
    anchos=[2.6, 1.0, 1.3, 1.5],
    resaltar_ultima=True,
)

parrafo(
    "El documento suma además 1,00 USD por CloudWatch y transferencia de datos de salida, "
    "lo que da el subtotal de 26,96 USD y 32,08 USD con IVA — unos 130.000 COP al mes.",
)

h("2.1 Confirmación de la advertencia sobre precios mal etiquetados", 2)
parrafo(
    "El documento advertía que algunas comparativas publican db.t4g.micro a 0,03 USD/h "
    "y que ese es en realidad el precio Multi-AZ. La calculadora lo confirma: "
    "Single-AZ son 0,016 USD/h y Multi-AZ son exactamente 0,032 USD/h, el doble. "
    "La advertencia del documento es correcta."
)

doc.add_page_break()

# --- 3. Costo fijo vs variable ---------------------------------------------
h("3. ¿El costo depende de cuánto se use la app?", 1)

parrafo(
    "Pregunta frecuente y necesaria: si la aplicación está disponible 24 horas al día "
    "los 7 días de la semana, y los 300 exploradores entran a consultar sus turnos, "
    "sanciones y restricciones, y los supervisores descargan el reporte diario y "
    "registran novedades, ¿el costo sigue siendo el mismo?"
)
parrafo(
    "Sí. Prácticamente todo el costo es por tener la infraestructura encendida, "
    "no por el trabajo que atiende.",
    negrita=True,
)

h("3.1 Lo que no cambia con el uso", 2)
parrafo(
    "Estos componentes se facturan por hora de existencia o por GB aprovisionado. "
    "Cuestan exactamente lo mismo con cero usuarios que con los 300 usándola "
    "intensamente todo el día:"
)

tabla(
    ["Componente", "Cómo se factura", "USD/mes"],
    [
        ["EC2 t4g.micro", "por hora encendida", "6,13"],
        ["Disco de la EC2", "por GB aprovisionado", "1,60"],
        ["RDS db.t4g.micro", "por hora encendida", "11,68"],
        ["Disco de RDS", "por GB aprovisionado", "2,30"],
        ["IPv4 pública", "por hora asignada", "3,65"],
        ["Subtotal fijo", "—", "25,36"],
    ],
    anchos=[2.4, 2.4, 1.2],
    resaltar_ultima=True,
)

parrafo(
    "AWS cobra por mantener la instancia disponible las 730 horas del mes, no por "
    "peticiones atendidas. Es el modelo opuesto al de un servicio «serverless», donde "
    "sí se paga por invocación."
)

h("3.2 Lo que sí varía (y ya está presupuestado)", 2)

tabla(
    ["Concepto", "Tarifa", "Uso real del proyecto", "USD/mes"],
    [
        [
            "Amazon SES",
            "0,10 USD / 1.000 correos",
            "≈ 6.000 correos al mes",
            "0,60",
        ],
        [
            "Transferencia de salida",
            "primeros 100 GB gratis",
            "decenas de GB al mes",
            "≈ 0",
        ],
    ],
    anchos=[1.9, 1.9, 2.0, 0.9],
)

parrafo(
    "Sobre la transferencia de datos, se revisó qué sale realmente hacia el navegador:"
)
vinetas([
    "Los archivos estáticos (72 MB de CSS, JavaScript, fuentes e imágenes) se descargan "
    "una sola vez y quedan en la caché del navegador. No se vuelven a transferir en "
    "cada visita.",
    "Ya cacheados, cada pantalla —Mis Turnos, sanciones, restricciones— mueve solo "
    "HTML y JSON, del orden de decenas de kilobytes.",
    "El reporte diario del supervisor (reporte_operacion_<fecha>.xlsx, cinco hojas, "
    "generado en turnos/api/views/reportes.py) pesa cientos de kilobytes. Treinta "
    "descargas al mes son irrelevantes frente al umbral gratuito.",
])
parrafo(
    "Para que SES llegara a importar, el volumen tendría que multiplicarse por dieciséis "
    "hasta unos 100.000 correos mensuales, y aun así serían 10 USD."
)

h("3.3 Dónde sí se nota el uso intensivo: en la velocidad, no en la factura", 2)

parrafo(
    "t4g.micro es una instancia «burstable»: tiene un rendimiento base y acumula "
    "créditos de CPU mientras está ociosa. Si el uso sostenido supera ese rendimiento "
    "base —por ejemplo, si buena parte del equipo abre el tablero a la misma hora del "
    "cambio de turno— los créditos se agotan."
)
parrafo(
    "Aquí es donde importa una decisión ya tomada en el plan: mantener la EC2 en modo "
    "«standard», no en «unlimited». En modo standard, al agotarse los créditos la "
    "instancia se ralentiza pero no cobra de más. En modo unlimited, que es el valor "
    "por defecto de AWS, seguiría rápida facturando el excedente sin techo.",
    negrita=True,
)
parrafo(
    "Consecuencia práctica: con la configuración del plan, el uso intenso se manifiesta "
    "como lentitud, nunca como una factura sorpresa. Y si la lentitud aparece, subir a "
    "t4g.small es un clic y una decisión deliberada, no un cargo inesperado."
)

h("3.4 La excepción que hay que vigilar", 2)
parrafo(
    "En RDS el modo unlimited no se puede desactivar. La documentación de AWS es "
    "explícita: todas las instancias burstable de RDS están configuradas en Unlimited y "
    "no existe un modo standard. Si la base de datos agotara créditos de forma "
    "sostenida, AWS cobraría el excedente."
)
parrafo(
    "Con 7,4 MB de base de datos —que cabe entera en memoria, de modo que las lecturas "
    "del tablero ni siquiera tocan disco— es improbable. Por eso el plan exige la alarma "
    "de CloudWatch sobre CPUSurplusCreditsCharged mayor que cero: es el único aviso de "
    "que RDS empezó a cobrar por encima del base."
)

parrafo(
    "En resumen: los 130.000 COP mensuales son un costo fijo, no una estimación de "
    "consumo. Lo que el uso real puede mover son céntimos de SES y de transferencia. "
    "El riesgo verdadero de tener 300 exploradores activos es de rendimiento, y está "
    "acotado por el modo standard más el presupuesto con alerta en 30 USD.",
    negrita=True,
)

doc.add_page_break()

# --- 4. Las dos trampas ----------------------------------------------------
h("4. Dos trampas de la propia calculadora de AWS", 1)
parrafo(
    "Al configurar Amazon RDS en calculator.aws, dos opciones vienen activadas por defecto "
    "y ninguna de las dos se usa en este proyecto:"
)

tabla(
    ["Opción activada por defecto", "Costo que añade", "¿La usa la app?"],
    [
        ["RDS Proxy", "21,90 USD/mes", "No"],
        ["CloudWatch Database Insights", "10,52 USD/mes", "No"],
        ["Sobrecosto total si no se apagan", "32,42 USD/mes", "—"],
    ],
    anchos=[3.0, 1.6, 1.4],
    resaltar_ultima=True,
)

parrafo(
    "Quien reproduzca la estimación sin apagar esos dos interruptores obtiene una factura "
    "de RDS más de tres veces mayor que la real, y concluye que el presupuesto está mal "
    "calculado. Es la explicación más probable de las cifras infladas que circulan.",
    negrita=True,
)

parrafo(
    "Recomendación operativa: cualquier estimación de RDS que se comparta debe indicar "
    "explícitamente que RDS Proxy y Database Insights están en «No».",
    cursiva=True,
)

doc.add_page_break()

# --- 4. Arquitectura genérica ----------------------------------------------
h("5. Desglose de la arquitectura genérica Well-Architected", 1)
parrafo(
    "Estos son los componentes que recomienda la guía genérica y lo que cuesta cada uno "
    "a la escala real del proyecto. Los importes marcados como verificados se midieron "
    "en calculator.aws durante esta auditoría."
)

tabla(
    ["Componente", "USD/mes", "Origen"],
    [
        ["EC2 t4g.micro × 2 (Auto Scaling, mínimo 2)", "12,26", "Verificado"],
        ["EBS gp3 20 GB × 2", "3,20", "Verificado"],
        ["Application Load Balancer", "16,66", "Verificado"],
        ["NAT Gateway (EC2 en subred privada)", "33,30", "Verificado"],
        ["RDS db.t4g.micro Multi-AZ", "23,36", "Verificado"],
        ["Almacenamiento RDS 20 GB Multi-AZ", "4,60", "Verificado"],
        ["ElastiCache cache.t4g.micro (Redis)", "11,68", "Verificado"],
        ["IPv4 pública para el NAT Gateway", "3,65", "Verificado"],
        ["Amazon SES", "0,60", "Verificado"],
        ["S3 + CloudFront para estáticos", "1,00", "Estimado"],
        ["CodePipeline / CodeBuild", "1,00", "Estimado"],
        ["CloudWatch y transferencia de salida", "1,00", "Estimado"],
        ["Total", "112,31", "—"],
    ],
    anchos=[3.4, 1.1, 1.5],
    resaltar_ultima=True,
)

parrafo(
    "Con IVA del 19 %: 133,65 USD/mes, unos 541.000 COP. El presupuesto del proyecto "
    "es de 150.000 COP/mes.",
    negrita=True,
)

h("5.1 Nota sobre ElastiCache", 2)
parrafo(
    "El precio de ElastiCache no se pudo obtener desde calculator.aws: el formulario "
    "bloquea el selector de tipo de nodo al filtrar por nombre. Se verificó contra la "
    "AWS Price List Bulk API, el catálogo oficial que alimenta a la propia calculadora "
    "(catálogo 20260903183902, publicado el 3 de septiembre de 2026)."
)

tabla(
    ["Motor", "Memoria", "vCPU", "USD/hora", "USD/mes"],
    [
        ["Redis", "0,5 GiB", "2", "0,0160", "11,68"],
        ["Memcached", "0,5 GiB", "2", "0,0160", "11,68"],
        ["Valkey", "0,5 GiB", "2", "0,0128", "9,34"],
    ],
    anchos=[1.6, 1.2, 0.8, 1.2, 1.2],
)

parrafo(
    "Dos observaciones que salieron de esa consulta:"
)
vinetas([
    "cache.t4g.micro comparte tarifa exacta con db.t4g.micro: 0,016 USD/hora. No es "
    "coincidencia, es la misma clase de instancia burstable.",
    "Valkey cuesta un 20 % menos que Redis con el mismo hardware (9,34 frente a "
    "11,68 USD/mes). Si algún día entra ElastiCache en la arquitectura, Valkey es el "
    "motor por defecto correcto.",
    "El catálogo también lista entradas de «ExtendedSupport» a 0,0130 y 0,0260 USD/hora. "
    "No son un precio de nodo más barato: son el recargo por permanecer en una versión "
    "de Redis fuera de soporte, y se SUMAN a la tarifa del nodo.",
])

h("5.2 De dónde sale realmente el sobrecosto", 2)
parrafo(
    "Tres decisiones concentran el 74 % de la diferencia, y ninguna aporta valor "
    "a la escala actual:"
)
vinetas([
    "NAT Gateway (33,30 USD/mes) — solo existe porque esa arquitectura mete la EC2 en "
    "una subred privada. Manteniendo la instancia en subred pública con un grupo de "
    "seguridad restrictivo, el gasto desaparece por completo.",
    "Application Load Balancer (16,66 USD/mes) — un balanceador con una sola instancia "
    "detrás no balancea nada. Solo tiene sentido a partir de dos instancias web.",
    "RDS Multi-AZ (+11,68 USD/mes sobre Single-AZ) — da conmutación automática por error. "
    "Es una mejora real de disponibilidad, pero es una decisión de negocio que hoy "
    "no cabe en el presupuesto.",
])

doc.add_page_break()

# --- 5. Auditoría del código -----------------------------------------------
h("6. Auditoría del código: por qué el dimensionamiento es correcto", 1)
parrafo(
    "Se revisó el código de la aplicación para comprobar que no existe ninguna pieza "
    "que justifique los servicios adicionales de la arquitectura genérica."
)

tabla(
    ["Servicio que se evita", "Evidencia en el código"],
    [
        [
            "Cola de tareas (Celery, SQS, Lambda)",
            "Los 23 comandos de mantenimiento se ejecutan por cron en la propia EC2.",
        ],
        [
            "ElastiCache / Redis",
            "config/settings.py líneas 307-338 contempla Redis y lo descarta "
            "explícitamente; la caché es local o en base de datos.",
        ],
        [
            "Amazon S3",
            "No hay cargas de archivos de usuario. Los 143 MB de estáticos los sirve Nginx.",
        ],
        [
            "Application Load Balancer",
            "Una sola instancia web. El HTTPS lo resuelve Certbot / Let's Encrypt gratis.",
        ],
    ],
    anchos=[2.3, 4.2],
)

h("6.1 Volumen de correo confirmado", 2)
parrafo(
    "El patrón outbox (solicitudes/management/commands/procesar_email_outbox.py y "
    "solicitudes/services/notificacion_service.py) confirma el conteo del documento: "
    "entre 1 y 3 correos al crear una solicitud y entre 2 y 4 al responderla, "
    "aproximadamente 6 por solicitud. A 30 solicitudes diarias son unos 5.400 correos "
    "al mes, más recuperación de contraseña y avisos de seguridad: cerca de 6.000. "
    "A 0,10 USD por millar, 0,60 USD al mes."
)

doc.add_page_break()

# --- 6. Recomendaciones ----------------------------------------------------
h("7. Recomendaciones", 1)

h("7.1 Mantener la arquitectura actual", 2)
parrafo(
    "La decisión del documento (EC2 t4g.micro en subred pública, RDS db.t4g.micro "
    "Single-AZ, SES, Elastic IP, sin balanceador ni caché) es la correcta para "
    "300 usuarios y 30 solicitudes al día, y está verificada contra precios oficiales."
)

h("7.2 Lo que sí conviene adoptar de la guía Well-Architected", 2)
parrafo("Dos prácticas de esa guía son válidas, no están en el plan actual y cuestan cero:")
tabla(
    ["Práctica", "Costo", "Por qué"],
    [
        [
            "Mover el .env a AWS Systems Manager Parameter Store",
            "0,00 USD",
            "La versión estándar es gratuita. Elimina los secretos del disco de la "
            "instancia y permite rotarlos sin volver a desplegar.",
        ],
        [
            "Probar la restauración de un snapshot de RDS",
            "0,00 USD",
            "Un backup que nunca se ha restaurado no es un backup. Hoy no está "
            "en el checklist de despliegue.",
        ],
    ],
    anchos=[2.4, 0.9, 3.2],
)

h("7.3 Controles de costo que siguen siendo obligatorios", 2)
vinetas([
    "Poner la instancia EC2 en modo standard, no unlimited: convierte el exceso de CPU "
    "en limitación de velocidad en lugar de en factura sin techo.",
    "Alarma de CloudWatch sobre CPUSurplusCreditsCharged de RDS mayor que cero: en RDS "
    "el modo unlimited no se puede desactivar, así que esta alarma es el único aviso.",
    "AWS Budget con alerta en 30 USD.",
    "No reservar la Elastic IP antes de necesitarla: se cobra aunque esté ociosa.",
    "Verificar si la cuenta tiene menos de 12 meses: con Free Tier el costo del primer "
    "año bajaría a unos 5 USD al mes.",
])

h("7.4 Cuándo revisar de nuevo", 2)
parrafo(
    "Los gatillos de escalado ya definidos siguen vigentes: CPU de EC2 sostenida por "
    "encima del 70 % lleva a t4g.small; agotamiento sostenido de créditos de CPU en RDS "
    "lleva a db.t4g.small; y solo si hacen falta dos instancias web entran en juego "
    "el balanceador y la caché compartida. Antes no."
)

doc.add_paragraph()
doc.add_paragraph()
parrafo(
    "Documento generado automáticamente a partir de la auditoría del "
    f"{FECHA}. Para regenerarlo con precios actualizados, solicitar de nuevo "
    "«Auditoria_Costos_AWS.docx».",
    cursiva=True,
)

doc.save(SALIDA)
print("OK ->", SALIDA)
