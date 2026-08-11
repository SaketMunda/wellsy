interface Props {
  onClose: () => void;
}

const SHORTCUTS: [string, string][] = [
  ['Space', 'Start / stop the camera'],
  ['N', 'Toggle narration'],
  ['B', 'Toggle boring mode'],
  ['V', 'Toggle voice'],
  ['?', 'Show / hide this list'],
];

export function ShortcutOverlay({ onClose }: Props) {
  return (
    <div className="shortcut-overlay" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts">
      <div className="shortcut-panel">
        <h2>Shortcuts</h2>
        <dl>
          {SHORTCUTS.map(([key, desc]) => (
            <div className="shortcut-row" key={key}>
              <dt>
                <kbd>{key}</kbd>
              </dt>
              <dd>{desc}</dd>
            </div>
          ))}
        </dl>
        <button className="btn" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}
