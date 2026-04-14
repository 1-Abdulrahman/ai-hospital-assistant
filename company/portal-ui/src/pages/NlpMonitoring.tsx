import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ModeAwareComingSoon } from '@/components/shared/ModeAwareComingSoon';

function NlpMonitoringPreview() {
  const samples = [
    { label: 'Cardiology', confidence: 0.91, ambiguous: false },
    { label: 'Neurology', confidence: 0.64, ambiguous: true },
    { label: 'Gastroenterology', confidence: 0.88, ambiguous: false },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <h2 className="text-2xl font-bold">NLP Monitoring</h2>
        <Badge variant="outline" className="bg-blue-500/15 text-blue-700 border-blue-300">
          Mock preview
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Future NLP monitoring preview</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {samples.map((sample, index) => (
            <div key={index} className="rounded-md border p-3 space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{sample.label}</span>
                <Badge variant={sample.ambiguous ? 'secondary' : 'outline'}>
                  {sample.ambiguous ? 'Ambiguous' : 'Clear'}
                </Badge>
              </div>
              <div className="text-xs text-muted-foreground">
                Confidence: {Math.round(sample.confidence * 100)}%
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

export default function NlpMonitoringPage() {
  return (
    <ModeAwareComingSoon
      title="NLP Monitoring"
      description="NLP monitoring is deferred for this checkpoint. The current focus is on real booking traceability, session timelines, and portal-backed operational visibility."
      bullets={[
        'Model health and threshold monitoring',
        'Recent classification views',
        'Confidence and ambiguity trend analysis',
      ]}
      preview={<NlpMonitoringPreview />}
    />
  );
}