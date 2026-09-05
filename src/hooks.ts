import { useEffect, useRef } from "react";
import { listen, type Event } from "@tauri-apps/api/event";

/** Subscribe once; asynchronous registration is also cleaned up after unmount. */
export function useTauriEvent<T>(name: string, handler: (event: Event<T>) => void) {
  const current = useRef(handler);
  current.current = handler;
  useEffect(() => {
    let disposed = false;
    let stop: (() => void) | undefined;
    void listen<T>(name, (event) => current.current(event)).then((unlisten) => {
      if (disposed) unlisten(); else stop = unlisten;
    });
    return () => { disposed = true; stop?.(); };
  }, [name]);
}
