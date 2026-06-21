/**
 * POST /api/v1/check
 * Scope: *  (requiere API Key con scope check o *)
 *
 * Background check completo — ejecuta todos los módulos seleccionados
 * en paralelo y devuelve un resultado unificado con scores y recomendación.
 *
 * Body:
 * {
 *   full_name:  string   (requerido)
 *   curp?:      string
 *   rfc?:       string
 *   email?:     string
 *   phone?:     string
 *   username?:  string
 *   nss?:       string
 *   estado?:    string   (clave INEGI, ej: "OC")
 *   modules?: {          (todos true por defecto)
 *     identity?:     boolean
 *     government?:   boolean
 *     sanctions?:    boolean
 *     digital?:      boolean
 *     ai_report?:    boolean
 *   }
 * }
 */
import { NextResponse } from 'next/server'
import { withApiAuth } from '@/lib/with-api-auth'
import {
  validateCurp, validateRfc,
  queryRenapo, querySat, queryImss, queryRnd,
  screenSanctions,
  enrichEmail, enrichPhone, discoverUsername,
  calculateDigitalFootprint, buildRelationshipGraph,
  calculateScores, correlateIdentity,
} from '@/lib/synkdata'
import { generateAiNarrative } from '@/lib/providers/ai-report'

export const POST = withApiAuth('check', async (request) => {
  const body = await request.json().catch(() => ({}))

  const {
    full_name, curp, rfc, email, phone, username, nss, estado,
    modules: mod = {},
  } = body

  if (!full_name) {
    return NextResponse.json(
      { error: 'El campo full_name es requerido.', code: 'MISSING_FIELD' },
      { status: 400 }
    )
  }

  const run = {
    identity:   mod.identity   !== false,
    government: mod.government !== false,
    sanctions:  mod.sanctions  !== false,
    digital:    mod.digital    !== false,
    ai_report:  mod.ai_report  !== false,
  }

  const sourcesConsulted:   string[] = []
  const sourcesUnavailable: string[] = []
  const result: any = {
    module:    'check.full',
    timestamp: new Date().toISOString(),
    subject: { full_name, curp, rfc, email, phone, username },
  }

  const track = (label: string, ok: boolean, detail?: string) => {
    if (ok) sourcesConsulted.push(label)
    else sourcesUnavailable.push(detail ? `${label}: ${detail}` : label)
  }

  // ── 1. Identity ────────────────────────────────────────────────────────
  if (run.identity) {
    if (curp) {
      result.curp_validation = validateCurp(curp, full_name)
      track('Algoritmo oficial CURP', true)
    }
    if (rfc) {
      result.rfc_validation = validateRfc(rfc)
      track('Algoritmo oficial RFC', true)
    }
  }

  // ── 2. Government ─────────────────────────────────────────────────────
  if (run.government) {
    const nameParts = full_name.split(' ')
    const [renapoR, satR, imssR, rndR] = await Promise.all([
      curp ? queryRenapo(curp, full_name) : Promise.resolve(null),
      rfc  ? querySat(rfc)               : Promise.resolve(null),
      curp ? queryImss(nss, curp)        : Promise.resolve(null),
      queryRnd(nameParts[0], nameParts[1] || '', nameParts[2], estado),
    ])
    const gov: any = {}
    if (renapoR) { gov.renapo = renapoR; track('RENAPO (Nubarium)', renapoR.available, renapoR.message) }
    if (satR)    { gov.sat    = satR;    track('SAT (Nubarium)',    satR.available,    satR.message)    }
    if (imssR)   { gov.imss   = imssR;   track('IMSS (Nubarium)',   imssR.available,   imssR.message)   }
    gov.rnd = rndR
    track('RND (SSPC)', false, rndR.message)
    result.government = gov
  }

  // ── 3. Sanctions ──────────────────────────────────────────────────────
  if (run.sanctions) {
    result.sanctions = await screenSanctions(full_name)
    for (const s of result.sanctions.sources_available   || []) sourcesConsulted.push(s)
    for (const s of result.sanctions.sources_unavailable || []) sourcesUnavailable.push(s)
  }

  // ── 4. Digital ────────────────────────────────────────────────────────
  if (run.digital) {
    const [emailR, phoneR, usernameR] = await Promise.all([
      email    ? enrichEmail(email)         : Promise.resolve(null),
      phone    ? enrichPhone(phone)         : Promise.resolve(null),
      username ? discoverUsername(username) : Promise.resolve(null),
    ])
    const di: any = {}
    if (emailR)    { di.email    = emailR;    track('Hunter.io + HIBP + DNS', emailR.available    ?? true) }
    if (phoneR)    { di.phone    = phoneR;    track('Numverify',               phoneR.available    ?? true) }
    if (usernameR) { di.username = usernameR; track('Username OSINT',          usernameR.available ?? true) }
    result.digital_identity  = di
    result.digital_footprint = calculateDigitalFootprint(emailR, phoneR, usernameR)
  }

  // ── 5. Relationship graph ──────────────────────────────────────────────
  result.relationship_graph = buildRelationshipGraph({
    subject:          { full_name, curp, rfc, email, phone, username },
    curp_validation:  result.curp_validation,
    rfc_validation:   result.rfc_validation,
    government:       result.government,
    sanctions:        result.sanctions,
    digital_identity: result.digital_identity,
  })

  // ── 6. Scores + Recomendación ──────────────────────────────────────────
  const identity_result = correlateIdentity({
    curp_validation: result.curp_validation,
    rfc_validation:  result.rfc_validation,
    government:      result.government,
  })

  const scores = calculateScores({
    curp_validation:  result.curp_validation,
    rfc_validation:   result.rfc_validation,
    government:       result.government,
    sanctions:        result.sanctions,
    digital_identity: result.digital_identity,
    digital_footprint:result.digital_footprint,
    relationship_graph: result.relationship_graph,
  })

  Object.assign(result, scores, identity_result)

  // ── 7. AI Report ──────────────────────────────────────────────────────
  if (run.ai_report) {
    result.ai_report = await generateAiNarrative({
      subject:           { full_name, curp, rfc, email, phone },
      trust_score:       result.trust_score,
      risk_score:        result.risk_score,
      risk_level:        result.risk_level,
      recommendation:    result.recommendation,
      flags:             result.flags,
      breakdown:         result.breakdown,
      curp_validation:   result.curp_validation,
      rfc_validation:    result.rfc_validation,
      government:        result.government,
      sanctions:         result.sanctions,
      digital_identity:  result.digital_identity,
      digital_footprint: result.digital_footprint,
    })
  }

  result.sources_consulted   = sourcesConsulted
  result.sources_unavailable = sourcesUnavailable

  return NextResponse.json(result)
})
