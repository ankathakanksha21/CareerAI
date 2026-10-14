import { useEffect } from 'react'
import { Award } from 'lucide-react'
import { post } from '../api'

// Milestones just reached, each shown once: they are marked seen as soon as the banner appears
export default function Milestones({ s }) {
  const items = s.habits.new_milestones
  const ids = items.map((m) => m.id).join(',')
  useEffect(() => {
    if (ids) post('/api/milestones/seen', { ids: ids.split(',') }).catch(() => {}) // if this fails the banner simply shows again
  }, [ids])
  if (!items.length) return null
  return (
    <section className="milestone" role="status">
      <Award size={22} />
      <div>{items.map((m) => <p key={m.id}>{m.text}</p>)}</div>
    </section>
  )
}
