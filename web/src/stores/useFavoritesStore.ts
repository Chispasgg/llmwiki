import { create } from "zustand";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";
import type { Favorite } from "@/lib/types";

type FavoritesState = {
  favorites: Favorite[];
  loaded: boolean;
  fetchFavorites: () => Promise<void>;
  isFavorite: (kbId: string) => boolean;
  toggleFavorite: (kbId: string) => Promise<void>;
};

export const useFavoritesStore = create<FavoritesState>((set, get) => ({
  favorites: [],
  loaded: false,

  fetchFavorites: async () => {
    try {
      const data = await apiFetch<Favorite[]>("/v1/favorites");
      set({ favorites: data, loaded: true });
    } catch {
      set({ loaded: true });
    }
  },

  isFavorite: (kbId: string) => get().favorites.some((f) => f.kb_id === kbId),

  toggleFavorite: async (kbId: string) => {
    const wasFavorite = get().isFavorite(kbId);
    const prev = get().favorites;
    // Actualización optimista (los más recientes van al principio).
    set({
      favorites: wasFavorite
        ? prev.filter((f) => f.kb_id !== kbId)
        : [{ kb_id: kbId, created_at: new Date().toISOString() }, ...prev],
    });
    try {
      await apiFetch(`/v1/favorites/${kbId}`, {
        method: wasFavorite ? "DELETE" : "PUT",
      });
    } catch (err) {
      set({ favorites: prev }); // rollback
      toast.error(
        err instanceof Error ? err.message : "No se pudo actualizar favoritos",
      );
    }
  },
}));
