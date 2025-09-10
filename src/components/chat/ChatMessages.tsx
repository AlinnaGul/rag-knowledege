import { useEffect, useRef } from 'react';
import { useChatStore } from '@/stores/chat';
import { MessageBubble } from './MessageBubble';
import { MessageSquare } from 'lucide-react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { EmptyState } from '@/components/ui/empty-state';
import { ChatBubbleSkeleton } from '@/components/ui/skeletons';
import { Button } from '@/components/ui/button';

export function ChatMessages() {
  const { messages, isLoading, currentSession, createSession } = useChatStore();
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const parentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 120,
    overscan: 20,
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (messages.length > 100) {
      rowVirtualizer.scrollToIndex(messages.length - 1);
    } else {
      scrollToBottom();
    }
  }, [messages, rowVirtualizer]);

  if (!currentSession) {
    return (
      <EmptyState
        icon={<MessageSquare className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />}
        title="Welcome to the Knowledge Hub"
        description="Start a conversation by asking a question about your organization's knowledge base."
        action={<Button onClick={createSession}>New Chat</Button>}
        className="p-8"
      />
    );
  }

  return (
    <div ref={parentRef} className="h-full overflow-auto">
      <div className="mx-auto max-w-3.5xl px-4">
        {messages.length === 0 && !isLoading ? (
          <EmptyState
            icon={<MessageSquare className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />}
            title="Start a conversation"
            description="Ask me anything about your organization's knowledge base."
            action={
              <Button onClick={() => document.getElementById('chat-input')?.focus()}>Ask a question</Button>
            }
          />
        ) : messages.length > 100 ? (
          <div style={{ height: `${rowVirtualizer.getTotalSize()}px`, position: 'relative' }}>
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const message = messages[virtualRow.index];
              return (
                <div
                  key={message.id}
                  ref={virtualRow.measureElement}
                  className="absolute top-0 left-0 w-full"
                  style={{ transform: `translateY(${virtualRow.start}px)` }}
                >
                  <MessageBubble message={message} />
                </div>
              );
            })}
          </div>
        ) : (
          <div className="flex flex-col">
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
          </div>
        )}

        {isLoading && <ChatBubbleSkeleton />}

        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}