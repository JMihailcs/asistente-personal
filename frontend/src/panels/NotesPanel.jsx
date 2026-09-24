import { usePanelData } from './usePanelData.js';
import EditableRow from './EditableRow.jsx';
import { proposeChange } from './proposeChange.js';

export default function NotesPanel({ refreshKey, onProposed }) {
  const { data, disconnected } = usePanelData('/notes/recent', { refreshKey });

  async function propose(payload) {
    const ok = await proposeChange(payload);
    if (ok) onProposed?.();
    return ok;
  }

  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 10 }}>notas recientes</div>
      {disconnected && <div className="label live">sin conexión con el backend</div>}
      {data?.notes.map((note) => (
        <EditableRow
          key={note.id}
          initialValue={note.title}
          onEdit={(title) => propose({ action: 'edit_note', note: note.id, new_title: title })}
          onDelete={() => propose({ action: 'delete_note', note: note.id })}
        >
          <div style={{ marginBottom: 10 }}>
            <div style={{ fontSize: 13 }}>{note.title}</div>
            <div
              className="label"
              style={{ textTransform: 'none', letterSpacing: 0, lineHeight: 1.5, marginTop: 2 }}
            >
              {note.excerpt}
            </div>
          </div>
        </EditableRow>
      ))}
    </div>
  );
}
