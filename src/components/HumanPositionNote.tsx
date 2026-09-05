import React from 'react';
import type { HumanPosition } from '../types/domain';
import { usePanta } from '../app/PantaContext';
import { actorById } from '../app/selectors';

export function HumanPositionNote({ position }: { position: HumanPosition }) {
  const { snapshot, setActiveObject } = usePanta();
  if (!snapshot) return null;
  const person = actorById(snapshot, position.authorActorId);
  return <button className="p-position-note p-selectable" onClick={() => void setActiveObject(position.id)}>
    <span className="p-position-label">Human view</span>
    <span>{position.text}</span>
    <small>{person?.displayName ?? 'Attributed reviewer'} · {formatDate(position.recordedAt)}</small>
  </button>;
}
function formatDate(value:string){try{return new Intl.DateTimeFormat('en',{day:'numeric',month:'short',year:'numeric'}).format(new Date(value));}catch{return value}}
