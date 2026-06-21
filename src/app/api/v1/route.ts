import { NextResponse } from 'next/server'

const BASE = 'https://sirax.lat'

export async function GET() {
  return NextResponse.json({
    api:     'Sirax Identity & Risk Intelligence API',
    vendor:  'Synkdata',
    version: 'v1',
    base_url: `${BASE}/api/v1`,
    auth:    'Bearer sirax_live_... (header Authorization o X-Api-Key)',
    docs:    `${BASE}/docs`,
    endpoints: {
      identity: {
        'POST /api/v1/identity/curp':       'Validación algorítmica de CURP (formato + dígito verificador)',
        'POST /api/v1/identity/rfc':        'Validación algorítmica de RFC + tipo de persona',
      },
      government: {
        'POST /api/v1/government/renapo':   'Consulta RENAPO — vigencia del registro CURP',
        'POST /api/v1/government/sat':      'Consulta SAT — estatus fiscal y régimen',
        'POST /api/v1/government/imss':     'Consulta IMSS — afiliación y empleador actual',
        'POST /api/v1/government/rnd':      'Consulta RND (SSPC) — registro nacional de detenciones',
      },
      sanctions: {
        'POST /api/v1/sanctions/screen':    'Screening en listas OFAC, ONU, EU, UK, PEPs',
      },
      digital: {
        'POST /api/v1/digital/email':       'Enriquecimiento de email: tipo, brechas HIBP, MX records',
        'POST /api/v1/digital/phone':       'Validación de teléfono: operadora, tipo de línea, spam',
        'POST /api/v1/digital/username':    'Descubrimiento de perfiles por username/alias',
      },
      footprint: {
        'POST /api/v1/footprint':           'Score de presencia digital consolidada',
      },
      check: {
        'POST /api/v1/check':               'Background check completo — todos los módulos en una sola llamada',
      },
      account: {
        'GET  /api/v1/keys':                'Listar tus API Keys',
        'POST /api/v1/keys':                'Crear nueva API Key',
        'DELETE /api/v1/keys/:id':          'Revocar una API Key',
        'GET  /api/v1/usage':               'Consumo mensual por endpoint',
      },
    },
    example: {
      curl: `curl -X POST ${BASE}/api/v1/identity/curp \\
  -H "Authorization: Bearer sirax_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{"curp":"GOMC900101HOCMRR09","full_name":"Carlos Gomez"}'`,
    },
  })
}
