import type { Frame } from '../vision/types';

function formatAge(ageMs: number): string {
  return `${(ageMs / 1000).toFixed(1)}s`;
}

const CYAN = '#22d3ee';
const AMBER = '#fbbf24';

/** Corner-bracket length as a fraction of the box's shorter side. */
const BRACKET_RATIO = 0.22;

/** Stable per-label accent so the same object keeps the same colour. */
function accentFor(label: string): string {
  let hash = 0;
  for (let i = 0; i < label.length; i++) hash = (hash * 31 + label.charCodeAt(i)) | 0;
  const hue = 160 + (Math.abs(hash) % 80); // cyan -> violet band only
  return `hsl(${hue} 90% 60%)`;
}

/**
 * Draws a reticle-style bracket instead of a plain rectangle. Four corners,
 * no full outline — reads as "tracking" rather than "screenshot annotation".
 */
function drawBrackets(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number,
  color: string,
) {
  const len = Math.min(w, h) * BRACKET_RATIO;
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.shadowColor = color;
  ctx.shadowBlur = 12;
  ctx.beginPath();
  // top-left
  ctx.moveTo(x, y + len); ctx.lineTo(x, y); ctx.lineTo(x + len, y);
  // top-right
  ctx.moveTo(x + w - len, y); ctx.lineTo(x + w, y); ctx.lineTo(x + w, y + len);
  // bottom-right
  ctx.moveTo(x + w, y + h - len); ctx.lineTo(x + w, y + h); ctx.lineTo(x + w - len, y + h);
  // bottom-left
  ctx.moveTo(x + len, y + h); ctx.lineTo(x, y + h); ctx.lineTo(x, y + h - len);
  ctx.stroke();
  ctx.shadowBlur = 0;
}

function drawLabel(
  ctx: CanvasRenderingContext2D,
  x: number, y: number,
  label: string, id: number, ageMs: number,
  color: string,
) {
  const text = `${label.toUpperCase()} #${id}  ·  ${formatAge(ageMs)}`;
  ctx.font = '600 13px ui-monospace, SFMono-Regular, Menlo, monospace';
  const pad = 6;
  const width = ctx.measureText(text).width + pad * 2;
  const height = 20;
  // Flip the tag below the box if it would clip off the top edge.
  const ty = y - height - 4 < 0 ? y + 4 : y - height - 4;

  ctx.fillStyle = 'rgba(3, 10, 18, 0.82)';
  ctx.fillRect(x, ty, width, height);
  ctx.fillStyle = color;
  ctx.fillRect(x, ty, 2, height);
  ctx.fillStyle = color;
  ctx.fillText(text, x + pad, ty + 14);
}

/** Scanline + crosshair chrome that sells the "HUD" read. */
function drawChrome(ctx: CanvasRenderingContext2D, w: number, h: number, t: number) {
  const cx = w / 2;
  const cy = h / 2;

  ctx.strokeStyle = 'rgba(34, 211, 238, 0.35)';
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(cx - 14, cy); ctx.lineTo(cx - 4, cy);
  ctx.moveTo(cx + 4, cy); ctx.lineTo(cx + 14, cy);
  ctx.moveTo(cx, cy - 14); ctx.lineTo(cx, cy - 4);
  ctx.moveTo(cx, cy + 4); ctx.lineTo(cx, cy + 14);
  ctx.stroke();

  // Frame corners.
  const m = 16;
  const l = 28;
  ctx.strokeStyle = 'rgba(34, 211, 238, 0.5)';
  ctx.beginPath();
  ctx.moveTo(m, m + l); ctx.lineTo(m, m); ctx.lineTo(m + l, m);
  ctx.moveTo(w - m - l, m); ctx.lineTo(w - m, m); ctx.lineTo(w - m, m + l);
  ctx.moveTo(w - m, h - m - l); ctx.lineTo(w - m, h - m); ctx.lineTo(w - m - l, h - m);
  ctx.moveTo(m + l, h - m); ctx.lineTo(m, h - m); ctx.lineTo(m, h - m - l);
  ctx.stroke();

  // Sweeping scanline.
  const sy = ((t / 3000) % 1) * h;
  const grad = ctx.createLinearGradient(0, sy - 40, 0, sy);
  grad.addColorStop(0, 'rgba(34, 211, 238, 0)');
  grad.addColorStop(1, 'rgba(34, 211, 238, 0.10)');
  ctx.fillStyle = grad;
  ctx.fillRect(0, sy - 40, w, 40);
}

/**
 * Renders one HUD frame. Pure draw call — takes state, touches no state.
 * `scale` maps video pixel space onto canvas pixel space.
 */
export function drawHud(
  ctx: CanvasRenderingContext2D,
  frame: Frame,
  canvasW: number,
  canvasH: number,
  scaleX: number,
  scaleY: number,
  t: number,
  mirrored: boolean,
) {
  ctx.clearRect(0, 0, canvasW, canvasH);
  drawChrome(ctx, canvasW, canvasH, t);

  // The video preview is mirrored for a natural selfie view. We mirror the
  // box *coordinates* rather than the canvas itself — flipping the canvas
  // would flip the label text along with it and render it backwards.
  const flipX = (x: number, w: number) => (mirrored ? canvasW - x - w : x);

  for (const t of frame.tracks) {
    const [bx, by, bw, bh] = t.bbox;
    const w = bw * scaleX;
    const h = bh * scaleY;
    const x = flipX(bx * scaleX, w);
    const y = by * scaleY;
    const color = t.label === 'person' ? AMBER : accentFor(t.label);

    drawBrackets(ctx, x, y, w, h, color);
    drawLabel(ctx, x, y, t.label, t.id, t.ageMs, color);
  }

  // Faint tracking line from centre to the largest target.
  const primary = [...frame.tracks].sort(
    (a, b) => b.bbox[2] * b.bbox[3] - a.bbox[2] * a.bbox[3],
  )[0];
  if (primary) {
    const pw = primary.bbox[2] * scaleX;
    const px = flipX(primary.bbox[0] * scaleX, pw) + pw / 2;
    const py = (primary.bbox[1] + primary.bbox[3] / 2) * scaleY;
    ctx.strokeStyle = 'rgba(34, 211, 238, 0.18)';
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.moveTo(canvasW / 2, canvasH / 2);
    ctx.lineTo(px, py);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  void CYAN;
}
