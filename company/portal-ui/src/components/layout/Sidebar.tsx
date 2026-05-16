import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  CalendarCheck,
  Building2,
  FileText,
  GitBranch,
  MessageSquare,
  Brain,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/contexts/AuthContext';

const allLinks = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/bookings', label: 'Bookings', icon: CalendarCheck },
  { to: '/tenants', label: 'Tenants', icon: Building2 },
  { to: '/audit', label: 'Audit Logs', icon: FileText },
  { to: '/traces', label: 'Traces', icon: GitBranch },
  { to: '/sessions', label: 'Sessions', icon: MessageSquare },
  { to: '/nlp-monitoring', label: 'NLP Monitoring', icon: Brain },
];

const adminOnlyPaths = new Set(['/tenants', '/audit', '/traces', '/nlp-monitoring']);

export function Sidebar() {
  const { role } = useAuth();
  const links =
    role === 'ADMIN'
      ? allLinks
      : allLinks.filter((l) => !adminOnlyPaths.has(l.to));

  return (
    <aside className="w-56 border-r bg-sidebar flex flex-col py-4">
      <nav className="flex flex-col gap-1 px-3">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                  : 'text-sidebar-foreground hover:bg-sidebar-accent/50'
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span className="truncate">{label}</span>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}