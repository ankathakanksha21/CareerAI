import { fmtDate, money } from '../ui'

const FULL_DATE = { day: 'numeric', month: 'short', year: 'numeric' }
const Link = ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>

// What the gov.uk register says about an advert's employer. Facts only: the user checks before applying
export function SponsorLine({ status, name, links, postedBy }) {
  const register = links && <Link href={links.register}>Check the register</Link>
  if (postedBy === 'training') return <p className="small muted">Advertised by a training company or a recruiter selling a programme. This is a course, not a job.</p>
  if (status === 'listed') return <p className="small">On the sponsor register as <span className="strong">{name}</span> (Skilled Worker).</p>
  if (status === 'possible') return <p className="small">Possible match on the register: <span className="strong">{name}</span>. Check before applying. {register}</p>
  if (status === 'agency') return <p className="small muted">Advertised by a recruiter or job board; the employer is not named.</p>
  return <p className="small muted">Not found on the register. Employers sometimes appear under a different registered name. {register}</p>
}

// A stated annual salary beside the published Skilled Worker figures. The figures come from the server, never from this file
export function SalaryFacts({ visa, advertised }) {
  const l = visa.links
  return (
    <div className="facts small">
      {advertised && <p><span className="strong">Advertised salary:</span> {advertised.min === advertised.max ? money(advertised.min) : `${money(advertised.min)} to ${money(advertised.max)}`}</p>}
      <p>
        <span className="strong">Skilled Worker visa:</span> usually at least {money(visa.standard_salary)} a year.
        At least {money(visa.lower_salary)} if you are on a Student or Graduate visa, or under 26.
      </p>
      <p>The <Link href={l.going_rates}>going rate</Link> for the occupation can be higher, and the occupation must be on the <Link href={l.eligible_occupations}>eligible list</Link>.</p>
      <p className="muted">Source: <Link href={l.salary}>gov.uk</Link> and <Link href={l.paid_less}>when you can be paid less</Link>, checked {fmtDate(visa.checked_on, FULL_DATE)}. Not immigration advice.</p>
    </div>
  )
}

// One line about the signed-in user's own visa, from the type and end date in their profile
export function VisaLine({ profile, links }) {
  if (profile.visa_type === 'graduate') {
    return (
      <p className="small">
        On a Graduate visa you can work in most jobs without a sponsor until your visa ends on {fmtDate(profile.visa_end_date, FULL_DATE)}.
        Sponsorship matters if you want to stay after that. <Link href={links.graduate_visa}>Graduate visa on gov.uk</Link>
      </p>
    )
  }
  return (
    <p className="small">
      On a Student visa, how much you can work depends on your course and whether it is term time.
      Check your conditions on gov.uk. <Link href={links.student_visa}>Student visa on gov.uk</Link>
    </p>
  )
}

// Where the sponsorship and salary facts come from, and how current they are
export function SourcesLine({ register, visa }) {
  return (
    <p className="small muted">
      {register ? `Sponsor register as of ${fmtDate(register.published_on, FULL_DATE)}.` : 'The sponsor register has not been loaded yet.'}
      {' '}Visa rules checked on {fmtDate(visa.checked_on, FULL_DATE)}. This is not immigration advice.
    </p>
  )
}
