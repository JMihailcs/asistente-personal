// Pide editar/eliminar algo. No ejecuta nada: el backend deja una accion
// pendiente que se aprueba en el panel "por confirmar".
export async function proposeChange(payload) {
  const response = await fetch('/changes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  return response.ok;
}
