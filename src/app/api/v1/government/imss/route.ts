import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { queryImss } from '@/lib/synkdata'

export const POST = withApiAuth('government', async (request) => {
  const { curp, nss } = await request.json().catch(() => ({}))
  if (!curp) return NextResponse.json({ error: 'El campo curp es requerido.', code: 'MISSING_FIELD' }, { status: 400 })
  const result = await queryImss(nss, curp)
  return NextResponse.json({ module: 'government.imss', timestamp: new Date().toISOString(), ...result })
})
