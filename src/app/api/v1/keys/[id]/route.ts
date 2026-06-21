/**
 * DELETE /api/v1/keys/:id — revocar (desactivar) una API Key
 */
import { NextResponse } from 'next/server'
import { verifyToken, getTokenFromHeaders } from '@/lib/auth'
import { db } from '@/lib/db'

export async function DELETE(request: Request, { params }: { params: { id: string } }) {
  const token = getTokenFromHeaders(request)
  if (!token) return NextResponse.json({ error: 'No autorizado.' }, { status: 401 })
  const user = verifyToken(token)
  if (!user) return NextResponse.json({ error: 'Token inválido.' }, { status: 401 })

  const key = await db.apiKey.findFirst({
    where: { id: params.id, userId: user.userId },
  })

  if (!key) {
    return NextResponse.json({ error: 'API Key no encontrada.' }, { status: 404 })
  }

  await db.apiKey.update({
    where: { id: params.id },
    data:  { active: false },
  })

  return NextResponse.json({ message: `API Key "${key.name}" revocada correctamente.`, id: params.id })
}
