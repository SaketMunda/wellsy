import type { CameraStatus } from '../vision/useCamera';
import type { ModelStatus } from '../vision/useDetector';

interface Props {
  cameraStatus: CameraStatus;
  modelStatus: ModelStatus;
  narratorEnabled: boolean;
}

interface Line {
  label: string;
  state: 'offline' | 'booting' | 'online' | 'standby' | 'denied' | 'error';
}

/**
 * Staged power-on in place of a static "loading" curtain. Every line below
 * is read directly off a real state value already produced elsewhere in the
 * app (`cameraStatus`, `modelStatus`, and whether the narrator is actually
 * enabled) — there is no fake progress bar or timer-driven percentage here.
 * The only thing "staged" about it is the CSS entrance animation on each
 * already-true line, not the truth value itself.
 */
export function BootSequence({ cameraStatus, modelStatus, narratorEnabled }: Props) {
  const lines: Line[] = [
    {
      label: 'camera',
      state:
        cameraStatus === 'live' ? 'online'
        : cameraStatus === 'denied' ? 'denied'
        : cameraStatus === 'error' ? 'error'
        : cameraStatus === 'starting' ? 'booting'
        : 'offline',
    },
    {
      label: 'vision model',
      state: modelStatus === 'ready' ? 'online' : modelStatus === 'error' ? 'error' : modelStatus === 'loading' ? 'booting' : 'offline',
    },
    {
      label: 'tracker',
      state: modelStatus === 'ready' ? 'online' : 'offline',
    },
    {
      label: 'narrator',
      state: narratorEnabled ? 'online' : modelStatus === 'ready' ? 'standby' : 'offline',
    },
  ];

  return (
    <div className="boot-sequence" role="status">
      <p className="boot-title">YAP · booting perception stack</p>
      <ul className="boot-lines">
        {lines.map((line, i) => (
          <li key={line.label} className="boot-line" style={{ animationDelay: `${i * 140}ms` }}>
            <span className="boot-line-label">{line.label}</span>
            <span className={`boot-line-state boot-line-state--${line.state}`}>{line.state}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
