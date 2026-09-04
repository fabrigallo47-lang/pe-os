import React, { useState } from 'react';

interface CaseChoice {
  id: string;
  name: string;
}

interface NoCaseSelectedProps {
  cases?: CaseChoice[];
  onStartNewCase?: () => void;
  onOpenExistingCase?: () => void;
  onSelectCase?: (id: string) => void;
}

export function NoCaseSelected({ cases = [], onStartNewCase, onOpenExistingCase, onSelectCase }: NoCaseSelectedProps) {
  const [choosing, setChoosing] = useState(false);
  const canOpenExisting = Boolean(onOpenExistingCase || (cases.length && onSelectCase));

  const openExisting = () => {
    if (onOpenExistingCase) onOpenExistingCase();
    else setChoosing(value => !value);
  };

  return <main className="p-page p-zero-state p-no-case-state">
    <section>
      <div className="p-kicker">PANTA</div>
      <h1>No case selected</h1>
      <p>Start a new investment case or open one that already exists.</p>
      <div className="p-action-row p-zero-state-actions">
        <button type="button" className="p-btn p-btn-primary" disabled={!onStartNewCase} onClick={onStartNewCase}>Start new case</button>
        <button type="button" className="p-btn" aria-expanded={onOpenExistingCase ? undefined : choosing} aria-controls={!onOpenExistingCase && cases.length ? 'existing-case-options' : undefined} disabled={!canOpenExisting} onClick={openExisting}>Open existing case</button>
      </div>
      {!onStartNewCase && <p className="p-zero-state-note">Starting a case is not available in this workspace.</p>}
      {!canOpenExisting && <p className="p-zero-state-note">No existing cases are available.</p>}
      {choosing && cases.length > 0 && <div id="existing-case-options" className="p-case-choice" aria-label="Existing cases">
        <strong>Choose a case</strong>
        {cases.map(item => <button type="button" key={item.id} onClick={() => onSelectCase?.(item.id)}>{item.name}<span aria-hidden="true">→</span></button>)}
      </div>}
    </section>
  </main>;
}

interface NewEmptyCaseProps {
  caseName: string;
  ownerName?: string;
  canAddMaterial: boolean;
  adding: boolean;
  onAddMaterial: () => void;
}

export function NewEmptyCase({ caseName, ownerName, canAddMaterial, adding, onAddMaterial }: NewEmptyCaseProps) {
  return <main className="p-page p-zero-state p-new-case-state">
    <section>
      <div className="p-kicker">Formation · New case</div>
      <h1>{caseName}</h1>
      <p>Add the first deck, call notes, model, or other deal material. PANTA will use what you provide to form the initial investment case for the Case Owner to review.</p>
      <div className="p-new-case-owner">
        <span>Case Owner</span>
        <strong>{ownerName ?? 'Owner not established'}</strong>
      </div>
      <div className="p-action-row p-zero-state-actions">
        <button type="button" className="p-btn p-btn-primary" disabled={!canAddMaterial || adding} title={!canAddMaterial ? 'Requires Add material authority' : undefined} onClick={onAddMaterial}>{adding ? 'Adding material…' : 'Add material'}</button>
      </div>
      <ol className="p-new-case-next" aria-label="What happens after material is added">
        <li><span>01</span><strong>PANTA reads the material</strong></li>
        <li><span>02</span><strong>Workstreams, questions and initial readings emerge</strong></li>
        <li><span>03</span><strong>The Case Owner reviews and adopts the structure</strong></li>
      </ol>
    </section>
  </main>;
}

export function EmptyCase() {
  return <NoCaseSelected />;
}
