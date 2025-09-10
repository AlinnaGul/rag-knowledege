import { AlertCircle, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface ErrorBannerProps {
  message: string;
  className?: string;
  onClose?: () => void;
}

export function ErrorBanner({ message, className, onClose }: ErrorBannerProps) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-4 py-2 text-sm text-destructive",
        className
      )}
      role="alert"
    >
      <AlertCircle className="mt-0.5 h-4 w-4" />
      <p className="flex-1">{message}</p>
      {onClose && (
        <button
          onClick={onClose}
          className="ml-2 text-destructive transition-colors hover:text-destructive/80"
        >
          <X className="h-4 w-4" />
          <span className="sr-only">Dismiss</span>
        </button>
      )}
    </div>
  );
}

export default ErrorBanner;
