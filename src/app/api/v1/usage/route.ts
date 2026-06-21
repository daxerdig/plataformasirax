/**
 * GET /api/v1/usage
 * Devuelve el consumo del mes actual agrupado por endpoint y API Key.
 * Autenticación: JWT (sesión de la plataforma)
 */
import { NextResponse } from 'next/server'
import { verifyToken, getTokenFromHeaders } from '@/lib/auth'
import { db } from '@/lib/db'

export async function GET(request: Request) {
  const token = getTokenFromHeaders(request)
  if (!token) return NextResponse.json({ error: 'No autorizado.' }, { status: 401 })
  const user = verifyToken(token)
  if (!user) return NextResponse.json({ error: 'Token inválido.' }, { status: 401 })

  const now        = new Date()
  const monthStart = new Date(now.getFullYear(), now.getMonth(), 1)
  const monthEnd   = new Date(now.getFullYear(), now.getMonth() + 1, 1)

  // API Keys del usuario
  const keys = await db.apiKey.findMany({
    where:  { userId: user.userId },
    select: { id: true, name: true, keyPrefix: true, rateLimit: true },
  })

  const keyIds = keys.map(k => k.id)

  // Logs del mes agrupados
  const logs = await db.apiRequestLog.findMany({
    where: {
      apiKeyId:  { in: keyIds },
      createdAt: { gte: monthStart, lt: monthEnd },
    },
    select: { apiKeyId: true, endpoint: true, statusCode: true, durationMs: true },
  })

  // Agrupar por key
  const byKey: Record<string, any> = {}
  for (const k of keys) {
    byKey[k.id] = {
      key_id:     k.id,
      name:       k.name,
      prefix:     k.keyPrefix,
      rate_limit: k.rateLimit,
      total:      0,
      success:    0,
      errors:     0,
      avg_ms:     0,
      by_endpoint: {} as Record<string, number>,
    }
  }

  for (const log of logs) {
    const k = byKey[log.apiKeyId]
    if (!k) continue
    k.total++
    if (log.statusCode < 400) k.success++; else k.errors++
    k.avg_ms += log.durationMs
    k.by_endpoint[log.endpoint] = (k.by_endpoint[log.endpoint] || 0) + 1
  }

  for (const k of Object.values(byKey) as any[]) {
    k.avg_ms = k.total > 0 ? Math.round(k.avg_ms / k.total) : 0
  }

  const totalRequests = logs.length

  return NextResponse.json({
    period: {
      start: monthStart.toISOString(),
      end:   monthEnd.toISOString(),
      month: now.toLocaleString('es-MX', { month: 'long', year: 'numeric' }),
    },
    summary: {
      total_requests: totalRequests,
      total_success:  logs.filter(l => l.statusCode < 400).length,
      total_errors:   logs.filter(l => l.statusCode >= 400).length,
    },
    by_key: Object.values(byKey),
  })
}
