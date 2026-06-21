import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { discoverUsername } from '@/lib/synkdata'

export const POST = withApiAuth('digital', async (request) => {
  const { username } = await request.json().catch(() => ({}))
  if (!username) return NextResponse.json({ error: 'El campo username es requerido.', code: 'MISSING_FIELD' }, { status: 400 })
  const result = await discoverUsername(username)
  return NextResponse.json({ module: 'digital.username', timestamp: new Date().toISOString(), ...result })
})
