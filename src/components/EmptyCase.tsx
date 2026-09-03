import React from 'react';

export function EmptyCase({ onAdd }: { onAdd?: () => void }) {
  return <main className="p-page p-empty"><div><div className="p-kicker">PANTA</div><h1>No case is loaded</h1><p>This frontend contains no demo or fixture data. Connect a backend case adapter or add deal material to form a case.</p>{onAdd && <button className="p-btn p-btn-primary" onClick={onAdd}>Add material</button>}</div></main>;
}
