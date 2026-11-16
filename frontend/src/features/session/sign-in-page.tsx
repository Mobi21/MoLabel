import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { createSessionMutation } from '@/api/generated/@tanstack/react-query.gen'
import { meQuery, reviewerProfilesQuery, workspacesQuery } from '@/api/queries'
import type { ReviewerProfileResponse } from '@/api/generated/types.gen'
import { errorMessage } from '@/api/client'
import { Kbd, KeyLegend } from '@/components/key-legend'
import { digitKey, plainKey, useKeymap, type Binding } from '@/lib/keymap'
import { cn } from '@/lib/utils'
import { useMe } from './session'

interface WorkspaceGroup {
  workspaceId: string
  name: string
  profiles: ReviewerProfileResponse[]
}

/**
 * Pick who you are. Profiles carry no credential today, so choosing one
 * creates its session, as the API has always allowed.
 */
export function SignInPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const me = useMe()
  const profiles = useQuery(reviewerProfilesQuery())
  const workspaces = useQuery(workspacesQuery())
  const [selected, setSelected] = useState(0)

  const groups = useMemo<WorkspaceGroup[]>(() => {
    const names = new Map(
      (workspaces.data?.items ?? []).map((w) => [
        w.workspace_id,
        w.workspace_name,
      ]),
    )
    const byWorkspace = new Map<string, WorkspaceGroup>()
    for (const profile of profiles.data ?? []) {
      const group = byWorkspace.get(profile.workspace_id) ?? {
        workspaceId: profile.workspace_id,
        name: names.get(profile.workspace_id) ?? 'Workspace',
        profiles: [],
      }
      group.profiles.push(profile)
      byWorkspace.set(profile.workspace_id, group)
    }
    return [...byWorkspace.values()]
  }, [profiles.data, workspaces.data])
  const ordered = groups.flatMap((g) => g.profiles)

  const signIn = useMutation({
    ...createSessionMutation(),
    onSuccess: async () => {
      queryClient.clear()
      await queryClient.fetchQuery(meQuery())
      void navigate('/')
    },
  })

  function choose(index: number) {
    const profile = ordered[index]
    if (profile === undefined || signIn.isPending) return
    signIn.mutate({ body: { reviewer_id: profile.id } })
  }

  const bindings: Binding[] = [
    {
      id: 'pick',
      caps: ['1–9'],
      label: 'Sign in as that reviewer',
      match: digitKey,
      run: (e) => {
        choose(Number(e.key) - 1)
      },
    },
    {
      id: 'down',
      caps: ['↓'],
      label: 'Next',
      match: plainKey('ArrowDown', 'j'),
      run: () => {
        setSelected((i) => Math.min(i + 1, ordered.length - 1))
      },
    },
    {
      id: 'up',
      caps: ['↑'],
      label: 'Previous',
      match: plainKey('ArrowUp', 'k'),
      run: () => {
        setSelected((i) => Math.max(i - 1, 0))
      },
    },
    {
      id: 'enter',
      caps: ['Enter'],
      label: 'Sign in',
      match: plainKey('Enter'),
      run: () => {
        choose(selected)
      },
    },
  ]
  useKeymap(bindings)

  return (
    <div className="flex min-h-screen flex-col pb-(--legend-height)">
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col justify-center px-6 py-16">
        <p className="font-mono text-xs tracking-[0.2em] text-faint uppercase">
          MoLabel · review desk
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">
          Who is reviewing?
        </h1>
        <p className="mt-2 text-sm text-ink-soft">
          Reviewer profiles have no password. Picking one starts a session as
          that reviewer.
          {me.data && (
            <>
              {' '}
              You are signed in as{' '}
              <strong className="text-ink">{me.data.display_name}</strong>.
            </>
          )}
        </p>

        {profiles.isError && (
          <p role="alert" className="mt-8 text-sm text-signal">
            Could not load reviewers: {errorMessage(profiles.error)}
          </p>
        )}
        {profiles.isSuccess && ordered.length === 0 && (
          <p className="mt-8 rounded-[3px] border border-dashed border-rule p-4 text-sm text-ink-soft">
            No reviewer profiles yet. Run{' '}
            <code className="font-mono">molabel workspace bootstrap</code> to
            create the first one.
          </p>
        )}

        <div className="mt-8 space-y-6">
          {groups.map((group) => (
            <section key={group.workspaceId} aria-label={group.name}>
              {groups.length > 1 && (
                <h2 className="mb-2 font-mono text-xs text-faint uppercase">
                  {group.name}
                </h2>
              )}
              <ul className="divide-y divide-rule border-y border-rule bg-sheet">
                {group.profiles.map((profile) => {
                  const index = ordered.indexOf(profile)
                  return (
                    <li key={profile.id}>
                      <button
                        type="button"
                        onClick={() => {
                          choose(index)
                        }}
                        onFocus={() => {
                          setSelected(index)
                        }}
                        className={cn(
                          'flex w-full items-center gap-4 px-4 py-3 text-left transition-colors hover:bg-paper',
                          index === selected && 'bg-paper',
                        )}
                      >
                        <Kbd>{index < 9 ? String(index + 1) : '·'}</Kbd>
                        <span
                          aria-hidden
                          className="size-2.5 rounded-full"
                          style={{
                            backgroundColor:
                              profile.avatar_color ?? 'var(--faint)',
                          }}
                        />
                        <span className="flex-1 font-medium">
                          {profile.display_name}
                        </span>
                        {profile.is_operator && (
                          <span className="font-mono text-[11px] text-faint">
                            operator
                          </span>
                        )}
                        {index === selected && (
                          <span className="text-xs text-ink-soft">
                            Enter to sign in
                          </span>
                        )}
                      </button>
                    </li>
                  )
                })}
              </ul>
            </section>
          ))}
        </div>
        {signIn.isError && (
          <p role="alert" className="mt-4 text-sm text-signal">
            {errorMessage(signIn.error)}
          </p>
        )}
      </main>
      <KeyLegend bindings={bindings} />
    </div>
  )
}
