import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { enrichEmail } from '@/lib/synkdata'

export const POST = withApiAuth('digital', async (request) => {
  const { email } = await request.json().catch(() => ({}))
  if (!email) return NextResponse.json({ error: 'El campo email es requerido.', code: 'MISSING_FIELD' }, { status: 400 })
  const result = await enrichEmail(email)
  return NextResponse.json({ module: 'digital.email', timestamp: new Date().toISOString(), ...result })
})
