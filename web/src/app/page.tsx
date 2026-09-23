import { redirect } from 'next/navigation'
import { cookies } from 'next/headers'

export default async function HomePage() {
  if (process.env.NEXT_PUBLIC_MODE === 'local') {
    redirect('/workspaces')
  }
  const store = await cookies()
  redirect(store.get('wiki_session') ? '/workspaces' : '/login')
}
