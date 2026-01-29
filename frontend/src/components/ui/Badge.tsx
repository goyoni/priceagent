/**
 * Badge component for status indicators.
 */

import { cn } from '@/lib/utils';

interface BadgeProps {
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info' | 'secondary' | 'primary';
  children: React.ReactNode;
  className?: string;
}

const variantStyles = {
  default: 'bg-surface text-secondary',
  success: 'bg-success/20 text-success',
  warning: 'bg-warning/20 text-warning',
  error: 'bg-error/20 text-error',
  info: 'bg-primary/20 text-primary',
  secondary: 'bg-secondary/20 text-secondary',
  primary: 'bg-primary/30 text-primary',
};

export function Badge({
  variant = 'default',
  children,
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded text-xs font-medium',
        variantStyles[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
