import { useAuth } from '@/contexts/AuthContext';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { LogOut, Mail } from 'lucide-react';

export function Header() {
  const { logout } = useAuth();

  return (
    <header className="h-14 border-b bg-card flex items-center justify-between px-4 gap-3">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-bold text-foreground">Company Portal</h1>
        <Badge variant="outline" className="bg-amber-500/15 text-amber-700 border-amber-300 text-xs">
          LOCAL OFFLINE DEMO
        </Badge>
        <Badge variant="secondary" className="text-xs">
          Tenant: demo
        </Badge>
      </div>
      <div className="flex items-center gap-2">
        <a
          href="http://localhost:8025"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <Mail className="h-4 w-4" />
          MailHog
        </a>
        <Button variant="ghost" size="sm" onClick={logout}>
          <LogOut className="h-4 w-4 mr-1" />
          Logout
        </Button>
      </div>
    </header>
  );
}
