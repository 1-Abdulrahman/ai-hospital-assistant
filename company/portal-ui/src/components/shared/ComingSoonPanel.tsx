import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface ComingSoonPanelProps {
  title: string;
  description: string;
  bullets?: string[];
}

export function ComingSoonPanel({
  title,
  description,
  bullets = [],
}: ComingSoonPanelProps) {
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h2 className="text-2xl font-bold">{title}</h2>
        <Badge variant="outline" className="bg-amber-500/15 text-amber-700 border-amber-300">
          Coming soon
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Planned portal capability</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <p className="text-muted-foreground">{description}</p>

          {bullets.length > 0 && (
            <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
              {bullets.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          )}

          <p className="text-xs text-muted-foreground">
            You can switch to mock mode from the top banner if you want to preview
            a more fully populated future portal experience.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}