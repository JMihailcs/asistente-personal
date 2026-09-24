import { useState } from 'react';

// Fila con "editar" y "eliminar". Ambos solo proponen el cambio.
export default function EditableRow({ children, initialValue, onEdit, onDelete }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(initialValue);

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
            await onEdit(value);
            setEditing(false);
          }}
        >
          guardar
        </button>
        <button type="button" onClick={() => setEditing(false)}>cancelar</button>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
      <div style={{ flex: 1 }}>{children}</div>
      <button type="button" onClick={() => setEditing(true)}>editar</button>
      <button type="button" onClick={() => onDelete()}>eliminar</button>
    </div>
  );
}
