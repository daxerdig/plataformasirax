import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { enrichPhone } from '@/lib/synkdata'

export const POST = withApiAuth('digital', async (request) => {
  const { phone } = await request.json().catch(() => ({}))
  if (!phone) return NextResponse.json({ error: 'El campo phone es requerido.', code: 'MISSING_FIELD' }, { status: 400 })
  const result = await enrichPhone(phone)
  return NextResponse.json({ module: 'digital.phone', timestamp: new Date().toISOString(), ...result })
})
