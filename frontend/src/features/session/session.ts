import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { deleteSessionMutation } from '@/api/generated/@tanstack/react-query.gen'
import { meQuery } from '@/api/queries'

export function useMe() {
  return useQuery(meQuery())
}

/** The signed-in reviewer. Only screens behind RequireSession call it. */
export function useReviewer() {
  const me = useMe().data
  if (me === undefined) throw new Error('useReviewer needs a session')
  return me
}

export function useSignOut() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  return useMutation({
    ...deleteSessionMutation(),
    onSuccess: () => {
      queryClient.clear()
      void navigate('/sign-in')
    },
  })
}
