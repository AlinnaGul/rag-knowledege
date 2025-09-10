import { useEffect, useState } from 'react';
import { useChatStore } from '@/stores/chat';
import { DisclaimerBanner } from '@/components/chat/DisclaimerBanner';
import { ChatMessages } from '@/components/chat/ChatMessages';
import { ChatInput } from '@/components/chat/ChatInput';
import { SettingsDrawer } from '@/components/chat/SettingsDrawer';
import { DOMAIN_INFO } from '@/lib/domain';
import AppShell from '@/components/layout/AppShell';
import { useAuthStore } from '@/stores/auth';

export default function Chat() {
  const [disclaimerDismissed, setDisclaimerDismissed] = useState(
    localStorage.getItem('rag-disclaimer-dismissed') === 'true'
  );

  const { loadSessions } = useChatStore();
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin';

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  const handleDismissDisclaimer = () => {
    setDisclaimerDismissed(true);
    localStorage.setItem('rag-disclaimer-dismissed', 'true');
  };

  const domain = import.meta.env.VITE_APP_DOMAIN as string | undefined;
  const disclaimer = domain ? DOMAIN_INFO[domain]?.disclaimer : undefined;

  return (
    <AppShell container={false}>
      <div className="relative flex flex-col h-full max-w-3.5xl mx-auto">
        <div className="absolute top-2 right-2">
          {isAdmin && <SettingsDrawer />}
        </div>
        {!disclaimerDismissed && disclaimer && (
          <DisclaimerBanner text={disclaimer} onDismiss={handleDismissDisclaimer} />
        )}
        <div className="flex-1 overflow-hidden">
          <ChatMessages />
        </div>
        <div className="border-t bg-card p-4">
          <ChatInput />
        </div>
      </div>
    </AppShell>
  );
}