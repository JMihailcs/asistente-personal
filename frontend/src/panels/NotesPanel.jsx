import { usePanelData } from './usePanelData.js';

export default function NotesPanel({ refreshKey }) {
  const { data, disconnected } = usePanelData('/notes/recent', { refreshKey });

  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 10 }}>notas recientes</div>
      {disconnected && <div className="label live">sin conexión con el backend</div>}
      {data?.notes.map((note) => (
        <div key={note.id} style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 13 }}>{note.title}</div>
          <div
            className="label"
            style={{ textTransform: 'none', letterSpacing: 0, lineHeight: 1.5, marginTop: 2 }}
          >
            {note.excerpt}
          </div>
        </div>
      ))}
    </div>
  );
}
