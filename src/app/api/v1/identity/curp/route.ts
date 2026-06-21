import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { validateCurp } from '@/lib/synkdata'

export const POST = withApiAuth('identity', async (request) => {
  const { curp, full_name } = await request.json().catch(() => ({}))
  if (!curp) return NextResponse.json({ error: 'El campo curp es requerido.', code: 'MISSING_FIELD' }, { status: 400 })
  return NextResponse.json({ module: 'identity.curp', timestamp: new Date().toISOString(), ...validateCurp(curp, full_name) })
})
