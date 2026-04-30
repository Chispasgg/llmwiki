import type { Metadata } from 'next'
import { LoginForm } from './LoginForm'

export const metadata: Metadata = {
  title: 'Iniciar sesión | LLM Wiki',
  description: 'Inicia sesión en LLM Wiki para gestionar tus wikis.',
}

export default function LoginPage() {
  return <LoginForm />
}
