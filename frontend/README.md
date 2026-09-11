# Frontend de Mikha

Dashboard en React + Vite: el orbe, el chat con streaming y los paneles
de estado. En produccion lo sirve el propio backend desde `dist/`; esta
carpeta solo hace falta para desarrollarlo.

```bash
npm install
npm run dev    # recarga en vivo, con proxy de la API al backend en el 8000
npm test       # vitest
npm run lint   # oxlint
```

## Como esta organizado

| Carpeta | Responsabilidad |
|---|---|
| `src/orb/` | El orbe: sistema de particulas Three.js y su ciclo de vida |
| `src/chat/` | Envio de mensajes, parseo del SSE y seguidor de envolvente |
| `src/panels/` | Paneles de sistema, tareas, notas y confirmaciones |
| `src/styles/` | Tokens de color y tipografia |

`src/orb/orb.js` es Three.js puro, sin React: `Orb.jsx` solo lo monta y
le pasa `state` y `level`. Esa separacion es a proposito — la animacion
corre en su propio bucle, ajena a los renders de React.
