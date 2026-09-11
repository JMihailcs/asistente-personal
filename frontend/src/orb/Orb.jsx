import { useEffect, useRef } from 'react';
import { createOrb } from './orb.js';

export default function Orb({ state = 'idle', level = 0 }) {
  const canvasRef = useRef(null);
  const orbRef = useRef(null);

  useEffect(() => {
    orbRef.current = createOrb(canvasRef.current);
    return () => {
      orbRef.current?.dispose();
      orbRef.current = null;
    };
  }, []);

  useEffect(() => {
    orbRef.current?.setState(state);
  }, [state]);

  useEffect(() => {
    orbRef.current?.setLevel(level);
  }, [level]);

  return <canvas ref={canvasRef} style={{ width: '100%', height: '100%', display: 'block' }} />;
}
