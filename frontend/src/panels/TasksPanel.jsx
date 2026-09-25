import { usePanelData } from './usePanelData.js';

export default function TasksPanel({ refreshKey }) {
  const { data, disconnected } = usePanelData('/tasks', { refreshKey });

  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 10 }}>tareas</div>
      {disconnected && <div className="label live">sin conexión con el backend</div>}
      {data?.lists.map((list) => (
        <div key={list.name} style={{ marginBottom: 12 }}>
          <div className="label" style={{ marginBottom: 4 }}>{list.name}</div>
          {list.tasks.map((task, index) => (
            <div
              key={`${task.text}-${index}`}
              style={{ fontSize: 13, opacity: task.done ? 0.45 : 1, lineHeight: 1.6 }}
            >
              {task.done ? '☑' : '☐'} {task.text}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
