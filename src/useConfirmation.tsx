import { useCallback, useEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { translate, type AppLanguage } from "./i18n";

// Browser confirm panels are not implemented by the macOS webview delegate.
// Keep confirmation inside React so browser and packaged-app behavior agree.
export function useConfirmation(language: AppLanguage) {
  const [message, setMessage] = useState<string | null>(null);
  const pending = useRef<((accepted: boolean) => void) | null>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const t = (text: string) => translate(language, text);
  const settle = useCallback((accepted: boolean) => {
    const resolve = pending.current;
    pending.current = null;
    setMessage(null);
    resolve?.(accepted);
  }, []);
  useEffect(() => () => { pending.current?.(false); pending.current = null; }, []);
  const confirm = useCallback((text: string): Promise<boolean> => {
    if (pending.current) return Promise.resolve(false);
    opener.current = document.activeElement as HTMLElement | null;
    return new Promise(resolve => { pending.current = resolve; setMessage(text); });
  }, []);
  const confirmation = <Dialog.Root open={message !== null} onOpenChange={open => { if (!open) settle(false); }}>
    <Dialog.Portal>
      <Dialog.Overlay className="confirmation-overlay" />
      <Dialog.Content className="confirmation-dialog" onOpenAutoFocus={event => { event.preventDefault(); cancelButton.current?.focus(); }} onCloseAutoFocus={event => { event.preventDefault(); if (opener.current?.isConnected) opener.current.focus(); }}>
        <Dialog.Title>{t("确认操作")}</Dialog.Title>
        <Dialog.Description>{message}</Dialog.Description>
        <div className="settings-confirm-actions">
          <button ref={cancelButton} className="secondary-button" onClick={() => settle(false)}>{t("取消")}</button>
          <button className="secondary-button text-danger" onClick={() => settle(true)}>{t("确认")}</button>
        </div>
      </Dialog.Content>
    </Dialog.Portal>
  </Dialog.Root>;
  return { confirm, confirmation };
}
