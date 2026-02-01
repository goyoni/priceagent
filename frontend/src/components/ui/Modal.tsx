/**
 * Modal component for overlays.
 */

import { useEffect } from 'react';
import { cn } from '@/lib/utils';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  footer,
  className,
}: ModalProps) {
  // Close on escape key
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      onClick={onClose}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70" />

      {/* Modal content */}
      <div
        className={cn(
          'relative bg-surface rounded-xl max-w-2xl w-[90%] max-h-[80vh] overflow-hidden',
          'shadow-2xl',
          className
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-surface-hover">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button
            onClick={onClose}
            className="text-secondary hover:text-gray-800 text-2xl leading-none"
          >
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="p-4 overflow-y-auto max-h-[60vh]">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="flex justify-end gap-3 px-5 py-4 border-t border-surface-hover">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
