# Pruebas y despliegue automático (GitHub Actions + AWS SSM)

Cada pull request y cada push a `master` corren las pruebas. Si un push a `master` pasa todo, el mismo flujo actualiza la EC2 ([Docker en EC2](docker-ec2.md)) sin SSH, sin abrir puertos y sin guardar llaves de AWS en GitHub. El flujo es `.github/workflows/ci.yml`.

**Cómo funciona:**
1. Los jobs `python` (`python tests/run.py`) y `frontend` (`npm ci`, `npm test`, `npm run typecheck`, `npm run build` y `python tests/next_pilot_e2e.py`) corren en cada pull request y en cada push a `master`.
2. El job `deploy` corre solo en un push a `master`, después de los dos anteriores, y solo si existe la variable `AWS_DEPLOY_ROLE_ARN`. Pide a AWS credenciales temporales con OIDC (GitHub prueba quién es y AWS le presta un rol por unos minutos) y manda un comando a la EC2 con Systems Manager Run Command.
3. En la EC2, como usuario `ubuntu`: `git fetch`, `git reset --hard <sha>` (el commit exacto que pasó las pruebas), `docker compose pull caddy`, `docker compose build --pull` (imágenes base al día, no las de caché), `docker compose up -d` y `docker image prune -f`.
4. Al final consulta `https://yumori.cl/robots.txt` hasta 10 veces. Si no responde, el job falla.

**Qué no hace:**
- **No toca `data/` ni `.env`.** No están en git y el despliegue nunca usa `git clean`.
- **No sube la base ni scrapea.** Eso sigue como en [Docker en EC2](docker-ec2.md) y el [scraping diario](daily-scraping.md).
- **No se configura solo.** Mientras falte la variable `AWS_DEPLOY_ROLE_ARN`, `deploy` se omite (aparece como "skipped", no como fallo) y las pruebas funcionan igual. Los pasos de AWS y GitHub de abajo son manuales.

Las regiones, cuentas e ids de abajo son marcadores (`<region>`, `<account-id>`, `<instance-id>`). Nada de esto se ha probado todavía en AWS: el flujo solo se valida con su primera ejecución real.

## 1. Rol de la instancia (para que Systems Manager la vea)
La EC2 necesita permiso para hablar con Systems Manager.
1. Consola de AWS > **IAM** > **Roles** > **Create role**.
2. *Trusted entity type*: **AWS service**. *Use case*: **EC2**. **Next**.
3. Buscar y marcar la política **`AmazonSSMManagedInstanceCore`**. **Next**.
4. *Role name*: `yumori-ec2-ssm`. **Create role**.
5. **EC2** > **Instances** > marcar la instancia > **Actions** > **Security** > **Modify IAM role** > elegir `yumori-ec2-ssm` > **Update IAM role**.
6. **Verificar:** **Systems Manager** > **Fleet Manager** (o *Node Management* > *Fleet Manager*). La instancia debe aparecer como **Online**; puede tardar unos minutos. Si no aparece, revisar en la instancia (por SSH):
   ```sh
   sudo snap list amazon-ssm-agent
   systemctl status snap.amazon-ssm-agent.amazon-ssm-agent
   ```
   El agente de SSM suele venir preinstalado en las imágenes de Ubuntu, como snap, pero **no está verificado en esta instancia**: hay que comprobarlo. El agente también necesita salida a internet por el 443; el security group por defecto la permite (revisar que no se haya cerrado). Mientras la instancia no sea **Online**, los pasos siguientes no sirven.

## 2. Proveedor OIDC de GitHub (una sola vez por cuenta)
1. **IAM** > **Identity providers** > **Add provider**.
2. *Provider type*: **OpenID Connect**.
3. *Provider URL*: `https://token.actions.githubusercontent.com`
4. *Audience*: `sts.amazonaws.com`. **Add provider**.

Si ya existe un proveedor con esa URL, no se crea otro.

## 3. Rol de despliegue `yumori-github-deploy`
Es el rol que asume el workflow.
1. **IAM** > **Roles** > **Create role** > *Trusted entity type*: **Custom trust policy**.
2. Pegar esta política de confianza (cambiar `<account-id>`):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": {
           "Federated": "arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com"
         },
         "Action": "sts:AssumeRoleWithWebIdentity",
         "Condition": {
           "StringEquals": {
             "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
             "token.actions.githubusercontent.com:sub": "repo:nicolashaly/yumori:ref:refs/heads/master"
           }
         }
       }
     ]
   }
   ```
3. **Next**, sin marcar políticas (se agrega una propia después), y *Role name*: `yumori-github-deploy`. **Create role**.
4. Abrir el rol > **Permissions** > **Add permissions** > **Create inline policy** > pestaña **JSON** y pegar (cambiar `<region>`, `<account-id>` e `<instance-id>`):
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "ssm:SendCommand",
         "Resource": [
           "arn:aws:ssm:<region>::document/AWS-RunShellScript",
           "arn:aws:ec2:<region>:<account-id>:instance/<instance-id>"
         ]
       },
       {
         "Effect": "Allow",
         "Action": [
           "ssm:GetCommandInvocation",
           "ssm:ListCommandInvocations"
         ],
         "Resource": "*"
       }
     ]
   }
   ```
   Nombre: `yumori-ssm-deploy`. **Create policy**.
5. Copiar el **ARN** del rol (arriba, en el resumen): es el valor de `AWS_DEPLOY_ROLE_ARN`.

Dónde encontrar los datos:
- `<region>`: el selector de región arriba a la derecha de la consola (por ejemplo `us-east-1`), la del servidor.
- `<account-id>`: los 12 dígitos del menú de tu usuario (arriba a la derecha).
- `<instance-id>`: **EC2** > **Instances** > columna *Instance ID* (`i-...`).

**Por qué importa la línea `sub`.** Sin ella, cualquier repositorio de GitHub (o cualquier rama) podría pedir este rol, porque el proveedor OIDC es el mismo para todos. Con ella, solo el workflow de `nicolashaly/yumori` ejecutándose en `master` obtiene credenciales: un pull request o una rama no pueden desplegar. Si algún día se agrega `environment:` al job `deploy`, el `sub` cambia (`repo:nicolashaly/yumori:environment:<nombre>`) y hay que actualizar la política de confianza.

`ssm:GetCommandInvocation` y `ssm:ListCommandInvocations` se dejan con `"Resource": "*"`: según lo que sé, no se pueden acotar de forma útil, pero **no lo verifiqué**. Lo que sí queda acotado es `SendCommand`: solo con `AWS-RunShellScript` y solo sobre esa instancia.

## 4. Variables en GitHub
Repositorio > **Settings** > **Secrets and variables** > **Actions** > pestaña **Variables** > **New repository variable**. Son **variables**, no *secrets*: ninguno de los tres valores es secreto.

| Nombre | Valor |
|---|---|
| `AWS_DEPLOY_ROLE_ARN` | el ARN del paso 3 (`arn:aws:iam::<account-id>:role/yumori-github-deploy`) |
| `AWS_REGION` | la región de la instancia (por ejemplo `us-east-1`) |
| `EC2_INSTANCE_ID` | `i-...` |

Crear `AWS_DEPLOY_ROLE_ARN` activa el despliegue: hasta entonces el job `deploy` se omite. Conviene crearla al final, con las otras dos ya puestas.

## 5. Proteger `master`
Repositorio > **Settings** > **Branches** > **Add branch ruleset** (o *Add classic branch protection rule*) para `master`:
- **Require a pull request before merging**.
- **Require status checks to pass**: agregar `python` y `frontend`. Los nombres solo aparecen en el buscador después de que el flujo corrió una vez.
- Con una sola persona desarrollando, se puede dejar que el dueño se salte la regla (*bypass list*). Es decisión tuya: con el bypass, un push directo a `master` también despliega, pero igual pasa por las pruebas del flujo, y `deploy` no se ejecuta si fallan.

## 6. Primera ejecución y cómo leerla
1. Subir `.github/workflows/ci.yml` a `master` (por pull request o directo). Se dispara el flujo.
2. Repositorio > pestaña **Actions** > la ejecución *CI*. Los jobs `python` y `frontend` salen en paralelo; `deploy` espera a ambos.
3. En `deploy`, el paso **Desplegar en la EC2 con SSM** muestra el `CommandId`, los estados (`Pending`, `InProgress`, `Success`) y, al terminar, dos secciones plegables: la salida estándar y el error estándar del servidor (lo que imprimieron `git` y `docker compose`). Lo que AWS devuelve en esos campos se corta en unos 24 000 caracteres (según la documentación de AWS, no verificado aquí).
4. **Un comando fallido** se ve así: el paso termina en rojo con `El despliegue terminó con estado: Failed` (o `TimedOut`, `Cancelled`) y la sección de error muestra la causa (por ejemplo, `git` sin acceso al repositorio, `docker: permission denied` o falta de memoria al compilar Next).
5. **En AWS:** **Systems Manager** > **Run Command** > pestaña **Command history**. Abrir el comando con ese `CommandId` > la instancia > **Output**. El comentario del comando dice el commit (`Deploy <12 caracteres> (run <n>)`).
6. Si el paso final falla (`curl`), el despliegue en sí terminó bien pero el sitio no respondió: probar `https://yumori.cl` y, en la EC2, `docker compose ps` y `docker compose logs --tail 100 caddy web api`.

Si un error dice `AccessDenied` o `Not authorized to perform sts:AssumeRoleWithWebIdentity`, casi siempre es la política de confianza (paso 3): el `sub` no coincide con `repo:nicolashaly/yumori:ref:refs/heads/master`, la audiencia, o el ARN del proveedor.

## 7. Volver atrás
El despliegue siempre deja la EC2 en el commit exacto que lo disparó (`git reset --hard <sha>`). Dos formas de volver:
- **Re-ejecutar una ejecución anterior:** **Actions** > una ejecución *CI* vieja que haya salido bien > **Re-run all jobs**. Una re-ejecución usa el mismo commit de aquella vez, así que despliega ese código. Es lo más rápido, pero `master` y producción quedan distintos hasta el siguiente push.
- **`git revert <commit>` y push** (por pull request): queda en el historial y produce un despliegue normal. Es lo más ordenado.

A tener en cuenta:
- Volver atrás cambia solo el código. `data/` se queda como está, y `db.connect()` ejecuta migraciones al arrancar ([esquema](../database/schema.md)); código viejo con una base ya migrada **no está verificado**, así que si un cambio toca el esquema hay que pensarlo antes.
- Cada despliegue **reconstruye las imágenes en la propia EC2** (`--build`) y recrea los contenedores que cambiaron: el sitio puede quedar unos segundos sin responder mientras se recrean. La memoria que necesita el build de Next en una instancia chica (por ejemplo una `t3.small`) **no está medida**: si el build se queda sin memoria, `deploy` falla con el error en la sección de error estándar.
- Un `docker image prune -f` borra las imágenes sin uso (sin etiqueta) después de cada despliegue. Las etiquetadas, las que están en uso y los volúmenes (`caddy_data`) no se tocan.
- Un solo despliegue a la vez: si se juntan dos pushes, el segundo espera. Si se pierde la espera por el límite (22 minutos), el paso falla aunque el comando pueda seguir corriendo en la EC2; mirar **Command history** en AWS antes de reintentar.

## 8. Seguridad
- **No se abre ningún puerto de entrada.** El comando llega porque la propia EC2 consulta a Systems Manager hacia afuera. El puerto 22 ya no hace falta para desplegar (puede seguir para uso manual).
- **No hay llaves de AWS en GitHub.** Las credenciales son temporales, de un rol que solo el workflow en `master` puede asumir.
- **El rol solo puede mandar comandos a esta instancia** y solo con el documento `AWS-RunShellScript`.
- **`AWS-RunShellScript` es poderoso:** quien pueda asumir el rol ejecuta lo que quiera en la EC2 como root. Por eso la restricción `sub` a `master` de la política de confianza es el control clave, y por eso `master` debe tener protección (paso 5): quien pueda cambiar `master` o el workflow controla el servidor.
- El SHA se pasa al script remoto por variable de entorno, se valida (40 caracteres hexadecimales) antes de usarse y no se interpola ningún dato de pull requests, ramas o mensajes.
- La clave de despliegue de la EC2 hacia GitHub (solo lectura, del usuario `ubuntu`) sigue siendo la que ya usa `git fetch`; este flujo no la cambia.
- Lo que ve cualquiera con acceso a los registros de Actions: la salida de `git` y `docker compose`. No imprime `.env`.
