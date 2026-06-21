// Punto de entrada único para generar texto con IA. El resto de la app NUNCA
// debe importar un proveedor directamente — siempre usa generateAiText().
//
// Selección de proveedor:
//   AI_PROVIDER=anthropic | openai | google | groq | custom
//   Si no se define, prueba todos en orden hasta encontrar uno configurado.
//   Si el preferido falla en tiempo de ejecución (rate limit, red, etc.),
//   automáticamente intenta el siguiente configurado como fallback.

import { anthropicProvider } from './providers/anthropic'
import { openaiProvider } from './providers/openai'
import { googleProvider } from './providers/google'
import { groqProvider } from './providers/groq'
import { customProvider } from './providers/custom'
import type { AiProvider, AiGenerateOptions, AiGenerateResult } from './types'

// Para agregar un proveedor nuevo: créalo en ./providers (usa _template.ts
// como base) y agrégalo a esta lista. No hay que tocar nada más.
const PROVIDERS: AiProvider[] = [
  anthropicProvider,
  openaiProvider,
  googleProvider,
  groqProvider,
  customProvider,
]

function resolveOrder(): AiProvider[] {
  const preferredId = (process.env.AI_PROVIDER || '').toLowerCase().trim()
  if (!preferredId) return PROVIDERS

  const preferred = PROVIDERS.find((p) => p.id === preferredId)
  if (!preferred) {
    console.warn(`[ai] AI_PROVIDER="${preferredId}" no coincide con ningún proveedor registrado (${PROVIDERS.map(p => p.id).join(', ')}). Usando orden por defecto.`)
    return PROVIDERS
  }
  return [preferred, ...PROVIDERS.filter((p) => p.id !== preferredId)]
}

export async function generateAiText(prompt: string, opts?: AiGenerateOptions): Promise<AiGenerateResult> {
  const order = resolveOrder()
  const attempted: string[] = []

  for (const provider of order) {
    if (!provider.configured()) continue
    attempted.push(provider.id)
    const result = await provider.generate(prompt, opts)
    if (result.ok) return result
    console.error(`[ai] proveedor "${provider.id}" falló, probando siguiente:`, result.error)
  }

  return {
    ok: false,
    provider: 'none',
    error: attempted.length > 0
      ? `Todos los proveedores configurados fallaron (${attempted.join(', ')})`
      : 'Ningún proveedor de IA configurado. Define AI_PROVIDER y la API key correspondiente (ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_AI_API_KEY, GROQ_API_KEY, o AI_CUSTOM_BASE_URL+AI_CUSTOM_MODEL).',
  }
}

export function listAiProviders() {
  return PROVIDERS.map((p) => ({ id: p.id, label: p.label, configured: p.configured() }))
}
