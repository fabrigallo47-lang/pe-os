import type { Claim, PantaCaseSnapshot, SourceLocator } from '../types/domain';

/** Resolve canonical version lineage; the convenience sourceId must agree. */
export function sourceLocatorForClaim(snapshot: PantaCaseSnapshot, claim: Claim): SourceLocator | undefined {
  const version = snapshot.sourceVersions.find(item => item.id === claim.sourceVersionId);
  const sourceId = version?.sourceId ?? claim.sourceId;
  if (!sourceId || (version && claim.sourceId && version.sourceId !== claim.sourceId)) return undefined;
  return { sourceId, sourceVersionId: claim.sourceVersionId, locator: claim.locator, claimId: claim.id };
}

/** An inspection may cite multiple passages from one source. Keep each address. */
export function inspectionSourceLocators(snapshot: PantaCaseSnapshot, objectId: string, locators: SourceLocator[]): SourceLocator[] {
  const claim = snapshot.claims.find(item => item.id === objectId);
  const direct = claim && sourceLocatorForClaim(snapshot, claim);
  const candidates = [...(direct ? [direct] : []), ...locators].map(ref => {
    const cited = snapshot.claims.find(item => item.id === ref.claimId);
    const canonical = cited && sourceLocatorForClaim(snapshot, cited);
    return canonical?.sourceId === ref.sourceId
      ? { ...ref, sourceVersionId: ref.sourceVersionId || canonical.sourceVersionId, locator: ref.locator || canonical.locator }
      : ref;
  });
  const seen = new Set<string>();
  return candidates.filter(ref => {
    const key = JSON.stringify([ref.sourceId, ref.sourceVersionId ?? '', ref.claimId ?? '', ref.locator ?? '']);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function resolveSourceEvidence(snapshot: PantaCaseSnapshot, target: SourceLocator) {
  const source = snapshot.sources.find(item => item.id === target.sourceId);
  const claim = target.claimId ? snapshot.claims.find(item => item.id === target.claimId) : undefined;
  const versionId = target.sourceVersionId || claim?.sourceVersionId || (!target.claimId && !target.locator ? source?.currentVersionId : undefined);
  const version = snapshot.sourceVersions.find(item => item.id === versionId);
  const claimVersion = snapshot.sourceVersions.find(item => item.id === claim?.sourceVersionId);
  const conflict = Boolean(
    (version && version.sourceId !== target.sourceId) ||
    (claimVersion && claimVersion.sourceId !== target.sourceId) ||
    (claim?.sourceId && claim.sourceId !== target.sourceId) ||
    (target.sourceVersionId && claim && target.sourceVersionId !== claim.sourceVersionId) ||
    (target.locator && claim?.locator && target.locator !== claim.locator)
  );
  const missingClaim = Boolean(target.claimId && !claim);
  const missingLineage = Boolean(claim && !claim.sourceId && !claimVersion);
  const exact = Boolean(target.claimId || target.sourceVersionId || target.locator);
  const locator = conflict ? undefined : target.locator || claim?.locator || (!exact ? source?.locator : undefined);
  // A document overview or current-version excerpt cannot stand in for a cited passage.
  const excerpt = conflict || missingClaim ? undefined : claim
    ? claim.verbatimOrLosslessSpan || claim.excerpt
    : !exact ? source?.excerpt : undefined;
  const issue = conflict ? 'The statement and source references do not agree. The cited passage cannot be verified.'
    : !source ? 'This source is not available in the selected case state.'
    : missingClaim ? 'The cited statement is not available in the selected case state.'
    : missingLineage ? 'The statement’s source version is not available. Its source cannot be verified.'
    : undefined;
  return { source, claim: issue ? undefined : claim, version, versionId, locator, excerpt: issue ? undefined : excerpt, issue, exact,
    historical: Boolean(versionId && source?.currentVersionId && versionId !== source.currentVersionId) };
}
