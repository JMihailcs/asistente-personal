import { usePanelData } from './usePanelData.js';

export default function PendingActionsPanel({ refreshKey, onResolved }) {
  const { data } = usePanelData('/actions/pending', { refreshKey });

  async function resolve(actionId, approve) {
    await fetch(`/confirm/${actionId}?approve=${approve}`, { method: 'POST' });
    onResolved?.();
  }

  // Este panel solo existe cuando te necesita: es la unica parte de la UI
  // que interrumpe visualmente.
  if (!data || data.actions.length === 0) return null;

  return (
    <div className="panel" style={{ borderColor: 'var(--amber)' }}>
      <div className="label live" style={{ marginBottom: 10 }}>por confirmar</div>
      {data.actions.map((action) => (
        <div key={action.action_id} style={{ marginBottom: 10 }}>
          <div style={{ fontSize: 13 }}>
            {action.tool_name} {Object.values(action.kwargs).join(' ')}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            <button type="button" onClick={() => resolve(action.action_id, true)}>
              aprobar
            </button>
            <button type="button" onClick={() => resolve(action.action_id, false)}>
              rechazar
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
