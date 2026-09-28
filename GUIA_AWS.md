# Guía paso a paso — FastAPI + PostgreSQL + Nginx Proxy Manager + S3 en AWS

> Pensada para hacerlo por primera vez desde la **Consola web de AWS** y **PowerShell en Windows**.
> Usa siempre la **misma región** en todo (ej. `us-east-1`, N. Virginia). Arriba a la derecha de la consola.

---

## 0. Mapa de lo que vas a construir

```
Internet ──80/443──► EC2 #1 Proxy (subnet pública 10.0.1.0/24)  [sg-proxy]
                          │ 8000
                          ▼
                     EC2 #2 FastAPI (subnet privada 10.0.2.0/24) [sg-api] ──IAM Role──► S3 (bucket privado)
                          │ 5432
                          ▼
                     EC2 #3 PostgreSQL (subnet privada)           [sg-db]
```

| Recurso | Valor sugerido |
|---|---|
| VPC | `reto-vpc` · `10.0.0.0/16` |
| Subnet pública | `10.0.1.0/24` |
| Subnet privada | `10.0.2.0/24` |
| Key pair | `reto-key.pem` |
| Bucket | `reto-imagenes-<tu-nombre>-<numero>` (debe ser único en el mundo) |

**Anota en un bloc de notas** a medida que avanzas: IP pública del proxy, IP privada de FastAPI, IP privada de PostgreSQL, nombre del bucket.

### Una cosa importante antes de empezar: la NAT Gateway
Las EC2 privadas **no tienen internet**, pero necesitan descargar Docker, las imágenes de Docker y tu código.
La solución estándar es una **NAT Gateway** en la subnet pública: deja *salir* a las privadas hacia internet, pero nadie de internet puede *entrar*.
⚠️ La NAT Gateway **no es gratis** (≈ US$0.045/hora + tráfico). Por una hora son centavos, pero **bórrala al terminar** (paso 12).
Para S3 usaremos un **VPC Endpoint de S3 (Gateway)**, que es gratis y hace que el tráfico a S3 no salga a internet.

---

## 1. Crear la VPC (≈5 min)

1. Consola → busca **VPC** → **Create VPC**.
2. Elige **VPC and more** (el asistente crea todo de una vez).
3. Configura:
   - Name tag auto-generation: `reto`
   - IPv4 CIDR: `10.0.0.0/16`
   - Number of Availability Zones: **1**
   - Number of public subnets: **1**
   - Number of private subnets: **1**
   - Customize subnets CIDR blocks: pública `10.0.1.0/24`, privada `10.0.2.0/24`
   - NAT gateways: **In 1 AZ**
   - VPC endpoints: **S3 Gateway**
   - DNS hostnames y DNS resolution: activados
4. **Create VPC** y espera a que todo esté en verde (la NAT tarda 1–2 min).

Lo que creó el asistente (y lo que debes poder explicar):
- **Internet Gateway** conectado a la VPC.
- **Route table pública**: `0.0.0.0/0 → Internet Gateway` → por eso la subnet es "pública".
- **Route table privada**: `0.0.0.0/0 → NAT Gateway` + ruta a S3 por el endpoint → sale a internet pero no es alcanzable desde afuera.

📸 Evidencia: captura del "Resource map" de la VPC (pestaña en el detalle de la VPC).

---

## 2. Crear los 3 Security Groups (≈5 min)

Consola → **EC2** → **Security Groups** → **Create security group**. En los tres elige la VPC `reto-vpc`. Deja las reglas de **salida (outbound)** como vienen (todo permitido).

Créalos **en este orden** (cada uno referencia al anterior):

### `sg-proxy` (EC2 pública)
| Tipo | Puerto | Origen | Por qué |
|---|---|---|---|
| HTTP | 80 | `0.0.0.0/0` | Es la puerta de entrada pública |
| HTTPS | 443 | `0.0.0.0/0` | Igual, con cifrado |
| Custom TCP | 81 | **My IP** | Panel de admin de Nginx Proxy Manager, solo tú |
| SSH | 22 | **My IP** | Administrar la máquina, solo tú |

### `sg-api` (EC2 FastAPI)
| Tipo | Puerto | Origen | Por qué |
|---|---|---|---|
| Custom TCP | 8000 | **sg-proxy** (escribe `sg-` y selecciónalo) | Solo el proxy puede hablar con la API |
| SSH | 22 | **sg-proxy** | Entras por SSH saltando desde el proxy (bastión) |

### `sg-db` (EC2 PostgreSQL)
| Tipo | Puerto | Origen | Por qué |
|---|---|---|---|
| PostgreSQL | 5432 | **sg-api** | Solo FastAPI puede consultar la base de datos |
| SSH | 22 | **sg-proxy** | Administración desde el bastión |

> Usar un Security Group como origen (en vez de una IP) significa "cualquier instancia que tenga ese SG". Es la forma más limpia de aplicar mínimo privilegio.

📸 Evidencia: captura de las reglas de entrada de los tres.

---

## 3. Crear el bucket S3 (≈2 min)

1. Consola → **S3** → **Create bucket**.
2. Nombre: `reto-imagenes-vane-2026` (o similar, único). Misma región.
3. **Block all public access: dejarlo ACTIVADO** (el bucket NO es público).
4. Lo demás por defecto → **Create bucket**.

---

## 4. Crear el IAM Role para FastAPI (≈4 min)

Así la API sube a S3 **sin llaves en el código ni en el .env**.

1. Consola → **IAM** → **Policies** → **Create policy** → pestaña **JSON**.
2. Pega el contenido de `deploy/s3-policy.json`, cambiando `NOMBRE-DE-TU-BUCKET` por el tuyo:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Sid": "SoloSubirYLeerImagenes",
       "Effect": "Allow",
       "Action": ["s3:PutObject", "s3:GetObject"],
       "Resource": "arn:aws:s3:::reto-imagenes-vane-2026/images/*"
     }]
   }
   ```
   Solo permite subir y leer, y solo dentro de la carpeta `images/` de ese bucket. No puede borrar ni listar otros buckets.
3. Nombre: `reto-s3-images-policy` → Create.
4. **IAM → Roles → Create role** → Trusted entity: **AWS service** → Use case: **EC2** → Next.
5. Busca y marca `reto-s3-images-policy` → Next → Nombre: `reto-fastapi-ec2-role` → Create.

> Si usas **AWS Academy / Learner Lab**, normalmente no puedes crear roles. En ese caso usa el perfil ya existente **`LabInstanceProfile`** en el paso 5 y menciónalo en la explicación.

---

## 5. Lanzar las 3 EC2 (≈8 min)

Consola → **EC2** → **Launch instance**. Repite 3 veces con estos valores:

| Campo | Proxy | FastAPI | PostgreSQL |
|---|---|---|---|
| Name | `ec2-proxy` | `ec2-fastapi` | `ec2-postgres` |
| AMI | Amazon Linux 2023 | Amazon Linux 2023 | Amazon Linux 2023 |
| Instance type | t3.micro (verifica "Free tier eligible") | t3.micro | t3.micro |
| Key pair | Create new → `reto-key` → **.pem** (se descarga; guárdalo) | `reto-key` | `reto-key` |
| Network settings → **Edit** → VPC | `reto-vpc` | `reto-vpc` | `reto-vpc` |
| Subnet | la **public** | la **private** | la **private** |
| Auto-assign public IP | **Enable** | **Disable** | **Disable** |
| Security group | Select existing → `sg-proxy` | `sg-api` | `sg-db` |
| Storage | 8 GiB gp3 | 8 GiB gp3 | 8 GiB gp3 |
| Advanced → IAM instance profile | (ninguno) | **`reto-fastapi-ec2-role`** | (ninguno) |
| Advanced → Metadata response hop limit | — | **2** | — |
| Advanced → **User data** | pega `deploy/install-docker.sh` | igual | igual |

Por qué cada detalle:
- **User data**: el script instala Docker + Compose automáticamente al arrancar. Te ahorra hacerlo a mano 3 veces.
- **Hop limit = 2**: FastAPI corre *dentro de un contenedor*, y para que Boto3 pueda leer las credenciales del IAM Role desde el contenedor, la petición al servicio de metadatos da un "salto" extra. Con el valor 1 Boto3 no encuentra credenciales.
- **Sin IP pública** en las privadas: nadie en internet puede ni siquiera intentar conectarse a ellas.

Cuando estén en **Running**, anota: IP **pública** del proxy, IP **privada** de FastAPI y de PostgreSQL (ej. `10.0.2.37`).

📸 Evidencia: lista de las 3 instancias mostrando subnet e IPs.

---

## 6. Conectarte por SSH desde Windows (≈3 min)

Abre PowerShell en la carpeta donde está `reto-key.pem`.

**Arreglar permisos del .pem** (si no, SSH lo rechaza por "bad permissions"):
```powershell
icacls .\reto-key.pem /inheritance:r
icacls .\reto-key.pem /grant:r "$($env:USERNAME):(R)"
```

**Entrar al proxy (pública):**
```powershell
ssh -i .\reto-key.pem ec2-user@IP_PUBLICA_PROXY
```

**Entrar a una privada saltando por el proxy (bastión):**
```powershell
ssh -i .\reto-key.pem -o ProxyCommand="ssh -i .\reto-key.pem -W %h:%p ec2-user@IP_PUBLICA_PROXY" ec2-user@IP_PRIVADA
```

En cada máquina verifica Docker (si el user data aún no termina, espera 1–2 min y vuelve a entrar):
```bash
docker --version
docker compose version
```
Si dice "permission denied", sal (`exit`) y vuelve a entrar: el grupo `docker` se aplica en la nueva sesión.
Si Docker no quedó instalado, córrelo a mano: copia el script y ejecuta `sudo bash install-docker.sh`.

📸 Evidencia: `docker --version` y `docker compose version` en las 3.

---

## 7. Llevar el código a las EC2 privadas (≈3 min)

**Opción A (recomendada): GitHub.** Sube este proyecto a un repositorio **público** en tu GitHub (sin archivos `.env`). Luego en `ec2-fastapi` y en `ec2-postgres`:
```bash
git clone https://github.com/TU_USUARIO/TU_REPO.git app
cd app
```

**Opción B: copiar el .zip desde tu PC** (sin GitHub):
```powershell
scp -i .\reto-key.pem -o ProxyCommand="ssh -i .\reto-key.pem -W %h:%p ec2-user@IP_PUBLICA_PROXY" .\fastapi_docker-main.zip ec2-user@IP_PRIVADA:~
```
y en la EC2: `unzip fastapi_docker-main.zip && mv fastapi_docker-main app && cd app`.

---

## 8. Desplegar PostgreSQL — EC2 #3 (≈3 min)

En `ec2-postgres`, dentro de `app`:
```bash
cd deploy/postgres
cp .env.example .env
nano .env        # cambia POSTGRES_PASSWORD por una clave larga. Guardar: Ctrl+O, Enter, Ctrl+X
docker compose up -d
docker compose ps       # debe decir "healthy"
```

Qué cumple esto:
- Imagen oficial `postgres:16-alpine`, usuario `app_user` y base `inventario` creados por variables de entorno.
- Volumen `postgres_data` → si borras el contenedor, los datos siguen.
- Publica el 5432, pero **el Security Group solo deja entrar a la EC2 de FastAPI** y la máquina no tiene IP pública.

📸 Evidencia: `docker compose ps` y `docker volume ls`.

---

## 9. Desplegar FastAPI — EC2 #2 (≈5 min)

En `ec2-fastapi`, dentro de `app`:
```bash
cp deploy/api/.env.example deploy/api/.env
nano deploy/api/.env
```
Rellena:
```
DATABASE_URL=postgresql://app_user:LA_MISMA_CLAVE@IP_PRIVADA_POSTGRES:5432/inventario
S3_BUCKET_NAME=reto-imagenes-vane-2026
AWS_REGION=us-east-1
```
> Si la clave tiene símbolos como `@`, `:` o `/`, en la URL van codificados (`@` → `%40`). Lo más fácil: usa una clave solo con letras y números, pero larga.

Construir y levantar (desde la carpeta `app`):
```bash
docker compose -f deploy/api/docker-compose.yml up -d --build
docker compose -f deploy/api/docker-compose.yml logs -f     # Ctrl+C para salir de los logs
```
Debes ver las migraciones de Alembic (`Running upgrade ... add_images_table`) y `Uvicorn running on http://0.0.0.0:8000`.

Prueba local dentro de la EC2:
```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

📸 Evidencia: logs con las migraciones y el `curl`.

---

## 10. Configurar Nginx Proxy Manager — EC2 #1 (≈6 min)

En `ec2-proxy` crea el compose (o clona el repo y usa `deploy/proxy`):
```bash
mkdir npm && cd npm
nano docker-compose.yml     # pega el contenido de deploy/proxy/docker-compose.yml
docker compose up -d
```

1. En tu navegador: `http://IP_PUBLICA_PROXY:81`
2. Crea tu usuario administrador (en versiones anteriores el login inicial es `admin@example.com` / `changeme` y te pide cambiarlo).
3. **Hosts → Proxy Hosts → Add Proxy Host**:
   - **Domain Names**: `IP-PUBLICA-CON-GUIONES.nip.io` → ej. si tu IP es `3.85.10.20`, escribe `3-85-10-20.nip.io`
     (nip.io es un DNS gratuito que resuelve ese nombre a tu IP; te sirve como "dominio" sin comprar uno).
   - Scheme: `http`
   - Forward Hostname / IP: **IP privada de ec2-fastapi** (ej. `10.0.2.37`)
   - Forward Port: `8000`
   - Activa **Block Common Exploits**
   - Save.
4. Abre `http://3-85-10-20.nip.io/health` → `{"status":"ok"}` 🎉
   y `http://3-85-10-20.nip.io/docs` para Swagger.

**Bonus HTTPS**: edita el Proxy Host → pestaña **SSL** → *Request a new SSL Certificate* (Let's Encrypt) → activa *Force SSL* → Save. Ya funcionará `https://3-85-10-20.nip.io/health`.
(Si Let's Encrypt falla por límite de nip.io, prueba con `sslip.io` en lugar de `nip.io`.)

📸 Evidencia: panel de NPM con el Proxy Host y `/health` en el navegador.

---

## 11. Validación final (≈5 min)

**API vía proxy:**
```powershell
curl.exe http://3-85-10-20.nip.io/health
```

**Base de datos (FastAPI ↔ PostgreSQL):** en `/docs`, haz `POST /product` y luego `GET /product`.

**S3:** en `/docs` → `POST /images` → *Try it out* → elige una imagen `.jpg`/`.png` → Execute. Respuesta esperada:
```json
{"message": "Imagen subida correctamente", "image": {"s3_key": "images/....png", ...}}
```
Luego ve a la consola de S3 → tu bucket → carpeta `images/` → ahí está 📸. `GET /images` devuelve las imágenes con una URL temporal (10 min) para verlas sin hacer público el bucket.
Prueba también subir un `.txt` → debe responder **415** (validación).

**Seguridad (demuestra que NO se puede):**
```powershell
# Desde tu PC: FastAPI directo NO responde (no tiene IP pública, y aunque la tuviera el SG lo bloquea)
curl.exe --max-time 5 http://IP_PUBLICA_PROXY:8000/health     # falla por timeout
```
Desde `ec2-proxy` (por SSH):
```bash
timeout 3 bash -c '</dev/tcp/IP_PRIVADA_POSTGRES/5432' && echo ABIERTO || echo BLOQUEADO   # BLOQUEADO
```
Desde `ec2-fastapi`:
```bash
timeout 3 bash -c '</dev/tcp/IP_PRIVADA_POSTGRES/5432' && echo ABIERTO || echo BLOQUEADO   # ABIERTO
```
Eso prueba que a PostgreSQL **solo** llega FastAPI.

---

## 12. Limpieza para no generar cobros ⚠️

En este orden:
1. **EC2 → Instances** → selecciona las 3 → *Instance state* → **Terminate**.
2. **VPC → NAT gateways** → selecciona → **Delete** (espera a que diga *Deleted*).
3. **VPC → Elastic IPs** → la IP que usaba la NAT → **Release**.
4. **S3** → tu bucket → **Empty** → luego **Delete**.
5. **VPC → Your VPCs** → `reto-vpc` → **Delete** (borra subnets, route tables, IGW y endpoint).
6. (Opcional) IAM → borra el role y la policy.

---

## 13. Respuestas para la explicación

- **¿Por qué FastAPI está en subnet privada?** Porque no necesita que internet la alcance: solo el proxy le habla. Sin IP pública y con el SG limitado al proxy, se reduce la superficie de ataque. El proxy filtra, centraliza HTTPS y puede bloquear exploits.
- **¿Por qué PostgreSQL en subnet privada?** Guarda los datos, que es lo más sensible. Solo la API necesita consultarlo. Exponerlo permitiría ataques de fuerza bruta a contraseñas o explotación de vulnerabilidades del motor.
- **¿Por qué Nginx Proxy Manager en subnet pública?** Es el único punto de entrada. Necesita IP pública y una ruta al Internet Gateway para recibir tráfico de los usuarios.
- **¿Qué puertos hay abiertos y quién accede?**
  - Proxy: 80/443 para todo internet, 81 y 22 solo para mi IP.
  - FastAPI: 8000 y 22 solo desde el SG del proxy.
  - PostgreSQL: 5432 solo desde el SG de FastAPI, y 22 solo desde el proxy.
- **¿Cómo se comunica FastAPI con PostgreSQL?** Por la red interna de la VPC, usando la IP privada de la EC2 de Postgres en el puerto 5432. La URL de conexión viene en la variable de entorno `DATABASE_URL`, no está en el código.
- **¿Cómo se comunica FastAPI con S3?** Con Boto3 (`put_object`). Las credenciales son temporales y las entrega automáticamente el **IAM Role** asignado a la EC2, que solo permite `PutObject` y `GetObject` en `images/*`. El tráfico va por el **VPC Endpoint de S3**, sin salir a internet.
- **¿Por qué no exponer PostgreSQL a internet?** Porque ningún usuario final lo necesita. Abrirlo solo añade riesgo: escaneos automáticos, fuerza bruta y robo de datos.
- **¿Para qué la NAT Gateway?** Permite que las privadas *salgan* a descargar paquetes e imágenes Docker sin permitir que nadie *entre*.

## Variables de entorno

| Dónde | Variable | Ejemplo |
|---|---|---|
| ec2-postgres `deploy/postgres/.env` | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `app_user`, `***`, `inventario` |
| ec2-fastapi `deploy/api/.env` | `DATABASE_URL` | `postgresql://app_user:***@10.0.2.X:5432/inventario` |
| ec2-fastapi `deploy/api/.env` | `S3_BUCKET_NAME`, `AWS_REGION` | `reto-imagenes-vane-2026`, `us-east-1` |

Los archivos `.env` están en `.gitignore`: **nunca los subas a GitHub.**
