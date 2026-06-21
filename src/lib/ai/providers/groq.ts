// Groq — inferencia ultra rápida (LPU) sobre modelos open-weight como Llama.
// API compatible con el formato de OpenAI Chat Completions.
// Docs: https://console.groq.com/docs/quickstart

import type { AiProvider, AiGenerateOptions, AiGenerateResult } from '../types'

const BASE_URL = process.env.GROQ_BASE_URL || 'https://api.groq.com/openai/v1'
const MODEL = process.env.GROQ_MODEL || 'llama-3.3-70b-versatile'

export const groqProvider: AiProvider = {
  id: 'groq',
  label: 'Groq',

  configured: () => !!process.env.GROQ_API_KEY,

  async generate(prompt: string, opts?: AiGenerateOptions): Promise<AiGenerateResult> {
    const apiKey = process.env.GROQ_API_KEY
    if (!apiKey) return { ok: false, error: 'GROQ_API_KEY no configurado', provider: 'groq' }

    const messages: any[] = []
    if (opts?.system) messages.push({ role: 'system', content: opts.system })
    messages.push({ role: 'user', content: prompt })

    try {
      const res = await fetch(`${BASE_URL.replace(/\/$/, '')}/chat/completions`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({
          model: MODEL,
          max_tokens: opts?.maxTokens || 1500,
          messages,
        }),
        signal: AbortSignal.timeout(30000),
      })

      if (!res.ok) {
        const detail = await res.text().catch(() => '')
        return { ok: false, error: `HTTP ${res.status}: ${detail.slice(0, 300)}`, provider: 'groq' }
      }

      const data = await res.json()
      const text = data.choices?.[0]?.message?.content || ''
      return { ok: true, text, provider: 'groq' }
    } catch (err: any) {
      return { ok: false, error: err?.message || 'Error de red consultando Groq', provider: 'groq' }
    }
  },
}
