import { useState } from 'react'
import { ChevronDown, ChevronUp, EyeOff, GripVertical } from 'lucide-react'
import EditableText from './EditableText'
import { SECTION_TITLE, SKILL_LABEL, abroad, addAchievement, contactLine, cvPeriod, joined, moved, shownAt, unused } from '../cv'

let dragging = null // the item being dragged: which list it belongs to and its place in it

// Reordering by drag. The grip is what is picked up; any other item of the same list is where it can be dropped
const drag = (group, at, onMove) => ({
  grip: {
    draggable: true,
    onDragStart: (e) => {
      dragging = { group, at }
      e.dataTransfer.effectAllowed = 'move'
      e.dataTransfer.setData('text/plain', '')
      const row = e.currentTarget.closest('.cv-drop')
      if (row) e.dataTransfer.setDragImage(row, 12, 12)
    },
    onDragEnd: () => { dragging = null },
  },
  drop: {
    onDragOver: (e) => { if (dragging?.group === group) e.preventDefault() },
    onDrop: (e) => {
      if (dragging?.group !== group) return
      e.preventDefault()
      e.stopPropagation()
      if (dragging.at !== at) onMove(dragging.at, at)
      dragging = null
    },
  },
})

// Move up, move down and hide for one item. Up and down step over anything hidden
function Acts({ what, list, at, onMove, onHide, grip }) {
  const shown = shownAt(list)
  const place = shown.indexOf(at)
  return (
    <span className="cv-acts">
      {grip && <span className="grip" title="Drag to reorder" {...grip}><GripVertical size={14} aria-hidden /></span>}
      <button type="button" className="icon-btn calm" aria-label={`Move ${what} up`} disabled={place <= 0} onClick={() => onMove(at, shown[place - 1])}><ChevronUp size={15} /></button>
      <button type="button" className="icon-btn calm" aria-label={`Move ${what} down`} disabled={place === shown.length - 1} onClick={() => onMove(at, shown[place + 1])}><ChevronDown size={15} /></button>
      {onHide && <button type="button" className="icon-btn calm" aria-label={`Hide ${what}`} title="Hide: it stays here but is not printed" onClick={onHide}><EyeOff size={14} /></button>}
    </span>
  )
}

function Hidden({ list, label, onRestore }) {
  const hidden = list.map((item, at) => ({ item, at })).filter((x) => x.item.hidden)
  if (!hidden.length) return null
  return (
    <div className="cv-hidden">
      <span className="small muted">Hidden, not printed</span>
      {hidden.map(({ item, at }) => (
        <div key={at} className="small"><span className="muted">{label(item)}</span> <button type="button" className="linkish" onClick={() => onRestore(at)}>Restore</button></div>
      ))}
    </div>
  )
}

// The bullets of one job or project. `edit(fn)` gives fn this entry inside a copy of the CV
function Bullets({ entry, group, edit }) {
  const list = entry.bullets
  const reorder = (from, to) => edit((e) => { e.bullets = moved(e.bullets, from, to) })
  return (
    <>
      <ul className="cv-bullets">
        {shownAt(list).map((at) => {
          const d = drag(group, at, reorder)
          return (
            <li key={at} className="cv-drop" {...d.drop}>
              <div className="cv-row">
                <EditableText value={list[at].text} max={600} label="bullet" onChange={(v) => edit((e) => { e.bullets[at].text = v })} />
                <Acts what="bullet" list={list} at={at} onMove={reorder} grip={d.grip} onHide={() => edit((e) => { e.bullets[at].hidden = true })} />
              </div>
            </li>
          )
        })}
      </ul>
      <Hidden list={list} label={(b) => b.text} onRestore={(at) => edit((e) => { e.bullets[at].hidden = false })} />
    </>
  )
}

// One section's entries (courses, jobs or projects): each can be moved, hidden and restored
function Entries({ doc, change, section, what, idKey, name, empty, children }) {
  const list = doc[section]
  const reorder = (from, to) => change((d) => { d[section] = moved(d[section], from, to) })
  const edit = (at) => (fn) => change((d) => fn(d[section][at]))
  if (!list.length) return <p className="small muted cv-note">{empty}</p>
  return (
    <>
      {shownAt(list).map((at) => {
        const d = drag(section, at, reorder)
        return (
          <div key={list[at][idKey]} className="cv-entry cv-drop" {...d.drop}>
            {children(list[at], edit(at), <Acts what={what} list={list} at={at} onMove={reorder} grip={d.grip} onHide={() => edit(at)((e) => { e.hidden = true })} />)}
          </div>
        )
      })}
      <Hidden list={list} label={name} onRestore={(at) => edit(at)((e) => { e.hidden = false })} />
    </>
  )
}

function Skills({ doc, change }) {
  const any = Object.keys(SKILL_LABEL).some((g) => doc.skills[g].length)
  return (
    <>
      {Object.entries(SKILL_LABEL).map(([group, label]) => (
        <div key={group} className="cv-row">
          <span>{label}:</span>
          <EditableText value={doc.skills[group].join(', ')} allowEmpty max={1200} label={`${label.toLowerCase()} skills`} placeholder="none (not printed). Click to add, separated by commas"
            onChange={(v) => change((d) => { d.skills[group] = v.split(',').map((x) => x.trim()).filter(Boolean) })} />
        </div>
      ))}
      {!any && <p className="small muted cv-note">No skills are listed, so this section is not printed.</p>}
    </>
  )
}

function Additional({ doc, change }) {
  const lines = doc.additional.lines
  const visa = doc.right_to_work
  const reorder = (from, to) => change((d) => { d.additional.lines = moved(d.additional.lines, from, to) })
  return (
    <>
      {shownAt(lines).map((at) => {
        const d = drag('additional', at, reorder)
        return (
          <div key={at} className="cv-row cv-drop" {...d.drop}>
            <EditableText value={lines[at].text} max={300} label="line" onChange={(v) => change((x) => { x.additional.lines[at].text = v })} />
            <Acts what="line" list={lines} at={at} onMove={reorder} grip={d.grip} onHide={() => change((x) => { x.additional.lines[at].hidden = true })} />
          </div>
        )
      })}
      {visa.shown && (
        <div className="cv-row">
          <EditableText value={visa.text} allowEmpty max={300} label="right-to-work line" placeholder="Type your right-to-work line" onChange={(v) => change((d) => { d.right_to_work.text = v })} />
        </div>
      )}
      <Hidden list={lines} label={(l) => l.text} onRestore={(at) => change((d) => { d.additional.lines[at].hidden = false })} />
      <div className="cv-note" style={{ marginTop: 8, display: 'grid', gap: 6 }}>
        {lines.length < 12 && (
          <EditableText key={lines.length} value="" max={300} label="a new line" placeholder="Add a line: a certification, an award, volunteering"
            onChange={(v) => change((d) => { d.additional.lines.push({ text: v, hidden: false }) })} />
        )}
        <label className="check"><input type="checkbox" checked={visa.shown} onChange={(e) => change((d) => { d.right_to_work.shown = e.target.checked })} />Show a right-to-work line</label>
        {visa.shown && <p className="small muted">It states your current visa and the date it ends, nothing more. Check it against your own visa before you send it. This is not immigration advice.</p>}
      </div>
    </>
  )
}

function AddFromProfile({ doc, change, achievements }) {
  const [open, setOpen] = useState(false)
  const spare = unused(doc, achievements)
  if (!spare.length) return null
  return (
    <div className="cv-add">
      <button type="button" className="btn ghost small" onClick={() => setOpen(!open)}>{open ? 'Close' : `Add a bullet from my profile (${spare.length} not used)`}</button>
      {open && (
        <div className="list" style={{ marginTop: 12 }}>
          {spare.map((a) => (
            <div key={a.id} className="entry">
              <div className="who"><div className="small strong">{a.title}</div><div className="small muted">{a.uk_version}</div></div>
              <div className="acts"><button type="button" className="linkish small" onClick={() => change((d) => addAchievement(d, a))}>Add</button></div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// The CV in the order and typeface it prints in. Wording is edited where it stands; employers, dates,
// courses and contact details are the user's records and are changed on the Profile page.
export default function CvSheet({ doc, change, s, go }) {
  const order = doc.section_order
  const sections = {
    education: (
      <Entries doc={doc} change={change} section="education" what="course" idKey="education_id" name={(e) => joined(e.institution, e.qualification)}
        empty="No courses on your profile, so this section is not printed.">
        {(e, edit, acts) => (
          <>
            <div className="cv-row"><div className="cv-line"><span className="cv-strong">{joined(e.institution, abroad(e.country) ? e.country : '')}</span><span className="cv-dates">{cvPeriod(e, true)}</span></div>{acts}</div>
            {(e.qualification || e.subject) && <div className="cv-strong">{[e.qualification, e.subject].filter(Boolean).join(' ')}</div>}
            {e.grade && <div>Grade: {e.grade}</div>}
            <div><EditableText value={e.note} allowEmpty max={300} label="modules or dissertation" placeholder="Add relevant modules or your dissertation (optional)" onChange={(v) => edit((x) => { x.note = v })} /></div>
          </>
        )}
      </Entries>
    ),
    work: (
      <Entries doc={doc} change={change} section="work" what="job" idKey="work_history_id" name={(e) => joined(e.job_title, e.employer)}
        empty="No jobs on your profile, so this section is not printed.">
        {(e, edit, acts) => (
          <>
            <div className="cv-row"><div className="cv-line"><span className="cv-strong">{joined(e.employer, e.location, e.country)}</span><span className="cv-dates">{cvPeriod(e)}</span></div>{acts}</div>
            {e.job_title && <div className="cv-strong">{e.job_title}</div>}
            {e.employer_context && <div>{e.employer_context}</div>}
            <Bullets entry={e} group={`work:${e.work_history_id}`} edit={edit} />
          </>
        )}
      </Entries>
    ),
    projects: (
      <Entries doc={doc} change={change} section="projects" what="project" idKey="achievement_id" name={(e) => e.title}
        empty="No projects on this CV, so this section is not printed.">
        {(e, edit, acts) => (
          <>
            <div className="cv-row">
              <div className="cv-line">
                <span className="cv-strong">
                  <EditableText value={e.title} max={160} label="project title" onChange={(v) => edit((x) => { x.title = v })} />
                  {e.where && `, ${e.where}`}{e.link && ` (${e.link})`}
                </span>
              </div>
              {acts}
            </div>
            <Bullets entry={e} group={`project:${e.achievement_id}`} edit={edit} />
          </>
        )}
      </Entries>
    ),
    skills: <Skills doc={doc} change={change} />,
    additional: <Additional doc={doc} change={change} />,
  }
  return (
    <section className="cvdoc" aria-label="Your CV as it will print">
      <div className="cv-name">{doc.contact.name}</div>
      <div>{contactLine(doc.contact)}</div>
      <p className="small muted cv-note" style={{ marginTop: 4 }}>
        Your contact details, employers, dates and courses come from your profile. <button type="button" className="linkish" onClick={() => go('profile')}>Edit them on Profile</button>
      </p>
      <div className="cv-row cv-h-row"><h3 className="cv-h">Personal profile</h3></div>
      <div className="cv-row">
        <EditableText value={doc.profile} allowEmpty max={1500} label="personal profile" placeholder="Add three or four lines on who you are and what you are looking for"
          onChange={(v) => change((d) => { d.profile = v })} />
      </div>
      {order.map((key, at) => (
        <div key={key}>
          <div className="cv-row cv-h-row">
            <h3 className="cv-h">{SECTION_TITLE[key]}</h3>
            <Acts what={`the ${SECTION_TITLE[key]} section`} list={order.map(() => ({}))} at={at} onMove={(from, to) => change((d) => { d.section_order = moved(d.section_order, from, to) })} />
          </div>
          {sections[key]}
        </div>
      ))}
      <AddFromProfile doc={doc} change={change} achievements={s.achievements} />
    </section>
  )
}
