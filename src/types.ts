export type LayerId = 'text' | 'bw_full' | 'detail' | 'color';

export type VisualMode = 'diary' | 'ink-comic';

export type SceneData = {
  id: string;
  duration_sec: number;
  text: string;
  summary_text?: string;
  narration?: string;
  visual: string;
  shot: string;
  focus?: 'center' | 'left' | 'right' | 'top' | 'bottom' | string;
  motion?:
    | 'hold'
    | 'push_soft'
    | 'push'
    | 'push_left'
    | 'push_right'
    | 'pull_soft'
    | 'pull'
    | 'pan_left'
    | 'pan_right'
    | 'pan_up'
    | 'pan_down'
    | string;
  transition_to_next?: 'cut' | 'fade' | string;
  visual_interval_id?: string;
  visual_interval_start?: boolean;
  visual_interval_progress_start?: number;
  visual_interval_progress_end?: number;
  visual_mode?: VisualMode;
  scene_kind?: 'host' | 'narrative' | 'evidence' | 'map' | 'title' | string;
  glyph?: string | null;
  case_label?: string | null;
  accent?: string | null;
  layers: LayerId[];
  color_hint: string | null;
  detail_hint: string | null;
  caption_box?: {
    top: number;
    height: number;
  } | null;
  assets: {
    text_image?: string | null;
    bw: string | null;
    detail: string | null;
    color: string | null;
  };
};

export type Storyboard = {
  project: {
    title: string;
    mode?: 'speed' | 'quality';
    images_per_scene?: number;
    derive_bw?: 'local' | 'ai';
    enable_detail?: boolean;
    gen_size?: number;
    export_size?: [number, number];
    visual_mode?: VisualMode;
    subtitle_contract?: 'draft_summary' | 'verbatim_tts';
    ratio: '3:4' | '16:9';
    width: number;
    height: number;
    fps: number;
    transition?: 'cut' | 'page-flip';
    transition_sec?: number;
    style_lock: string;
    character_lock: string;
    cover?: {
      series_title?: string;
      episode_label?: string;
      episode_number?: string;
      title?: string;
      background?: string;
      accent?: string;
      dark_accent?: string;
      badge?: string;
      card?: string;
      foreground?: string;
    };
    audio: {
      voiceover: 'post' | 'continuous_groups';
      bgm: 'optional_bed_only';
      bgm_follows_text: false;
    };
  };
  scenes: SceneData[];
};
