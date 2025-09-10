import { Citation } from '@/stores/chat';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { X, FileText, Book, Folder } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CitationDrawerProps {
  open: boolean;
  onClose: () => void;
  citation: Citation | null;
}

export function CitationDrawer({ open, onClose, citation }: CitationDrawerProps) {
  if (!open || !citation) return null;

  return (
    <>
      {/* Overlay */}
      <div 
        className="fixed inset-0 bg-black/20 z-40"
        onClick={onClose}
      />
      
      {/* Drawer */}
      <div className={cn(
        "fixed right-0 top-0 h-full w-full max-w-md bg-card border-l shadow-lg z-50 transform transition-transform duration-200 ease-in-out",
        open ? "translate-x-0" : "translate-x-full"
      )}>
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between p-4 border-b">
            <h2 className="text-lg font-semibold">Citation Details</h2>
            <Button variant="ghost" size="sm" onClick={onClose}>
              <X className="h-4 w-4" />
            </Button>
          </div>

          {/* Content */}
          <ScrollArea className="flex-1 p-4">
            <div className="space-y-6">
              {/* Document Info */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <FileText className="h-5 w-5 text-primary" />
                  <h3 className="font-medium">Document</h3>
                </div>
                <div className="space-y-2 pl-7">
                  <p className="font-medium">{citation.filename}</p>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">
                      Page {citation.page}
                    </Badge>
                  </div>
                  {citation.url && (
                    <a
                      href={citation.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-primary underline"
                    >
                      View source
                    </a>
                  )}
                </div>
              </div>

              <Separator />

              {/* Collection Info */}
              <div>
                <div className="flex items-center gap-2 mb-3">
                  <Folder className="h-5 w-5 text-primary" />
                  <h3 className="font-medium">Collection</h3>
                </div>
                <div className="pl-7">
                  <p className="text-sm text-muted-foreground">{citation.collection}</p>
                </div>
              </div>

              <Separator />

              {/* Snippet */}
              <div>
              <div className="flex items-center gap-2 mb-3">
                <Book className="h-5 w-5 text-primary" />
                <h3 className="font-medium">Relevant Excerpt</h3>
              </div>
              <div className="pl-7">
                <div className="bg-muted/50 p-3 rounded-md">
                  <p className="text-sm leading-relaxed">
                    {citation.snippet}
                  </p>
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  This excerpt was found to be relevant to your question.
                </p>
              </div>
            </div>

              {/* Metadata */}
              <div className="space-y-2 text-xs text-muted-foreground bg-muted/30 p-3 rounded-md">
                <div className="flex justify-between">
                  <span>Citation ID:</span>
                  <span className="font-mono">{citation.id}</span>
                </div>
                <div className="flex justify-between">
                  <span>Page Number:</span>
                  <span>{citation.page}</span>
                </div>
              </div>
            </div>
          </ScrollArea>

          {/* Footer */}
          <div className="p-4 border-t bg-muted/20">
            <p className="text-xs text-muted-foreground text-center">
              Citations help verify the accuracy of AI responses by showing source materials.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}