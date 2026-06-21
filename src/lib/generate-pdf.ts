/**
 * Sirax · PDF Report Generator
 * Genera un reporte profesional en PDF con todos los módulos del check
 */

// ── Tipos ──────────────────────────────────────────────────────────────────
interface CheckData {
  id: string
  created_at: string
  subject?: { full_name?: string; curp?: string; rfc?: string; email?: string; phone?: string }
  trust_score: number
  risk_score: number
  identity_confidence: number
  risk_level: 'BAJO' | 'MEDIO' | 'ALTO' | 'CRITICO'
  recommendation: 'APPROVE' | 'REVIEW' | 'REJECT'
  flags?: string[]
  curp_validation?: any
  rfc_validation?: any
  government?: any
  sanctions?: any
  digital_identity?: any
  digital_footprint?: any
  relationship_graph?: any
  breakdown?: { trust_components?: any[]; risk_components?: any[] }
  ai_report?: string
  sources_consulted?: string[]
}

// ── Paleta Sirax ───────────────────────────────────────────────────────────
const NAVY    = [10, 25, 47]   as const   // #0a192f
const TEAL    = [0, 209, 160]  as const   // #00d1a0
const TEAL2   = [46, 232, 184] as const   // #2ee8b8
const WHITE   = [255, 255, 255] as const
const GRAY90  = [230, 235, 242] as const  // surface light
const GRAY70  = [180, 190, 205] as const  // muted
const GRAY50  = [120, 135, 155] as const  // placeholder
const RED     = [239, 68, 68]  as const
const AMBER   = [245, 158, 11] as const
const INDIGO  = [99, 102, 241] as const

const RISK_COLORS: Record<string, readonly number[]> = {
  BAJO:   TEAL,
  MEDIO:  AMBER,
  ALTO:   RED,
  CRITICO:[159, 18, 57],
}

const REC_LABELS: Record<string, string> = {
  APPROVE: 'APROBAR',
  REVIEW:  'REVISAR',
  REJECT:  'RECHAZAR',
}

// ── Helpers internos ───────────────────────────────────────────────────────
function setFill(doc: any, rgb: readonly number[]) { doc.setFillColor(...rgb) }
function setDraw(doc: any, rgb: readonly number[]) { doc.setDrawColor(...rgb) }
function setFont(doc: any, rgb: readonly number[], size: number, style = 'normal') {
  doc.setTextColor(...rgb)
  doc.setFontSize(size)
  doc.setFont('helvetica', style)
}

function rect(doc: any, x: number, y: number, w: number, h: number, color: readonly number[]) {
  setFill(doc, color)
  doc.rect(x, y, w, h, 'F')
}

function pill(doc: any, x: number, y: number, text: string, bg: readonly number[], fg: readonly number[], size = 7) {
  setFont(doc, fg, size, 'bold')
  const tw = doc.getTextWidth(text)
  const pw = tw + 8
  const ph = size * 0.72
  setFill(doc, bg)
  doc.roundedRect(x, y - ph + 1, pw, ph + 2, 1.5, 1.5, 'F')
  doc.text(text, x + 4, y + 0.5)
  return pw + 4
}

function sectionHeader(doc: any, y: number, title: string, iconChar = '▪') {
  setFill(doc, NAVY)
  doc.roundedRect(14, y, 182, 7.5, 1.5, 1.5, 'F')
  setFont(doc, TEAL as readonly number[], 7.5, 'bold')
  doc.text(iconChar, 18, y + 5)
  setFont(doc, WHITE, 7.5, 'bold')
  doc.text(title.toUpperCase(), 24, y + 5)
  return y + 11
}

function fieldRow(doc: any, y: number, label: string, value: string | undefined, valueColor: readonly number[] = NAVY) {
  setFont(doc, GRAY50, 7, 'normal')
  doc.text(label, 18, y)
  setFont(doc, valueColor, 7, 'bold')
  doc.text(value || '—', 75, y)
  setDraw(doc, GRAY90)
  doc.setLineWidth(0.2)
  doc.line(18, y + 1.5, 192, y + 1.5)
  return y + 6.5
}

function checkRow(doc: any, y: number, label: string, ok: boolean, note = '') {
  setFont(doc, ok ? (TEAL as readonly number[]) : (RED as readonly number[]), 8, 'bold')
  doc.text(ok ? '✓' : '✗', 18, y)
  setFont(doc, NAVY, 7.5, 'normal')
  doc.text(label, 25, y)
  if (note) {
    setFont(doc, GRAY50, 6.5, 'normal')
    doc.text(note, 110, y)
  }
  return y + 6
}

function scoreCircle(doc: any, cx: number, cy: number, value: number, label: string, color: readonly number[]) {
  const r = 11
  // Track
  setDraw(doc, GRAY90)
  doc.setLineWidth(2.5)
  doc.circle(cx, cy, r, 'S')
  // Arc (progress) — draw series of short arcs to simulate progress
  const pct = value / 100
  const steps = Math.round(pct * 60)
  doc.setLineWidth(2.5)
  setDraw(doc, color)
  for (let i = 0; i < steps; i++) {
    const a1 = (-Math.PI / 2) + (i / 60) * (2 * Math.PI)
    const a2 = (-Math.PI / 2) + ((i + 1) / 60) * (2 * Math.PI)
    const x1 = cx + r * Math.cos(a1)
    const y1 = cy + r * Math.sin(a1)
    const x2 = cx + r * Math.cos(a2)
    const y2 = cy + r * Math.sin(a2)
    setDraw(doc, color)
    doc.setLineWidth(2.5)
    doc.line(x1, y1, x2, y2)
  }
  // Value
  setFont(doc, color, 11, 'bold')
  const vw = doc.getTextWidth(String(value))
  doc.text(String(value), cx - vw / 2, cy + 2)
  // Label
  setFont(doc, GRAY50, 6, 'normal')
  const lw = doc.getTextWidth(label)
  doc.text(label, cx - lw / 2, cy + r + 5)
}

// ── Paginación ─────────────────────────────────────────────────────────────
function maybeNewPage(doc: any, y: number, needed = 20): number {
  if (y + needed > 274) {
    doc.addPage()
    return drawPageHeader(doc, false) // cabecera reducida en páginas internas
  }
  return y
}

function drawPageHeader(doc: any, isFirst: boolean): number {
  // Franja navy top
  rect(doc, 0, 0, 210, isFirst ? 36 : 12, NAVY)
  if (isFirst) {
    // Logo text
    setFont(doc, WHITE, 18, 'bold')
    doc.text('sirax', 14, 18)
    setFont(doc, TEAL as readonly number[], 18, 'bold')
    doc.text('x', 36.5, 18)   // x en teal — aproximación sin SVG
    setFont(doc, GRAY70, 7, 'normal')
    doc.text('Identity & Risk Intelligence · a Synkdata product', 14, 24)
    setFont(doc, GRAY70, 7, 'normal')
    doc.text('Know More. Risk Less.', 14, 30)
    // Línea teal decorativa
    setFill(doc, TEAL)
    doc.rect(0, 35, 210, 1, 'F')
    return 45
  } else {
    setFont(doc, WHITE, 7, 'normal')
    doc.text('sirax · Reporte de Verificación', 14, 8)
    setFill(doc, TEAL)
    doc.rect(0, 11, 210, 0.5, 'F')
    return 18
  }
}

function drawFooter(doc: any, pageNum: number, total: number, checkId: string, date: string) {
  const y = 285
  setFill(doc, NAVY)
  doc.rect(0, y - 2, 210, 14, 'F')
  setFont(doc, GRAY70, 6, 'normal')
  doc.text(`ID de consulta: ${checkId}`, 14, y + 4)
  doc.text(`Generado: ${date}`, 14, y + 8)
  setFont(doc, GRAY70, 6, 'normal')
  const pageText = `Página ${pageNum} / ${total}`
  const pw = doc.getTextWidth(pageText)
  doc.text(pageText, 210 - 14 - pw, y + 4)
  setFont(doc, TEAL as readonly number[], 6, 'normal')
  doc.text('Documento generado automáticamente por Sirax · Synkdata', 70, y + 8)
}

// ── Export principal ───────────────────────────────────────────────────────
export async function generateCheckPDF(check: CheckData): Promise<void> {
  const { jsPDF } = await import('jspdf')
  const doc = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' })

  const genDate = new Date().toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' })
  const checkDate = check.created_at ? new Date(check.created_at).toLocaleString('es-MX', { dateStyle: 'long', timeStyle: 'short' }) : '—'

  // ══ PÁGINA 1 — Portada + Resumen ejecutivo ══════════════════════════════
  let y = drawPageHeader(doc, true)

  // Nombre del sujeto
  setFont(doc, NAVY, 16, 'bold')
  doc.text(check.subject?.full_name || 'Sujeto no identificado', 14, y + 6)
  y += 10

  // Fecha consulta + ID
  setFont(doc, GRAY50, 7, 'normal')
  doc.text(`Fecha de consulta: ${checkDate}  ·  ID: ${check.id}`, 14, y)
  y += 8

  // ── Risk level pill + recomendación ──
  const rColor = RISK_COLORS[check.risk_level] ?? GRAY70
  pill(doc, 14, y, `  ${check.risk_level}  `, rColor, WHITE, 8)
  const recLabel = REC_LABELS[check.recommendation] ?? check.recommendation
  const recColor = check.recommendation === 'APPROVE' ? TEAL : check.recommendation === 'REVIEW' ? AMBER : RED
  pill(doc, 48, y, `  ${recLabel}  `, recColor, WHITE, 8)
  y += 10

  // ── Score circles ──
  y = maybeNewPage(doc, y, 50)
  const scoreY = y + 22
  scoreCircle(doc, 40,  scoreY, check.trust_score,         'Trust Score',        TEAL)
  scoreCircle(doc, 100, scoreY, check.risk_score,          'Risk Score',         rColor as readonly number[])
  scoreCircle(doc, 160, scoreY, check.identity_confidence, 'Confianza Identidad',INDIGO)
  y = scoreY + 22

  // ── Alertas / Flags ──
  if (check.flags && check.flags.length > 0) {
    y += 4
    y = maybeNewPage(doc, y, 12 + check.flags.length * 6)
    setFill(doc, [255, 240, 240])
    setDraw(doc, RED)
    doc.setLineWidth(0.4)
    doc.roundedRect(14, y, 182, 6 + check.flags.length * 5.5, 2, 2, 'FD')
    setFont(doc, RED, 7.5, 'bold')
    doc.text('⚠  ALERTAS DETECTADAS', 18, y + 4.5)
    y += 7
    for (const flag of check.flags) {
      setFont(doc, RED, 7, 'normal')
      doc.text(`• ${flag}`, 20, y)
      y += 5.5
    }
    y += 3
  }

  // ══ MÓDULO 1 — Identity Verification ════════════════════════════════════
  y += 4
  y = maybeNewPage(doc, y, 50)
  y = sectionHeader(doc, y, '01 · Identity Verification', '⬡')

  if (check.curp_validation) {
    const cv = check.curp_validation
    setFont(doc, NAVY, 8, 'bold')
    doc.text('CURP', 18, y)
    y += 5
    y = fieldRow(doc, y, 'CURP', cv.curp)
    y = fieldRow(doc, y, 'Válido', cv.is_valid ? 'SÍ' : 'NO', cv.is_valid ? TEAL as readonly number[] : RED)
    y = fieldRow(doc, y, 'Mensaje', cv.message)
    if (cv.components) {
      y = fieldRow(doc, y, 'Fecha nacimiento', cv.components.birth_date)
      y = fieldRow(doc, y, 'Sexo',            cv.components.sex)
      y = fieldRow(doc, y, 'Estado',          cv.components.state)
      y = fieldRow(doc, y, 'Dígito verificador', cv.check_digit_valid ? 'Válido' : 'Inválido', cv.check_digit_valid ? TEAL as readonly number[] : RED)
    }
    y += 4
  }

  if (check.rfc_validation) {
    const rv = check.rfc_validation
    y = maybeNewPage(doc, y, 30)
    setFont(doc, NAVY, 8, 'bold')
    doc.text('RFC', 18, y)
    y += 5
    y = fieldRow(doc, y, 'RFC',    rv.rfc)
    y = fieldRow(doc, y, 'Válido', rv.is_valid ? 'SÍ' : 'NO', rv.is_valid ? TEAL as readonly number[] : RED)
    y = fieldRow(doc, y, 'Tipo',   rv.type === 'fisica' ? 'Persona Física' : 'Persona Moral')
    if (rv.components) {
      y = fieldRow(doc, y, 'SAT Status',    rv.sat_status,    rv.sat_status === 'ACTIVO' ? TEAL as readonly number[] : RED)
      y = fieldRow(doc, y, 'Régimen Fiscal', rv.regimen_fiscal)
      y = fieldRow(doc, y, 'Homoclave',      rv.components?.homoclave)
    }
    y += 4
  }

  // ══ MÓDULO 2 — Government Intelligence ══════════════════════════════════
  if (check.government) {
    y = maybeNewPage(doc, y, 55)
    y = sectionHeader(doc, y, '02 · Government Intelligence', '⬡')
    const gov = check.government

    if (gov.renapo) {
      setFont(doc, NAVY, 8, 'bold')
      doc.text('RENAPO', 18, y); y += 5
      y = checkRow(doc, y, gov.renapo.found ? 'Registro vigente encontrado' : 'No encontrado en RENAPO', gov.renapo.found ?? false, gov.renapo.message)
      y = fieldRow(doc, y, 'Disponibilidad', gov.renapo.available ? 'Conectado' : 'Sin conexión', gov.renapo.available ? TEAL as readonly number[] : AMBER)
      y += 3
    }
    if (gov.sat) {
      y = maybeNewPage(doc, y, 20)
      setFont(doc, NAVY, 8, 'bold')
      doc.text('SAT', 18, y); y += 5
      y = fieldRow(doc, y, 'Estatus SAT',   gov.sat.status, gov.sat.status === 'ACTIVO' ? TEAL as readonly number[] : RED)
      y = fieldRow(doc, y, 'Régimen',       gov.sat.regimen_fiscal)
      y = fieldRow(doc, y, 'Disponibilidad', gov.sat.available ? 'Conectado' : 'Sin conexión', gov.sat.available ? TEAL as readonly number[] : AMBER)
      y += 3
    }
    if (gov.imss) {
      y = maybeNewPage(doc, y, 20)
      setFont(doc, NAVY, 8, 'bold')
      doc.text('IMSS', 18, y); y += 5
      y = checkRow(doc, y, gov.imss.affiliated ? 'Afiliado al IMSS' : 'Sin afiliación IMSS', gov.imss.affiliated ?? false, gov.imss.message)
      if (gov.imss.employer) y = fieldRow(doc, y, 'Empleador', gov.imss.employer)
      y += 3
    }
    if (gov.rnd) {
      y = maybeNewPage(doc, y, 15)
      setFont(doc, NAVY, 8, 'bold')
      doc.text('RND — Registro Nacional de Detenciones', 18, y); y += 5
      y = checkRow(doc, y, gov.rnd.sin_resultados ? 'Sin registros de detención' : '⚠ Registro encontrado', gov.rnd.sin_resultados ?? true, gov.rnd.message)
      y += 3
    }
    y += 2
  }

  // ══ MÓDULO 3 — Compliance / Sanctions ═══════════════════════════════════
  if (check.sanctions) {
    y = maybeNewPage(doc, y, 55)
    y = sectionHeader(doc, y, '03 · Compliance Intelligence — Sanciones & PEP', '⬡')
    const s = check.sanctions

    const statusColor = s.is_sanctioned ? RED : s.is_pep ? AMBER : TEAL
    const statusText  = s.is_sanctioned ? 'MATCH EN LISTAS DE SANCIONES' : s.is_pep ? 'PERSONA EXPUESTA POLÍTICAMENTE (PEP)' : 'SIN COINCIDENCIAS'
    setFont(doc, statusColor, 9, 'bold')
    doc.text(statusText, 18, y); y += 6

    y = fieldRow(doc, y, 'Listas consultadas', String(s.lists_checked?.length ?? 0))
    y = fieldRow(doc, y, 'Registros revisados', String(s.total_records_screened ?? 0))
    y = fieldRow(doc, y, 'Score máximo',        String(s.max_score ?? 0))
    y += 3

    if (s.matches?.length > 0) {
      setFont(doc, NAVY, 8, 'bold')
      doc.text('Coincidencias encontradas:', 18, y); y += 5
      for (const m of s.matches) {
        y = maybeNewPage(doc, y, 18)
        setFill(doc, [255, 245, 245])
        setDraw(doc, RED)
        doc.setLineWidth(0.3)
        doc.roundedRect(18, y - 1, 176, 13, 1.5, 1.5, 'FD')
        setFont(doc, RED, 7.5, 'bold')
        doc.text(m.matched_name || '—', 22, y + 3.5)
        setFont(doc, GRAY50, 6.5, 'normal')
        doc.text(`${m.list_name || ''}  ·  ${m.type || ''}  ·  ${m.country || ''}  ·  Score: ${m.score ?? '?'}%`, 22, y + 8)
        y += 16
      }
    } else {
      setFont(doc, GRAY70, 7, 'normal')
      doc.text('No se encontraron coincidencias en ninguna lista restringida.', 18, y); y += 7
    }
    y += 3
  }

  // ══ MÓDULO 4 — Digital Identity Intelligence ═════════════════════════════
  if (check.digital_identity) {
    y = maybeNewPage(doc, y, 60)
    y = sectionHeader(doc, y, '04 · Digital Identity Intelligence', '⬡')
    const di = check.digital_identity

    if (di.email) {
      setFont(doc, NAVY, 8, 'bold')
      doc.text('Email', 18, y); y += 5
      y = fieldRow(doc, y, 'Dirección',    di.email.email)
      y = fieldRow(doc, y, 'Tipo',         di.email.is_disposable ? 'DESECHABLE' : di.email.is_corporate_business ? 'Corporativo' : 'Personal',
                             di.email.is_disposable ? RED : TEAL as readonly number[])
      y = fieldRow(doc, y, 'Brechas de datos', String(di.email.breach_count ?? 0),
                             di.email.breach_count > 0 ? RED : TEAL as readonly number[])
      y = fieldRow(doc, y, 'Formato válido', di.email.is_valid ? 'SÍ' : 'NO')
      y += 3
    }

    if (di.phone) {
      y = maybeNewPage(doc, y, 25)
      setFont(doc, NAVY, 8, 'bold')
      doc.text('Teléfono', 18, y); y += 5
      y = fieldRow(doc, y, 'Número',       di.phone.phone)
      y = fieldRow(doc, y, 'Operadora',    di.phone.carrier)
      y = fieldRow(doc, y, 'Tipo de línea',di.phone.line_type)
      y = fieldRow(doc, y, 'Región',       di.phone.region)
      if (di.phone.is_spam_reported) {
        setFont(doc, RED, 7, 'bold')
        doc.text('⚠ Reportado como número spam / fraude', 18, y); y += 5
      }
      y += 3
    }

    if (di.username?.found) {
      y = maybeNewPage(doc, y, 30)
      setFont(doc, NAVY, 8, 'bold')
      doc.text(`Username / Alias: @${di.username.username}`, 18, y); y += 5
      y = fieldRow(doc, y, 'Perfiles encontrados', String(di.username.profile_count ?? 0))
      if (di.username.profiles?.length > 0) {
        const plats = di.username.profiles.map((p: any) => p.platform).join('  ·  ')
        setFont(doc, GRAY50, 7, 'normal')
        const lines = doc.splitTextToSize(plats, 175)
        doc.text(lines, 18, y)
        y += lines.length * 4.5 + 3
      }
    }
    y += 2
  }

  // ══ MÓDULO 5 — Digital Footprint ══════════════════════════════════════════
  if (check.digital_footprint) {
    y = maybeNewPage(doc, y, 35)
    y = sectionHeader(doc, y, '05 · Digital Footprint', '⬡')
    const df = check.digital_footprint
    y = fieldRow(doc, y, 'Presencia digital (0-100)', String(df.presence_score ?? 0))
    y = fieldRow(doc, y, 'Perfiles sociales',         String(df.social_profiles_count ?? 0))
    y = fieldRow(doc, y, 'Perfiles dev',              String(df.developer_profiles_count ?? 0))
    if (df.professional_presence) {
      setFont(doc, TEAL as readonly number[], 7, 'bold')
      doc.text('✓  Presencia profesional verificada', 18, y); y += 5
    }
    y += 4
  }

  // ══ MÓDULO 6 — Relationship Intelligence ══════════════════════════════════
  if (check.relationship_graph) {
    const rg = check.relationship_graph
    y = maybeNewPage(doc, y, 40)
    y = sectionHeader(doc, y, '06 · Relationship Intelligence — Knowledge Graph', '⬡')
    y = fieldRow(doc, y, 'Nodos totales',     String(rg.analysis?.total_nodes ?? 0))
    y = fieldRow(doc, y, 'Conexiones',        String(rg.analysis?.total_edges ?? 0))
    y = fieldRow(doc, y, 'Clusters',          String(rg.analysis?.clusters ?? 0))

    if (rg.analysis?.suspicious_patterns?.length > 0) {
      y += 3
      setFont(doc, RED, 7.5, 'bold')
      doc.text('Patrones sospechosos detectados:', 18, y); y += 5
      for (const p of rg.analysis.suspicious_patterns) {
        y = maybeNewPage(doc, y, 10)
        setFont(doc, RED, 7, 'normal')
        doc.text(`• ${p.description || p}`, 22, y); y += 5
      }
    }

    if (rg.graph?.nodes?.length > 0) {
      y += 3
      setFont(doc, NAVY, 7.5, 'bold')
      doc.text('Entidades relacionadas:', 18, y); y += 5
      const nodeTypes: Record<string, string[]> = {}
      for (const n of rg.graph.nodes) {
        const t = n.data?.type || 'Otro'
        if (!nodeTypes[t]) nodeTypes[t] = []
        nodeTypes[t].push(n.data?.label || '')
      }
      for (const [type, labels] of Object.entries(nodeTypes)) {
        y = maybeNewPage(doc, y, 10)
        setFont(doc, GRAY50, 6.5, 'bold')
        doc.text(`${type}:`, 18, y)
        setFont(doc, NAVY, 6.5, 'normal')
        const line = doc.splitTextToSize(labels.join(' · '), 150)
        doc.text(line, 42, y)
        y += line.length * 4 + 2
      }
    }
    y += 4
  }

  // ══ MÓDULO 7 — Score Breakdown ═══════════════════════════════════════════
  if (check.breakdown) {
    const bd = check.breakdown
    y = maybeNewPage(doc, y, 55)
    y = sectionHeader(doc, y, '07 · Risk Intelligence Engine — Score Breakdown', '⬡')

    const col1x = 18, col2x = 110
    const startY = y

    if (bd.trust_components?.length) {
      setFont(doc, TEAL as readonly number[], 7.5, 'bold')
      doc.text('Factores positivos (Trust)', col1x, y); y += 5
      for (const c of bd.trust_components) {
        y = maybeNewPage(doc, y, 7)
        setFont(doc, NAVY, 7, 'normal')
        doc.text(c.label, col1x, y)
        setFont(doc, TEAL as readonly number[], 7, 'bold')
        doc.text(`+${c.points}`, col1x + 82, y)
        setDraw(doc, GRAY90)
        doc.setLineWidth(0.2)
        doc.line(col1x, y + 1.5, col1x + 90, y + 1.5)
        y += 6
      }
    }

    let y2 = startY
    if (bd.risk_components?.length) {
      // Reset to side-by-side column
      doc.setPage(doc.internal.getCurrentPageInfo().pageNumber)
      setFont(doc, RED, 7.5, 'bold')
      doc.text('Factores de riesgo', col2x, y2); y2 += 5
      for (const c of bd.risk_components) {
        setFont(doc, NAVY, 7, 'normal')
        doc.text(c.label, col2x, y2)
        setFont(doc, RED, 7, 'bold')
        doc.text(`+${c.points}`, col2x + 72, y2)
        setDraw(doc, GRAY90)
        doc.setLineWidth(0.2)
        doc.line(col2x, y2 + 1.5, col2x + 80, y2 + 1.5)
        y2 += 6
      }
    }

    y = Math.max(y, y2) + 4
  }

  // ══ MÓDULO 8 — AI Investigation Report ═══════════════════════════════════
  if (check.ai_report) {
    y = maybeNewPage(doc, y, 40)
    y = sectionHeader(doc, y, '08 · AI Investigation Report  ·  sirax · AI', '⬡')

    const lines = check.ai_report.split('\n')
    for (const raw of lines) {
      const line = raw.trim()
      if (!line) { y += 2.5; continue }

      y = maybeNewPage(doc, y, 10)

      if (line.startsWith('## ')) {
        y += 2
        setFont(doc, NAVY, 9, 'bold')
        doc.text(line.slice(3), 18, y)
        // underline
        setDraw(doc, TEAL)
        doc.setLineWidth(0.5)
        doc.line(18, y + 1, 192, y + 1)
        y += 7
      } else if (line.startsWith('**') && line.endsWith('**')) {
        setFont(doc, NAVY, 8, 'bold')
        doc.text(line.replace(/\*\*/g, ''), 18, y)
        y += 6
      } else if (line.startsWith('- ') || line.startsWith('• ')) {
        setFont(doc, NAVY, 7, 'normal')
        const bullet = doc.splitTextToSize('• ' + line.slice(2), 170)
        for (const bl of bullet) {
          y = maybeNewPage(doc, y, 6)
          doc.text(bl, 22, y)
          y += 5
        }
      } else {
        setFont(doc, NAVY, 7, 'normal')
        const wrapped = doc.splitTextToSize(line, 174)
        for (const wl of wrapped) {
          y = maybeNewPage(doc, y, 6)
          doc.text(wl, 18, y)
          y += 5
        }
      }
    }
    y += 4
  }

  // ══ Fuentes consultadas ═══════════════════════════════════════════════════
  if (check.sources_consulted?.length) {
    y = maybeNewPage(doc, y, 25)
    y = sectionHeader(doc, y, 'Fuentes Consultadas', '⬡')
    const srcText = check.sources_consulted.join('  ·  ')
    setFont(doc, GRAY70, 6.5, 'normal')
    const srcLines = doc.splitTextToSize(srcText, 174)
    doc.text(srcLines, 18, y)
    y += srcLines.length * 4.5 + 4
  }

  // ══ Disclaimer legal ══════════════════════════════════════════════════════
  y = maybeNewPage(doc, y, 25)
  setFill(doc, GRAY90)
  doc.rect(14, y, 182, 0.5, 'F')
  y += 4
  setFont(doc, GRAY50, 6, 'normal')
  const disclaimer = 'Este reporte es generado automáticamente por la plataforma Sirax · Synkdata con fines informativos y de cumplimiento regulatorio. ' +
    'Las fuentes gubernamentales y de sanciones son consultadas en tiempo real; algunos módulos pueden operar en modo simulado cuando las APIs externas no estén disponibles. ' +
    'Este documento no constituye una opinión legal ni un dictamen vinculante. Sirax · © 2026 Synkdata. Todos los derechos reservados.'
  const discLines = doc.splitTextToSize(disclaimer, 182)
  doc.text(discLines, 14, y)
  y += discLines.length * 3.5

  // ══ Footers en todas las páginas ══════════════════════════════════════════
  const totalPages = doc.internal.getNumberOfPages()
  for (let i = 1; i <= totalPages; i++) {
    doc.setPage(i)
    drawFooter(doc, i, totalPages, check.id, genDate)
  }

  // ══ Guardar ═══════════════════════════════════════════════════════════════
  const safeName = (check.subject?.full_name || 'check').replace(/\s+/g, '_').toLowerCase()
  doc.save(`sirax_reporte_${safeName}_${check.id.slice(0, 8)}.pdf`)
}
