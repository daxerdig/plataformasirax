import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { validateRfc } from '@/lib/synkdata'

export const POST = withApiAuth('identity', async (request) => {
  const { rfc } = await request.json().catch(() => ({}))
  if (!rfc) return NextResponse.json({ error: 'El campo rfc es requerido.', code: 'MISSING_FIELD' }, { status: 400 })
  return NextResponse.json({ module: 'identity.rfc', timestamp: new Date().toISOString(), ...validateRfc(rfc) })
})
