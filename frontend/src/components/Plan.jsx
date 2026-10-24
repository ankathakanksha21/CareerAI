import { InfoTip } from '../ui'

// This week's plan: up to five tasks built by rules from what the user has done, most pressing first.
// There are no tick boxes: a task that is done is not built again, so it disappears on the next load.
// skip holds the ids of tasks the page already shows elsewhere; if they were all it had, the card is not drawn,
// since "all clear" would not be true. A goal task shows how far along it is as a chip
export default function Plan({ s, go, skip }) {
  const tasks = skip ? s.plan.filter((t) => !skip.has(t.id)) : s.plan
  if (s.plan.length > 0 && tasks.length === 0) return null
  return (
    <section className="card">
      <div className="row" style={{ gap: 6 }}>
        <h2>Weekly plan</h2>
        <InfoTip label="How the plan is built">Built from your applications, goals and profile. A task disappears once it is done.</InfoTip>
      </div>
      {s.plan.length === 0 && <p className="muted" style={{ marginTop: 8 }}>All clear: goals met, nothing waiting on you.</p>}
      {tasks.length > 0 && (
        <div className="list" style={{ marginTop: 12 }}>
          {tasks.map((t) => (
            <div key={t.id} className="task plan-task">
              <div>
                <div className="t">{t.text}</div>
                {t.why && <div className="why">{t.why}</div>}
                {t.count && <span className="chip muted plan-count">{t.count}</span>}
              </div>
              <button className="btn ghost small" onClick={() => go(t.page, t.tab)}>{t.label}</button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
