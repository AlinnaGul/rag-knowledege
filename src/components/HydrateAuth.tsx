import { useEffect, useState } from 'react';
import { authApi } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';

interface Props {
  children: React.ReactNode;
}

export default function HydrateAuth({ children }: Props) {
  const { token, user, setUser, clearAuth } = useAuthStore();
  const [ready, setReady] = useState(!token || !!user);

  useEffect(() => {
    const hydrate = async () => {
      if (token && !user) {
        try {
          const me = await authApi.me();
          setUser(me);
        } catch {
          clearAuth();
        }
      }
      setReady(true);
    };
    if (!ready) {
      hydrate();
    }
  }, [token, user, ready, setUser, clearAuth]);

  if (!ready) {
    return null;
  }

  return <>{children}</>;
}
