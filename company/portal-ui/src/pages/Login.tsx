import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ErrorBanner } from '@/components/shared/ErrorBanner';
import { Eye, EyeOff } from 'lucide-react';
import type { ApiError } from '@/api/types';
import { MockBanner } from '@/components/layout/MockBanner';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(username, password);
      navigate('/dashboard');
    } catch (err: any) {
      setError(err as ApiError);
    } finally {
      setLoading(false);
    }
  };

  const isValid = username.trim().length > 0 && password.trim().length > 0;

  return (
    <div className="min-h-screen flex flex-col">
      <MockBanner />
      <div className="flex-1 flex items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">Company Portal</CardTitle>
            <CardDescription>Sign in to access the admin dashboard</CardDescription>
          </CardHeader>
          <CardContent>
            {error && <div className="mb-4"><ErrorBanner error={error} /></div>}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="username">Username</Label>
                <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              <Button type="submit" className="w-full" disabled={!isValid || loading}>
                {loading ? 'Signing in…' : 'Sign In'}
              </Button>
            </form>
            <div className="mt-4 text-xs text-muted-foreground text-center space-y-1">
              <p><code className="bg-muted px-1 rounded">admin</code> / <code className="bg-muted px-1 rounded">admin</code> <span className="text-muted-foreground">(Platform Admin)</span></p>
              <p><code className="bg-muted px-1 rounded">tenant</code> / <code className="bg-muted px-1 rounded">tenant</code> <span className="text-muted-foreground">(Tenant Admin)</span></p>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
