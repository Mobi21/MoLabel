import { useCallback, useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import {
  claimNextItemMutation,
  getReviewTaskEndpointQueryKey,
} from '@/api/generated/@tanstack/react-query.gen'
import { myTasksQuery, reviewTaskQuery } from '@/api/queries'
import type { BlindReviewTaskResponse } from '@/api/generated/types.gen'
import { queuesKey } from '@/features/queues/queues'

/**
 * Where the reviewer stands in a queue. The head is the one task they hold
 * a claim on: unknown until their trail loads, a task, or empty once the
 * queue has nothing left for them.
 */
export type Head =
  | { kind: 'unknown' }
  | { kind: 'task'; taskId: string }
  | { kind: 'empty' }

export function reviewTaskKey(taskId: string) {
  return getReviewTaskEndpointQueryKey({ path: { task_id: taskId } })
}

/**
 * One reviewer's pass through a queue: the tasks they worked, the task they
 * hold, and the one on screen. It loads one item at a time and prefetches
 * the items on either side, never the whole queue.
 */
export function useReviewSession(queueId: string) {
  const queryClient = useQueryClient()
  const [params, setParams] = useSearchParams()
  const trailOptions = myTasksQuery(queueId)
  const trail = useQuery(trailOptions)
  const [head, setHead] = useState<Head>({ kind: 'unknown' })
  const claim = useMutation(claimNextItemMutation())

  const seed = useCallback(
    (task: BlindReviewTaskResponse) => {
      queryClient.setQueryData(reviewTaskKey(task.id), {
        ...task,
        review: null,
      })
    },
    [queryClient],
  )

  const refreshTrail = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: trailOptions.queryKey })
    void queryClient.invalidateQueries({ queryKey: queuesKey })
  }, [queryClient, trailOptions.queryKey])

  const held = trail.data?.items.find((t) => t.status === 'claimed')
  const { mutate: claimNext } = claim
  const claimStarted = useRef(false)
  useEffect(() => {
    if (head.kind !== 'unknown' || !trail.isSuccess) return
    if (held) {
      setHead({ kind: 'task', taskId: held.task_id })
      return
    }
    if (claimStarted.current) return
    claimStarted.current = true
    claimNext(
      { path: { queue_id: queueId } },
      {
        onSuccess: (response) => {
          if (response.task) {
            seed(response.task)
            setHead({ kind: 'task', taskId: response.task.id })
          } else {
            setHead({ kind: 'empty' })
          }
          refreshTrail()
        },
      },
    )
  }, [head.kind, trail.isSuccess, held, claimNext, queueId, seed, refreshTrail])

  const headId = head.kind === 'task' ? head.taskId : null
  const ids = (trail.data?.items ?? []).map((t) => t.task_id)
  if (headId !== null && !ids.includes(headId)) ids.push(headId)

  const requested = params.get('task')
  const currentId = requested ?? headId
  const index = currentId === null ? ids.length : ids.indexOf(currentId)
  const previousId = index > 0 ? (ids[index - 1] ?? null) : null
  const nextId =
    index >= 0 && index < ids.length - 1 ? (ids[index + 1] ?? null) : null
  // From the last item stepped back to, next returns to the head.
  const hasNext = nextId !== null || (requested !== null && index >= 0)

  const go = useCallback(
    (taskId: string | null) => {
      setParams(taskId === null || taskId === headId ? {} : { task: taskId })
    },
    [setParams, headId],
  )
  const goNext = useCallback(() => {
    go(nextId)
  }, [go, nextId])

  useEffect(() => {
    for (const taskId of [previousId, nextId]) {
      if (taskId !== null) {
        void queryClient.prefetchQuery(reviewTaskQuery(taskId))
      }
    }
  }, [queryClient, previousId, nextId])

  const item = useQuery({
    ...reviewTaskQuery(currentId ?? ''),
    enabled: currentId !== null,
  })

  /** Move the head to the task a submit or skip claimed, or to empty. */
  const advanceHead = useCallback(
    (next: BlindReviewTaskResponse | null | undefined) => {
      if (next) {
        seed(next)
        setHead({ kind: 'task', taskId: next.id })
      } else {
        setHead({ kind: 'empty' })
      }
      setParams({})
      refreshTrail()
    },
    [seed, setParams, refreshTrail],
  )

  return {
    trail,
    claim,
    head,
    item,
    currentId,
    isHead: currentId !== null && currentId === headId,
    position: { index, total: ids.length },
    previousId,
    hasNext,
    goNext,
    go,
    advanceHead,
    refreshTrail,
  }
}

export type ReviewSession = ReturnType<typeof useReviewSession>
