import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import AdminCard from "@/components/admin/AdminCard";
import AppShell from "@/components/layout/AppShell";

type Collection = {
  id: number;
  name: string;
  description?: string;
  doc_count?: number;
  created_at: string;
};

interface Doc {
  document_id: number;
  collections: { collection_id: number }[];
}

export default function Collections() {
  const token = useAuthStore((s) => s.token);
  const role = useAuthStore((s) => s.user?.role);
  const qc = useQueryClient();
  const { toast } = useToast();

  const {
    data: collections,
    isLoading,
    error,
    refetch,
  } = useQuery<Collection[]>({
    queryKey: ["admin-collections"],
    queryFn: adminApi.getCollections,
    enabled: !!token,
    staleTime: 10_000,
  });

  const [newCol, setNewCol] = useState({ name: "", description: "" });
  const [editing, setEditing] = useState<Collection | null>(null);

  const createCol = useMutation({
    mutationFn: () => adminApi.createCollection(newCol),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-collections"] });
      setNewCol({ name: "", description: "" });
    },
  });

  const updateCol = useMutation({
    mutationFn: (c: Collection) =>
      adminApi.updateCollection(String(c.id), {
        name: c.name,
        description: c.description,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-collections"] });
      setEditing(null);
    },
  });

  const deleteCol = useMutation({
    mutationFn: (id: number) => adminApi.deleteCollection(String(id)),
    onSuccess: (_data, id) => {
      qc.invalidateQueries({ queryKey: ["admin-collections"] });
      qc.invalidateQueries({ queryKey: ["admin-documents"] });
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      qc.invalidateQueries({ queryKey: ["admin-collection-docs"] });
      qc.setQueryData<{ items: Doc[] }>(["admin-documents"], (old) =>
        old
          ? {
              items: old.items.map((d) => ({
                ...d,
                collections: d.collections.filter((c) => c.collection_id !== id),
              })),
            }
          : old
      );
    },
  });

  if (!token)
    return <AppShell title="Collections"><div>Loading auth…</div></AppShell>;
  if (role !== "admin")
    return <AppShell title="Collections"><div>Access denied</div></AppShell>;
  if (isLoading)
    return <AppShell title="Collections"><div>Loading collections…</div></AppShell>;
  if (error)
    return (
      <AppShell title="Collections">
        <div className="text-destructive">
          Failed to load collections: {error instanceof Error ? error.message : String(error)}
          <Button className="ml-3" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      </AppShell>
    );

  return (
    <AppShell title="Collections">
      {/* Create */}
      <AdminCard title="Create collection" className="mb-8">
        <div className="grid gap-3 md:grid-cols-3">
          <Input
            placeholder="Name"
            value={newCol.name}
            onChange={(e) => setNewCol({ ...newCol, name: e.target.value })}
            disabled={createCol.isPending}
          />
          <Input
            placeholder="Description (optional)"
            value={newCol.description}
            onChange={(e) => setNewCol({ ...newCol, description: e.target.value })}
            disabled={createCol.isPending}
          />
          <Button
            disabled={createCol.isPending || !newCol.name}
            onClick={() =>
              createCol.mutate(undefined, {
                onSuccess: () => toast({ title: "Collection created" }),
                onError: (err) =>
                  toast({
                    variant: "destructive",
                    title: "Create failed",
                    description:
                      err instanceof Error ? err.message : String(err),
                  }),
              })
            }
          >
            {createCol.isPending ? "Creating…" : "Create"}
          </Button>
        </div>
        {createCol.isError && (
          <div className="text-destructive mt-2">
            {createCol.error instanceof Error
              ? createCol.error.message
              : "Create failed"}
          </div>
        )}
      </AdminCard>

      {/* List */}
      <section className="rounded-xl border border-border overflow-x-auto mb-8">
        {collections && collections.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="bg-muted">
              <tr>
                <th className="text-left px-3 py-2">Name</th>
                <th className="text-left px-3 py-2">Description</th>
                <th className="text-left px-3 py-2">Docs</th>
                <th className="text-left px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {collections.map((c) => (
                <tr key={c.id} className="border-t border-border">
                  <td className="px-3 py-2">
                    {editing?.id === c.id ? (
                      <Input
                        value={editing.name}
                        onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                        className="h-8"
                      />
                    ) : (
                      c.name
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {editing?.id === c.id ? (
                      <Input
                        value={editing.description ?? ""}
                        onChange={(e) =>
                          setEditing({ ...editing, description: e.target.value })
                        }
                        className="h-8"
                      />
                    ) : (
                      c.description ?? "-"
                    )}
                  </td>
                  <td className="px-3 py-2">{c.doc_count ?? 0}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-2">
                      {editing?.id === c.id ? (
                        <>
                          <Button
                            size="sm"
                            onClick={() =>
                              updateCol.mutate(editing!, {
                                onSuccess: () => toast({ title: "Collection updated" }),
                                onError: (err) =>
                                  toast({
                                    variant: "destructive",
                                    title: "Update failed",
                                    description:
                                      err instanceof Error
                                        ? err.message
                                        : String(err),
                                  }),
                              })
                            }
                          >
                            Save
                          </Button>
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => setEditing(null)}
                          >
                            Cancel
                          </Button>
                        </>
                      ) : (
                        <>
                          <Button asChild size="sm" variant="secondary">
                            <a href={`/admin/collections/${c.id}`}>Manage</a>
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setEditing(c)}
                          >
                            Edit
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => {
                              if (window.confirm("Delete collection?")) {
                                deleteCol.mutate(c.id, {
                                  onSuccess: () =>
                                    toast({ title: "Collection deleted" }),
                                  onError: (err) =>
                                    toast({
                                      variant: "destructive",
                                      title: "Delete failed",
                                      description:
                                        err instanceof Error
                                          ? err.message
                                          : String(err),
                                    }),
                                });
                              }
                            }}
                          >
                            Delete
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="p-6 text-center text-muted-foreground">
            No collections yet
          </div>
        )}
      </section>
    </AppShell>
  );
}
