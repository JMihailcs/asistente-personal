import { usePanelData } from './usePanelData.js';

const LOAD_THRESHOLD = 80;

function Metric({ label, value, percent }) {
  const underLoad = typeof percent === 'number' && percent >= LOAD_THRESHOLD;
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'baseline' }}>
      <span className="label">{label}</span>
      <span
        className={underLoad ? 'live' : undefined}
        style={{ fontFamily: 'var(--font-mono)', fontSize: 12, textAlign: 'right' }}
      >
        {value}
      </span>
    </div>
  );
}

export default function SystemPanel() {
  const { data, disconnected } = usePanelData('/system', { intervalMs: 5000 });

  return (
    <div className="panel">
      <div className="label" style={{ marginBottom: 10 }}>sistema</div>
      {disconnected && <div className="label live">sin conexión con el backend</div>}
      {data && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <Metric
            label="ram"
            value={`${data.ram.available_gb} / ${data.ram.total_gb} GB`}
            percent={data.ram.percent_used}
          />
          <Metric
            label="disco"
            value={`${data.disk.free_gb} GB libres`}
            percent={data.disk.percent_used}
          />
          {data.gpu.available ? (
            <Metric
              label="gpu"
              value={`${data.gpu.vram_used_percent}% vram`}
              percent={data.gpu.vram_used_percent}
            />
          ) : (
            <Metric label="gpu" value={data.gpu.reason} />
          )}
        </div>
      )}
    </div>
  );
}
