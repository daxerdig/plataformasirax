/**
 * Sirax · API pública — autenticación por API Key + rate limiting
 * Usada por todos los endpoints /api/v1/*
 */
import { createHash } from 'crypto'
import { NextResponse } from 'next/server'
import { db } from './db'

export interface ApiKeyPayload {
  apiKeyId: string
  userId: string
  scopes: string[]
}

// ── Helpers ────────────────────────────────────────────────────────────────
function hashKey(raw: string): string {
  return createHash('sha256').update(raw).digest('hex')
}

function parseScopes(s: string): string[] {
  return s === '*' ? ['*'] : s.split(',').map(x => x.trim()).filter(Boolean)
}

export function hasScope(payload: ApiKeyPayload, scope: string): boolean {
  return payload.scopes.includes('*') || payload.scopes.includes(scope)
}

// Genera un nuevo API Key  →  sirax_live_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
export function generateApiKey(): { raw: string; hash: string; prefix: string } {
  const bytes = createHash('sha256')
    .update(Math.random().toString() + Date.now())
    .digest('hex')
  const raw    = `sirax_live_${bytes}`
  const hash   = hashKey(raw)
  const prefix = raw.slice(0, 16)
  return { raw, hash, prefix }
}

// ── Verificar API Key de una request ──────────────────────────────────────
export async function verifyApiKey(request: Request): Promise<
  | { ok: true;  payload: ApiKeyPayload }
  | { ok: false; response: NextResponse }
> {
  const auth = request.headers.get('authorization') || ''
  const raw  = auth.startsWith('Bearer ') ? auth.slice(7) : request.headers.get('x-api-key') || ''

  if (!raw || !raw.startsWith('sirax_live_')) {
    return {
      ok: false,
      response: NextResponse.json(
        { error: 'API Key requerida. Incluye: Authorization: Bearer sirax_live_...', code: 'MISSING_API_KEY' },
        { status: 401 }
      ),
    }
  }

  const key = await db.apiKey.findUnique({
    where: { keyHash: hashKey(raw) },
    include: { user: { select: { id: true } } },
  })

  if (!key || !key.active) {
    return {
      ok: false,
      response: NextResponse.json(
        { error: 'API Key inválida o desactivada.', code: 'INVALID_API_KEY' },
        { status: 401 }
      ),
    }
  }

  if (key.expiresAt && key.expiresAt < new Date()) {
    return {
      ok: false,
      response: NextResponse.json(
        { error: 'API Key expirada.', code: 'EXPIRED_API_KEY' },
        { status: 401 }
      ),
    }
  }

  // Rate limit mensual
  const now       = new Date()
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
  const usageThisMonth = await db.apiRequestLog.count({
    where: { apiKeyId: key.id, createdAt: { gte: monthStart } },
  })

  if (usageThisMonth >= key.rateLimit) {
    return {
      ok: false,
      response: NextResponse.json(
        {
          error: `Límite mensual de ${key.rateLimit} peticiones alcanzado.`,
          code:  'RATE_LIMIT_EXCEEDED',
          limit: key.rateLimit,
          used:  usageThisMonth,
          resets: new Date(now.getFullYear(), now.getMonth() + 1, 1).toISOString(),
        },
        {
          status: 429,
          headers: {
            'X-RateLimit-Limit':     String(key.rateLimit),
            'X-RateLimit-Remaining': '0',
            'X-RateLimit-Reset':     String(Math.floor(new Date(now.getFullYear(), now.getMonth() + 1, 1).getTime() / 1000)),
          },
        }
      ),
    }
  }

  // Actualizar lastUsedAt (no bloqueante)
  db.apiKey.update({ where: { id: key.id }, data: { lastUsedAt: now, usageCount: { increment: 1 } } }).catch(() => {})

  return {
    ok: true,
    payload: {
      apiKeyId: key.id,
      userId:   key.userId,
      scopes:   parseScopes(key.scopes),
    },
  }
}

// ── Log de petición (llamar al final de cada handler) ─────────────────────
export async function logApiRequest(opts: {
  apiKeyId:   string
  endpoint:   string
  method:     string
  statusCode: number
  durationMs: number
  ip?:        string
}) {
  await db.apiRequestLog.create({ data: opts }).catch(() => {})
}

// ── Helper para construir response con headers de rate limit ──────────────
export function withRateLimitHeaders(
  response: NextResponse,
  limit: number,
  used: number
): NextResponse {
  response.headers.set('X-RateLimit-Limit',     String(limit))
  response.headers.set('X-RateLimit-Remaining', String(Math.max(0, limit - used - 1)))
  response.headers.set('X-Sirax-Version',        'v1')
  return response
}
