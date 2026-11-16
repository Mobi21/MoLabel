import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AdjudicationPage } from '@/features/adjudication/adjudication-page'
import { CalibrationPage } from '@/features/calibration/calibration-page'
import { QueueListPage } from '@/features/queues/queue-list-page'
import { ReviewPage } from '@/features/review/review-page'
import { RequireSession } from '@/features/session/require-session'
import { SignInPage } from '@/features/session/sign-in-page'

export const router = createBrowserRouter([
  { path: '/sign-in', element: <SignInPage /> },
  {
    element: <RequireSession />,
    children: [
      { path: '/', element: <QueueListPage /> },
      { path: '/queues/:queueId/review', element: <ReviewPage /> },
      {
        path: '/queues/:queueId/adjudication',
        element: <AdjudicationPage />,
      },
      { path: '/queues/:queueId/calibration', element: <CalibrationPage /> },
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
])
