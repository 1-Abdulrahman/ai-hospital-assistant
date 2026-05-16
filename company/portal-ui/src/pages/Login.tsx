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

// Login
//
// Public login page for the Company Portal. Accepts username/email and password,
// submits to backend for JWT validation, and redirects to dashboard on success.
// Supports password visibility toggle and displays demo credentials for dev/testing.

export default function LoginPage() {
  // Form inputs: username (email or plain username) and password.
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  // Toggle password field visibility (show plain text or asterisks).
  const [showPassword, setShowPassword] = useState(false);
  // Track login request in progress (disables submit button).
  const [loading, setLoading] = useState(false);
  // Store login error (invalid credentials, network, etc) for display.
  const [error, setError] = useState<ApiError | null>(null);
  // AuthContext provides login() function for JWT validation and state management.
  const { login } = useAuth();
  // Router hook to redirect to dashboard on successful login.
  const navigate = useNavigate();

  // Handle form submission: validate credentials and log in user.
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      // Call AuthContext.login() to validate JWT and populate auth state.
      await login(username, password);
      // Redirect to dashboard on successful authentication.
      navigate('/dashboard');
    } catch (err: any) {
      // Capture and display login error (bad credentials, server down, etc).
      setError(err as ApiError);
    } finally {
      setLoading(false);
    }
  };

  // Enable submit button only when both fields are non-empty.
  const isValid = username.trim().length > 0 && password.trim().length > 0;

  return (
    <div className="min-h-screen flex flex-col">
      <MockBanner />
      {/* Center login card on screen, allow scrolling if content exceeds viewport. */}
      <div className="flex-1 flex items-center justify-center bg-background p-4">
        <Card className="w-full max-w-md">
          {/* Card header with portal title and description. */}
          <CardHeader className="text-center">
            <CardTitle className="text-2xl">Company Portal</CardTitle>
            <CardDescription>Sign in to access the admin dashboard</CardDescription>
          </CardHeader>
          <CardContent>
            {/* Display login error if authentication failed. */}
            {error && <div className="mb-4"><ErrorBanner error={error} /></div>}
            <form onSubmit={handleSubmit} className="space-y-4">
              {/* Username/email input field. */}
              <div className="space-y-2">
                <Label htmlFor="username">Username or Email</Label>
                <Input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin or admin@company.local"
                />              </div>
              {/* Password input field with show/hide toggle. */}
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
                  {/* Eye icon button toggles password visibility. */}
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>
              {/* Submit button: disabled when fields empty or request in progress. */}
              <Button type="submit" className="w-full" disabled={!isValid || loading}>
                {loading ? 'Signing in…' : 'Sign In'}
              </Button>
            </form>
            {/* Demo credentials reference box for development/testing. */}
            <div className="rounded-md border bg-muted/30 px-3 py-2 text-xs text-muted-foreground space-y-2">
              <div className="font-medium text-foreground">Demo logins</div>

              <div className="space-y-1">
                {/* Platform admin (full system access). */}
                <div>
                  <span className="font-medium">Platform Admin:</span>{" "}
                  <code>admin / CompanyAdmin123!</code>
                </div>
                {/* Tenant admin (scoped to a specific tenant). */}
                <div>
                  <span className="font-medium">Tenant Admin:</span>{" "}
                  <code>tenant / Admin123!</code>
                </div>
              </div>

              {/* Alternative login methods: email addresses that map to demo accounts. */}
              <div className="text-[11px] text-muted-foreground/80">
                Email login also works in the username field:
                <div className="mt-1 font-mono">admin@company.local</div>
                <div className="font-mono">admin@mvp.local</div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
