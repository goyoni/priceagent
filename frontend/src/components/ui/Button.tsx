/**
 * Button component with variants.
 */

import { cn } from '@/lib/utils';
import { forwardRef } from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'success' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
}

const variantStyles = {
  primary: 'bg-primary text-white hover:bg-primary/80',
  secondary: 'bg-surface text-secondary hover:bg-surface-hover',
  success: 'bg-success text-white hover:bg-success/80',
  danger: 'bg-error text-white hover:bg-error/80',
  ghost: 'bg-transparent text-secondary hover:bg-surface',
};

const sizeStyles = {
  sm: 'px-2 py-1 text-xs',
  md: 'px-4 py-2 text-sm',
  lg: 'px-6 py-3 text-base',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { variant = 'primary', size = 'md', className, disabled, ...props },
    ref
  ) => {
    return (
      <button
        ref={ref}
        className={cn(
          'inline-flex items-center justify-center rounded font-medium transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-primary/50',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          variantStyles[variant],
          sizeStyles[size],
          className
        )}
        disabled={disabled}
        {...props}
      />
    );
  }
);

Button.displayName = 'Button';
