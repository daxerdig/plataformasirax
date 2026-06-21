import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import { calculateDigitalFootprint } from '@/lib/synkdata'

export const POST = withApiAuth('digital', async (request) => {
  const { email, phone, username } = await request.json().catch(() => ({}))
  if (!email && !phone && !username) return NextResponse.json({ error: 'Se requiere al menos email, phone o username.', code: 'MISSING_FIELD' }, { status: 400 })
  const [emailR, phoneR, usernameR] = await Promise.all([
    email    ? import('@/lib/synkdata').then(m => m.enrichEmail(email))       : Promise.resolve(null),
    phone    ? import('@/lib/synkdata').then(m => m.enrichPhone(phone))       : Promise.resolve(null),
    username ? import('@/lib/synkdata').then(m => m.discoverUsername(username)): Promise.resolve(null),
  ])
  const result = calculateDigitalFootprint(emailR, phoneR, usernameR)
  return NextResponse.json({ module: 'digital.footprint', timestamp: new Date().toISOString(), ...result })
})
