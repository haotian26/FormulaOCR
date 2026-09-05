import type { AppLanguage } from "./i18n";

export type Source = "local" | "api";
export type RecognitionMode = "chemistry" | "math";
export type Settings = {
  auto_copy: boolean;
  hide_dock_on_close: boolean;
  hotkey: string;
  history_limit: number;
  layout_restore_mode: string;
  layout_version?: number;
  default_recognition_mode: RecognitionMode;
  language: AppLanguage;
};
export type Profile = {
  id: string;
  name: string;
  enabled: boolean;
  provider_type: string;
  base_url?: string;
  model?: string;
  timeout_s?: number;
  prompt_override?: string;
  api_key?: string;
  app_id?: string;
  app_key?: string;
};
export type RecordItem = {
  id: string;
  image_path: string;
  created_at: number;
  updated_at: number;
  local_raw_latex: string;
  local_formatted_latex?: string;
  local_draft_latex: string;
  local_render_error?: string | null;
  api_raw_latex?: string | null;
  api_formatted_latex?: string | null;
  api_draft_latex?: string | null;
  api_profile_name?: string | null;
  api_model?: string | null;
  active_source?: string;
  recognition_mode?: RecognitionMode;
  has_api?: boolean;
};
export type Layout = { image: number; result: number; drawerWidth: number };

export const defaults: Settings = {
  auto_copy: false,
  hide_dock_on_close: true,
  hotkey: "ctrl+alt+cmd+o",
  history_limit: 200,
  layout_restore_mode: "remember_window_history_closed",
  default_recognition_mode: "chemistry",
  language: "zh-CN",
};
