import { useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { errorMessage } from '@/api/client'
import { KeyLegend } from '@/components/key-legend'
import { Button } from '@/components/ui/button'
import { plainKey, useKeymap, type Binding } from '@/lib/keymap'

/** A read that failed, with a retry and a way back to the queues. */
export function ReadFailed({
  error,
  onRetry,
}: {
  error: unknown
  onRetry: () => void
}) {
  const navigate = useNavigate()
  const retry = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    retry.current?.focus()
  }, [])
  const bindings: Binding[] = [
    {
      id: 'queues',
      caps: ['Esc'],
      label: 'Queues',
      match: plainKey('Escape'),
      run: () => {
        void navigate('/')
      },
    },
  ]
  useKeymap(bindings)
  return (
    <>
      <div className="p-8">
        <p role="alert" className="text-sm text-signal">
          {errorMessage(error)}
        </p>
        <div className="mt-4 flex gap-2">
          <Button ref={retry} onClick={onRetry}>
            Retry
          </Button>
          <Button variant="outline" asChild>
            <Link to="/">Back to queues</Link>
          </Button>
        </div>
      </div>
      <KeyLegend bindings={bindings} />
    </>
  )
}
