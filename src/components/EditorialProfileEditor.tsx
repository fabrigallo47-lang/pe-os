import React, { useEffect, useState } from 'react';
import { usePanta } from '../app/PantaContext';
import type { Artifact, EditorialConfig } from '../types/domain';

type TextKey = Exclude<keyof EditorialConfig, 'sections'>;
const COMMON: Array<[TextKey, string, number]> = [
  ['name', 'Profile name', 120], ['language', 'Memo language', 80],
  ['audience', 'Audience', 1000], ['tone', 'Tone and terminology', 1000],
  ['decisionPurpose', 'Decision requested', 2000], ['investmentContext', 'Fund strategy, investment type and stage', 2000],
  ['lengthGuidance', 'Length and depth', 2000],
];
const ADVANCED: Array<[TextKey, string, number]> = [
  ['analysisGuidance', 'Analysis and investment thesis', 3000], ['recommendationGuidance', 'Conclusions and recommendations', 3000],
  ['numbersGuidance', 'Metrics, periods and calculations', 3000], ['scenarioGuidance', 'Scenarios and sensitivities', 3000],
  ['riskGuidance', 'Risks, mitigations and open diligence', 3000], ['evidenceGuidance', 'Evidence, contradictions and missing information', 3000],
  ['citationGuidance', 'Citations and source presentation', 2000], ['presentationGuidance', 'Tables, charts and appendices', 3000],
  ['qualityCriteria', 'Quality criteria', 3000],
];

export function EditorialProfileEditor({ artifact, disabled, onEditingChange }: { artifact?: Artifact; disabled: boolean; onEditingChange: (editing: boolean) => void }) {
  const { snapshot, actor, execute, pendingAction, asOf } = usePanta();
  const [draft, setDraft] = useState<{ config: EditorialConfig; versionId: string } | null>(null);
  const [notice, setNotice] = useState('');
  useEffect(() => { onEditingChange(Boolean(draft)); return () => onEditingChange(false); }, [Boolean(draft), onEditingChange]);
  if (!snapshot?.editorialContext) return null;
  const context = snapshot.editorialContext;
  const { profile } = context;
  const canConfigure = !asOf && context.configurable && actor?.entitlements.includes('EDIT_EDITORIAL_PROFILE');
  const canApply = !asOf && actor?.entitlements.includes('EDIT_ARTIFACT') && artifact?.editorialUpdateAvailable;
  const pending = artifact?.blockIds.some(id => snapshot.artifactBlocks.find(b => b.id === id)?.suggestion);
  const busy = disabled || Boolean(pendingAction);
  const valid = draft && [...COMMON, ...ADVANCED].every(([key]) => draft.config[key].trim()) && draft.config.sections.every(s => s.title.trim());
  const changed = draft && JSON.stringify(draft.config) !== JSON.stringify(profile.config);
  function update(key: TextKey, value: string) { setDraft(d => d ? { ...d, config: { ...d.config, [key]: value } } : d); }
  function move(index: number, delta: number) {
    setDraft(d => { if (!d) return d; const sections = [...d.config.sections]; [sections[index], sections[index + delta]] = [sections[index + delta], sections[index]]; return { ...d, config: { ...d.config, sections } }; });
  }
  async function save() {
    if (!draft) return;
    if (await execute({ type: 'SAVE_EDITORIAL_PROFILE', config: draft.config, expectedProfileVersion: draft.versionId })) {
      setDraft(null); setNotice('Fund profile saved. Existing memos keep their previous profile until you apply this version.');
    }
  }
  const fields = (items: typeof COMMON) => <div className="p-editorial-fields">{items.map(([key, label, limit]) => <label key={key}>{label}{limit <= 120
    ? <input value={draft!.config[key]} maxLength={limit} onChange={e => update(key, e.target.value)} />
    : <textarea rows={3} value={draft!.config[key]} maxLength={limit} onChange={e => update(key, e.target.value)} />}</label>)}</div>;
  return <section className="p-editorial-profile" aria-label="Fund editorial profile">
    <div className="p-editorial-heading"><div><strong>{profile.fund?.name ?? 'Default editorial profile'}</strong><p>{profile.config.name} · {profile.version ? `Version ${profile.version}` : 'Default'} · {profile.config.language}</p></div>
      <button className="p-btn" disabled={busy || !canConfigure || Boolean(draft)} onClick={() => { setDraft({ config: structuredClone(profile.config), versionId: profile.versionId }); setNotice(''); }}>Customize fund profile</button>
    </div>
    {!canConfigure && <p className="p-meta">{context.unavailableReason || 'A fund profile can be edited by a partner for this case.'}</p>}
    <p className="p-meta">Shared by cases in this fund. {artifact ? `This memo uses ${artifact.editorialProfile?.config.name ?? 'the original editorial settings'}${artifact.editorialProfile ? ` · ${artifact.editorialProfile.version ? `version ${artifact.editorialProfile.version}` : 'default version'}` : ''}.` : 'New IC memos use the latest saved profile.'}</p>
    {artifact?.editorialUpdateAvailable && <div className="p-editorial-update"><span>A newer fund profile is available. Applying it updates headings and order, keeps passage text, and returns the memo to draft for review.</span><button className="p-btn p-btn-accent" disabled={busy || !canApply || Boolean(draft) || pending} onClick={async () => { if (await execute({ type: 'APPLY_EDITORIAL_PROFILE', artifactId: artifact.id, expectedProfileVersion: profile.versionId })) setNotice('Profile applied. Review the memo and use Suggest redraft to request wording in the selected style.'); }}>Apply profile to this memo</button>{pending && <small>Review the pending passage proposals first.</small>}</div>}
    {notice && <p role="status">{notice}</p>}
    {draft && <form onSubmit={e => { e.preventDefault(); void save(); }}>
      <fieldset disabled={busy}><legend>Customize the editorial brief</legend>{fields(COMMON)}
        <details className="p-editorial-sections" open><summary>Section titles and order</summary><p className="p-meta">Every available case content category remains included. Empty categories produce no invented content.</p>{draft.config.sections.map((section, index) => <div className="p-editorial-section-row" key={section.key}><span>{index + 1}</span><label><span className="p-editorial-key">{section.key.replaceAll('_', ' ')}</span><input aria-label={`Section title: ${section.key}`} maxLength={160} value={section.title} onChange={e => setDraft(d => d ? { ...d, config: { ...d.config, sections: d.config.sections.map(s => s.key === section.key ? { ...s, title: e.target.value } : s) } } : d)} /></label><button className="p-btn" type="button" aria-label={`Move ${section.title} up`} disabled={index === 0} onClick={() => move(index, -1)}>↑</button><button className="p-btn" type="button" aria-label={`Move ${section.title} down`} disabled={index === draft.config.sections.length - 1} onClick={() => move(index, 1)}>↓</button></div>)}</details>
        <details><summary>Analysis, evidence and presentation rules</summary>{fields(ADVANCED)}</details>
        <p className="p-meta">Preferences guide the writing assistant. Document links, recorded human views and missing evidence remain protected. Generated wording requires review.</p>
        {draft.versionId !== profile.versionId && <p role="alert">The fund profile changed while you were editing. Your draft is retained; cancel to load the latest profile before saving.</p>}
        <div className="p-action-row"><button className="p-btn p-btn-primary" type="submit" disabled={!valid || !changed || draft.versionId !== profile.versionId}>Save new profile version</button><button className="p-btn" type="button" onClick={() => setDraft(null)}>Cancel profile edits</button></div>
      </fieldset>
    </form>}
    {!draft && <details><summary>Saved brief and version history</summary><dl>{[...COMMON, ...ADVANCED].map(([key, label]) => <React.Fragment key={key}><dt>{label}</dt><dd>{profile.config[key]}</dd></React.Fragment>)}</dl><ol>{profile.config.sections.map(s => <li key={s.key}>{s.title}</li>)}</ol>{context.history.length ? <ul>{context.history.map(version => <li key={version.versionId}>Version {version.version} · {snapshot.actors.find(a => a.id === version.actorId)?.displayName ?? version.actorId} · {version.recordedAt}</li>)}</ul> : <p className="p-meta">No custom version saved yet.</p>}</details>}
  </section>;
}
