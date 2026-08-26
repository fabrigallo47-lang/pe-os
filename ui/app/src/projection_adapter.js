(function(){
  'use strict';

  const clone = value => JSON.parse(JSON.stringify(value));
  const arr = value => Array.isArray(value) ? value : value && typeof value === 'object' ? Object.values(value) : [];

  function normalizeCasePosition(position){
    return {
      id: position.position_id || position.cp_id || position.id,
      statement: position.statement || position.view || position.label || position.metric || position.name || 'Unnamed position',
      value: position.typed_value ?? position.value ?? null,
      unit: position.unit || '',
      period: position.period || position.period_iso || position.effective_date || '',
      perimeter: position.perimeter || '',
      epistemic: position.epistemic_class || position.epistemic || 'UNKNOWN',
      decision_status: position.decision_status || position.status || 'CURRENT',
      support_route_ids: position.support_route_ids || (position.support_routes || []).map(route => route.route_id).filter(Boolean),
      model_node_ids: position.model_node_ids || []
    };
  }

  function normalizeClaim(claim){
    return {
      id: claim.claim_id || claim.stable_id || claim.id,
      statement: claim.statement || claim.text || claim.label || '',
      value: claim.typed_value ?? claim.value ?? null,
      unit: claim.unit || '',
      period: claim.period || claim.effective_date || '',
      perimeter: claim.perimeter || '',
      epistemic: claim.epistemic_class || claim.epistemic || 'UNKNOWN',
      source_id: claim.source_id || claim.source_doc || claim.document_version_id || null,
      locator: claim.source_locator || claim.locator || null,
      known_at: claim.known_at || null
    };
  }

  function normalizeModelNode(node){
    return {
      id: node.model_node_id || node.id,
      label: node.label || node.name || node.model_node_id || node.id,
      value: node.current_value ?? node.initial_value ?? node.value_current ?? node.value ?? null,
      unit: node.unit || '',
      period: node.period || node.effective_date || '',
      perimeter: node.perimeter || '',
      computational_form: node.computational_form || null,
      workbook_ref: node.workbook_ref || null,
      formula_id: node.formula_id || null
    };
  }

  function fromCompilerBundle(bundle){
    const current = bundle.current_graph || bundle.current || bundle.case || bundle;
    const mapping = bundle.execution_mapping || bundle.mapping || {};
    return {
      case_id: current.case_id || current.deal || bundle.case_id,
      company: current.company || current.deal?.company || '',
      state: current.state || 'CURRENT',
      as_of_known_at: current.as_of_known_at || current.known_at || null,
      claims: arr(current.claims || bundle.claims).map(normalizeClaim),
      case_positions: arr(current.case_positions || current.positions).map(normalizeCasePosition),
      support_routes: arr(current.support_routes),
      claim_position_edges: arr(current.claim_position_edges),
      position_dependencies: arr(current.position_dependencies),
      model_nodes: arr(current.model_nodes || mapping.model_nodes).map(normalizeModelNode),
      coverage_limits: arr(current.coverage_gaps || current.coverage_limits || mapping.coverage_limits),
      artifacts: arr(current.artifacts),
      manifest: bundle.admission_manifest || bundle.manifest || null,
      mapping_version: mapping.mapping_version || null,
      raw: clone(bundle)
    };
  }

  function fromTransitionOutput(output){
    const affected = arr(output.affected_set || output.ordered_transitions || output.model_node_deltas).map((item,index)=>({
      order:item.order || index+1,
      object_id:item.object_id || item.target_ref || item.model_node_id || item.id,
      label:item.label || item.name || item.object_id || item.target_ref || item.model_node_id || item.id,
      disposition:item.disposition || item.behavior || item.transition_type || 'RECOMPUTES',
      before:item.before ?? item.old_value ?? item.old ?? null,
      after:item.after ?? item.new_value ?? item.new ?? null,
      explanation:item.explanation || item.reason || item.detail || '',
      source_trace:item.source_trace || item.source_ref || null
    }));
    return {
      schema_version:output.schema_version || 'frontend-transition-projection/1.0',
      run_id:output.run_id || output.transition_id || null,
      case_id:output.case_id || output.base_case_id || null,
      prior_state_id:output.prior_state_id || output.base_state || null,
      candidate_state_id:output.candidate_state_id || output.candidate_id || null,
      status:output.partial_settlement_status || output.status || 'UNKNOWN',
      affected_set:affected,
      recomputed_values:arr(output.recomputed_values || output.model_node_deltas),
      unchanged_objects:arr(output.unchanged_objects),
      human_stops:arr(output.human_stops),
      blocked_components:arr(output.blocked_components),
      coverage_limits:arr(output.coverage_limits),
      artifact_change_sets:arr(output.artifact_change_sets || output.change_sets),
      policy_result:output.policy_result || output.materiality || null,
      replay_hash:output.replay_hash || null,
      raw:clone(output)
    };
  }

  function frontendProjectionFromBackend(payload){
    if(payload.frontend_projection) return clone(payload.frontend_projection);
    return {
      compiler:fromCompilerBundle(payload),
      transition:payload.transition_output ? fromTransitionOutput(payload.transition_output) : null
    };
  }

  window.PantaProjectionAdapter = {
    fromCompilerBundle,
    fromTransitionOutput,
    frontendProjectionFromBackend,
    normalizeCasePosition,
    normalizeClaim,
    normalizeModelNode
  };
})();
