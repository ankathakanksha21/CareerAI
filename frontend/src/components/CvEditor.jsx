import { useRef, useState } from 'react'
import { patch } from '../api'
import CvSheet from './CvSheet'
import CvSide from './CvSide'
import { factsChanged } from '../cv'

// One CV on screen. Every change is shown at once and saved in the background, one request at a time
// and in order; there is no Save button. A version already sent with an application is never changed:
// the server answers with a new version, and the page carries on with that one.
export default function CvEditor({ version, s, go, notify, refresh, onSaved }) {
  const [doc, setDoc] = useState(version.content)
  const [meta, setMeta] = useState(version)     // the version as last saved: its id, name, page count
  const [status, setStatus] = useState('saved') // 'saving', 'saved', or the error that stopped a save
  const [notice, setNotice] = useState(null)
  const latest = useRef(version.content)        // the CV as it now reads, ahead of the next render
  const queue = useRef({ waiting: null, busy: false, id: version.id })

  const flush = async () => {
    const q = queue.current
    if (q.busy) return
    q.busy = true
    while (q.waiting) {
      const body = q.waiting
      q.waiting = null
      setStatus('saving')
      try {
        const saved = await patch(`/api/cv-versions/${q.id}`, body)
        q.id = saved.id
        setMeta(saved)
        if (!q.waiting) { // nothing newer is waiting: take the saved copy, with its facts and keyword groups as the server has them
          latest.current = saved.content
          setDoc(saved.content)
        }
        if (saved.replaced) setNotice(`Sent CVs never change, so your edits are saved as a new version, ${saved.name}.`)
        onSaved(saved)
        setStatus('saved')
      } catch (e) {
        q.waiting = { ...body, ...(q.waiting || {}) } // still to save, under anything newer
        setStatus(e)
        break
      }
    }
    q.busy = false
  }
  const save = (body) => {
    queue.current.waiting = { ...(queue.current.waiting || {}), ...body }
    flush()
  }
  // Change the CV: `edit` alters a copy, which is shown straight away and then saved
  const change = (edit) => {
    const next = structuredClone(latest.current)
    edit(next)
    latest.current = next
    setDoc(next)
    save({ content: next })
  }

  return (
    <div className="grid split">
      <div className="stack">
        {notice && <p className="card tight tint small" role="status">{notice}</p>}
        {factsChanged(doc, s) && (
          <div className="card tight row" role="status">
            <span className="small" style={{ flex: 1, minWidth: 220 }}>Profile changed since this CV was built: a job, course or contact detail.</span>
            <button type="button" className="btn ghost small" disabled={status === 'saving'} onClick={() => save({ content: latest.current, refresh_facts: true })}>Update from profile</button>
          </div>
        )}
        <CvSheet doc={doc} change={change} s={s} go={go} />
      </div>
      <CvSide doc={doc} meta={meta} status={status} retry={flush} change={change} save={save} s={s} notify={notify} refresh={refresh} />
    </div>
  )
}
