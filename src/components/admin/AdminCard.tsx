import { ReactNode } from "react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface AdminCardProps {
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}

export default function AdminCard({ title, children, footer, className }: AdminCardProps) {
  return (
    <Card className={cn("p-4", className)}>
      <h2 className="font-medium mb-3">{title}</h2>
      {children}
      {footer && <div className="mt-4">{footer}</div>}
    </Card>
  );
}
