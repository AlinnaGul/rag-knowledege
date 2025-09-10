import { Skeleton } from "./skeleton";

export function CardSkeleton() {
  return <Skeleton className="h-32 w-full" />;
}

export function RowSkeleton() {
  return (
    <div className="flex items-center justify-between border-b border-border p-3">
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
      </div>
      <Skeleton className="h-4 w-6" />
    </div>
  );
}

export function ChatBubbleSkeleton() {
  return (
    <div className="flex items-start gap-3 py-4">
      <Skeleton className="h-8 w-8 rounded-full" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-3/5" />
        <Skeleton className="h-4 w-4/5" />
      </div>
    </div>
  );
}
