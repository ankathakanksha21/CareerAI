// A CV made before full CVs existed: a profile paragraph, a few bullets and a cover letter. It has
// no education, dates or contact details, so it can be read and rebuilt but not edited or downloaded.
export default function OldCv({ version, name, canRebuild, rebuilding, onRebuild }) {
  const d = version.content
  return (
    <div className="grid split">
      <section className="cv-sheet">
        <div className="row"><h2 style={{ fontSize: 20 }}>{name}</h2><span className="spacer" /><span className="chip">{version.name}</span></div>
        <h3>Profile</h3>
        <p>{d.profile}</p>
        <h3>Experience, selected for this role</h3>
        <ul>{(d.bullets || []).map((b, i) => <li key={i}>{b.text}</li>)}</ul>
        {(d.keywords || []).length > 0 && <><h3>Keywords covered</h3><div className="row">{d.keywords.map((k) => <span key={k} className="chip good">{k}</span>)}</div></>}
      </section>
      <div className="stack">
        <section className="card">
          <h3>An earlier, shorter CV</h3>
          <p className="small" style={{ margin: '8px 0 12px' }}>This version was made before full CVs. It has no education, dates or contact details, so it cannot be edited or downloaded.</p>
          {canRebuild
            ? <button type="button" className="btn" disabled={rebuilding} onClick={onRebuild}>{rebuilding ? 'Building, about 20 seconds' : 'Rebuild as a full CV'}</button>
            : <p className="small muted">The job it was written for has been removed. Add the job again, or build a base CV.</p>}
        </section>
        {d.cover_letter && (
          <section className="card letter">
            <h2>Cover letter</h2>
            <p className="part">Why them</p><p>{d.cover_letter.why_them}</p>
            <p className="part">Why you</p><p>{d.cover_letter.why_you}</p>
            <p className="part">What you will deliver</p><p>{d.cover_letter.what_you_deliver}</p>
          </section>
        )}
      </div>
    </div>
  )
}
