export interface ChatMessage {
  id: string;
  role: 'user' | 'agent' | 'status';
  text?: string;
  records?: any[];
  total?: number;
  jobId?: string;
  createdAt: string;
}

export interface ChatSessionData {
  sessionId: string;
  messages: ChatMessage[];
  pendingAction: any | null;
  activeJobId: string | null;
  updatedAt: string;
}

export const getChatStorageKey = (userId: string) => `chat:v1:${userId}`;

export const loadChatData = (userId: string): ChatSessionData | null => {
  const data = localStorage.getItem(getChatStorageKey(userId));
  if (!data) return null;
  try {
    return JSON.parse(data);
  } catch {
    return null;
  }
};

export const saveChatData = (userId: string, data: ChatSessionData) => {
  data.updatedAt = new Date().toISOString();
  // Keep at most 200 messages
  if (data.messages.length > 200) {
    data.messages = data.messages.slice(data.messages.length - 200);
  }
  localStorage.setItem(getChatStorageKey(userId), JSON.stringify(data));
};

export const clearChatData = (userId: string) => {
  localStorage.removeItem(getChatStorageKey(userId));
};
