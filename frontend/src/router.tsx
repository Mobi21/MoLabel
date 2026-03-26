import { lazy, Suspense } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { AppLayout } from '@/components/layout/app-layout'
import { Skeleton } from '@/components/ui/skeleton'

function PageLoader() {
  return (
    <div className="flex flex-col gap-6 p-6">
      <Skeleton className="h-10 w-64" />
      <Skeleton className="h-[400px] w-full" />
    </div>
  )
}

function lazyPage(factory: () => Promise<{ [key: string]: React.ComponentType }>, name: string) {
  const Component = lazy(() =>
    factory().then((mod) => ({ default: mod[name] as React.ComponentType })),
  )
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  )
}

export const router = createBrowserRouter([
  {
    element: <AppLayout />,
    children: [
      { path: '/', element: lazyPage(() => import('@/pages/home'), 'HomePage') },
      { path: '/mission-control', element: lazyPage(() => import('@/pages/mission-control'), 'MissionControlPage') },
      { path: '/data', element: lazyPage(() => import('@/pages/data'), 'DataPage') },
      { path: '/data/catalog', element: lazyPage(() => import('@/pages/data'), 'DataPage') },
      { path: '/data/record/:id', element: lazyPage(() => import('@/pages/data'), 'DataPage') },
      { path: '/data/analytics', element: lazyPage(() => import('@/pages/data'), 'DataPage') },
      { path: '/tasks', element: lazyPage(() => import('@/pages/tasks'), 'TasksPage') },
      { path: '/workflow', element: lazyPage(() => import('@/pages/workflow'), 'WorkflowPage') },
      { path: '/workflow/:id', element: lazyPage(() => import('@/pages/workflow'), 'WorkflowPage') },
      { path: '/agents', element: lazyPage(() => import('@/pages/agents'), 'AgentsPage') },
      { path: '/review', element: lazyPage(() => import('@/pages/review'), 'ReviewPage') },
      { path: '/adjudication', element: lazyPage(() => import('@/pages/adjudication'), 'AdjudicationPage') },
      { path: '/quality', element: lazyPage(() => import('@/pages/quality'), 'QualityPage') },
      { path: '/curation', element: lazyPage(() => import('@/pages/curation'), 'CurationPage') },
      { path: '/exports', element: lazyPage(() => import('@/pages/exports'), 'ExportsPage') },
      { path: '/plugins', element: lazyPage(() => import('@/pages/plugins'), 'PluginsPage') },
      { path: '/settings', element: lazyPage(() => import('@/pages/settings'), 'SettingsPage') },
    ],
  },
])
