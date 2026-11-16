import { Link, Navigate, Outlet } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useMe, useSignOut } from './session'

/** Screens behind a reviewer session, under the shared header. */
export function RequireSession() {
  const me = useMe()
  const signOut = useSignOut()

  if (me.isPending) {
    return <p className="p-8 text-sm text-faint">Checking your session…</p>
  }
  if (me.isError) return <Navigate to="/sign-in" replace />

  return (
    <div className="flex min-h-screen flex-col pb-24">
      <header className="border-b border-rule bg-paper/90 backdrop-blur-sm">
        <div className="mx-auto flex h-12 max-w-[1400px] items-center gap-4 px-6">
          <Link
            to="/"
            className="flex items-center gap-2 font-mono text-sm font-semibold tracking-tight"
          >
            <span aria-hidden className="size-2.5 bg-signal" />
            MoLabel
          </Link>
          <span className="font-mono text-xs text-faint">review desk</span>
          <div className="ml-auto flex items-center gap-3 text-sm">
            <span className="flex items-center gap-2">
              <span
                aria-hidden
                className="size-2 rounded-full"
                style={{
                  backgroundColor: me.data.avatar_color ?? 'var(--faint)',
                }}
              />
              <span data-testid="signed-in-as">{me.data.display_name}</span>
            </span>
            <Button
              variant="ghost"
              size="sm"
              disabled={signOut.isPending}
              onClick={() => {
                signOut.mutate({})
              }}
            >
              Switch reviewer
            </Button>
          </div>
        </div>
      </header>
      <Outlet />
    </div>
  )
}
