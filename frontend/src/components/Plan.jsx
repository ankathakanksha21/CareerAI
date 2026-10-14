// This week's plan: up to five tasks built by rules from what the user has done, most pressing first.
// There are no tick boxes: a task that is done is not built again, so it disappears on the next load.
export default function Plan({ s, go }) {
  return (
    <section className="card">
      <h2>Weekly plan</h2>
      <p className="sub">Built from your applications, goals and profile. A task disappears once it is done.</p>
      {s.plan.length === 0 && <p className="muted">Nothing left on this week's plan. Your goals are met and nothing is waiting on you.</p>}
      <div className="list">
        {s.plan.map((t) => (
          <div key={t.id} className="task plan-task">
            <div><div className="t">{t.text}</div><div className="why">{t.why}</div></div>
            <button className="btn ghost small" onClick={() => go(t.page, t.tab)}>{t.label}</button>
          </div>
        ))}
      </div>
    </section>
  )
}
