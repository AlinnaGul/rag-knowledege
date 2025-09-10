import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { meApi, adminApi } from "@/lib/api";
import type { AxiosError } from "axios";
import { useAuthStore } from "@/stores/auth";
import AppShell from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { CardSkeleton } from "@/components/ui/skeletons";
import { ErrorBanner } from "@/components/ui/error-banner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Link } from "react-router-dom";
import { MoreVertical } from "lucide-react";

interface Collection {
  id: number;
  name: string;
  doc_count: number;
  updated_at: string;
}

export default function MyCollections() {
  const { token, user } = useAuthStore((s) => ({ token: s.token, user: s.user }));
  const isAdmin = user?.role === "admin" || user?.role === "superadmin";
  const { data, isLoading, error, refetch } = useQuery<Collection[]>({
    queryKey: [isAdmin ? "admin-collections" : "my-collections"],
    queryFn: isAdmin ? adminApi.getCollections : meApi.listCollections,
    enabled: !!token,
    staleTime: 10_000,
  });

  const cols = data ?? [];

  const [filter, setFilter] = useState("");
  const [debounced, setDebounced] = useState(filter);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(filter), 300);
    return () => clearTimeout(id);
  }, [filter]);

  const filtered = useMemo(
    () => cols.filter((c) => c.name.toLowerCase().includes(debounced.toLowerCase())),
    [cols, debounced],
  );

  if (!token)
    return <AppShell title="Collections"><div className="p-6">Loading auth…</div></AppShell>;
  if (isLoading)
    return (
      <AppShell title="Collections">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <CardSkeleton key={i} />
          ))}
        </div>
      </AppShell>
    );
  if (error) {
    const status = (error as AxiosError)?.response?.status;
    const message = status === 403 ? "Access denied" : "Failed to load collections";
    return (
      <AppShell title="Collections">
        <ErrorBanner message={message} className="mb-4" />
        {status !== 403 && <Button onClick={() => refetch()}>Retry</Button>}
      </AppShell>
    );
  }

  return (
    <AppShell title="Collections">
      <section className="mb-8">
        <div className="sticky top-0 z-10 mb-4 flex flex-col gap-4 bg-background pb-4 sm:flex-row sm:items-center sm:justify-between">
          <Input
            placeholder="Filter collections"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="sm:max-w-xs"
          />
          {isAdmin && (
            <Button asChild>
              <Link to="/collections/new">New Collection</Link>
            </Button>
          )}
        </div>
        {filtered.length > 0 ? (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {filtered.map((c) => (
              <Card key={c.id} className="flex flex-col justify-between p-4">
                <div>
                  <h3 className="font-medium leading-none">{c.name}</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {c.doc_count ?? 0} docs · {new Date(c.updated_at).toLocaleDateString()}
                  </p>
                </div>
                <div className="mt-4 flex items-center gap-2">
                  <Button asChild size="sm">
                    <Link to={`/collections/${c.id}`}>Open</Link>
                  </Button>
                  {isAdmin && (
                    <>
                      <Button asChild size="sm" variant="secondary">
                        <Link to={`/collections/${c.id}/upload`}>Upload</Link>
                      </Button>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="ml-auto h-8 w-8">
                            <MoreVertical className="h-4 w-4" />
                            <span className="sr-only">More options</span>
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem asChild>
                            <Link to={`/collections/${c.id}/edit`}>Rename</Link>
                          </DropdownMenuItem>
                          <DropdownMenuItem className="text-destructive">
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </>
                  )}
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <EmptyState
            title={isAdmin ? "No collections" : "No collections assigned"}
            description={
              isAdmin
                ? "Create a new collection to start organizing documents."
                : "You don't have any collections assigned."
            }
            action={
              isAdmin ? (
                <Button asChild>
                  <Link to="/collections/new">New Collection</Link>
                </Button>
              ) : undefined
            }
          />
        )}
      </section>
    </AppShell>
  );
}
