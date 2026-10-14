import { useLayoutEffect, useRef, useState } from 'react'

// Text the user can change where it stands. Click it (or press Enter on it) to edit; Enter or leaving
// the field keeps the change, Escape drops it. `onChange` is only called with text that really changed,
// and never with nothing unless `allowEmpty` is set.
export default function EditableText({ value, onChange, label, placeholder = '', max, allowEmpty = false, className = '' }) {
  const [draft, setDraft] = useState(null) // null: not being edited
  const box = useRef(null)
  const closed = useRef(true) // the edit is over: a field that loses focus as it is taken away must not save twice

  useLayoutEffect(() => {
    if (draft === null || !box.current) return
    box.current.style.height = 'auto' // grow with the text, so the whole of it stays in view
    box.current.style.height = `${box.current.scrollHeight}px`
  }, [draft])

  if (draft === null) {
    const open = () => { closed.current = false; setDraft(value || '') }
    return (
      <span role="button" tabIndex={0} className={`editable ${value ? '' : 'blank'} ${className}`} aria-label={`Edit ${label}`} title="Click to edit"
        onClick={open} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open() } }}>
        {value || placeholder}
      </span>
    )
  }

  const close = (keep) => {
    if (closed.current) return
    closed.current = true
    // read from the field itself: what was typed last may not have reached this component's state yet
    const next = (box.current ? box.current.value : draft).replace(/\s+/g, ' ').trim()
    setDraft(null)
    if (keep && next !== (value || '') && (next || allowEmpty)) onChange(next)
  }
  const onKey = (e) => {
    if (e.key === 'Escape') close(false)
    if (e.key === 'Enter') { e.preventDefault(); close(true) }
  }
  return (
    <textarea ref={box} autoFocus rows={1} className={`editing ${className}`} value={draft} maxLength={max} aria-label={label} placeholder={placeholder}
      onChange={(e) => setDraft(e.target.value)} onBlur={() => close(true)} onKeyDown={onKey} />
  )
}
