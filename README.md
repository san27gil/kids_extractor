# KID Extractor

![KID Extractor leyendo tres KID](docs/demo.gif)

Programa de terminal que lee los **KID** (Documento de Datos Fundamentales) de fondos de inversión en PDF y saca, para cada uno, lo más importante:

| Dato | Cómo se obtiene |
| --- | --- |
| **ISIN** | Reglas fijas, con comprobación del dígito de control |
| **Nombre** del fondo y su clase | IA local, validada palabra por palabra contra el PDF |
| **Fecha** del documento | Reglas fijas |
| **Idioma** | Reglas fijas (título obligatorio del documento) |
| **Riesgo** (SRI 1-7) | Reglas fijas |
| **TER** (comisiones de gestión y otros costes, % anual) | Reglas fijas |
| **Descripción** breve de en qué invierte | IA local: resume el apartado «Objetivos» |

Funciona con KID en **español, inglés, francés y alemán**. La descripción
siempre sale en español.

El resultado se muestra como tabla en la terminal y se guarda en una **base de
datos SQLite** personal (`resultados/kids.db`) que se va acumulando entre
ejecuciones: guarda cada versión de cada KID con su fecha, para poder identificar si tienes es el último.

---

## Privacidad y uso legal

- **No descarga nada de internet.** El usuario aporta los KID que ya tiene.
- **Nada sale del ordenador.** Los PDF se leen en local y la IA
  ([Ollama](https://ollama.com)) también se ejecuta en local: no hay APIs
  externas ni se envían documentos a terceros.
- **Los PDF solo se leen**: no se mueven, modifican ni borran.
- El repositorio no incluye ningún KID.

> Herramienta de apoyo para leer documentos. No es asesoramiento financiero.
> comprueba siempre los datos en el KID original.

---

## Cómo funciona

```
kids/*.pdf ──► texto del PDF ──► reglas fijas ──────────► ISIN, fecha, idioma, riesgo, TER
               (pypdf)       └─► sección «Producto» ──► IA local ──► nombre (solo si es literal)
                             └─► sección «Objetivos» ─► IA local ──► descripción resumida
                                                                          │
                                           terminal + resultados/kids.db (SQLite)
```

### Primero reglas fijas; la IA solo donde no llegan

El Reglamento PRIIPs obliga a usar frases concretas en casi todos los
apartados («clase de riesgo 4», «comisiones de gestión y otros costes
administrativos o de funcionamiento»…). Por eso casi todo se lee con
**expresiones regulares**, sin IA, en los cuatro idiomas.

Principio: **mejor ningún dato que un dato dudoso.** Si el documento se
contradice (por ejemplo, dos riesgos distintos), si el TER pasa del 5 % o si
la cifra leída es en realidad la de costes de operación, el dato se deja en
blanco y se avisa.

### IA local, auditable

- **Nombre**: cada gestora lo escribe a su manera, así que lo lee la IA. Pero
  solo se acepta si **cada pieza aparece palabra por palabra en el PDF**: la IA
  no puede inventarse un nombre, como mucho puede escoger mal un trozo de
  texto real (y entonces se deja en blanco).
- **Descripción**: la IA resume en una o dos frases el apartado «Objetivos»,
  con instrucciones de usar solo lo que dice el texto.
- `temperature: 0`: el mismo PDF da siempre la misma respuesta.
- **Sin Ollama también funciona**: saca todo lo demás, deja el nombre en
  blanco y pone como descripción un extracto literal de «Objetivos».

---

## Instalación

Requisitos: Python 3.9 o superior y, para la IA, la app
[Ollama](https://ollama.com).

```bash
git clone https://github.com/san27gil/kids_extractor.git
cd kid_extractor
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

ollama pull gemma4:12b      # opcional, se usa para nombre y descripción resumida
```

`gemma4:12b` testeado en un Mac M4 con 16 GB y tarda unos 15 ssegundos por KID. Se
puede cambiar el modelo de Ollama con `--modelo`.

## Uso

1. Copia los KID en PDF en la carpeta `kids/`.
2. Ejecuta:

```bash
.venv/bin/python extraer.py
```

Opciones:

| Comando | Para qué |
| --- | --- |
| `extraer.py` | Lee todos los PDF de `kids/` |
| `extraer.py ruta/a/carpeta` | Lee los PDF de otra carpeta |
| `extraer.py a.pdf b.pdf` | Lee PDF sueltos |
| `extraer.py --sin-ia` | Sin Ollama (rápido: menos de 1 s por KID) |
| `extraer.py --modelo llama3.1:8b` | Otro modelo de Ollama |
| `extraer.py --ver` | Muestra la última versión de cada KID guardado |
| `extraer.py --salida otra/carpeta` | Usa la base de datos de otra carpeta |

## Base de datos

Todo se guarda en `resultados/kids.db`, que se va acumulando entre ejecuciones:

- **Cada PDF es una fila**, identificada por su huella (sha256). Volver a leer
  el mismo PDF actualiza su fila, no la duplica. Si se relee sin IA un PDF que
  ya se leyó con IA, se conservan el nombre y la descripción de la IA.
- **Cada versión de un KID se guarda aparte**: un mismo ISIN puede tener
  varias filas, una por fecha del KID.
- Al leer, la columna **En la base** de la tabla dice si cada KID es *nuevo*,
  si *sustituye* a una versión anterior, si es el *último* o si **ya tienes uno
  más reciente**.
- `--ver` marca en rojo los KID con más de un año: la norma PRIIPs obliga a
  revisarlos al menos una vez al año, así que seguramente la gestora ya ha
  publicado uno nuevo.

Tabla y vistas:

| Nombre | Contenido |
| --- | --- |
| `kid` | Todos los datos de cada PDF leído: ISIN, nombre, `fecha_kid`, idioma, riesgo, TER, descripción, avisos, archivo, `leido_primero`, `leido_ultimo`… |
| `kids` | Lo mismo, con la columna `ultimo` (`sí` / `no` / `?` si falta ISIN o fecha) |
| `ultimos` | Solo la última versión de cada fondo |

Consultas desde la terminal con `sqlite3` (viene con macOS):

```bash
sqlite3 -box resultados/kids.db "SELECT isin, nombre, fecha_kid, riesgo, ter FROM ultimos"

# Fondos de riesgo 5 o más, del más barato al más caro
sqlite3 -box resultados/kids.db "SELECT isin, nombre, riesgo, ter FROM ultimos WHERE riesgo >= 5 ORDER BY ter"

# Historial de un fondo: cómo han cambiado riesgo y TER entre versiones
sqlite3 -box resultados/kids.db "SELECT fecha_kid, riesgo, ter, ultimo FROM kids WHERE isin = 'LU0136044012' ORDER BY fecha_kid"

# KID con más de un año: buscar la versión nueva en la web de la gestora
sqlite3 -box resultados/kids.db "SELECT isin, nombre, fecha_kid FROM ultimos WHERE fecha_kid < date('now', '-1 year')"

# Datos dudosos o incompletos
sqlite3 -box resultados/kids.db "SELECT archivo, avisos FROM kid WHERE avisos IS NOT NULL"

# Sesión interactiva
sqlite3 -box resultados/kids.db
```

La columna `avisos` explica cualquier dato que no se haya podido leer con
seguridad.

---

## Estructura

```
extraer.py                 programa de terminal
kid_extractor/
  reglas.py                reglas fijas: ISIN, fecha, idioma, riesgo, TER, «Objetivos»
  nombre.py                nombre del fondo (IA + validación literal)
  ia.py                    conexión con Ollama (localhost)
  extractor.py             lee un KID y devuelve su ficha
  bd.py                    base de datos SQLite (resultados/kids.db)
  salida.py                tablas de la terminal
tests/                     pruebas de las reglas y de la base de datos (sin PDF ni IA)
kids/                      aquí se dejan los KID (no se suben a git)
resultados/                base de datos kids.db (no se sube a git)
```

Pruebas:

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```

## Stack

| Tecnología | Uso |
| --- | --- |
| **Python** | Todo el programa |
| **pypdf** | Texto de los PDF |
| **re** (expresiones regulares) | Lectura de los datos con formato fijo |
| **Ollama** + `gemma4:12b` | IA local para el nombre y la descripción |
| **urllib** (librería estándar) | Conexión con Ollama |
| **rich** | Tabla y barra de progreso en la terminal |
| **sqlite3** (librería estándar) | Base de datos de resultados |

## Licencia

[MIT](LICENSE)
