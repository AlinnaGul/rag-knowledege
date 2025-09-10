import { useState } from 'react';
import { Message, Citation } from '@/stores/chat';
import { useChatStore } from '@/stores/chat';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { CitationDrawer } from './CitationDrawer';
import {
  Copy,
  ThumbsUp,
  ThumbsDown,
  User,
  Bot,
  Check,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useToast } from '@/hooks/use-toast';
import ReactMarkdown from 'react-markdown';
import { chatApi } from '@/lib/api';

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const [copied, setCopied] = useState(false);
  const [citationDrawerOpen, setCitationDrawerOpen] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(message.feedback ?? null);

  const { toast } = useToast();

  const isUser = message.role === 'user';

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
      toast({
        title: 'Copied to clipboard',
        description: 'Message content has been copied.',
      });
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Failed to copy',
        description: 'Could not copy message to clipboard.',
      });
    }
  };

  const handleFeedback = async (type: 'up' | 'down') => {
    if (!message.query_id) return;
    try {
      await chatApi.sendFeedback(message.query_id, type);
      setFeedback(type);
      toast({
        title: 'Feedback sent',
        description: 'Thank you for your feedback!',
      });
    } catch (error) {
      toast({
        variant: 'destructive',
        title: 'Failed to send feedback',
        description: 'Could not record your feedback.',
      });
    }
  };

  const handleCitationClick = (citation: Citation) => {
    setSelectedCitation(citation);
    setCitationDrawerOpen(true);
  };

  const { settings } = useChatStore();

  return (
    <div className={cn('py-4', settings.compactMode && 'py-2')}>
      <div className={cn('flex gap-3 group', isUser && 'flex-row-reverse')}>
        <Avatar className={cn('w-8 h-8 shrink-0', isUser ? 'bg-muted' : 'bg-primary')}>
          <AvatarFallback className={cn(isUser ? 'bg-muted text-muted-foreground' : 'bg-primary text-primary-foreground')}>
            {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
          </AvatarFallback>
        </Avatar>

        <div className={cn('flex-1 min-w-0', isUser && 'flex justify-end')}>
          <div
            className={cn(
              'rounded-md text-sm',
              isUser
                ? 'bg-primary text-primary-foreground px-3 py-2 max-w-[80%] ml-auto'
                : 'bg-card border shadow-sm px-4 py-3'
            )}
          >
            <div className="prose prose-sm max-w-none dark:prose-invert">
              {isUser ? (
                <p className="mb-0">{message.content}</p>
              ) : (
                <ReactMarkdown
                  components={{
                    p: ({ children }) => <p className="mb-4 last:mb-0">{children}</p>,
                    ul: ({ children }) => <ul className="list-disc pl-4 mb-4">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal pl-4 mb-4">{children}</ol>,
                    li: ({ children }) => <li className="mb-1">{children}</li>,
                    img: (props) =>
                      settings.showImages ? (
                        <img {...props} className="my-2 max-w-full rounded" />
                      ) : null,
                    code: ({ children, className }) => {
                      const isInline = !className;
                      const content = String(children);
                      return isInline ? (
                        <code className="bg-accent px-1 py-0.5 rounded text-sm">{content}</code>
                      ) : (
                        <pre className="group relative bg-accent p-3 rounded-md text-sm overflow-x-auto">
                          <button
                            onClick={() => navigator.clipboard.writeText(content)}
                            className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition"
                          >
                            <Copy className="h-4 w-4" />
                          </button>
                          <code>{content}</code>
                        </pre>
                      );
                    },
                  }}
                >
                  {message.content}
                </ReactMarkdown>
              )}
            </div>

            {message.citations && message.citations.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1">
                <TooltipProvider>
                  {message.citations.slice(0, 3).map((citation, index) => {
                    const title = citation.filename
                      .replace(/\.[^/.]+$/, '')
                      .replace(/[_-]+/g, ' ');
                    const snippet = citation.snippet
                      .split('\n')
                      .slice(0, 3)
                      .join(' ');
                    return (
                      <Tooltip key={index}>
                        <TooltipTrigger asChild>
                          <Badge
                            variant="secondary"
                            className="cursor-pointer hover:bg-secondary/80 text-xs"
                            onClick={() => handleCitationClick(citation)}
                          >
                            [{index + 1}] {title} (p. {citation.page})
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs text-xs">{snippet}</TooltipContent>
                      </Tooltip>
                    );
                  })}
                </TooltipProvider>
              </div>
            )}
          </div>

          {!isUser && (
            <div className="flex items-center gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
              <Button variant="ghost" size="sm" onClick={handleCopy} className="h-7 px-2">
                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleFeedback('up')}
                className={cn('h-7 px-2', feedback === 'up' && 'text-success')}
              >
                <ThumbsUp className="h-3 w-3" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleFeedback('down')}
                className={cn('h-7 px-2', feedback === 'down' && 'text-destructive')}
              >
                <ThumbsDown className="h-3 w-3" />
              </Button>
            </div>
          )}

          <div className={cn('text-xs text-muted-foreground mt-1', isUser && 'text-right')}>
            {message.timestamp.toLocaleTimeString([], {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
        </div>
      </div>

      <CitationDrawer
        open={citationDrawerOpen}
        onClose={() => setCitationDrawerOpen(false)}
        citation={selectedCitation}
      />
    </div>
  );
}
