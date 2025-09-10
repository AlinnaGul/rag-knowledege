import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { meApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import AppShell from "@/components/layout/AppShell";
import { RowSkeleton } from "@/components/ui/skeletons";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBanner } from "@/components/ui/error-banner";
import type { AxiosError } from "axios";

interface Doc {
  document_id: number;
  title: string;
  size_bytes: number;
}

export default function MyCollection() {
  const { id } = useParams<{ id: string }>();
  const { token, user } = useAuthStore((s) => ({ token: s.token, user: s.user }));

  const numericId = Number(id);
  const isNewCollection = !id || isNaN(numericId);

  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery<{ items: Doc[] }>({
    queryKey: ["my-collection-docs", id],
    queryFn: () => meApi.listCollectionDocs(String(numericId)),
    enabled: !!token && !isNewCollection,
    staleTime: 10_000,
  });

  const isAdmin = user?.role === "admin" || user?.role === "superadmin";

  if (!token)
    return <AppShell title="Documents"><div className="p-6">Loading auth…</div></AppShell>;

  if (isNewCollection)
    return (
      <AppShell title="New Collection">
        <EmptyState
          title="Create a collection"
          description="Collections are created in the admin section."
          action={
            <Button asChild>
              <Link to={isAdmin ? "/admin/collections" : "/collections"}>
                {isAdmin ? "Go to Admin" : "Back to Collections"}
              </Link>
            </Button>
          }
        />
      </AppShell>
    );

  if (isLoading)
    return (
      <AppShell title="Documents">
        <div className="rounded-xl border border-border overflow-hidden">
          {Array.from({ length: 3 }).map((_, i) => (
            <RowSkeleton key={i} />
          ))}
        </div>
      </AppShell>
    );
  if (error) {
    const status = (error as AxiosError)?.response?.status;
    const message =
      status === 403
        ? "Access denied to this collection"
        : status === 404
        ? "Collection not found"
        : "Failed to load documents";
    return (
      <AppShell title="Documents">
        <ErrorBanner message={message} className="mb-4" />
        {status === 403 || status === 404 ? (
          <Button asChild>
            <Link to="/collections">Back to Collections</Link>
          </Button>
        ) : (
          <Button onClick={() => refetch()}>Retry</Button>
        )}
      </AppShell>
    );
  }

  const docs = data?.items ?? [];

  return (
    <AppShell title="Documents">
      <section className="mb-8">
        <div className="rounded-xl border border-border overflow-x-auto">
          {docs.length > 0 ? (
            <table className="w-full text-sm">
              <thead className="bg-muted">
                <tr>
                  <th className="text-left px-3 py-2">Title</th>
                  <th className="text-left px-3 py-2">Size</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr key={d.document_id} className="border-t border-border">
                    <td className="px-3 py-2">{d.title}</td>
                    <td className="px-3 py-2">{Math.round(d.size_bytes / 1024)} KB</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <EmptyState
              title="No documents"
              description="Upload files to populate this collection."
              action={
                isAdmin ? (
                  <Button asChild>
                    <Link to={`/collections/${id}/upload`}>Upload</Link>
                  </Button>
                ) : undefined
              }
            />
          )}
        </div>
      </section>
    </AppShell>
  );
}
