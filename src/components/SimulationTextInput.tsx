import React, { useEffect, useRef, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import type { GraphMutation, PantaCaseSnapshot, SimulationProposal } from '../types/domain';

export function SimulationTextInput({ snapshot, disabled, resetToken, onEditing, onSimulate, onInspect }: {
  snapshot: PantaCaseSnapshot; disabled: boolean; resetToken: number;
  onEditing: () => void; onSimulate: (mutations: GraphMutation[], description: string) => Promise<void>; onInspect: (id: string) => void;
}) {
  const { adapter } = usePanta();
  const [text, setText] = useState('');
  const [proposal, setProposal] = useState<SimulationProposal>();
  const [preparing, setPreparing] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const scope = snapshot.graphSimulationScope;
  const capability = snapshot.simulationTextInput;
  useEffect(() => {
    generation.current++; setText(''); setProposal(undefined); setPreparing(false); setError('');
    return () => { generation.current++; };
  }, [snapshot.caseRef.id, snapshot.caseVersion, scope?.version, resetToken]);
  function edit(value: string) {
    generation.current++; setText(value); setProposal(undefined); setPreparing(false); setError(''); onEditing();
  }
  function insertName(id: string) {
    const obj = scope?.objects.find(o => o.id === id);
    if (!obj) return;
    const start = textarea.current?.selectionStart ?? text.length, end = textarea.current?.selectionEnd ?? text.length;
    const name = '«' + obj.label + '»';
    edit(text.slice(0, start) + name + text.slice(end));
    requestAnimationFrame(() => { textarea.current?.focus(); textarea.current?.setSelectionRange(start + name.length, start + name.length); });
  }
  async function prepare() {
    if (!scope || !adapter.proposeSimulation || !text.trim()) return;
    const token = ++generation.current;
    setPreparing(true); setProposal(undefined); setError('');
    try {
      const result = await adapter.proposeSimulation(snapshot.caseRef.id, { text, caseVersion: scope.caseVersion, graphVersion: scope.version });
      if (token === generation.current) setProposal(result);
    } catch (reason) {
      if (token === generation.current) setError(reason instanceof Error ? reason.message : 'The description could not be interpreted.');
    } finally {
      if (token === generation.current) setPreparing(false);
    }
  }
  const labels = Object.fromEntries(scope?.objects.map(o => [o.id, o.label]) ?? []);
  function display(value: unknown): string {
    if (value === null || value === undefined) return 'Not recorded';
    if (value === true) return 'Usable'; if (value === false) return 'Not usable';
    if (Array.isArray(value)) return value.map(v => labels[String(v)] ?? String(v)).join(' · ') || 'No connections';
    if (typeof value === 'object') return 'lifecycle' in value && value.lifecycle === 'RETRACTED' ? 'Withdrawn' : 'Available';
    return String(value);
  }
  return <section className="p-sim-text-input" aria-label="Describe a scenario">
    <label htmlFor="simulation-description"><strong>What would you like to change?</strong><span>Describe one change or combine several. Review the interpretation before running the test.</span></label>
    <textarea ref={textarea} id="simulation-description" aria-label="Scenario description" maxLength={6000} rows={4} value={text} disabled={disabled} onChange={e => edit(e.target.value)} placeholder="Describe the hypothetical change…" />
    <div className="p-sim-text-tools"><label>Insert a case item (optional)<select aria-label="Insert case item name (optional)" value="" disabled={disabled} onChange={e => insertName(e.target.value)}><option value="">Choose an item…</option>{scope?.objects.filter(o => o.fields.length).map(o => <option key={o.id} value={o.id}>{o.kindLabel} · {o.label}</option>)}</select></label><span>{text.length}/6000</span></div>
    {!!capability?.examples.length && <div className="p-sim-text-examples" role="group" aria-label="Scenario examples (optional)"><span>Examples (optional)</span>{capability.examples.map(example => <button key={example.label} type="button" disabled={disabled} onClick={() => edit(example.text)}>{example.label}</button>)}</div>}
    {(!capability || !adapter.proposeSimulation) && <p>Text interpretation is not connected to this workspace. Use the item editor or refresh the case.</p>}
    <button className="p-btn p-btn-primary" disabled={disabled || preparing || !capability || !adapter.proposeSimulation || !text.trim()} onClick={() => void prepare()}>{preparing ? 'Preparing the changes…' : 'Preview proposed changes'}</button>
    {error && <p role="alert">{error}</p>}
    {proposal && <section className="p-sim-proposal" aria-label="Proposed scenario" aria-live="polite">
      <div className="p-section-heading"><h2>{proposal.status === 'READY' ? 'Review this interpretation' : 'A few details are still missing'}</h2><span>{proposal.interpreter === 'GUIDED' ? 'From your explicit instructions' : 'Suggested interpretation'}</span></div>
      {proposal.items.map(item => <article key={item.id}>
        <button className="p-unboxed-select" onClick={() => onInspect(item.objectId)}>{item.label}</button><p>{item.changeLabel}</p>
        <div className="p-sim-proposal-change"><div><small>Current</small><span>{display(item.before)}</span></div><span aria-hidden="true">→</span><div><small>Hypothetical</small><strong>{display(item.after)}</strong></div></div>
        <details><summary>Why this change was proposed</summary><blockquote>{item.sourceText}</blockquote><p>{item.rationale}</p></details>
      </article>)}
      {!!proposal.questions.length && <div className="p-sim-clarifications"><h3>Clarify your description</h3>{proposal.questions.map((question, index) => <div key={index}><p>{question.question}</p>{question.objectIds.map(id => <button key={id} className="p-related-link" onClick={() => onInspect(id)}>{labels[id]}</button>)}</div>)}<p>Edit the description above and preview it again. No part of an ambiguous proposal runs automatically.</p></div>}
      {proposal.limits.map(limit => <p key={limit}>{limit}</p>)}
      <div className="p-action-row"><button className="p-btn p-btn-primary" disabled={disabled || proposal.status !== 'READY'} onClick={() => void onSimulate(proposal.items.flatMap(item => item.mutations), proposal.text)}>Simulate these changes</button><button className="p-btn" disabled={disabled} onClick={() => { setProposal(undefined); textarea.current?.focus(); }}>Revise description</button></div>
    </section>}
  </section>;
}
