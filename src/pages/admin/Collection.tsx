import { useParams } from "react-router-dom";
import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { useToast } from "@/hooks/use-toast";
import AdminCard from "@/components/admin/AdminCard";
import AppShell from "@/components/layout/AppShell";

interface Doc {
  document_id: number;
  title: string;
  mime: string;
  size_bytes: number;
  status: string;
  progress: number | null;
  created_at: string;
}

interface CollectionInfo {
  id: number;
  name: string;
}

type QueuedFile = {
  file: File;
  status: "Queued" | "Parsing" | "Embedding" | "Done";
  progress: number;
};

export default function Collection() {
  const { id } = useParams<{ id: string }>();
  const token = useAuthStore((s) => s.token);
  const qc = useQueryClient();
  const { toast } = useToast();

  const {
    data,
    isLoading,
    error,
    refetch,
  } = useQuery<{ items: Doc[] }>({
    queryKey: ["admin-collection-docs", id],
    queryFn: () => adminApi.getDocuments(id!),
    enabled: !!token && !!id,
    staleTime: 10_000,
  });

  const [queue, setQueue] = useState<QueuedFile[]>([]);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const { data: collInfo } = useQuery<CollectionInfo | undefined>({
    queryKey: ["admin-collection", id],
    queryFn: async () => {
      const list = await adminApi.getCollections();
      return list.find((c: CollectionInfo) => c.id === Number(id));
    },
    enabled: !!token && !!id,
  });

  const handleFiles = (fs: File[]) => {
    const items = fs.map((f) => ({ file: f, status: "Queued" as const, progress: 0 }));
    setQueue((prev) => [...prev, ...items]);
  };

  const upload = useMutation({
    mutationFn: async (items: QueuedFile[]) => {
      for (const q of items) {
        setQueue((prev) =>
          prev.map((f) =>
            f.file === q.file ? { ...f, status: "Parsing", progress: 25 } : f
          )
        );
        await adminApi.uploadDocument(id!, q.file);
        setQueue((prev) =>
          prev.map((f) =>
            f.file === q.file ? { ...f, status: "Embedding", progress: 66 } : f
          )
        );
        setQueue((prev) =>
          prev.map((f) =>
            f.file === q.file ? { ...f, status: "Done", progress: 100 } : f
          )
        );
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-collection-docs", id] });
      setQueue([]);
    },
  });

  const rename = useMutation({
    mutationFn: ({ docId, title }: { docId: number; title: string }) =>
      adminApi.updateDocument(String(docId), { title }),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin-collection-docs", id] }),
  });

  const reindex = useMutation({
    mutationFn: (docId: number) =>
      adminApi.reindexDocument(id!, String(docId)),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["admin-collection-docs", id] }),
  });

  const unlink = useMutation({
    mutationFn: (docId: number) =>
      adminApi.unlinkDocument(id!, String(docId)),
    onSuccess: (_data, docId) => {
      qc.invalidateQueries({ queryKey: ["admin-collection-docs", id] });
      qc.invalidateQueries({ queryKey: ["admin-documents"] });
      qc.invalidateQueries({ queryKey: ["admin-collections"] });
      qc.setQueryData<{ items: Doc[] }>(["admin-collection-docs", id], (old) =>
        old
          ? {
              items: old.items.filter((d) => d.document_id !== docId),
            }
          : old
      );
    },
  });

  const purge = useMutation({
    mutationFn: (docId: number) => adminApi.purgeDocument(String(docId)),
    onSuccess: (_, docId) => {
      qc.setQueryData<{ items: Doc[] }>(
        ["admin-collection-docs", id],
        (old) => (old ? { items: old.items.filter((d) => d.document_id !== docId) } : old)
      );
      qc.invalidateQueries({ queryKey: ["admin-documents"] });
      qc.invalidateQueries({ queryKey: ["admin-collections"] });
      qc.invalidateQueries({ queryKey: ["admin-collection-docs"] });
    },
  });

  if (!token)
    return <AppShell title="Collection"><div>Loading auth…</div></AppShell>;
  if (isLoading)
    return <AppShell title="Collection"><div>Loading collection…</div></AppShell>;
  if (error)
    return (
      <AppShell title="Collection">
        <div className="text-destructive">
          Failed to load documents: {error instanceof Error ? error.message : String(error)}
          <Button className="ml-3" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      </AppShell>
    );

  const docs = data?.items ?? [];

  const statusCounts = docs.reduce(
    (acc, d) => {
      acc[d.status] = (acc[d.status] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>
  );

  return (
    <AppShell title={collInfo ? collInfo.name : `Collection ${id}`}>
      <div className="space-y-8">
        <AdminCard title="Overview">
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <div className="text-sm text-muted-foreground">Documents</div>
              <div className="text-2xl font-semibold">{docs.length}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Processing</div>
              <div className="text-2xl font-semibold">
                {(statusCounts["queued"] || 0) +
                  (statusCounts["parsing"] || 0) +
                  (statusCounts["embedding"] || 0)}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Completed</div>
              <div className="text-2xl font-semibold">
                {statusCounts["done"] || statusCounts["completed"] || 0}
              </div>
            </div>
          </div>
        </AdminCard>

        <AdminCard title="Documents">
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              handleFiles(Array.from(e.dataTransfer.files));
            }}
            className="mb-4 flex flex-col items-center justify-center rounded-md border-2 border-dashed p-8 text-sm text-muted-foreground"
          >
            Drag & drop files here or
            <Button
              variant="secondary"
              className="mt-2"
              onClick={() => fileInput.current?.click()}
            >
              Browse
            </Button>
            <Input
              ref={fileInput}
              type="file"
              multiple
              className="hidden"
              onChange={(e) => handleFiles(Array.from(e.target.files || []))}
            />
          </div>

          {queue.length > 0 && (
            <ul className="mb-6 space-y-2">
              {queue.map((q) => (
                <li
                  key={q.file.name}
                  className="flex items-center gap-3 text-sm"
                >
                  <span className="flex-1 truncate">{q.file.name}</span>
                  <Badge>{q.status}</Badge>
                  <Progress className="h-2 w-32" value={q.progress} />
                </li>
              ))}
            </ul>
          )}

          <Button
            disabled={queue.length === 0 || upload.isPending}
            onClick={() =>
              queue.length > 0 &&
              upload.mutate(queue, {
                onSuccess: () => toast({ title: "Upload complete" }),
                onError: (err) =>
                  toast({
                    variant: "destructive",
                    title: "Upload failed",
                    description:
                      err instanceof Error ? err.message : String(err),
                  }),
              })
            }
          >
            {upload.isPending ? "Uploading…" : "Start upload"}
          </Button>
          {upload.isError && (
            <div className="text-destructive mt-2">
              {upload.error instanceof Error
                ? upload.error.message
                : "Upload failed"}
            </div>
          )}

          <div className="mt-8 rounded-xl border border-border overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted">
                <tr>
                  <th className="text-left px-3 py-2">Title</th>
                  <th className="text-left px-3 py-2">MIME</th>
                  <th className="text-left px-3 py-2">Size</th>
                  <th className="text-left px-3 py-2">Status</th>
                  <th className="text-left px-3 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((d) => (
                  <tr
                    key={d.document_id}
                    className="border-t border-border align-top"
                  >
                    <td className="px-3 py-2">{d.title}</td>
                    <td className="px-3 py-2">{d.mime}</td>
                    <td className="px-3 py-2">
                      {Math.round(d.size_bytes / 1024)} KB
                    </td>
                    <td className="px-3 py-2">
                      <Badge className="mr-2">
                        {d.status}
                      </Badge>
                      {typeof d.progress === "number" && (
                        <span>{Math.round(d.progress * 100)}%</span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-2">
                        <div className="flex gap-1">
                          <Button
                            size="xs"
                            onClick={() =>
                              reindex.mutate(d.document_id, {
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
                              })
                            }
                          >
                            Reindex
                          </Button>
                          <Button
                            size="xs"
                            variant="outline"
                            onClick={() =>
                              toast({ title: "Re-embed started" })
                            }
                          >
                            Re-embed
                          </Button>
                        </div>
                        <Button
                          size="xs"
                          variant="destructive"
                          onClick={() =>
                            unlink.mutate(d.document_id, {
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
                            })
                          }
                        >
                          Unlink
                        </Button>
                        <Button
                          size="xs"
                          onClick={() => {
                            const title = prompt("New title", d.title);
                            if (title)
                              rename.mutate({
                                docId: d.document_id,
                                title,
                              }, {
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
                              });
                          }}
                        >
                          Rename
                        </Button>
                        <Button
                          size="xs"
                          variant="destructive"
                          onClick={() =>
                            window.confirm("Delete document?") &&
                            purge.mutate(d.document_id, {
                              onSuccess: () => toast({ title: "Deleted" }),
                              onError: (err) => {
                                const apiErr = err as {
                                  status?: number;
                                  message?: string;
                                };
                                let description = apiErr.message || "Delete failed";
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
                            })
                          }
                        >
                          Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </AdminCard>

        <AdminCard title="Settings">
          <div className="flex flex-wrap gap-2">
            <Button size="sm" onClick={() => toast({ title: "Reindex started" })}>
              Reindex collection
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => toast({ title: "Re-embed started" })}
            >
              Re-embed collection
            </Button>
          </div>
        </AdminCard>
      </div>
    </AppShell>
  );
}

