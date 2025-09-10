import { useMemo, useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { MoreVertical } from "lucide-react";

import { adminApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationPrevious,
  PaginationNext,
} from "@/components/ui/pagination";
import { useToast } from "@/hooks/use-toast";
import AppShell from "@/components/layout/AppShell";

interface DocCollection {
  collection_id: number;
  collection_name: string;
  status: string;
  progress: number | null;
}

interface Doc {
  document_id: number;
  title: string;
  mime: string;
  size_bytes: number;
  pages: number;
  sha256: string;
  collections: DocCollection[];
}

export default function AdminDocuments() {
  const token = useAuthStore((s) => s.token);
  const { toast } = useToast();
  const qc = useQueryClient();

  const { data, isLoading, isFetching, error, refetch } = useQuery<{ items: Doc[] }>({
    queryKey: ["admin-documents"],
    queryFn: () => adminApi.listAllDocuments(),
    enabled: !!token,
    staleTime: 10_000,
  });

  const [collectionFilter, setCollectionFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [pageSize, setPageSize] = useState(25);
  const [page, setPage] = useState(1);

  const rename = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) =>
      adminApi.updateDocument(String(id), { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-documents"] }),
  });

  const reindex = useMutation({
    mutationFn: ({ docId, collectionId }: { docId: number; collectionId: number }) =>
      adminApi.reindexDocument(String(collectionId), String(docId)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-documents"] }),
  });

  const unlink = useMutation({
    mutationFn: ({ docId, collectionId }: { docId: number; collectionId: number }) =>
      adminApi.unlinkDocument(String(collectionId), String(docId)),
    onSuccess: (_data, { collectionId, docId }) => {
      qc.invalidateQueries({ queryKey: ["admin-documents"] });
      qc.invalidateQueries({ queryKey: ["admin-collections"] });
      qc.invalidateQueries({ queryKey: ["admin-collection-docs", collectionId] });
      qc.setQueryData<{ items: Doc[] }>(["admin-documents"], (old) =>
        old
          ? {
              items: old.items.map((d) =>
                d.document_id === docId
                  ? {
                      ...d,
                      collections: d.collections.filter((c) => c.collection_id !== collectionId),
                    }
                  : d
              ),
            }
          : old
      );
    },
  });

  const purge = useMutation({
    mutationFn: (docId: number) => adminApi.purgeDocument(String(docId)),
    onSuccess: (_, docId) => {
      qc.setQueryData<{ items: Doc[] }>(["admin-documents"], (old) =>
        old ? { items: old.items.filter((d) => d.document_id !== docId) } : old
      );
      qc.invalidateQueries({ queryKey: ["admin-collections"] });
      qc.invalidateQueries({ queryKey: ["admin-collection-docs"] });
    },
  });

  useEffect(() => {
    setPage(1);
  }, [collectionFilter, statusFilter, pageSize]);

  const docs = data?.items ?? [];

  const collectionOptions = useMemo(() => {
    const map = new Map<number, string>();
    docs.forEach((d) =>
      d.collections.forEach((c) => map.set(c.collection_id, c.collection_name))
    );
    return Array.from(map.entries());
  }, [docs]);

  const statusOptions = useMemo(() => {
    const set = new Set<string>();
    docs.forEach((d) => d.collections.forEach((c) => set.add(c.status)));
    return Array.from(set);
  }, [docs]);

  const filteredDocs = useMemo(
    () =>
      docs.filter((d) => {
        const matchesCollection =
          collectionFilter === "all" ||
          d.collections.some(
            (c) => String(c.collection_id) === collectionFilter
          );
        const matchesStatus =
          statusFilter === "all" ||
          d.collections.some((c) => c.status === statusFilter);
        return matchesCollection && matchesStatus;
      }),
    [docs, collectionFilter, statusFilter]
  );

  const totalPages = Math.max(1, Math.ceil(filteredDocs.length / pageSize));
  const pageDocs = filteredDocs.slice(
    (page - 1) * pageSize,
    page * pageSize
  );

  if (!token)
    return (
      <AppShell title="Documents">
        <div>Loading auth…</div>
      </AppShell>
    );

  return (
    <AppShell title="Documents">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Select value={collectionFilter} onValueChange={setCollectionFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Collection" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All collections</SelectItem>
              {collectionOptions.map(([id, name]) => (
                <SelectItem key={id} value={String(id)}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              {statusOptions.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Select value={String(pageSize)} onValueChange={(v) => setPageSize(Number(v))}>
          <SelectTrigger className="w-[120px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="25">25 / page</SelectItem>
            <SelectItem value="50">50 / page</SelectItem>
            <SelectItem value="100">100 / page</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {error && (
        <div className="mb-4 text-destructive">
          Failed to load documents
          <Button className="ml-3" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      )}

      {/* Mobile list view */}
      <div className="sm:hidden">
        {isLoading || isFetching ? (
          Array.from({ length: pageSize }).map((_, i) => (
            <div key={i} className="border-b border-border p-3 space-y-2">
              <Skeleton className="h-4 w-3/4" />
              <Skeleton className="h-3 w-1/2" />
            </div>
          ))
        ) : pageDocs.length ? (
          pageDocs.map((d) => (
            <div key={d.document_id} className="border-b border-border p-3 space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{d.title}</div>
                  <div className="text-sm text-muted-foreground">
                    {Math.round(d.size_bytes / 1024)} KB
                  </div>
                </div>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon">
                      <MoreVertical className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      onClick={() => {
                        const title = prompt("New title", d.title);
                        if (title)
                          rename.mutate(
                            { id: d.document_id, title },
                            {
                              onSuccess: () => toast({ title: "Renamed" }),
                              onError: (err) =>
                                toast({
                                  variant: "destructive",
                                  title: "Rename failed",
                                  description:
                                    err instanceof Error
                                      ? err.message
                                      : String(err),
                                }),
                            }
                          );
                      }}
                    >
                      Rename
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      disabled={d.collections.length > 0}
                      onClick={() => {
                        if (window.confirm("Delete document?"))
                          purge.mutate(d.document_id, {
                            onSuccess: () => toast({ title: "Deleted" }),
                            onError: (err) => {
                              const apiErr = err as {
                                status?: number;
                                message?: string;
                              };
                              let description =
                                apiErr.message || "Delete failed";
                              if (apiErr.status === 409) {
                                description =
                                  "Document is still linked to a collection. Unlink it everywhere before deleting.";
                              }
                              toast({
                                variant: "destructive",
                                title: "Delete failed",
                                description,
                              });
                            },
                          });
                      }}
                    >
                      Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
              <div className="space-y-1">
                {d.collections.map((c) => (
                  <div
                    key={c.collection_id}
                    className="flex items-center justify-between gap-2 text-sm"
                  >
                    <span className="truncate">
                      {c.collection_name} ({c.status}
                      {typeof c.progress === "number"
                        ? ` ${Math.round(c.progress * 100)}%`
                        : ""}
                      )
                    </span>
                    <div className="flex gap-2">
                      <Button
                        size="xs"
                        onClick={() =>
                          reindex.mutate(
                            {
                              docId: d.document_id,
                              collectionId: c.collection_id,
                            },
                            {
                              onSuccess: () => toast({ title: "Reindex started" }),
                              onError: (err) =>
                                toast({
                                  variant: "destructive",
                                  title: "Reindex failed",
                                  description:
                                    err instanceof Error
                                      ? err.message
                                      : String(err),
                                }),
                            }
                          )
                        }
                      >
                        Reindex
                      </Button>
                      <Button
                        size="xs"
                        variant="destructive"
                        onClick={() =>
                          unlink.mutate(
                            {
                              docId: d.document_id,
                              collectionId: c.collection_id,
                            },
                            {
                              onSuccess: () => toast({ title: "Unlinked" }),
                              onError: (err) =>
                                toast({
                                  variant: "destructive",
                                  title: "Unlink failed",
                                  description:
                                    err instanceof Error
                                      ? err.message
                                      : String(err),
                                }),
                            }
                          )
                        }
                      >
                        Unlink
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))
        ) : (
          <div className="py-10 text-center text-sm text-muted-foreground">
            {collectionFilter !== "all" || statusFilter !== "all"
              ? "No documents match the selected filters."
              : "No documents yet. Upload documents from a collection to get started."}
          </div>
        )}
      </div>

      {/* Desktop table view */}
      <div className="hidden sm:block rounded-xl border border-border overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-muted">
            <tr>
              <th className="w-[40%] px-3 py-2 text-left">Title</th>
              <th className="px-3 py-2 text-left">Size</th>
              <th className="px-3 py-2 text-left">Collections</th>
              <th className="w-10 px-3 py-2 text-left">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading || isFetching
              ? Array.from({ length: pageSize }).map((_, i) => (
                  <tr key={i} className="border-t border-border">
                    <td className="px-3 py-2">
                      <Skeleton className="h-4 w-3/4" />
                    </td>
                    <td className="px-3 py-2">
                      <Skeleton className="h-4 w-16" />
                    </td>
                    <td className="px-3 py-2">
                      <Skeleton className="h-4 w-1/2" />
                    </td>
                    <td className="px-3 py-2">
                      <Skeleton className="h-4 w-6" />
                    </td>
                  </tr>
                ))
              : pageDocs.length
              ? pageDocs.map((d) => (
                  <tr
                    key={d.document_id}
                    className="border-t border-border align-top"
                  >
                    <td className="max-w-xs px-3 py-2 truncate">
                      {d.title}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {Math.round(d.size_bytes / 1024)} KB
                    </td>
                    <td className="px-3 py-2 space-y-2">
                      {d.collections.map((c) => (
                        <div
                          key={c.collection_id}
                          className="flex items-center justify-between gap-2"
                        >
                          <span className="truncate">
                            {c.collection_name} ({c.status}
                            {typeof c.progress === "number"
                              ? ` ${Math.round(c.progress * 100)}%`
                              : ""}
                            )
                          </span>
                          <div className="flex gap-2">
                            <Button
                              size="xs"
                              onClick={() =>
                                reindex.mutate(
                                  {
                                    docId: d.document_id,
                                    collectionId: c.collection_id,
                                  },
                                  {
                                    onSuccess: () =>
                                      toast({ title: "Reindex started" }),
                                    onError: (err) =>
                                      toast({
                                        variant: "destructive",
                                        title: "Reindex failed",
                                        description:
                                          err instanceof Error
                                            ? err.message
                                            : String(err),
                                      }),
                                  }
                                )
                              }
                            >
                              Reindex
                            </Button>
                            <Button
                              size="xs"
                              variant="destructive"
                              onClick={() =>
                                unlink.mutate(
                                  {
                                    docId: d.document_id,
                                    collectionId: c.collection_id,
                                  },
                                  {
                                    onSuccess: () =>
                                      toast({ title: "Unlinked" }),
                                    onError: (err) =>
                                      toast({
                                        variant: "destructive",
                                        title: "Unlink failed",
                                        description:
                                          err instanceof Error
                                            ? err.message
                                            : String(err),
                                      }),
                                  }
                                )
                              }
                            >
                              Unlink
                            </Button>
                          </div>
                        </div>
                      ))}
                    </td>
                    <td className="px-3 py-2">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon">
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => {
                              const title = prompt("New title", d.title);
                              if (title)
                                rename.mutate(
                                  { id: d.document_id, title },
                                  {
                                    onSuccess: () => toast({ title: "Renamed" }),
                                    onError: (err) =>
                                      toast({
                                        variant: "destructive",
                                        title: "Rename failed",
                                        description:
                                          err instanceof Error
                                            ? err.message
                                            : String(err),
                                      }),
                                  }
                                );
                            }}
                          >
                            Rename
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            disabled={d.collections.length > 0}
                            onClick={() => {
                              if (window.confirm("Delete document?"))
                                purge.mutate(d.document_id, {
                                  onSuccess: () =>
                                    toast({ title: "Deleted" }),
                                  onError: (err) => {
                                    const apiErr = err as {
                                      status?: number;
                                      message?: string;
                                    };
                                    let description =
                                      apiErr.message || "Delete failed";
                                    if (apiErr.status === 409) {
                                      description =
                                        "Document is still linked to a collection. Unlink it everywhere before deleting.";
                                    }
                                    toast({
                                      variant: "destructive",
                                      title: "Delete failed",
                                      description,
                                    });
                                  },
                                });
                            }}
                          >
                            Delete
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </td>
                  </tr>
                ))
              : (
                  <tr>
                    <td
                      colSpan={4}
                      className="px-3 py-10 text-center text-sm text-muted-foreground"
                    >
                      {collectionFilter !== "all" || statusFilter !== "all"
                        ? "No documents match the selected filters."
                        : "No documents yet. Upload documents from a collection to get started."}
                    </td>
                  </tr>
                )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between">
        <Pagination>
          <PaginationContent>
            <PaginationItem>
              <PaginationPrevious
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  setPage((p) => Math.max(1, p - 1));
                }}
                className={page === 1 ? "pointer-events-none opacity-50" : undefined}
              />
            </PaginationItem>
            <PaginationItem>
              <PaginationLink href="#" isActive>
                {page}
              </PaginationLink>
            </PaginationItem>
            <PaginationItem>
              <PaginationNext
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  setPage((p) => Math.min(totalPages, p + 1));
                }}
                className={
                  page === totalPages ? "pointer-events-none opacity-50" : undefined
                }
              />
            </PaginationItem>
          </PaginationContent>
        </Pagination>
        <div className="text-sm text-muted-foreground">
          {filteredDocs.length} items
        </div>
      </div>
    </AppShell>
  );
}
