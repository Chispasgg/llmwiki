import type { Metadata } from 'next'
import { privacy } from '@/content/privacy'
import { PolicyPage } from '@/components/PolicyPage'

export const metadata: Metadata = {
  title: 'Privacy Policy',
  description: 'Privacy Policy for LLM Wiki.',
}

export default function PrivacyPage() {
  return <PolicyPage content={privacy} />
}
