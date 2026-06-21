import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { queryRenapo } from '@/lib/synkdata'

export const POST = withApiAuth('government', async (request) => {
  const { curp, full_name } = await request.json().catch(() => ({}))
  if (!curp || !full_name) return NextResponse.json({ error: 'curp y full_name son requeridos.', code: 'MISSING_FIELD' }, { status: 400 })
  const result = await queryRenapo(curp, full_name)
  return NextResponse.json({ module: 'government.renapo', timestamp: new Date().toISOString(), ...result })
})
