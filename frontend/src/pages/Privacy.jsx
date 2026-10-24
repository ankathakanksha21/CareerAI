import { useEffect, useState } from 'react'
import { getConfig } from '../supabase'
import { Brand } from '../ui'

// A plain statement of what the app stores and who processes it. Draft: review before a public launch.
export default function Privacy({ go, signedIn }) {
  const [contact, setContact] = useState('')
  useEffect(() => { getConfig().then((c) => setContact(c.contact_email || '')).catch(() => {}) }, [])

  return (
    <div>
      <header className="ob-top">
        <Brand onClick={() => go(signedIn ? 'home' : 'landing')} />
        <span className="spacer" />
        <button className="linkish small" onClick={() => go(signedIn ? 'home' : 'landing')}>{signedIn ? 'Back to the app' : 'Back'}</button>
      </header>
      <main className="ob-body prose">
        <h1>Privacy notice</h1>
        <p className="muted">How UK Career Navigator uses your information.</p>

        <h2>What we collect</h2>
        <ul className="dots">
          <li>Your email address and name.</li>
          <li>Your university, course, graduation date, visa type, visa end date and preferred locations.</li>
          <li>What you tell the careers coach in a voice call, or paste into the app, about your background.</li>
          <li>The text of a CV you upload. The file is read once and discarded: we keep the text we read from it, never the file.</li>
          <li>Your work history, education, skills and languages, once you confirm them.</li>
          <li>Your phone number, town or city and LinkedIn address, if you add them for your CV, and any certifications, awards or volunteering you list. They are printed on your CVs. Your name, email and these contact details are not sent to the AI when a CV is written.</li>
          <li>Your GitHub username, if you import projects, and the public description and README of the repositories you pick.</li>
          <li>Job descriptions you add, which matched jobs you save or dismiss, and the applications you log: each one's stage changes with their dates, notes, follow-up dates, and the name and contact details of anyone you dealt with there.</li>
          <li>When an application is rejected, where it ended and any feedback you type. To write a lesson from it, the CV you sent, the job description, where it ended and that feedback are sent to the AI. Your name and contact details are not.</li>
          <li>To draft a follow-up, only the role, the company, the date you applied and your contact's name are sent to the AI. How to reach them and your own name are not; your name is added to the draft afterwards. Nothing is ever sent to an employer for you.</li>
          <li>For a prep pack: the company you prepare for, its website if you give it, the pack written for you, the questions you tick and your edits. To write the pack, the job description, your achievements, your stories and your course are sent to the AI. Your name, contact details and visa are not; your right-to-work line is written by the app from your visa details.</li>
          <li>The competencies each of your stories shows.</li>
          <li>People you add in Networking: their name, role, company, how you know them, a profile link and your notes, and each step you record with them (a message marked as sent, a reply, a chat, a referral). No email address or phone number is asked for. To write a draft, the AI is sent their role, their company and how you know them (with your university's name if they studied there too, or the event's name if you met there), your own pitch or course, and, depending on the kind of message: what you learned in a chat, when you can start and when your course ends, your target roles, or the saved job you want a referral for with up to five of your achievements. Their name, your notes about them, your name and your contact details are not sent; the greeting and sign-off are added afterwards. Nothing is ever sent to them for you: you copy a draft and send it yourself.</li>
          <li>Events you save: the name, time, place, link and your notes, and the preparation written for one. To prepare, the event's name and kind are sent to the AI with your pitch.</li>
          <li>Your university's careers events page, if you add it. The search links on Networking open LinkedIn, Meetup, Eventbrite and professional bodies' sites with your university, field, city or a company name as the search words; the app itself sends those sites nothing.</li>
          <li>If you switch Peers on: that you confirmed you are 18 or over and agreed to the code of conduct, the field you chose, and when you joined the list. To suggest a field, only the names of your target roles are sent to the AI. The people in your buddy group see your first name, university, course and target roles, how many of your weekly targets you met and your streak, the one line you write each week, whether you have done nothing that counts (an application logged with its CV, a mock interview, a message or a check-in) for three weeks, and a contact link if you share one (a WhatsApp link shows them your phone number). Before everyone in a group has said yes, they see only your first name, university, course and target roles. They never see your email address, visa, applications, employers, CVs, achievements, journal or transcripts. Your first name is the first word of the full name in your profile, so they see your surname only if you wrote it first; the Peers page shows exactly how you appear. Matching uses your field, your preferred locations and your university, never your visa.</li>
          <li>Nudges you send and receive, blocks you make, and reports you make. A report is kept for the app's owner to review, with a copy of the line you reported. Switching Peers off removes you from your group at once and deletes your check-ins and the nudges you sent and received.</li>
          <li>Your weekly goals, including how many messages to people you aim to send, and which milestones you have already been shown. Streaks and the weekly plan are worked out from your data each time and not stored.</li>
          <li>Content the AI writes for you: achievements, CVs, cover letters, interview stories, feedback and lessons from rejections.</li>
          <li>The wording of each CV and cover letter you build or edit. The Word and PDF files are made when you download them and are not kept.</li>
          <li>A count of how many AI actions and voice calls you use each day.</li>
        </ul>

        <h2>Why we use it</h2>
        <p>To build your profile, tailor CVs and interview practice to you, and show you what is and is not working in your job search. We do not sell your information or use it for advertising.</p>

        <h2>Who processes it</h2>
        <ul className="dots">
          <li><span className="strong">Supabase</span> stores your account and data, in London.</li>
          <li><span className="strong">Amazon Web Services (Bedrock)</span> runs the AI model that writes text for you, in the United States.</li>
          <li><span className="strong">ElevenLabs</span> runs voice calls and turns them into text.</li>
          <li><span className="strong">GitHub</span> supplies public repository details when you import projects. We send it the username you type, nothing else about you.</li>
          <li><span className="strong">Companies House</span> supplies a company's official record when you prepare for an interview. We send it the company name you confirm, nothing about you.</li>
          <li><span className="strong">Tavily</span>, a web search service, finds a company's recent news and competitors. We send it the company's name only.</li>
          <li><span className="strong">The employer's own website</span>: our server reads up to six of its public pages, identifying itself as this app and following the site's rules for automated readers. Nothing about you is sent.</li>
          <li><span className="strong">Shared company research</span>: what was found about a company is kept for 14 days and reused when anyone prepares for it. It holds only public facts about the company, never your pack or anything about you.</li>
          <li><span className="strong">Reed</span> supplies job adverts. We send it job titles and locations from your target roles, never your name or anything else about you.</li>
        </ul>

        <h2>Visa and sponsorship facts</h2>
        <p>Salary figures and the register of licensed sponsors come from gov.uk and are shown with the date we last checked them. They are facts to check for yourself, not immigration advice. Contains public sector information licensed under the Open Government Licence v3.0.</p>

        <h2>How long we keep it</h2>
        <p>Until you delete your account.</p>

        <h2>Your choices</h2>
        <p>You can delete your account and everything in it at any time from the Account page. You can also edit or remove individual achievements, jobs, courses, skills, stories, applications, contacts and events. Deleting a contact removes their details; the messages you sent them still count in your weekly goals, without their name. In Peers you can leave your group, block or report someone, or switch Peers off at any time; deleting your account also deletes every report, block and nudge that names you.</p>

        {contact && <><h2>Contact</h2><p>Questions about your information: <a href={`mailto:${contact}`}>{contact}</a></p></>}
      </main>
    </div>
  )
}
