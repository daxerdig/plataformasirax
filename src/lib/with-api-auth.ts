/**
 * withApiAuth — HOF que envuelve un handler v1 con:
 *   1. Autenticación por API Key
 *   2. Verificación de scope
 *   3. Log automático de la petición
 */
import { NextResponse } from 'next/server'
import { verifyApiKey, logApiRequest, ApiKeyPayload } from './api-auth'

type Handler = (
  request: Request,
  payload: ApiKeyPayload
) => Promise<NextResponse>

export function withApiAuth(scope: string, handler: Handler) {
  return async (request: Request): Promise<NextResponse> => {
    const t0     = Date.now()
    const ip     = request.headers.get('x-forwarded-for')?.split(',')[0] ?? undefined
    const url    = new URL(request.url)
    const endpoint = url.pathname

    const auth = await verifyApiKey(request)
    if (!auth.ok) return auth.response

    const { payload } = auth

    // Verificar scope
    if (scope !== '*' && !payload.scopes.includes('*') && !payload.scopes.includes(scope)) {
      return NextResponse.json(
        { error: `Tu API Key no tiene el scope requerido: ${scope}`, code: 'INSUFFICIENT_SCOPE' },
        { status: 403 }
      )
    }

    let statusCode = 200
    let response: NextResponse

    try {
      response = await handler(request, payload)
      statusCode = response.status
    } catch (err: any) {
      statusCode = 500
      response = NextResponse.json(
        { error: 'Error interno del servidor', detail: err?.message },
        { status: 500 }
      )
    }

    // Log no bloqueante
    logApiRequest({
      apiKeyId:   payload.apiKeyId,
      endpoint,
      method:     request.method,
      statusCode,
      durationMs: Date.now() - t0,
      ip,
    })

    response.headers.set('X-Sirax-Version',  'v1')
    response.headers.set('X-Response-Time',  `${Date.now() - t0}ms`)

    return response
  }
}
