# HANA Bridge

Microservicio intermediario (FastAPI + hdbcli) entre la capa MIL y **SAP HANA**
(BEAS Manufacturing + SAP Business One). Expone HTTP de solo lectura sobre HANA,
nunca expone HANA directamente a internet. Corre detrás de Cloudflare Tunnel.

> **v2.1.0** — agrega `/invoices` (OINV) y **`/table/{name}`** (consulta dinámica
> segura) sobre la base SOLID de v2.0.0 (refactor de los 5 issues críticos).

## Arquitectura (SOLID por capas)

```
routes/     →  Presentación: routers FastAPI (health, sales, production, schema)
services/   →  Negocio: qué tabla/columnas/filtros usa cada endpoint
db/         →  Datos: pool, query_builder (SQL seguro), whitelist, repository
core/       →  Cross-cutting: errores, error_handlers, error_log, security
models/     →  DTOs: paginación, schema
config.py   →  Settings (todas las env vars; sin secretos por defecto)
main.py     →  App factory + lifespan (crea pool + servicios)
```

Flujo de una request:
`router → verify_auth (Bearer) → service → whitelist + query_builder → repository → pool → HANA`

## Issues resueltos (vs el bridge original)

| # | Issue original | Solución |
|---|---|---|
| 1 | SQL injection (f-strings con input crudo) | `query_builder` parametriza TODO valor; identificadores validados por regex + entrecomillados |
| 2 | Paginación con duplicados en `/production-orders` | `LIMIT/OFFSET` + `ORDER BY` por columna estable (obligatorio) |
| 3 | `/schema/columns` duplicado | Definido una sola vez en `routes/schema.py` |
| 4 | `schema` param ignorado | `whitelist.resolve_schema` valida contra `ALLOWED_SCHEMAS`; `/production-orders` ahora apunta a `BEAS_FTHAUPT` (tabla real) |
| 5 | Conexión global no thread-safe | `HanaConnectionPool` con cola thread-safe, health-check + reconexión |
| +E1 | Secretos hardcodeados | Salen a `.env` (gitignored); `config.py` falla si faltan |
| +E2 | Errores 500 filtrando internals | Jerarquía de errores + `ErrorResponse` uniforme; el detalle va al log |

## Variables de entorno

Todas se declaran en `config.py` y se cargan desde `.env` (ver `.env.example`).
Copia la plantilla y completa los valores reales:

```bash
cp .env.example .env   # luego edita .env con el token y el password reales
```

Claves principales: `API_TOKEN`, `HANA_HOST`, `HANA_USER`, `HANA_PASSWORD`,
`ALLOWED_SCHEMAS`, `POOL_SIZE`. El `.env` NUNCA se commitea (`.gitignore`).

## Correr en local

```bash
# 1) Dependencias
pip install -r requirements-dev.txt

# 2) Tests (no requieren HANA real)
pytest

# 3) Servidor
uvicorn main:app --reload --port 8080
#   o con Docker:
docker compose up --build
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Estado del bridge y de HANA (sin auth) |
| GET | `/items` | Artículos SAP B1 (OITM) |
| GET | `/orders` | Órdenes de venta (ORDR) |
| GET | `/purchase-orders` | Órdenes de compra (OPOR) |
| GET | `/invoices` | **Facturas de deudores (OINV)** |
| GET | `/stock/critical` | Artículos bajo stock mínimo |
| GET | `/production-orders` | Órdenes de producción BEAS (`BEAS_FTHAUPT`) |
| GET | `/schema/tables` | Tablas de un esquema autorizado |
| GET | `/schema/columns` | Columnas de una tabla |
| GET | `/table/{table}` | **Consulta dinámica genérica** sobre cualquier tabla de la whitelist (ver patrón abajo) |

Todos (excepto `/health`) requieren `Authorization: Bearer <API_TOKEN>`.
Paginación: `?page=1&page_size=20` (máx 100).

### Patrón "descubrir → consultar" (`/table/{name}`)
Pensado para el agente o para queries ad-hoc, manteniendo defensa anti-injection:

```bash
# 1) Descubrir tablas disponibles
curl -H "Authorization: Bearer $API_TOKEN" \
     "https://api-hana.codeds.xyz/schema/tables?schema=<COMPANY_DB>"

# 2) Descubrir columnas de una tabla
curl -H "Authorization: Bearer $API_TOKEN" \
     "https://api-hana.codeds.xyz/schema/columns?table=OINV&schema=<COMPANY_DB>"

# 3) Armar la consulta con esas columnas (TODA entrada se valida y parametriza)
curl -G -H "Authorization: Bearer $API_TOKEN" \
     "https://api-hana.codeds.xyz/table/OINV" \
     --data-urlencode "columns=DocNum,CardCode,CardName,DocDate,DocTotal,DocStatus" \
     --data-urlencode 'filters=[{"column":"DocStatus","op":"eq","value":"O"},{"column":"DocDate","op":"gte","value":"2026-01-01"}]' \
     --data-urlencode "order_by=DocDate:DESC,DocNum:DESC" \
     --data-urlencode "page=1" --data-urlencode "page_size=20"
```

**Defensa anti-injection (capas que toda request atraviesa)**:
1. `schema` → contra `ALLOWED_SCHEMAS` (lista cerrada).
2. `table` → contra `SYS.TABLES` (introspección live cacheada).
3. `columns` (seleccionadas + en filtros + en order_by) → contra `SYS.TABLE_COLUMNS`.
4. Identificadores → regex `^[A-Za-z_][A-Za-z0-9_]*$` + entrecomillados (`"col"`).
5. Operadores → whitelist `eq, ne, gt, gte, lt, lte, like, in, between`.
6. Valores → siempre como parámetro `?` (bind), nunca concatenados.

Cualquier intento fuera de esas reglas devuelve **400/404** con `ErrorResponse`; jamás llega a HANA como SQL.

## Operaciones Docker (en el servidor)

```bash
# === Build + arranque (primera vez o tras cambiar Dockerfile/requirements) ===
docker compose up -d --build

# === Detener y eliminar el contenedor ===
docker compose down

# === Si cambiaste el `.env`: usa SIEMPRE down + up (no `restart`) ===
#  `docker compose restart` NO recarga `env_file` en muchas versiones de compose.
docker compose down
docker compose up -d --build

# === Logs ===
docker compose logs --tail=50 hana-bridge       # últimas 50 líneas
docker compose logs -f hana-bridge              # en vivo (tail -f)

# === Estado ===
docker compose ps
```

### Diagnóstico dentro del contenedor (sin exponer secretos)
```bash
# Confirmar que las env vars llegaron al contenedor — muestra solo longitud y
# primer/último char del password, nunca su valor completo.
docker compose exec hana-bridge sh -c '
  echo "HOST=$HANA_HOST  USER=$HANA_USER  PORT=$HANA_PORT  ENCRYPT=$HANA_ENCRYPT"
  echo "PASS_LEN=${#HANA_PASSWORD}"
  echo "PASS_FIRST=$(printf %s "$HANA_PASSWORD" | head -c1)"
  echo "PASS_LAST=$(printf %s "$HANA_PASSWORD" | tail -c1)"
'

# Probar la conexión a HANA directamente (imprime el error real si falla)
docker compose exec hana-bridge python3 -c "
import os
from hdbcli import dbapi
try:
    c = dbapi.connect(
        address=os.environ['HANA_HOST'],
        port=int(os.environ['HANA_PORT']),
        user=os.environ['HANA_USER'],
        password=os.environ['HANA_PASSWORD'],
        encrypt=(os.environ.get('HANA_ENCRYPT','true').lower()=='true'),
        sslValidateCertificate=(os.environ.get('HANA_SSL_VALIDATE','false').lower()=='true'),
    )
    print('CONECTADO:', c.isconnected())
    c.close()
except Exception as e:
    print('ERROR HANA:', type(e).__name__, '-', e)
"
```

### Tests rápidos desde afuera (Cloudflare Tunnel)
```bash
# /health (sin auth): esperado {"ok":true,"hana":true}
curl -s https://api-hana.codeds.xyz/health

# Sin token → 401 + ErrorResponse
curl -s "https://api-hana.codeds.xyz/items?page=1&page_size=1"

# Con token
curl -H "Authorization: Bearer <API_TOKEN>" \
     "https://api-hana.codeds.xyz/items?page=1&page_size=1"
```

---

## Administración del usuario HANA de servicio

Estas SQL se corren como **`SYSTEM`** (o un DBA con `USER ADMIN`). Reemplaza
todo `<PASSWORD>` por una clave generada localmente — **NUNCA** la pegues en
chats, tickets o el control de versiones. `<HANA_USER>` y `<COMPANY_DB>` son
placeholders: cámbialos por el nombre real de tu usuario y tu company DB.

### 1) Crear el usuario por primera vez
```sql
-- Crear con password inicial; NO FORCE_FIRST_PASSWORD_CHANGE es CRÍTICO para
-- usuarios de servicio (si no, HANA pide cambio en el primer login y el bridge falla).
CREATE USER <HANA_USER> PASSWORD "<PASSWORD>" NO FORCE_FIRST_PASSWORD_CHANGE;

-- Que el password no expire por inactividad (usuario de servicio).
ALTER USER <HANA_USER> DISABLE PASSWORD LIFETIME;
```

### 2) Otorgar permisos de solo-lectura
```sql
-- SELECT sobre TODO el schema de la company DB (tablas actuales y futuras:
-- OITM, ORDR, OPOR, OINV, BEAS_*, etc.)
GRANT SELECT ON SCHEMA <COMPANY_DB> TO <HANA_USER>;

-- Necesario para los endpoints de introspección (/schema/tables, /schema/columns)
GRANT CATALOG READ TO <HANA_USER>;

-- (Opcional) acceso a un segundo schema (ej. DB de pruebas)
-- GRANT SELECT ON SCHEMA OTRO_SCHEMA TO <HANA_USER>;
```

> ❌ NO le des `INSERT/UPDATE/DELETE/CREATE`. El bridge es GET-only.

### 3) Cambiar / rotar el password
```sql
-- Rotación. NO FORCE_FIRST_PASSWORD_CHANGE OBLIGATORIO.
ALTER USER <HANA_USER> PASSWORD "<NUEVO_PASSWORD>" NO FORCE_FIRST_PASSWORD_CHANGE;

-- Si HANA devuelve error 413 ("last n passwords can not be reused"):
-- es la política de historial. Usa una clave nueva que no esté en las últimas 5.
```

### 4) Desbloqueo / reactivación
```sql
-- Si quedó bloqueado por intentos fallidos
ALTER USER <HANA_USER> RESET CONNECT ATTEMPTS;

-- Si fue desactivado
ALTER USER <HANA_USER> ACTIVATE USER NOW;
```

### 5) Validar el estado del usuario
```sql
-- Lo importante: USER_DEACTIVATED=FALSE, PASSWORD_CHANGE_NEEDED=FALSE
SELECT USER_NAME,
       USER_DEACTIVATED,
       IS_PASSWORD_ENABLED,
       PASSWORD_CHANGE_NEEDED,
       INVALID_CONNECT_ATTEMPTS,
       LAST_SUCCESSFUL_CONNECT,
       LAST_PASSWORD_CHANGE_TIME,
       VALID_UNTIL
FROM   "SYS"."USERS"
WHERE  USER_NAME = '<HANA_USER>';
```

### 6) Validar los permisos otorgados
```sql
-- Debe verse: SELECT en <COMPANY_DB> + CATALOG READ
SELECT PRIVILEGE, OBJECT_TYPE, SCHEMA_NAME, OBJECT_NAME
FROM   "SYS"."GRANTED_PRIVILEGES"
WHERE  GRANTEE = '<HANA_USER>'
ORDER  BY PRIVILEGE;

-- Probar lectura efectiva
SELECT TOP 1 "ItemCode", "ItemName"
FROM   "<COMPANY_DB>"."OITM"
WHERE  "InvntItem" = 'Y';
```

### Después de cualquier cambio en el password
1. Pon el password nuevo en el `.env` del servidor: `HANA_PASSWORD=<NUEVO>`
2. **`docker compose down && docker compose up -d --build`** (el `restart` no recarga env vars en algunas versiones)
3. `curl -s https://api-hana.codeds.xyz/health` → debe dar `{"ok":true,"hana":true}`

---

## Operaciones Git

Recetario del workflow del repo. Manténganlo a mano para no romper nada.

### Flujo normal (cambios cotidianos)
```bash
git status                 # ¿qué cambió?
git diff                   # revisa el diff antes de commitear
git add -A                 # stage de todo (.env / logs / __pycache__ excluidos por .gitignore)
git commit -m "descripción del cambio"
git push origin main
```

### Traer cambios desde GitHub
```bash
git fetch origin
git pull origin main       # solo si NO hubo force-push en el remoto
```

### Si la historia local quedó desincronizada del remoto
Pasa típicamente **después de un force-push**: `git pull` da error de
*"divergent branches"*. La forma correcta es alinear con el remoto:
```bash
git fetch origin
git reset --hard origin/main    # ⚠️ descarta cambios locales NO commiteados
git log --oneline               # confirma que quedó al día
```

### Squash de varios commits en UN solo commit (limpieza de historia)
Útil para colapsar commits exploratorios o **borrar información sensible**
de commits anteriores (secretos, IPs internas, nombres de BD).

```bash
# 1) Stage cualquier cambio pendiente
git add -A

# 2) Mueve HEAD al commit raíz, conservando todos los archivos como están
git reset --soft $(git rev-list --max-parents=0 HEAD)

# 3) Reescribe el commit raíz con TODO el estado actual
git commit --amend -m "feat: mensaje consolidado"

# 4) Sobreescribe el remoto
git push --force origin main
```
Después, en **cada clone existente** (server, otra laptop), corre el bloque
*"historia desincronizada"* de arriba para alinearlos.

### Reglas para no dañar el proyecto

1. **NUNCA commitees el `.env`** — está en `.gitignore`, debe quedarse ahí.
2. Si tocas el `.env.example`, **scrubea** valores reales (IP, usuario, BD,
   tokens) antes de commitear. Solo placeholders genéricos (`X.X.X.X`,
   `<HANA_USER>`, `change-me`).
3. Antes de `git commit`, **siempre** corre `git status` y `git diff --cached`
   y verifica que no se cuele algo sensible.
4. Si **commiteaste un secreto por error**, antes de cualquier otra cosa
   **rótalo** (cambia el password/token de inmediato). Borrar del historial
   NO basta — GitHub guarda copias temporales y puede haber clones por ahí.
5. **`git push --force` solo cuando estés solo en el repo**. Si trabajan
   varios, avisa antes y coordínalo.
6. El `.env` del servidor es **independiente del git** — los cambios al
   código NO modifican el `.env`. Esa es la separación que mantiene los
   secretos a salvo.

### Checklist mínimo antes de cada push
```bash
git status                                      # ¿hay archivos no deseados?
git diff --cached                               # mira el contenido del staging
# (opcional) busca rastros de info sensible olvidada
grep -rE "password|secret|10\.[0-9]+\.[0-9]+\.[0-9]+" --include="*.py" --include="*.md" .env.example .
```

### Tip: cambiar la cuenta de GitHub en esta máquina (Windows / Git Credential Manager)
Si el push da `403 denied to <usuario>` y necesitas autenticar con otra cuenta:
```bash
# Borra la credencial cacheada para github.com
printf "protocol=https\nhost=github.com\n\n" | git credential reject

# El siguiente push pedirá login → entra con la cuenta correcta (la que tenga
# permiso de escritura sobre el repo).
git push origin main
```
La identidad del **autor del commit** (`git config user.name/email`) es
**independiente** de la cuenta de autenticación de GitHub.

---

## Pendiente (siguiente iteración)

- Endpoints específicos BEAS: `/downtime` (`BEAS_APLATZ_STILLSTAND`),
  `/traceability` (`BEAS_FTAPLCHARGE`), `/production-times` (`BEAS_ARBZEIT`).
  *(Mientras tanto, `/table/{name}` ya permite consultarlas dinámicamente.)*
- Fijar el base image Docker a un digest parcheado.

## Deploy

Imagen Docker en un servidor privado, expuesta vía Cloudflare Tunnel
(detrás del propio dominio del proyecto). En producción las variables llegan
por el runtime, no por un `.env` embebido (ver `.dockerignore`).
