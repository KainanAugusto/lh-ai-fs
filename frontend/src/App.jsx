import { useMemo, useState } from 'react'
import './App.css'

const API_URL = 'http://localhost:8002/analyze'

// Agents shown during the (single, ~30s) analysis call. We can't stream real
// per-stage progress without an SSE backend, so this is honest "what's running"
// context rather than a faked progress bar.
const AGENTS = [
  ['Citation & Fact Extractor', 'pulls citations and factual claims from the motion'],
  ['Citation Verifier', 'checks whether each authority supports its proposition'],
  ['Consistency Checker', 'cross-checks the motion against the record'],
  ['Confidence Scorer', 'ranks every flag by how certain we are'],
  ['Judicial Memo', 'synthesizes the top findings for the court'],
]

const CONF_ORDER = { high: 0, medium: 1, low: 2 }

// Turn the backend's raw error strings into a short, human-readable line.
function friendlyError(errors) {
  const joined = (errors || []).join(' ')
  if (/rate.?limit|\b429\b|rate_limit_exceeded|tokens per day|\bTPD\b/i.test(joined)) {
    return 'The language model hit its rate limit. Wait a moment and re-run — or switch MODEL in .env.'
  }
  const first = (errors || [])[0] || 'The pipeline could not complete.'
  return first.length > 200 ? first.slice(0, 200) + '…' : first
}

function Badge({ text, kind }) {
  if (!text) return null
  return <span className={`badge ${kind}`}>{text}</span>
}

function confBar(score, level) {
  const pct = Math.round((Number(score) || 0) * 100)
  return (
    <div className={`confbar ${level}`} title={`Confidence ${pct}%`} aria-label={`Confidence ${pct}%`}>
      <span style={{ width: `${pct}%` }} />
    </div>
  )
}

function Expandable({ children }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button className="expander" onClick={() => setOpen((o) => !o)}>
        {open ? 'Hide detail' : 'Show detail'}
      </button>
      {open && <div>{children}</div>}
    </>
  )
}

function ToastStack({ toasts, onDismiss }) {
  if (!toasts.length) return null
  return (
    <div className="toast-wrap" role="region" aria-label="Notifications">
      {toasts.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`} role="alert">
          <span className="t-icon">{t.kind === 'error' ? '⛔' : t.kind === 'warn' ? '⚠️' : 'ℹ️'}</span>
          <div className="t-body">
            <div className="t-title">{t.title}</div>
            <div>{t.message}</div>
          </div>
          <button className="t-close" onClick={() => onDismiss(t.id)} aria-label="Dismiss">×</button>
        </div>
      ))}
    </div>
  )
}

export default function App() {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [confFilter, setConfFilter] = useState('all') // all | high | medium | low
  const [showRaw, setShowRaw] = useState(false)
  const [toasts, setToasts] = useState([])

  const pushToast = (t) => {
    const id = Date.now() + Math.random()
    setToasts((ts) => [...ts, { id, ...t }])
    setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), t.duration ?? 7000)
  }
  const dismissToast = (id) => setToasts((ts) => ts.filter((x) => x.id !== id))

  const runAnalysis = async () => {
    setLoading(true); setError(null); setReport(null)
    try {
      const res = await fetch(API_URL, { method: 'POST' })
      if (!res.ok) throw new Error(`Server responded with ${res.status}`)
      const data = await res.json()
      const rep = data.report
      setReport(rep)
      if (rep?.status === 'failed') {
        pushToast({ kind: 'error', title: 'Analysis failed', message: friendlyError(rep.errors) })
      } else if (rep?.status === 'partial') {
        pushToast({ kind: 'warn', title: 'Partial analysis', message: 'Some agents failed — the report may be incomplete.' })
      }
    } catch (err) {
      setError(err.message)
      pushToast({ kind: 'error', title: 'Could not reach the server', message: err.message })
    } finally {
      setLoading(false)
    }
  }

  const downloadJson = () => {
    const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url; a.download = 'bs-detector-report.json'; a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="app">
      <ToastStack toasts={toasts} onDismiss={dismissToast} />

      <header className="app-header">
        <div>
          <h1>BS Detector</h1>
          <p className="subtitle">
            Multi-agent legal brief verification — every flag is grounded in a verbatim quote from the source documents.
          </p>
        </div>
        <div className="header-actions">
          {report && (
            <button className="btn btn-ghost" onClick={downloadJson} title="Download the full report as JSON">
              Download JSON
            </button>
          )}
          <button className="btn btn-primary" onClick={runAnalysis} disabled={loading}>
            {loading ? 'Analyzing…' : report ? 'Re-run analysis' : 'Run analysis'}
          </button>
        </div>
      </header>

      {error && !report && (
        <div className="error-banner"><strong>Could not reach the server:</strong> {error}. Is the backend running on :8002?</div>
      )}

      {loading && <LoadingView />}

      {!loading && !error && report === null && (
        <p className="empty-state">Click "Run analysis" to verify the case file (Rivera v. Harmon Construction Group).</p>
      )}

      {report && !loading && (
        report.status === 'failed'
          ? <FailedView report={report} showRaw={showRaw} setShowRaw={setShowRaw} />
          : <Report report={report} confFilter={confFilter} setConfFilter={setConfFilter} showRaw={showRaw} setShowRaw={setShowRaw} />
      )}
    </div>
  )
}

function LoadingView() {
  return (
    <section className="loading" aria-live="polite">
      <h2>Running the multi-agent pipeline…</h2>
      <ol className="agent-stages">
        {AGENTS.map(([name, role]) => (
          <li className="agent-stage" key={name}>
            <span className="dot" />
            <span>
              <span className="name">{name}</span>{' '}
              <span className="role">— {role}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="loading-note">Five agents run end-to-end; this usually takes ~30 seconds.</p>
    </section>
  )
}

// Rendered when a required stage failed: NO analysis was produced, so we must
// never imply a clean result. This is the opposite of "no issues found".
function FailedView({ report, showRaw, setShowRaw }) {
  return (
    <div>
      <div className="verdict level-failed">
        <span className="icon">⛔</span>
        <span>
          <div className="headline">{report.case_name}</div>
          <div className="sub">Analysis could not be completed — {friendlyError(report.errors)}</div>
        </span>
      </div>
      <p className="section-hint" style={{ marginTop: '16px' }}>
        No verification was produced. This is <strong>not</strong> a clean result — the pipeline could not run. Please re-run the analysis.
      </p>
      <RawJson report={report} showRaw={showRaw} setShowRaw={setShowRaw} />
    </div>
  )
}

function Report({ report, confFilter, setConfFilter, showRaw, setShowRaw }) {
  const stats = report.stats || {}
  const scored = report.scored_findings || []
  const consistency = report.consistency_findings || []
  const citations = report.citation_findings || []
  const flaggedCitations = citations.filter((c) => c.is_problem)

  const sortedScored = useMemo(() => {
    return [...scored].sort(
      (a, b) =>
        (CONF_ORDER[a.confidence] ?? 9) - (CONF_ORDER[b.confidence] ?? 9) ||
        (b.confidence_score || 0) - (a.confidence_score || 0),
    )
  }, [scored])

  const visibleScored = sortedScored.filter((f) => confFilter === 'all' || f.confidence === confFilter)
  const highCount = scored.filter((f) => f.confidence === 'high').length

  let verdict
  if (scored.length === 0) {
    // A "clean" verdict is only trustworthy when the pipeline actually ran fully.
    verdict = report.status === 'completed'
      ? { level: 'clean', icon: '✓', headline: 'No issues flagged', sub: 'The pipeline ran fully and did not surface any integrity problems.' }
      : { level: 'medium', icon: '⚠️', headline: 'Analysis incomplete', sub: 'Some agents failed, so no findings could be produced. Re-run before trusting this.' }
  } else if (highCount > 0) {
    verdict = { level: 'high', icon: '⚠️', headline: `${scored.length} issue${scored.length > 1 ? 's' : ''} flagged — ${highCount} high-confidence`, sub: 'High-confidence flags are backed by verbatim document evidence.' }
  } else {
    verdict = { level: 'medium', icon: '⚠️', headline: `${scored.length} issue${scored.length > 1 ? 's' : ''} flagged`, sub: 'Review each finding against its cited source.' }
  }

  return (
    <div>
      <div className={`verdict level-${verdict.level}`}>
        <span className="icon">{verdict.icon}</span>
        <span>
          <div className="headline">{report.case_name}</div>
          <div className="sub">{verdict.headline}. {verdict.sub}</div>
        </span>
      </div>

      <div className="stats">
        <Stat value={stats.citations_extracted} label="citations" />
        <Stat value={stats.factual_claims_extracted} label="facts" />
        <Stat value={stats.citation_problems} label="citation flags" />
        <Stat value={stats.consistency_issues} label="inconsistencies" />
        <Stat value={stats.high_confidence_flags} label="high-conf flags" />
      </div>

      {report.status === 'partial' && report.errors?.length > 0 && (
        <div className="warn-banner">
          <strong>Partial run (graceful degradation):</strong> {report.errors.join(' · ')}
        </div>
      )}

      {report.judicial_memo && (
        <div className="memo">
          <h2>⚖️ Judicial Memo</h2>
          <p>{report.judicial_memo}</p>
        </div>
      )}

      {/* Ranked findings */}
      <section className="section">
        <h2>Top Findings <span className="count">{visibleScored.length} of {scored.length}</span></h2>
        <p className="section-hint">Ranked by confidence. Document-grounded findings outrank citation verdicts that rely on legal knowledge alone.</p>
        <div className="filters">
          <div className="group" role="group" aria-label="Filter by confidence">
            {['all', 'high', 'medium', 'low'].map((c) => (
              <button key={c} className={confFilter === c ? 'active' : ''} onClick={() => setConfFilter(c)}>
                {c === 'all' ? 'All' : c}
              </button>
            ))}
          </div>
        </div>
        {scored.length === 0 && <p className="empty-state">No findings were produced.</p>}
        {scored.length > 0 && visibleScored.length === 0 && <p className="empty-state">No findings at this confidence level.</p>}
        {visibleScored.map((f, i) => (
          <article className="finding" key={i}>
            <div className="finding-head">
              <Badge text={`${f.severity} severity`} kind={f.severity} />
              <Badge text={f.finding_type} kind="muted" />
              <span className="meta">{Math.round((f.confidence_score || 0) * 100)}% confidence</span>
            </div>
            <div className="summary">{f.summary}</div>
            {confBar(f.confidence_score, f.confidence)}
            {f.reasoning && <div className="reasoning">{f.reasoning}</div>}
            {f.source && <div className="source">Source: {f.source}</div>}
          </article>
        ))}
      </section>

      {/* Cross-document consistency */}
      <section className="section">
        <h2>Cross-Document Consistency <span className="count">{consistency.length}</span></h2>
        <p className="section-hint">Factual assertions in the motion that the supporting record contradicts.</p>
        {consistency.map((f, i) => (
          <article className="finding" key={i}>
            <div className="finding-head">
              <Badge text={`${f.severity} severity`} kind={f.severity} />
              <span className="meta">inconsistency</span>
            </div>
            <div className="contrast">
              <div className="contrast-row contrast-wrong">
                <div className="clabel">✗ What the motion claims</div>
                <div className="ctext">{f.msj_claim}</div>
              </div>
              <div className="contrast-row contrast-right">
                <div className="clabel">✓ What the record actually says · <span className="doc-tag">{f.contradicting_document}</span></div>
                <div className="ctext cverbatim">“{f.contradicting_quote}”</div>
              </div>
            </div>
            {f.reasoning && <div className="reasoning">{f.reasoning}</div>}
          </article>
        ))}
      </section>

      {/* Citation integrity */}
      <section className="section">
        <h2>Citation Integrity <span className="count">{citations.length}</span></h2>
        <p className="section-hint">{flaggedCitations.length} of {citations.length} citations flagged. Verified-OK citations are kept for transparency.</p>
        {citations.map((f, i) => (
          <article className={`finding ${f.is_problem ? '' : 'dim'}`} key={i}>
            <div className="finding-head">
              <Badge text={f.verdict} kind={verdictKind(f.verdict)} />
              {f.is_problem && <Badge text="flagged" kind="high" />}
              <span className="meta">quote: {f.quote_accuracy}</span>
            </div>
            <div>
              <span className="case-name">{f.case_name}</span>{' '}
              <span className="case-cite">{f.citation}</span>
            </div>
            {f.is_problem ? (
              <div className="contrast">
                <div className="contrast-row contrast-wrong">
                  <div className="clabel">✗ What the brief claims it supports</div>
                  <div className="ctext">{f.proposition}</div>
                  {f.evidence_quote && <div className="ctext cverbatim">“{f.evidence_quote}”</div>}
                </div>
                <div className={`contrast-row ${f.verdict === 'unverifiable' ? 'contrast-unverif' : 'contrast-right'}`}>
                  <div className="clabel">
                    {f.verdict === 'unverifiable' ? '⚠ Could not verify' : '✓ What the authority actually holds'}
                  </div>
                  <div className="ctext">{f.reasoning}</div>
                </div>
              </div>
            ) : (
              <>
                <div className="proposition">{f.proposition}</div>
                <Expandable>
                  {f.reasoning && <div className="reasoning">{f.reasoning}</div>}
                  {f.evidence_quote && <div className="quote">“{f.evidence_quote}”</div>}
                </Expandable>
              </>
            )}
          </article>
        ))}
      </section>

      <RawJson report={report} showRaw={showRaw} setShowRaw={setShowRaw} />
    </div>
  )
}

function RawJson({ report, showRaw, setShowRaw }) {
  return (
    <section className="raw">
      <button className="btn btn-ghost btn-sm" onClick={() => setShowRaw((r) => !r)}>
        {showRaw ? 'Hide' : 'Show'} raw JSON
      </button>
      {showRaw && <pre>{JSON.stringify(report, null, 2)}</pre>}
    </section>
  )
}

function Stat({ value, label }) {
  return (
    <div className="stat">
      <div className="value">{value ?? '—'}</div>
      <div className="label">{label}</div>
    </div>
  )
}

function verdictKind(verdict) {
  if (verdict === 'supports') return 'good'
  if (verdict === 'contradicts') return 'high'
  if (verdict === 'overstated') return 'medium'
  return 'muted' // unverifiable
}
