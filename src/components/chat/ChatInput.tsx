import { useState, useRef, useEffect } from 'react';
import { useChatStore } from '@/stores/chat';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ErrorBanner } from '@/components/ui/error-banner';
import { Send, RotateCcw, Square } from 'lucide-react';
import { cn } from '@/lib/utils';

export function ChatInput() {
  const [input, setInput] = useState('');
  const [isComposing, setIsComposing] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  
  const { sendMessage, isLoading, currentSession, stopGeneration, regenerate, messages, error, clearError } = useChatStore();

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [input]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!input.trim() || isLoading || !currentSession) return;
    
    const message = input.trim();
    setInput('');
    
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
    
    await sendMessage(message);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      if (e.shiftKey || isComposing) {
        // Allow new line with Shift+Enter or during IME composition
        return;
      } else {
        // Submit with Enter
        e.preventDefault();
        handleSubmit(e);
      }
    }
  };

  const isDisabled = isLoading || !currentSession;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      {error && <ErrorBanner message={error} onClose={clearError} className="mb-2" />}
      <div className="relative">
        <Textarea
          id="chat-input"
          ref={textareaRef}
          value={input}
          onChange={(e) => {
            clearError();
            setInput(e.target.value);
          }}
          onKeyDown={handleKeyDown}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          placeholder={
            currentSession 
              ? "Ask a question about your knowledge base..." 
              : "Create or select a chat session to start"
          }
          disabled={isDisabled}
          className={cn(
            "min-h-[60px] max-h-[200px] pr-12 resize-none p-3",
            "focus:ring-2 focus:ring-primary"
          )}
          rows={1}
        />
        <Button
          type="submit"
          size="sm"
          disabled={isDisabled || !input.trim()}
          className="absolute right-2 top-2 h-10 w-10 p-0"
        >
          <Send className="h-5 w-5" />
        </Button>
      </div>

      <div className="flex justify-end gap-2">
        {isLoading ? (
          <Button type="button" size="sm" variant="ghost" onClick={stopGeneration} className="h-8">
            <Square className="h-4 w-4 mr-1" /> Stop
          </Button>
        ) : messages.length > 0 ? (
          <Button type="button" size="sm" variant="ghost" onClick={regenerate} className="h-8">
            <RotateCcw className="h-4 w-4 mr-1" /> Regenerate
          </Button>
        ) : null}
      </div>
      
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <div className="flex items-center gap-4">
          <span>
            Press <kbd className="px-1 py-0.5 bg-muted rounded text-xs">Enter</kbd> to send,{' '}
            <kbd className="px-1 py-0.5 bg-muted rounded text-xs">Shift + Enter</kbd> for new line
          </span>
        </div>
        
        {input && (
          <span className={cn(
            "transition-colors",
            input.length > 4000 ? "text-destructive" : "text-muted-foreground"
          )}>
            {input.length}/4000
          </span>
        )}
      </div>
    </form>
  );
}