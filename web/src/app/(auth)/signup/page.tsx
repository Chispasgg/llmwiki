import type { Metadata } from 'next'
import { SignupForm } from './SignupForm'

export const metadata: Metadata = {
  title: 'Sign Up',
  description: "Create a free LLM Wiki account. Upload documents and build a compounding wiki powered by Claude.",
  openGraph: {
    title: 'Sign Up',
    description: "Create a free LLM Wiki account. Upload documents and build a compounding wiki powered by Claude.",
  },
}

export default function SignupPage() {
  return <SignupForm />
}
