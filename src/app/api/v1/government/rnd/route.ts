import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { queryRnd } from '@/lib/synkdata'

export const POST = withApiAuth('government', async (request) => {
  const { first_name, paternal, maternal, estado } = await request.json().catch(() => ({}))
  if (!first_name || !paternal) return NextResponse.json({ error: 'first_name y paternal son requeridos.', code: 'MISSING_FIELD' }, { status: 400 })
  const result = await queryRnd(first_name, paternal, maternal, estado)
  return NextResponse.json({ module: 'government.rnd', timestamp: new Date().toISOString(), ...result })
})
