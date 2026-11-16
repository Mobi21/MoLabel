import { createBrowserRouter } from 'react-router-dom'

export const router = createBrowserRouter([
  {
    path: '*',
    element: (
      <main className="p-6">
        <h1 className="text-lg font-semibold">MoLabel</h1>
      </main>
    ),
  },
])
