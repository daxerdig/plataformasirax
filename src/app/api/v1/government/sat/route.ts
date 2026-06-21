import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { querySat } from '@/lib/synkdata'

export const POST = withApiAuth('government', async (request) => {
  const { rfc } = await request.json().catch(() => ({}))
  if (!rfc) return NextResponse.json({ error: 'El campo rfc es requerido.', code: 'MISSING_FIELD' }, { status: 400 })
  const result = await querySat(rfc)
  return NextResponse.json({ module: 'government.sat', timestamp: new Date().toISOString(), ...result })
})
