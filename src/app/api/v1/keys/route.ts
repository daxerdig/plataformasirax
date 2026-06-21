/**
 * GET  /api/v1/keys  — listar API Keys del usuario autenticado
 * POST /api/v1/keys  — crear nueva API Key
 *
 * Estos endpoints usan JWT (sesión de la plataforma), NO API Key,
 * porque son los que crean/gestionan las keys.
 */
import { NextResponse } from 'next/server'
import { verifyToken, getTokenFromHeaders } from '@/lib/auth'
import { generateApiKey } from '@/lib/api-auth'
import { db } from '@/lib/db'

function authUser(request: Request) {
  const token = getTokenFromHeaders(request)
  if (!token) return null
  return verifyToken(token)
}

// ── GET: listar keys del usuario ──────────────────────────────────────────
export async function GET(request: Request) {
  const user = authUser(request)
  if (!user) return NextResponse.json({ error: 'No autorizado.' }, { status: 401 })

  const keys = await db.apiKey.findMany({
    where: { userId: user.userId },
    select: {
      id: true, name: true, keyPrefix: true, scopes: true,
      rateLimit: true, usageCount: true, lastUsedAt: true,
      expiresAt: true, active: true, createdAt: true,
    },
    orderBy: { createdAt: 'desc' },
  })

  return NextResponse.json({ keys })
}

// ── POST: crear nueva API Key ──────────────────────────────────────────────
export async function POST(request: Request) {
  const user = authUser(request)
  if (!user) return NextResponse.json({ error: 'No autorizado.' }, { status: 401 })

  const {
    name       = 'Mi API Key',
    scopes     = '*',
    rateLimit  = 1000,
    expiresAt,
  } = await request.json().catch(() => ({}))

  // Límite: máximo 10 keys activas por usuario
  const count = await db.apiKey.count({ where: { userId: user.userId, active: true } })
  if (count >= 10) {
    return NextResponse.json(
      { error: 'Límite de 10 API Keys activas alcanzado. Revoca alguna antes de crear una nueva.' },
      { status: 400 }
    )
  }

  const { raw, hash, prefix } = generateApiKey()

  await db.apiKey.create({
    data: {
      userId:    user.userId,
      name:      String(name).slice(0, 60),
      keyHash:   hash,
      keyPrefix: prefix,
      scopes:    String(scopes),
      rateLimit: Number(rateLimit) || 1000,
      expiresAt: expiresAt ? new Date(expiresAt) : null,
    },
  })

  return NextResponse.json({
    message: '⚠ Guarda esta key ahora — no se mostrará de nuevo.',
    api_key: raw,
    prefix,
    scopes,
    rate_limit: rateLimit,
    note: 'Úsala en el header: Authorization: Bearer ' + raw,
  }, { status: 201 })
}
