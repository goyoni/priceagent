/**
 * DraftModal component for reviewing and sending negotiation messages.
 */

'use client';

import { useDraftStore } from '@/stores/useDraftStore';
import { Modal } from '@/components/ui/Modal';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/utils';

export function DraftModal() {
  const {
    isModalOpen,
    closeModal,
    drafts,
    sentIndices,
    updateDraftMessage,
    updateDraftPhone,
    markAsSent,
    isGenerating,
    error,
  } = useDraftStore();

  const handleSend = (index: number) => {
    const draft = drafts[index];
    window.open(draft.wa_link, '_blank');
    markAsSent(index);
  };

  const handleSendAll = () => {
    drafts.forEach((_, index) => {
      if (!sentIndices.has(index)) {
        setTimeout(() => handleSend(index), index * 500);
      }
    });
  };

  const handleCopyLink = async (index: number) => {
    const draft = drafts[index];
    await navigator.clipboard.writeText(draft.wa_link);
  };

  return (
    <Modal
      isOpen={isModalOpen}
      onClose={closeModal}
      title="Review Negotiation Messages"
      footer={
        <>
          <Button variant="success" onClick={handleSendAll}>
            Send All via WhatsApp
          </Button>
          <Button variant="secondary" onClick={closeModal}>
            Cancel
          </Button>
        </>
      }
    >
      {isGenerating ? (
        <p className="text-secondary text-center py-8">Generating drafts...</p>
      ) : error ? (
        <p className="text-error text-center py-8">{error}</p>
      ) : (
        <div className="space-y-4">
          {drafts.map((draft, index) => (
            <div
              key={index}
              className={cn(
                'bg-background rounded-lg p-4',
                sentIndices.has(index) && 'opacity-60 border-2 border-success'
              )}
            >
              {/* Header */}
              <div className="flex items-center gap-2 mb-2">
                <input
                  type="checkbox"
                  checked
                  readOnly
                  className="w-4 h-4"
                />
                <strong className="text-primary">{draft.seller_name}</strong>
              </div>

              <p className="text-sm text-secondary mb-3">
                Product: {draft.product_name}
              </p>

              {/* Phone field */}
              <div className="mb-3">
                <label className="block text-xs text-secondary mb-1">
                  Phone Number:
                </label>
                <input
                  type="text"
                  value={draft.phone_number}
                  onChange={(e) => updateDraftPhone(index, e.target.value)}
                  className="w-48 px-3 py-1.5 bg-surface border border-surface-hover rounded
                             text-white text-sm focus:outline-none focus:border-primary"
                />
              </div>

              {/* Message field */}
              <div className="mb-3">
                <label className="block text-xs text-secondary mb-1">
                  Message:
                </label>
                <textarea
                  value={draft.message}
                  onChange={(e) => updateDraftMessage(index, e.target.value)}
                  className="w-full min-h-[80px] px-3 py-2 bg-surface border border-surface-hover rounded
                             text-white text-sm resize-y
                             focus:outline-none focus:border-primary"
                />
              </div>

              {/* Actions */}
              <div className="flex gap-2">
                <Button
                  variant="success"
                  size="sm"
                  onClick={() => handleSend(index)}
                  disabled={sentIndices.has(index)}
                >
                  {sentIndices.has(index) ? '✓ Opened' : '📱 Send via WhatsApp'}
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => handleCopyLink(index)}
                >
                  🔗 Copy Link
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </Modal>
  );
}
