import { Clock, FileText, Cpu, Sparkles, AlertCircle } from 'lucide-react';
import type { ProcessingStatus } from '../db';

// ---------------------------------------------------------------------------
// Status config
// ---------------------------------------------------------------------------

interface StatusConfig {
  label: string;
  icon: React.ReactElement;
  className: string;
}

const STATUS_CONFIG: Record<ProcessingStatus, StatusConfig> = {
  raw: {
    label: 'Raw',
    icon: <Clock className="h-3 w-3" aria-hidden="true" />,
    className: 'bg-slate-700 text-slate-300 border-slate-600',
  },
  transcribed: {
    label: 'Transcribed',
    icon: <FileText className="h-3 w-3" aria-hidden="true" />,
    className: 'bg-blue-900/50 text-blue-300 border-blue-700',
  },
  processed: {
    label: 'Processed',
    icon: <Cpu className="h-3 w-3" aria-hidden="true" />,
    className: 'bg-indigo-900/50 text-indigo-300 border-indigo-700',
  },
  enriched: {
    label: 'Enriched',
    icon: <Sparkles className="h-3 w-3" aria-hidden="true" />,
    className: 'bg-purple-900/50 text-purple-300 border-purple-700',
  },
  failed: {
    label: 'Failed',
    icon: <AlertCircle className="h-3 w-3" aria-hidden="true" />,
    className: 'bg-red-900/50 text-red-300 border-red-700',
  },
};

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ProcessingBadgeProps {
  status: ProcessingStatus;
  className?: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

/**
 * ProcessingBadge — displays the note's processing status with icon + colour.
 * States: raw | transcribed | processed | enriched | failed (mitigation #5).
 */
export function ProcessingBadge({ status, className = '' }: ProcessingBadgeProps): React.ReactElement {
  const config = STATUS_CONFIG[status];

  return (
    <span
      role="status"
      aria-label={`Processing status: ${config.label}`}
      className={[
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
        config.className,
        className,
      ].join(' ')}
    >
      {config.icon}
      {config.label}
    </span>
  );
}

export default ProcessingBadge;
