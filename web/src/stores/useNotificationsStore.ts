import { create } from "zustand";
import { apiFetch } from "@/lib/api";
import type { WikiNotification } from "@/lib/types";

type NotificationsState = {
  notifications: WikiNotification[];
  fetchNotifications: () => Promise<void>;
  markRead: (kbId: string) => Promise<void>;
  unreadTotal: () => number;
};

export const useNotificationsStore = create<NotificationsState>((set, get) => ({
  notifications: [],

  fetchNotifications: async () => {
    try {
      const data = await apiFetch<WikiNotification[]>("/v1/notifications");
      set({ notifications: data });
    } catch {
      // silencioso: la campana simplemente no muestra avisos
    }
  },

  markRead: async (kbId: string) => {
    const prev = get().notifications;
    if (!prev.some((n) => n.kb_id === kbId)) return;
    set({ notifications: prev.filter((n) => n.kb_id !== kbId) }); // optimista
    try {
      await apiFetch(`/v1/notifications/${kbId}/read`, { method: "POST" });
    } catch {
      set({ notifications: prev }); // rollback
    }
  },

  unreadTotal: () => get().notifications.length,
}));
