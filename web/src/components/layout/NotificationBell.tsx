"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Bell } from "lucide-react";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover";
import { useNotificationsStore } from "@/stores";

export function NotificationBell() {
  const router = useRouter();
  const notifications = useNotificationsStore((s) => s.notifications);
  const fetchNotifications = useNotificationsStore((s) => s.fetchNotifications);
  const markRead = useNotificationsStore((s) => s.markRead);
  const markAllRead = useNotificationsStore((s) => s.markAllRead);
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const count = notifications.length;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          aria-label="Notificaciones"
          className="relative p-2 rounded-lg hover:bg-accent transition-colors cursor-pointer"
        >
          <Bell className="size-5 text-foreground" />
          {count > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-4 h-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] font-semibold flex items-center justify-center">
              {count}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="px-3 py-2 border-b flex items-center justify-between gap-2">
          <span className="text-sm font-semibold">Novedades</span>
          {count > 0 && (
            <button
              onClick={() => markAllRead()}
              className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              Leer todas
            </button>
          )}
        </div>
        {count === 0 ? (
          <p className="px-3 py-6 text-sm text-muted-foreground text-center">
            No hay novedades.
          </p>
        ) : (
          <ul className="max-h-80 overflow-y-auto">
            {notifications.map((n) => (
              <li key={n.kb_id}>
                <button
                  onClick={() => {
                    markRead(n.kb_id);
                    setOpen(false);
                    router.push(`/wikis/${n.kb_slug}`);
                  }}
                  className="w-full text-left px-3 py-2 hover:bg-accent transition-colors cursor-pointer"
                >
                  <span className="text-sm font-medium text-foreground">
                    Novedades en {n.kb_name}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {n.unread_count} cambio(s)
                    {n.last_actor_name ? ` · por ${n.last_actor_name}` : ""}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </PopoverContent>
    </Popover>
  );
}
