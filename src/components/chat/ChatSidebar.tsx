import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useChatStore, Session } from '@/stores/chat';
import { useAuthStore } from '@/stores/auth';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Plus, Search, MoreHorizontal, Edit2, Trash2, X } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import { useToast } from '@/hooks/use-toast';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

interface ChatSidebarProps {
  onClose?: () => void;
  searchRef?: React.RefObject<HTMLInputElement>;
}

export function ChatSidebar({ onClose, searchRef }: ChatSidebarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [editingSession, setEditingSession] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const {
    sessions,
    currentSession,
    createSession,
    selectSession,
    renameSession,
    deleteSession,
  } = useChatStore();

  const { user } = useAuthStore();
  const { toast } = useToast();

  const filteredSessions = sessions.filter(session =>
    session.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const groups = { today: [] as Session[], week: [] as Session[], older: [] as Session[] };
  const now = new Date();
  filteredSessions.forEach(s => {
    const date = new Date(s.last_message_at || s.updated_at);
    const diffDays = (now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24);
    if (diffDays < 1) groups.today.push(s);
    else if (diffDays < 7) groups.week.push(s);
    else groups.older.push(s);
  });

  const formatTime = (iso?: string | null) => {
    if (!iso) return '';
    const date = new Date(iso);
    if (now.toDateString() === date.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    const diffDays = (now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24);
    if (diffDays < 7) {
      return date.toLocaleDateString(undefined, { weekday: 'short' });
    }
    return date.toLocaleDateString();
  };

  const renderSession = (session: Session) => (
    <div
      key={session.id}
      className={cn(
        "group flex items-center gap-2 p-3 md:p-2 rounded-md transition-colors cursor-pointer",
        currentSession?.id === session.id
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "hover:bg-sidebar-accent/50"
      )}
      onClick={() => handleSelectSession(session.id)}
    >
      {editingSession === session.id ? (
        <div className="flex-1 flex gap-1" onClick={(e) => e.stopPropagation()}>
          <Input
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSaveEdit();
              if (e.key === 'Escape') handleCancelEdit();
            }}
            onBlur={handleSaveEdit}
            className="h-6 text-xs"
            autoFocus
          />
        </div>
      ) : (
        <>
          <div className="flex-1 min-w-0">
            <TooltipProvider delayDuration={0}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <p className="text-sm font-medium truncate">{session.title}</p>
                </TooltipTrigger>
                <TooltipContent side="right">{session.title}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
            <p className="text-xs text-muted-foreground truncate">
              {session.last_message ?? 'No messages yet'}
            </p>
          </div>
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground">
              {formatTime(session.last_message_at || session.updated_at)}
            </span>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="opacity-0 group-hover:opacity-100 h-6 w-6 p-0"
                  onClick={(e) => e.stopPropagation()}
                >
                  <MoreHorizontal className="h-3 w-3" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    handleStartEdit(session.id, session.title);
                  }}
                >
                  <Edit2 className="h-4 w-4 mr-2" />
                  Rename
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteSession(session.id);
                  }}
                  className="text-destructive"
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </>
      )}
    </div>
  );

  const handleCreateSession = async () => {
    await createSession();
    onClose?.();
  };

  const handleSelectSession = async (sessionId: string) => {
    await selectSession(sessionId);
    onClose?.();
  };

  const handleStartEdit = (sessionId: string, currentTitle: string) => {
    setEditingSession(sessionId);
    setEditTitle(currentTitle);
  };

  const handleSaveEdit = async () => {
    if (editingSession && editTitle.trim()) {
      await renameSession(editingSession, editTitle.trim());
      setEditingSession(null);
      setEditTitle('');
      toast({
        title: "Session renamed",
        description: "Chat session has been renamed successfully.",
      });
    }
  };

  const handleCancelEdit = () => {
    setEditingSession(null);
    setEditTitle('');
  };

  const handleDeleteSession = async (sessionId: string) => {
    if (confirm('Are you sure you want to delete this chat session?')) {
      await deleteSession(sessionId);
      toast({
        title: "Session deleted",
        description: "Chat session has been deleted.",
      });
    }
  };

  useEffect(() => {
    if (!searchRef?.current) return;
    searchRef.current.focus();
  }, [searchRef]);

  return (
    <div className="flex flex-col h-full bg-sidebar border-r">
      <div className="p-4 border-b border-sidebar-border space-y-4">
        {onClose && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="lg:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          >
            <X className="h-4 w-4" />
          </Button>
        )}

        <nav className="space-y-1">
          <Button variant="ghost" className="w-full justify-start" asChild>
            <Link to="/chat" className="w-full text-left">Chat</Link>
          </Button>
          <Button variant="ghost" className="w-full justify-start" asChild>
            <Link to="/collections" className="w-full text-left">Collections</Link>
          </Button>
          <Button variant="ghost" className="w-full justify-start" asChild>
            <Link to="/profile" className="w-full text-left">Profile</Link>
          </Button>
          {(user?.role === 'admin' || user?.role === 'superadmin') && (
            <>
              <div className="pt-2">
                <p className="px-3 text-xs font-semibold text-muted-foreground">Admin</p>
              </div>
              <Button variant="ghost" className="w-full justify-start" asChild>
                <Link to="/admin/collections" className="w-full text-left">Collections</Link>
              </Button>
              <Button variant="ghost" className="w-full justify-start" asChild>
                <Link to="/admin/documents" className="w-full text-left">Documents</Link>
              </Button>
              <Button variant="ghost" className="w-full justify-start" asChild>
                <Link to="/admin/users" className="w-full text-left">Users</Link>
              </Button>
            </>
          )}
        </nav>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            ref={searchRef}
            placeholder="Search chats..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          />
        </div>
      </div>

        {/* Sessions List */}
        <ScrollArea className="flex-1">
          <div className="sticky top-0 z-10 p-2 bg-sidebar">
            <Button onClick={handleCreateSession} className="w-full justify-start" size="sm">
              <Plus className="h-4 w-4 mr-2" />
              New Chat
            </Button>
          </div>
          <div className="p-2 space-y-4">
            {filteredSessions.length === 0 && (
              <div className="text-center py-8 text-muted-foreground">
                <p className="text-sm">
                  {searchQuery ? 'No chats found' : 'No chat sessions yet'}
                </p>
                {!searchQuery && (
                  <p className="text-xs mt-1">Click "New Chat" to get started</p>
                )}
              </div>
            )}
            {groups.today.length > 0 && (
              <div>
                <h4 className="px-2 text-xs font-semibold text-muted-foreground mb-1">Today</h4>
                <div className="space-y-1">{groups.today.map(renderSession)}</div>
              </div>
            )}
            {groups.week.length > 0 && (
              <div>
                <h4 className="px-2 text-xs font-semibold text-muted-foreground mb-1">This week</h4>
                <div className="space-y-1">{groups.week.map(renderSession)}</div>
              </div>
            )}
            {groups.older.length > 0 && (
              <div>
                <h4 className="px-2 text-xs font-semibold text-muted-foreground mb-1">Older</h4>
                <div className="space-y-1">{groups.older.map(renderSession)}</div>
              </div>
            )}
          </div>
        </ScrollArea>
    </div>
  );
}