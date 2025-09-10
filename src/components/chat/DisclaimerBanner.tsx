import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { X, AlertTriangle } from 'lucide-react';

interface DisclaimerBannerProps {
  text: string;
  onDismiss: () => void;
}

export function DisclaimerBanner({ text, onDismiss }: DisclaimerBannerProps) {
  if (!text) return null;
  return (
    <Alert className="rounded-none border-x-0 border-t-0 bg-warning/10 border-warning/20">
      <AlertTriangle className="h-4 w-4 text-warning" />
      <AlertDescription className="flex items-center justify-between">
        <div className="flex-1 pr-4">
          {text}
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onDismiss}
          className="shrink-0 h-6 w-6 p-0 text-warning hover:text-warning hover:bg-warning/10"
        >
          <X className="h-3 w-3" />
        </Button>
      </AlertDescription>
    </Alert>
  );
}