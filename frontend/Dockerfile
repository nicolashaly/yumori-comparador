# Presentación Next.js de Yumori (ADR-009). Tres etapas: dependencias, compilación y ejecución.
# Contexto de construcción: esta carpeta (frontend/). Ver docker-compose.yml, servicio `web`.

# 1) Dependencias exactas del lockfile.
FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# 2) Compilación. `next build` no necesita la API: las rutas son dinámicas (force-dynamic) y leen Python al pedirse, no al compilar.
FROM node:22-bookworm-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build && npm prune --omit=dev

# 3) Ejecución: solo lo necesario para `next start`, sin código fuente ni dependencias de desarrollo.
FROM node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build --chown=node:node /app/package.json /app/next.config.mjs ./
COPY --from=build --chown=node:node /app/node_modules ./node_modules
COPY --from=build --chown=node:node /app/.next ./.next
COPY --from=build --chown=node:node /app/public ./public

# Menos superficie y sin hallazgos altos o críticos de Trivy (.github/workflows/security.yml):
# - se actualiza perl-base, del sistema de la imagen base;
# - se quitan npm, corepack y yarn, que el servidor no usa (arranca con `node`, no con `npm start`) y cuyos paquetes
#   internos eran los hallazgos altos del análisis de la imagen. Las etapas anteriores sí los usan; esta es la imagen final.
RUN apt-get update \
    && apt-get install -y --no-install-recommends --only-upgrade perl-base \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/corepack /opt/yarn-* \
    && rm -f /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack /usr/local/bin/yarn /usr/local/bin/yarnpkg

# Usuario `node` (UID 1000) de la imagen, sin privilegios.
USER node

# Escucha en 0.0.0.0 para que Docker pueda publicar el 3000 (a diferencia de `npm start`, que usa 127.0.0.1).
# YUMORI_API_ORIGIN sigue siendo http://127.0.0.1:8000 (solo admite loopback, ADR-009): funciona porque este contenedor
# comparte la red del de la API.
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD ["node", "-e", "fetch('http://127.0.0.1:3000/robots.txt').then(() => process.exit(0), () => process.exit(1))"]

CMD ["./node_modules/.bin/next", "start", "--hostname", "0.0.0.0", "--port", "3000"]
