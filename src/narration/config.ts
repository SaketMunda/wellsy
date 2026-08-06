/** Tunables for the personality layer. Persisted to localStorage, no server. */
export interface NarratorConfig {
  /** 0 = clean, 1 = default snark, 2 = allows mild swears. */
  spice_level: 0 | 1 | 2;
  /** Hard ceiling on words in a generated line. */
  line_max_words: number;
  /** Rate limit: the narrator will not speak more often than this. */
  min_seconds_between_lines: number;
  /** How often a motionless scene earns a `still_present` remark. */
  idle_escalation_minutes: number;
  /** Web Speech output. Off by default — a talking page is a rude default. */
  voice_enabled: boolean;
}

export const DEFAULT_CONFIG: NarratorConfig = {
  spice_level: 1,
  line_max_words: 14,
  min_seconds_between_lines: 4,
  idle_escalation_minutes: 2,
  voice_enabled: false,
};

const KEY = 'yap.narrator.config';

export function loadConfig(): NarratorConfig {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...DEFAULT_CONFIG };
    // Merge over defaults so a config written by an older build still boots.
    return { ...DEFAULT_CONFIG, ...(JSON.parse(raw) as Partial<NarratorConfig>) };
  } catch {
    return { ...DEFAULT_CONFIG };
  }
}

export function saveConfig(config: NarratorConfig): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(config));
  } catch {
    // Private browsing, quota, whatever. The narrator still works in memory.
  }
}
