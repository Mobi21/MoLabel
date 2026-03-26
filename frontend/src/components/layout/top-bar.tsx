import { useLocation } from 'react-router-dom'
import { Sun, Moon, MessageSquare } from 'lucide-react'
import { SidebarTrigger } from '@/components/ui/sidebar'
import { Separator } from '@/components/ui/separator'
import { Button } from '@/components/ui/button'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useUIStore } from '@/stores/ui-store'

const pageTitles: Record<string, string> = {
  '/': 'Home',
  '/mission-control': 'Mission Control',
  '/data': 'Data',
  '/tasks': 'Tasks',
  '/workflow': 'Workflow',
  '/agents': 'Agents',
  '/review': 'Review',
  '/adjudication': 'Adjudication',
  '/quality': 'Quality',
  '/curation': 'Curation',
  '/exports': 'Exports & Releases',
  '/plugins': 'Plugins',
  '/settings': 'Settings',
}

function getBreadcrumb(pathname: string): string {
  const exact = pageTitles[pathname]
  if (exact) return exact

  const segments = pathname.split('/').filter(Boolean)
  const base = `/${segments[0] ?? ''}`
  return pageTitles[base] ?? 'MoLabel'
}

export function TopBar() {
  const location = useLocation()
  const { theme, toggleTheme, toggleAssistant } = useUIStore()
  const breadcrumb = getBreadcrumb(location.pathname)

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 h-4" />
      <div className="flex flex-1 items-center gap-2">
        <span className="text-sm font-medium">{breadcrumb}</span>
      </div>
      <div className="flex items-center gap-1">
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={toggleTheme}
            >
              {theme === 'dark' ? (
                <Sun className="h-4 w-4" />
              ) : (
                <Moon className="h-4 w-4" />
              )}
              <span className="sr-only">Toggle theme</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            {theme === 'dark' ? 'Light mode' : 'Dark mode'}
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={toggleAssistant}
            >
              <MessageSquare className="h-4 w-4" />
              <span className="sr-only">Toggle assistant</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent>AI Assistant</TooltipContent>
        </Tooltip>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 w-8 rounded-full p-0">
              <Avatar className="h-7 w-7">
                <AvatarFallback
                  className="text-xs"
                  style={{ backgroundColor: '#6366f1', color: 'white' }}
                >
                  SC
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel>
              <div className="flex flex-col space-y-1">
                <p className="text-sm font-medium leading-none">Sarah Chen</p>
                <p className="text-xs leading-none text-muted-foreground">
                  Operator
                </p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem>Profile</DropdownMenuItem>
            <DropdownMenuItem>Preferences</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem>Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  )
}
