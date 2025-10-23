"""
Enhanced Reasoning Agent - News Domain Rules Implementation
Leveraging full Nucleoid potential for advanced news validation logic
"""

# NEWS CREDIBILITY RULES
NEWS_DOMAIN_RULES = [
    # Source credibility based on track record
    "if (source_age_days > 365 && fact_checks_passed > 50 && error_rate < 0.1) then source_tier = 'tier1'",
    "if (source_tier == 'tier1' && claim_controversial == false) then auto_approve_threshold = 0.7",
    "if (source_tier == 'tier1' && claim_controversial == true) then auto_approve_threshold = 0.9",

    # Breaking news validation
    "if (news_type == 'breaking' && confirmation_sources < 2) then require_manual_review = true",
    "if (news_type == 'breaking' && time_since_event < 60_minutes) then confidence_penalty = 0.2",

    # Cross-reference validation
    "if (claim_in_reuters == true && claim_in_ap == true) then cross_confirmation_bonus = 0.3",
    "if (claim_only_in_single_source == true && controversy_score > 0.8) then skepticism_flag = true",

    # Temporal consistency
    "if (quoted_event_date > publication_date) then temporal_error = true",
    "if (article_age_hours > 48 && urgency_tag == 'breaking') then stale_breaking_flag = true",

    # Multi-agent consensus
    "if (scout_confidence > 0.8 && fact_checker_score > 0.75 && analyst_sentiment == 'factual') then strong_consensus = true",
    "if (agent_agreement_count >= 3 && average_confidence > 0.85) then high_confidence_consensus = true",

    # Contradiction handling
    "if (internal_contradiction_detected == true) then credibility_score -= 0.4",
    "if (contradicts_established_fact == true) then flag_for_investigation = true",

    # Evidence strength rules
    "if (primary_sources_count >= 2 && expert_quotes >= 1) then evidence_strength = 'strong'",
    "if (evidence_strength == 'strong' && source_tier == 'tier1') then verification_confidence = 0.95"
]

# TEMPORAL REASONING RULES
TEMPORAL_RULES = [
    "if (event_timestamp > current_timestamp) then future_event_flag = true",
    "if (breaking_news_age_minutes > 180) then no_longer_breaking = true",
    "if (fact_last_updated_days > 30 && fact_volatility == 'high') then revalidation_required = true"
]

# AGENT ORCHESTRATION RULES
ORCHESTRATION_RULES = [
    "if (fact_checker_confidence < 0.6) then escalate_to_reasoning_validation = true",
    "if (scout_quality_score < 0.5) then skip_detailed_analysis = true",
    "if (multiple_agents_disagree == true) then require_chief_editor_review = true"
]


class EnhancedReasoningEngine:
    def __init__(self, nucleoid_engine=None):
        """Create an EnhancedReasoningEngine.

        If `nucleoid_engine` is provided, it will be used (preferred) so the
        runtime has a single shared engine instance. Otherwise a local
        NucleoidEngine wrapper will be created lazily.
        """
        if nucleoid_engine is not None:
            self.nucleoid = nucleoid_engine
        else:
            # import lazily to avoid circular imports during module import
            from .main import NucleoidEngine as _NucleoidEngine
            self.nucleoid = _NucleoidEngine()

        # Detect engine capabilities. If the engine exposes add_rule/add_fact/query
        # we can load the expressive NEWS rules. If it only exposes `run` (the
        # lightweight Nucleoid), skip loading domain rules because they use a
        # different DSL and would raise syntax errors.
        self._supports_add_rule = hasattr(self.nucleoid, 'add_rule')
        self._supports_query = hasattr(self.nucleoid, 'query')

        if self._supports_add_rule:
            try:
                self._load_news_domain_rules()
            except Exception:
                # swallow to avoid import-time failures
                pass

    def _load_news_domain_rules(self):
        """Load comprehensive news domain validation rules"""
        for rule in NEWS_DOMAIN_RULES + TEMPORAL_RULES + ORCHESTRATION_RULES:
            try:
                self._add_rule(rule)
            except Exception:
                # Silently continue; engine may not be ready during import-time
                pass

    def validate_news_claim_with_context(self, claim: str, article_metadata: dict) -> dict:
        """Advanced news validation using domain-specific logic"""
        # Add article context as facts
        for key, value in article_metadata.items():
            try:
                if isinstance(value, str):
                    self._add_fact({"statement": f"{key} = \"{value}\""})
                else:
                    self._add_fact({"statement": f"{key} = {value}"})
            except Exception:
                continue

        # Add the claim
        try:
            self._add_fact({"statement": claim, "type": "claim"})
        except Exception:
            pass

        # Query derived conclusions
        results = {
            "credibility_assessment": self._query("source_tier"),
            "requires_review": self._query("require_manual_review"),
            "confidence_modifier": self._query("confidence_penalty"),
            "evidence_strength": self._query("evidence_strength"),
            "temporal_validity": not self._query("temporal_error"),
            "reasoning_chain": None
        }

        return results

    def orchestrate_multi_agent_decision(self, agent_outputs: dict) -> dict:
        """Use Nucleoid to coordinate between multiple agents"""
        # Add agent outputs as facts
        for agent, output in agent_outputs.items():
            for key, value in output.items():
                try:
                    if isinstance(value, str):
                        self._add_fact({"statement": f"{agent}_{key} = \"{value}\""})
                    else:
                        self._add_fact({"statement": f"{agent}_{key} = {value}"})
                except Exception:
                    continue

        # Query orchestration logic using adapter _query so both wrapper
        # engines and raw Nucleoid.run implementations are supported.
        decision = {
            "consensus_reached": self._query("strong_consensus"),
            "confidence_level": self._query("high_confidence_consensus"),
            "requires_escalation": self._query("require_chief_editor_review"),
            "recommended_action": None,
            "explanation": None
        }

        return decision

    # Adapter helpers: support both the NucleoidEngine wrapper (with add_rule/add_fact/query)
    # and raw Nucleoid implementations that expose .run(statement)
    def _add_rule(self, rule: str):
        if hasattr(self.nucleoid, 'add_rule'):
            return self.nucleoid.add_rule(rule)
        if hasattr(self.nucleoid, 'run'):
            return self.nucleoid.run(rule)
        raise AttributeError('Underlying engine has no add_rule or run')

    def _add_fact(self, fact: dict):
        # Accept either dict with 'statement' or raw statement
        if hasattr(self.nucleoid, 'add_fact'):
            return self.nucleoid.add_fact(fact)
        if hasattr(self.nucleoid, 'run'):
            stmt = fact.get('statement') if isinstance(fact, dict) else str(fact)
            return self.nucleoid.run(stmt)
        raise AttributeError('Underlying engine has no add_fact or run')

    def _query(self, query_str: str):
        # Prefer a native `query` method if available, otherwise fall back to
        # `run`. Catch runtime errors from the engine (e.g. NameError when a
        # variable is not defined in the lightweight Nucleoid) and return
        # None so callers can handle missing values gracefully.
        if hasattr(self.nucleoid, 'query'):
            try:
                return self.nucleoid.query(query_str)
            except Exception:
                return None
        if hasattr(self.nucleoid, 'run'):
            try:
                return self.nucleoid.run(query_str)
            except Exception:
                return None
        raise AttributeError('Underlying engine has no query or run')

__all__ = ["EnhancedReasoningEngine", "NEWS_DOMAIN_RULES", "TEMPORAL_RULES", "ORCHESTRATION_RULES"]
