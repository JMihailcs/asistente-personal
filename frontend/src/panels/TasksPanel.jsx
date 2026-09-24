import { usePanelData } from './usePanelData.js';
import EditableRow from './EditableRow.jsx';
import { proposeChange } from './proposeChange.js';

export default function TasksPanel({ refreshKey, onProposed }) {
  const { data, disconnected } = usePanelData('/tasks', { refreshKey });

  async function propose(payload) {
    const ok = await proposeChange(payload);
    if (ok) onProposed?.();
    return ok;
  }

  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 10 }}>tareas</div>
      {disconnected && <div className="label live">sin conexión con el backend</div>}
      {data?.lists.map((list) => (
        <div key={list.name} style={{ marginBottom: 12 }}>
          <div className="label" style={{ marginBottom: 4 }}>{list.name}</div>
          {list.tasks.map((task, index) => (
            <EditableRow
              key={`${task.text}-${index}`}
              initialValue={task.text}
              onEdit={(newText) =>
                propose({ action: 'edit_task', list_name: list.name, text: task.text, new_text: newText })
              }
              onDelete={() =>
                propose({ action: 'delete_task', list_name: list.name, text: task.text })
              }
            >
              <div style={{ fontSize: 13, opacity: task.done ? 0.45 : 1, lineHeight: 1.6 }}>
                {task.done ? '☑' : '☐'} {task.text}
              </div>
            </EditableRow>
          ))}
        </div>
      ))}
    </div>
  );
}
