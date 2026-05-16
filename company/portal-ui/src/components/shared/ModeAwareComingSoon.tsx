import { getIsMockMode } from '@/api/apiClient';
import { ComingSoonPanel } from '@/components/shared/ComingSoonPanel';
import type { ReactNode } from 'react';

interface ModeAwareComingSoonProps {
  title: string;
  description: string;
  bullets?: string[];
  preview: ReactNode;
}

export function ModeAwareComingSoon({
  title,
  description,
  bullets = [],
  preview,
}: ModeAwareComingSoonProps) {
  const isMockMode = getIsMockMode();

  if (isMockMode) {
    return <>{preview}</>;
  }

  return (
    <ComingSoonPanel
      title={title}
      description={description}
      bullets={bullets}
    />
  );
}