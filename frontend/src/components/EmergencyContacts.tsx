import { Ambulance, Flame, LifeBuoy, PhoneCall, Shield, Siren, type LucideIcon } from 'lucide-react'
import { Panel, SectionHeading } from './Shared'

type EmergencyContact = {
  service: string
  number: string
  icon: LucideIcon
  primary?: boolean
}

const emergencyContacts: readonly EmergencyContact[] = [
  { service: 'National Emergency Helpline (SOS)', number: '112', icon: Siren, primary: true },
  { service: 'Police', number: '100', icon: Shield },
  { service: 'Ambulance', number: '108', icon: Ambulance },
  { service: 'Fire Brigade', number: '101', icon: Flame },
  { service: 'District Disaster Control Room', number: '1077', icon: LifeBuoy },
]

export function EmergencyContacts() {
  return <Panel className="emergency-contacts">
    <SectionHeading eyebrow="QUICK HELP" title="Emergency Contacts" action={<PhoneCall size={19} aria-hidden="true"/>}/>
    <p className="emergency-contacts-context">General helplines for India and Pune District, not facility-specific contacts.</p>
    <div className="emergency-contact-list">
      {emergencyContacts.map(({ service, number, icon: Icon, primary }) =>
        <a className={`emergency-contact ${primary ? 'emergency-contact-primary' : ''}`} href={`tel:${number}`}
          aria-label={`Call ${service} at ${number}`} key={number}>
          <span className="emergency-contact-icon"><Icon size={18} aria-hidden="true"/></span>
          <span className="emergency-contact-service">{service}</span>
          <strong className="emergency-contact-number">{number}</strong>
          <span className="emergency-contact-call">Call {number}</span>
        </a>)}
    </div>
    <p className="emergency-contacts-note">Call only when assistance is needed. Your device handles the call.</p>
  </Panel>
}
