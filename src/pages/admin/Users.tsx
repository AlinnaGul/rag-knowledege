import { useMemo, useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { useToast } from "@/hooks/use-toast";
import AppShell from "@/components/layout/AppShell";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { MoreVertical } from "lucide-react";

type User = {
  id: number;
  name: string;
  email: string;
  role: "admin" | "user";
  active: boolean;
  last_active?: string;
};

type Collection = {
  id: number;
  name: string;
};

export default function Users() {
  const token = useAuthStore((s) => s.token);
  const qc = useQueryClient();
  const { toast } = useToast();

  const {
    data: users,
    isLoading,
    error,
    refetch,
  } = useQuery<User[]>({
    queryKey: ["admin-users"],
    queryFn: adminApi.getUsers,
    enabled: !!token,
    staleTime: 10_000,
  });

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm] = useState({
    name: "",
    email: "",
    password: "",
    role: "user" as "user" | "admin",
    active: true,
    top_k: 6,
    mmr_lambda: 0.5,
    temperature: 0.2,
  });
  const [errors, setErrors] = useState<{
    name?: string;
    email?: string;
    password?: string;
  }>({});
  const [selected, setSelected] = useState<number[]>([]);

  const [assignDialogOpen, setAssignDialogOpen] = useState(false);
  const [assigning, setAssigning] = useState<User | null>(null);
  const [assignedCols, setAssignedCols] = useState<number[]>([]);

  const { data: collections } = useQuery<Collection[]>({
    queryKey: ["admin-collections"],
    queryFn: adminApi.getCollections,
    enabled: !!token && assignDialogOpen,
    staleTime: 10_000,
  });

  const {
    data: userCols,
    isLoading: loadingUserCols,
  } = useQuery<{ assigned: number[] }>({
    queryKey: ["admin-user-collections", assigning?.id],
    queryFn: () => adminApi.getUserCollections(String(assigning!.id)),
    enabled: !!token && assignDialogOpen && !!assigning,
  });

  useEffect(() => {
    if (userCols?.assigned) setAssignedCols(userCols.assigned);
  }, [userCols]);

  const createUser = useMutation({
    mutationFn: async () => {
      const user = await adminApi.createUser({
        name: form.name,
        email: form.email,
        password: form.password,
        role: form.role,
        active: form.active,
      });
      await adminApi.updateUserPrefs(String(user.id), {
        top_k: form.top_k,
        mmr_lambda: form.mmr_lambda,
        temperature: form.temperature,
      });
      return user;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      setDialogOpen(false);
      setForm({
        name: "",
        email: "",
        password: "",
        role: "user",
        active: true,
        top_k: 6,
        mmr_lambda: 0.5,
        temperature: 0.2,
      });
      toast({ title: "User created" });
    },
    onError: (err) =>
      toast({
        variant: "destructive",
        title: "Create failed",
        description: err instanceof Error ? err.message : String(err),
      }),
  });

  const updateUser = useMutation({
    mutationFn: ({ id }: { id: number }) =>
      Promise.all([
        adminApi.updateUser(String(id), {
          name: form.name,
          email: form.email,
          active: form.active,
          password: form.password || undefined,
        }),
        adminApi.updateUserPrefs(String(id), {
          top_k: form.top_k,
          mmr_lambda: form.mmr_lambda,
          temperature: form.temperature,
        }),
      ]),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      setEditing(null);
      setDialogOpen(false);
      toast({ title: "User updated" });
    },
    onError: (err) =>
      toast({
        variant: "destructive",
        title: "Update failed",
        description: err instanceof Error ? err.message : String(err),
      }),
  });

  const bulkUpdate = useMutation({
    mutationFn: ({ ids, active }: { ids: number[]; active: boolean }) =>
      Promise.all(ids.map((id) => adminApi.updateUser(String(id), { active }))),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      setSelected([]);
      toast({ title: "Users updated" });
    },
    onError: (err) =>
      toast({
        variant: "destructive",
        title: "Update failed",
        description: err instanceof Error ? err.message : String(err),
      }),
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, active }: { id: number; active: boolean }) =>
      adminApi.updateUser(String(id), { active }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      toast({ title: "User updated" });
    },
    onError: (err) =>
      toast({
        variant: "destructive",
        title: "Update failed",
        description: err instanceof Error ? err.message : String(err),
      }),
  });

  const assignCollections = useMutation({
    mutationFn: (ids: number[]) =>
      adminApi.assignCollections(String(assigning!.id), ids.map(String)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      toast({ title: "Collections updated" });
      setAssignDialogOpen(false);
      setAssigning(null);
    },
    onError: (err) =>
      toast({
        variant: "destructive",
        title: "Update failed",
        description: err instanceof Error ? err.message : String(err),
      }),
  });

  const rows = useMemo(() => users ?? [], [users]);

  const allSelected = rows.length > 0 && selected.length === rows.length;
  const toggleAll = (checked: boolean) =>
    setSelected(checked ? rows.map((u) => u.id) : []);
  const toggleOne = (id: number, checked: boolean) =>
    setSelected((prev) =>
      checked ? [...prev, id] : prev.filter((uid) => uid !== id)
    );

  const toggleAssign = (id: number, checked: boolean) =>
    setAssignedCols((prev) =>
      checked ? [...prev, id] : prev.filter((cid) => cid !== id)
    );

  const openCreate = () => {
    setForm({
      name: "",
      email: "",
      password: "",
      role: "user",
      active: true,
      top_k: 6,
      mmr_lambda: 0.5,
      temperature: 0.2,
    });
    setErrors({});
    setEditing(null);
    setDialogOpen(true);
  };

  const openEdit = (u: User) => {
    setForm({
      name: u.name,
      email: u.email,
      password: "",
      role: u.role,
      active: u.active,
      top_k: 6,
      mmr_lambda: 0.5,
      temperature: 0.2,
    });
    setErrors({});
    setEditing(u);
    setDialogOpen(true);
    adminApi
      .getUserPrefs(String(u.id))
      .then((p) =>
        setForm((f) => ({
          ...f,
          top_k: p.top_k,
          mmr_lambda: p.mmr_lambda,
          temperature: p.temperature,
        }))
      )
      .catch(() => undefined);
  };

  const openAssign = (u: User) => {
    setAssigning(u);
    setAssignDialogOpen(true);
  };

  const validate = (mode: "create" | "edit") => {
    const errs: typeof errors = {};
    if (!form.name) errs.name = "Name is required";
    if (!form.email) errs.email = "Email is required";
    else if (!/^\S+@\S+\.\S+$/.test(form.email)) errs.email = "Invalid email";
    if (mode === "create" && !form.password)
      errs.password = "Password is required";
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const submit = () => {
    if (editing) {
      if (!validate("edit")) return;
      updateUser.mutate({ id: editing.id });
    } else {
      if (!validate("create")) return;
      createUser.mutate();
    }
  };

  if (!token)
    return <AppShell title="Users"><div>Loading auth…</div></AppShell>;
  if (isLoading)
    return <AppShell title="Users"><div>Loading users…</div></AppShell>;
  if (error)
    return (
      <AppShell title="Users">
        <div className="text-destructive">
          Failed to load users: {error instanceof Error ? error.message : String(error)}
          <Button className="ml-3" size="sm" onClick={() => refetch()}>
            Retry
          </Button>
        </div>
      </AppShell>
    );

  return (
    <AppShell title="Users">
      <div className="mb-4 flex items-center justify-between">
        {selected.length > 0 ? (
          <div className="flex items-center gap-2">
            <span>{selected.length} selected</span>
            <Button
              size="sm"
              onClick={() =>
                window.confirm("Activate selected users?") &&
                bulkUpdate.mutate({ ids: selected, active: true })
              }
            >
              Activate
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                window.confirm("Deactivate selected users?") &&
                bulkUpdate.mutate({ ids: selected, active: false })
              }
            >
              Deactivate
            </Button>
          </div>
        ) : (
          <div />
        )}
        <Button onClick={openCreate}>Create user</Button>
      </div>

      <section className="mb-8 overflow-x-auto rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead className="bg-muted">
            <tr>
              <th className="w-12 px-3 py-2">
                <Checkbox
                  checked={allSelected}
                  onCheckedChange={(c) => toggleAll(c as boolean)}
                  aria-label="Select all"
                />
              </th>
              <th className="px-3 py-2 text-left">Name</th>
              <th className="px-3 py-2 text-left">Email</th>
              <th className="px-3 py-2 text-left">Role</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-left">Last Active</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.id} className="border-t border-border">
                <td className="px-3 py-2">
                  <Checkbox
                    checked={selected.includes(u.id)}
                    onCheckedChange={(c) => toggleOne(u.id, c as boolean)}
                    aria-label="Select row"
                  />
                </td>
                <td className="px-3 py-2">{u.name}</td>
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2">{u.role}</td>
                <td className="px-3 py-2">
                  {u.active ? "Active" : "Disabled"}
                </td>
                <td className="px-3 py-2">
                  {u.last_active
                    ? new Date(u.last_active).toLocaleDateString()
                    : "—"}
                </td>
                <td className="px-3 py-2">
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8"
                      >
                        <MoreVertical className="h-4 w-4" />
                        <span className="sr-only">Actions</span>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={() => openEdit(u)}>
                        Edit
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={() => openAssign(u)}>
                        Assign collections
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() =>
                          window.confirm(
                            `${u.active ? "Disable" : "Enable"} ${u.name}?`
                          ) &&
                            toggleActive.mutate({ id: u.id, active: !u.active })
                        }
                      >
                        {u.active ? "Disable" : "Enable"}
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        onClick={() => toast({ title: "UI preferences reset" })}
                      >
                        Reset UI prefs
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? "Edit user" : "Create user"}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
              {errors.name && (
                <p className="text-sm text-destructive">{errors.name}</p>
              )}
            </div>
            <div className="grid gap-1">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
              {errors.email && (
                <p className="text-sm text-destructive">{errors.email}</p>
              )}
            </div>
            <div className="grid gap-1">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={form.password}
                placeholder={editing ? "Leave blank to keep current" : ""}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
              {editing ? (
                <p className="text-xs text-muted-foreground">
                  Leave blank to keep current password
                </p>
              ) : (
                errors.password && (
                  <p className="text-sm text-destructive">{errors.password}</p>
                )
              )}
            </div>
            <div className="grid gap-1">
              <Label htmlFor="role">Role</Label>
              <select
                id="role"
                className="rounded border border-input bg-background px-3 py-2"
                value={form.role}
                onChange={(e) =>
                  setForm({ ...form, role: e.target.value as "user" | "admin" })
                }
              >
                <option value="user">user</option>
                <option value="admin">admin</option>
              </select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="top_k">Top K</Label>
              <Input
                id="top_k"
                type="number"
                min={1}
                max={20}
                value={form.top_k}
                onChange={(e) =>
                  setForm({ ...form, top_k: Number(e.target.value) })
                }
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="mmr_lambda">MMR Lambda</Label>
              <Input
                id="mmr_lambda"
                type="number"
                step="0.05"
                min={0}
                max={1}
                value={form.mmr_lambda}
                onChange={(e) =>
                  setForm({ ...form, mmr_lambda: Number(e.target.value) })
                }
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="temperature">Answer temperature</Label>
              <Input
                id="temperature"
                type="number"
                step="0.05"
                min={0}
                max={2}
                value={form.temperature}
                onChange={(e) =>
                  setForm({ ...form, temperature: Number(e.target.value) })
                }
              />
            </div>
            <div className="flex items-center gap-2 pt-1">
              <Checkbox
                id="active"
                checked={form.active}
                onCheckedChange={(c) =>
                  setForm({ ...form, active: c as boolean })
                }
              />
              <Label htmlFor="active" className="cursor-pointer">
                Active
              </Label>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setDialogOpen(false)}
              disabled={createUser.isPending || updateUser.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={submit}
              disabled={createUser.isPending || updateUser.isPending}
            >
              {createUser.isPending || updateUser.isPending
                ? "Saving…"
                : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={assignDialogOpen}
        onOpenChange={(o) => {
          setAssignDialogOpen(o);
          if (!o) setAssigning(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Assign collections</DialogTitle>
          </DialogHeader>
          {loadingUserCols || !collections ? (
            <div className="py-4">Loading…</div>
          ) : (
            <div className="grid gap-2 py-2 max-h-60 overflow-y-auto">
              {collections.map((c) => (
                <div key={c.id} className="flex items-center gap-2">
                  <Checkbox
                    id={`col-${c.id}`}
                    checked={assignedCols.includes(c.id)}
                    onCheckedChange={(checked) =>
                      toggleAssign(c.id, checked as boolean)
                    }
                  />
                  <Label
                    htmlFor={`col-${c.id}`}
                    className="cursor-pointer"
                  >
                    {c.name}
                  </Label>
                </div>
              ))}
            </div>
          )}
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setAssignDialogOpen(false)}
              disabled={assignCollections.isPending}
            >
              Cancel
            </Button>
            <Button
              onClick={() => assignCollections.mutate(assignedCols)}
              disabled={assignCollections.isPending}
            >
              {assignCollections.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}

