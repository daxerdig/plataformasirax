import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { screenSanctions } from '@/lib/synkdata'

export const POST = withApiAuth('sanctions', async (request) => {
  const { full_name, threshold } = await request.json().catch(() => ({}))
  if (!full_name) return NextResponse.json({ error: 'El campo full_name es requerido.', code: 'MISSING_FIELD' }, { status: 400 })
  const result = await screenSanctions(full_name, threshold)
  return NextResponse.json({ module: 'sanctions.screen', timestamp: new Date().toISOString(), ...result })
})
