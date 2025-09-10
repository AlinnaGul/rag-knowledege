import { create } from 'zustand';
import { useAuthStore } from './auth';
import { chatApi } from '@/lib/api';
import { generateSessionTitle } from '@/lib/utils';

const SETTINGS_KEY = 'rag-settings';

const baseSettings = {
  topK: 5,
  mmr: 0.5,
  temperature: 0.7,
  showImages: true,
  compactMode: false,
};

function getStoredSettings() {
  try {
    const raw = typeof window !== 'undefined' ? localStorage.getItem(SETTINGS_KEY) : null;
    return raw ? { ...baseSettings, ...JSON.parse(raw) } : baseSettings;
  } catch {
    return baseSettings;
  }
}

export interface Citation {
  id: string;
  filename: string;
  page: number;
  snippet: string;
  collection: string;
  url?: string | null;
}

export interface Message {
  id: string;
  content: string;
  role: 'user' | 'assistant';
  timestamp: Date;
  citations?: Citation[];
  query_id?: string;
  feedback?: 'up' | 'down' | null;
}

export interface Session {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
  last_message?: string | null;
  last_message_at?: string | null;
}

interface ChatState {
  sessions: Session[];
  currentSession: Session | null;
  messages: Message[];
  isLoading: boolean;
  error: string | null;
  settings: {
    topK: number;
    mmr: number;
    temperature: number;
    showImages: boolean;
    compactMode: boolean;
  };
  abortController: AbortController | null;
  
  // Actions
  loadSessions: () => Promise<void>;
  createSession: () => Promise<void>;
  selectSession: (sessionId: string) => Promise<void>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  sendMessage: (content: string) => Promise<void>;
  loadMessages: (sessionId: string) => Promise<void>;
  updateSettings: (settings: Partial<ChatState['settings']>) => void;
  resetSettings: () => void;
  clearError: () => void;
  clearCurrentSession: () => void;
  stopGeneration: () => void;
  regenerate: () => Promise<void>;
}

interface ApiSession {
  id: number | string;
  session_title?: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
  last_message?: string | null;
  last_message_at?: string | null;
}

interface ChatHistoryEntry {
  id: number;
  query: string;
  response: string;
  created_at: string;
  session_id: number;
  query_id?: number;
  feedback?: 'up' | 'down' | null;
}

function normalizeSession(s: ApiSession): Session {
  return {
    id: String(s.id),
    title: s.session_title ?? 'New Chat',
    created_at: s.created_at,
    updated_at: s.updated_at,
    message_count: s.message_count,
    last_message: s.last_message ?? null,
    last_message_at: s.last_message_at ?? null,
  };
}

const defaultSettings = getStoredSettings();

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  currentSession: null,
  messages: [],
  isLoading: false,
  error: null,
  settings: { ...defaultSettings },
  abortController: null,

  loadSessions: async () => {
    try {
      const token = useAuthStore.getState().token;
      if (!token) return;

      const raw = await chatApi.listSessions();
      const sessions = raw.map(normalizeSession);
      if (sessions.length === 0) {
        // auto-create first session if none exist
        const session = normalizeSession(await chatApi.createSession());
        set({ sessions: [session], currentSession: session, messages: [] });
      } else {
        set({ sessions, currentSession: sessions[0] });
        // preload messages for the selected session
        await get().loadMessages(sessions[0].id);
      }
    } catch (error) {
      console.error('Failed to load sessions:', error);
    }
  },

  createSession: async () => {
    try {
      const token = useAuthStore.getState().token;
      if (!token) return;

      const session = normalizeSession(await chatApi.createSession());
      set(state => ({
        sessions: [session, ...state.sessions],
        currentSession: session,
        messages: [],
      }));
    } catch (error) {
      console.error('Failed to create session:', error);
    }
  },

  selectSession: async (sessionId: string) => {
    const { sessions } = get();
    const session = sessions.find(s => s.id === sessionId);
    if (session) {
      set({ currentSession: session });
      await get().loadMessages(sessionId);
    }
  },

  renameSession: async (sessionId: string, title: string) => {
    try {
      const token = useAuthStore.getState().token;
      if (!token) return;

      await chatApi.renameSession(sessionId, { session_title: title });
      set(state => ({
        sessions: state.sessions.map(s =>
          s.id === sessionId ? { ...s, title } : s
        ),
        currentSession: state.currentSession?.id === sessionId
          ? { ...state.currentSession, title }
          : state.currentSession,
      }));
    } catch (error) {
      console.error('Failed to rename session:', error);
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
      const token = useAuthStore.getState().token;
      if (!token) return;

      await chatApi.deleteSession(sessionId);
      set(state => ({
        sessions: state.sessions.filter(s => s.id !== sessionId),
        currentSession: state.currentSession?.id === sessionId ? null : state.currentSession,
        messages: state.currentSession?.id === sessionId ? [] : state.messages,
      }));
    } catch (error) {
      console.error('Failed to delete session:', error);
    }
  },

  sendMessage: async (content: string) => {
    const { currentSession, settings } = get();
    if (!currentSession) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      content,
      role: 'user',
      timestamp: new Date(),
    };

    const controller = new AbortController();
    set(state => ({
      messages: [...state.messages, userMessage],
      isLoading: true,
      abortController: controller,
      error: null,
    }));

    try {
      const token = useAuthStore.getState().token;
      if (!token) return;

      const data = await chatApi.ask(
        {
          question: content,
          session_id: currentSession.id,
          top_k: settings.topK,
          temperature: settings.temperature,
          mmr_lambda: settings.mmr,
        },
        { signal: controller.signal }
      );

      const assistantMessage: Message = {
        id: data.query_id || Date.now().toString(),
        content: data.answer,
        role: 'assistant',
        timestamp: new Date(),
        citations: data.citations.map((c: {
          id: string;
          filename: string;
          page: number;
          snippet: string;
          collection_name: string;
          url?: string | null;
        }) => ({
          id: c.id,
          filename: c.filename,
          page: c.page,
          snippet: c.snippet,
          collection: c.collection_name,
          url: c.url,
        })),
        query_id: data.query_id,
        feedback: null,
      };

      set(state => {
        const nowIso = new Date().toISOString();
        let sessions = state.sessions;
        let current = state.currentSession;
        let title = currentSession.title;
        if (currentSession.title === 'New Chat') {
          title = generateSessionTitle(content);
        }
        sessions = state.sessions.map(s =>
          s.id === currentSession.id
            ? {
                ...s,
                title,
                updated_at: nowIso,
                last_message: content,
                last_message_at: nowIso,
              }
            : s
        );
        current = {
          ...currentSession,
          title,
          updated_at: nowIso,
          last_message: content,
          last_message_at: nowIso,
        };
        return {
          messages: [...state.messages, assistantMessage],
          isLoading: false,
          sessions,
          currentSession: current,
          abortController: null,
        };
      });
    } catch (err: unknown) {
      console.error('Failed to send message:', err);
      const status = (err as { status?: number })?.status;
      let errorMsg = 'Failed to send message.';
      if (status === 404) {
        errorMsg = 'No indexed documents are available yet. Upload and index documents in Admin → Collections.';
      } else if (status === 403) {
        errorMsg = "You don't have access to any collections. Contact an admin.";
      }
      set({ isLoading: false, abortController: null, error: errorMsg });
    }
  },

  stopGeneration: () => {
    const controller = get().abortController;
    controller?.abort();
    set({ isLoading: false, abortController: null });
  },

  regenerate: async () => {
    const { messages } = get();
    const lastUser = [...messages].reverse().find(m => m.role === 'user');
    if (lastUser) {
      await get().sendMessage(lastUser.content);
    }
  },

  loadMessages: async (sessionId: string) => {
    try {
      const token = useAuthStore.getState().token;
      if (!token) return;

      const history: ChatHistoryEntry[] = await chatApi.getHistory(sessionId);
      const messages: Message[] = [];
      history.forEach((entry) => {
        messages.push({
          id: `${entry.id}-q`,
          content: entry.query,
          role: 'user',
          timestamp: new Date(entry.created_at),
        });
        messages.push({
          id: entry.query_id ? String(entry.query_id) : `${entry.id}-a`,
          content: entry.response,
          role: 'assistant',
          timestamp: new Date(entry.created_at),
          query_id: entry.query_id ? String(entry.query_id) : undefined,
          feedback: entry.feedback ?? null,
        });
      });
      set({ messages });
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  },

  updateSettings: (newSettings) => {
    set(state => {
      const settings = { ...state.settings, ...newSettings };
      if (typeof window !== 'undefined') {
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
      }
      return { settings };
    });
  },

  resetSettings: () => {
    set({ settings: getStoredSettings() });
  },

  clearError: () => set({ error: null }),

  clearCurrentSession: () => {
    set({ currentSession: null, messages: [] });
  },
}));
