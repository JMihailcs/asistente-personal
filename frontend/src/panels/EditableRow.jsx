import { useState } from 'react';

// Fila con "editar" y "eliminar". Ambos solo proponen el cambio.
export default function EditableRow({ children, initialValue, onEdit, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(initialValue);
  const [failed, setFailed] = useState(false);

  async function run(action) {
    const ok = await action();
    setFailed(ok === false);
    return ok !== false;
  }

  if (editing) {
    return (
      <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
        <input
          aria-label="nuevo texto"
          value={value}
          onChange={(event) => setValue(event.target.value)}
        />
        <button
          type="button"
          onClick={async () => {
            if (await run(() => onEdit(value))) setEditing(false);
          }}
        >
          guardar
        </button>
        <button
          type="button"
          onClick={() => {
            setFailed(false);
            setEditing(false);
          }}
        >
          cancelar
        </button>
        {failed && <span role="alert">no se pudo proponer el cambio</span>}
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
      <div style={{ flex: 1 }}>{children}</div>
      <button type="button" onClick={() => setEditing(true)}>editar</button>
      <button type="button" onClick={() => run(() => onDelete())}>eliminar</button>
      {failed && <span role="alert">no se pudo proponer el cambio</span>}
    </div>
  );
}
