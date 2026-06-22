# syntax=docker/dockerfile:1.7
# Sirax · Synkdata — Production Dockerfile (Railway)
# Multi-stage build: builder → runner minimal

# ─────────────────────────────────────────────
# 1. BUILDER
# ─────────────────────────────────────────────
FROM node:20-slim AS builder
WORKDIR /app

# Dependencias del sistema para Prisma
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    openssl ca-certificates && rm -rf /var/lib/apt/lists/*

# Lockfiles primero (cache de capas)
COPY package.json package-lock.json* bun.lock* ./
COPY prisma ./prisma

# Instalar dependencias
RUN npm ci

# Generar Prisma client
RUN npx prisma generate

# Copiar fuente y construir
COPY . .
RUN npm run build

# ─────────────────────────────────────────────
# 2. RUNNER
# ─────────────────────────────────────────────
FROM node:20-slim AS runner
WORKDIR /app

RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    openssl ca-certificates && rm -rf /var/lib/apt/lists/*

ENV NODE_ENV=production
ENV PORT=3000
ENV NEXT_TELEMETRY_DISABLED=1
ENV NEXT_PUBLIC_APP_NAME="Sirax"
ENV NEXT_PUBLIC_APP_VENDOR="Synkdata"

# Usuario sin privilegios
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 --ingroup nodejs nextjs

# Servidor standalone de Next.js (Se extrae directamente a la raíz de /app)
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

# Prisma client + schema (necesarios para migraciones en runtime)
COPY --from=builder --chown=nextjs:nodejs /app/prisma ./prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/@prisma ./node_modules/@prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules/prisma ./node_modules/prisma

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://localhost:3000/api/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

# Comando de arranque: ejecuta migraciones y levanta el servidor standalone
CMD ["sh", "-c", "npx prisma db push --accept-data-loss && node server.js"]
