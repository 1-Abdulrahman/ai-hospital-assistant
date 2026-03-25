import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { getTenantId, setTenantId, getSessionId, resetSession, getCorrelationId } from "@/lib/session";
import { toast } from "sonner";

export default function SettingsScreen() {
  const [tenant, setTenant] = useState(getTenantId());
  const [sessionId, setSessionId] = useState(getSessionId());
  const [lastCorrelation, setLastCorrelation] = useState(getCorrelationId() || "—");
  const navigate = useNavigate();

  const handleSaveTenant = () => {
    setTenantId(tenant);
    toast.success("Tenant ID updated");
  };

  const handleResetSession = () => {
    const newId = resetSession();
    setSessionId(newId);
    setLastCorrelation("—");
    toast.success("Session reset");
  };

  return (
    <div className="container max-w-lg py-8">
      <Button variant="ghost" className="mb-4" onClick={() => navigate("/")}>
        ← Back
      </Button>
      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
          <CardDescription>Configure tenant and session</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <label className="text-sm font-medium">Tenant ID</label>
            <div className="flex gap-2">
              <Input value={tenant} onChange={(e) => setTenant(e.target.value)} />
              <Button onClick={handleSaveTenant}>Save</Button>
            </div>
          </div>

          <Separator />

          <div className="space-y-2">
            <label className="text-sm font-medium">Session ID</label>
            <p className="rounded bg-muted px-3 py-2 font-mono text-xs break-all">{sessionId}</p>
            <Button variant="destructive" size="sm" onClick={handleResetSession}>
              Reset Session
            </Button>
          </div>

          <Separator />

          <div className="space-y-2">
            <label className="text-sm font-medium text-muted-foreground">Debug Info</label>
            <div className="rounded bg-muted px-3 py-2 text-xs space-y-1">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Last Correlation ID</span>
                <span className="font-mono">{lastCorrelation}</span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
