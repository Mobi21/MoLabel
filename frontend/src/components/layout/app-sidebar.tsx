import { useLocation, Link } from 'react-router-dom'
import {
  House,
  Activity,
  Database,
  ClipboardList,
  GitBranch,
  Bot,
  Eye,
  Scale,
  Shield,
  Filter,
  Package,
  Puzzle,
  Settings,
  Sun,
  Moon,
  Hexagon,
} from 'lucide-react'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
} from '@/components/ui/sidebar'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { useUIStore } from '@/stores/ui-store'

interface NavItem {
  title: string
  url: string
  icon: React.ComponentType<{ className?: string | undefined }>
}

interface NavGroup {
  label: string
  items: NavItem[]
}

const navGroups: NavGroup[] = [
  {
    label: 'Overview',
    items: [
      { title: 'Home', url: '/', icon: House },
      { title: 'Mission Control', url: '/mission-control', icon: Activity },
    ],
  },
  {
    label: 'Data',
    items: [
      { title: 'Data', url: '/data', icon: Database },
      { title: 'Tasks', url: '/tasks', icon: ClipboardList },
      { title: 'Workflow', url: '/workflow', icon: GitBranch },
    ],
  },
  {
    label: 'AI',
    items: [{ title: 'Agents', url: '/agents', icon: Bot }],
  },
  {
    label: 'Human',
    items: [
      { title: 'Review', url: '/review', icon: Eye },
      { title: 'Adjudication', url: '/adjudication', icon: Scale },
    ],
  },
  {
    label: 'Quality',
    items: [
      { title: 'Quality', url: '/quality', icon: Shield },
      { title: 'Curation', url: '/curation', icon: Filter },
    ],
  },
  {
    label: 'Output',
    items: [
      { title: 'Exports & Releases', url: '/exports', icon: Package },
    ],
  },
  {
    label: 'System',
    items: [
      { title: 'Plugins', url: '/plugins', icon: Puzzle },
      { title: 'Settings', url: '/settings', icon: Settings },
    ],
  },
]

export function AppSidebar() {
  const location = useLocation()
  const { theme, toggleTheme } = useUIStore()

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild tooltip="MoLabel">
              <Link to="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <Hexagon className="size-4" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">MoLabel</span>
                  <span className="truncate text-xs text-muted-foreground">
                    Data Operations
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarSeparator />

      <SidebarContent>
        {navGroups.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel>{group.label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => {
                  const isActive =
                    item.url === '/'
                      ? location.pathname === '/'
                      : location.pathname.startsWith(item.url)
                  return (
                    <SidebarMenuItem key={item.title}>
                      <SidebarMenuButton
                        asChild
                        isActive={isActive}
                        tooltip={item.title}
                      >
                        <Link to={item.url}>
                          <item.icon />
                          <span>{item.title}</span>
                        </Link>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  )
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              tooltip={theme === 'dark' ? 'Light mode' : 'Dark mode'}
              onClick={toggleTheme}
            >
              {theme === 'dark' ? (
                <Sun className="size-4" />
              ) : (
                <Moon className="size-4" />
              )}
              <span>{theme === 'dark' ? 'Light mode' : 'Dark mode'}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" tooltip="Sarah Chen">
              <Avatar className="h-8 w-8">
                <AvatarFallback
                  className="text-xs"
                  style={{ backgroundColor: '#6366f1', color: 'white' }}
                >
                  SC
                </AvatarFallback>
              </Avatar>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-semibold">Sarah Chen</span>
                <span className="truncate text-xs text-muted-foreground">
                  Operator
                </span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  )
}
