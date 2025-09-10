import { useEffect, useState } from 'react';
import AppShell from '@/components/layout/AppShell';
import { useAuthStore } from '@/stores/auth';
import { authApi } from '@/lib/api';
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useTheme } from '@/components/ui/theme-provider';
import { useChatStore } from '@/stores/chat';
import { useToast } from '@/components/ui/use-toast';

export default function Profile() {
  const { token, user, setUser } = useAuthStore();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const { theme, setTheme } = useTheme();
  const { settings, updateSettings } = useChatStore();
  const { toast } = useToast();

  const [prefTheme, setPrefTheme] = useState(theme);
  const [topK, setTopK] = useState(settings.topK);
  const [temperature, setTemperature] = useState(settings.temperature);

  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');

  const isAdmin = user?.role === 'admin' || user?.role === 'superadmin';

  useEffect(() => {
    const fetchProfile = async () => {
      if (!token) return;
      try {
        const data = await authApi.me();
        setUser(data);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load profile');
      } finally {
        setLoading(false);
      }
    };
    fetchProfile();
  }, [token, setUser]);

  const handleSave = () => {
    setTheme(prefTheme);
    if (isAdmin) {
      updateSettings({ topK, temperature });
    }
    toast({ description: 'Preferences saved' });
  };

  const handlePasswordChange = async () => {
    if (newPw !== confirmPw) {
      toast({ variant: 'destructive', description: 'Passwords do not match' });
      return;
    }
    try {
      await authApi.changePassword({ old_password: currentPw, new_password: newPw });
      toast({ description: 'Password updated' });
      setCurrentPw('');
      setNewPw('');
      setConfirmPw('');
    } catch (err: unknown) {
      toast({ variant: 'destructive', description: err instanceof Error ? err.message : 'Failed to update password' });
    }
  };

  const handleCancel = () => {
    setPrefTheme(theme);
    if (isAdmin) {
      setTopK(settings.topK);
      setTemperature(settings.temperature);
    }
  };

  if (loading) {
    return <AppShell title="Profile"><div>Loading...</div></AppShell>;
  }

  if (error) {
    return (
      <AppShell title="Profile">
        <div className="text-destructive">{error}</div>
      </AppShell>
    );
  }

  return (
    <AppShell title="Profile">
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Account</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div>
              <Label className="text-sm">Name</Label>
              <p className="text-sm">{user?.name}</p>
            </div>
            <div>
              <Label className="text-sm">Email</Label>
              <p className="text-sm">{user?.email}</p>
            </div>
            <div>
              <Label className="text-sm">Role</Label>
              <p className="text-sm capitalize">{user?.role}</p>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Preferences</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="theme">Theme</Label>
              <Select value={prefTheme} onValueChange={setPrefTheme}>
                <SelectTrigger id="theme">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="light">Light</SelectItem>
                  <SelectItem value="dark">Dark</SelectItem>
                  <SelectItem value="system">System</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {isAdmin && (
              <>
                <div className="space-y-2">
                  <Label>Default Top-K</Label>
                  <Slider min={1} max={20} step={1} value={[topK]} onValueChange={v => setTopK(v[0])} />
                  <div className="text-sm text-muted-foreground">{topK}</div>
                </div>
                <div className="space-y-2">
                  <Label>Default Temperature</Label>
                  <Slider min={0} max={1} step={0.1} value={[temperature]} onValueChange={v => setTemperature(v[0])} />
                  <div className="text-sm text-muted-foreground">{temperature.toFixed(1)}</div>
                </div>
              </>
            )}
          </CardContent>
          <CardFooter className="justify-end gap-2">
            <Button variant="outline" onClick={handleCancel}>Cancel</Button>
            <Button onClick={handleSave}>Save</Button>
          </CardFooter>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Change Password</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="grid gap-1">
              <Label htmlFor="current-pw">Current Password</Label>
              <Input id="current-pw" type="password" value={currentPw} onChange={e => setCurrentPw(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="new-pw">New Password</Label>
              <Input id="new-pw" type="password" value={newPw} onChange={e => setNewPw(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="confirm-pw">Confirm New Password</Label>
              <Input id="confirm-pw" type="password" value={confirmPw} onChange={e => setConfirmPw(e.target.value)} />
            </div>
          </CardContent>
          <CardFooter className="justify-end gap-2">
            <Button variant="outline" onClick={() => { setCurrentPw(''); setNewPw(''); setConfirmPw(''); }}>Cancel</Button>
            <Button onClick={handlePasswordChange}>Change</Button>
          </CardFooter>
        </Card>
      </div>
    </AppShell>
  );
}

