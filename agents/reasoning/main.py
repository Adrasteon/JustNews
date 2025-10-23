"""
Reasoning Agent (Nucleoid) - Production Implementation
Purpose: Symbolic reasoning, fact validation, contradiction detection, and explainability for news analysis
GPU Status: ❌ CPU Only (symbolic logic)
Performance: Fast for logic/rule queries; not GPU-accelerated
V4 Compliance: Designed for multi-agent orchestration, FastAPI, and MCP bus integration
Dependencies: git, networkx, fastapi, pydantic, uvicorn
"""

import asyncio
import importlib
import importlib.util
import json
import os
import subprocess
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from agents.common.schemas import NeuralAssessment, ReasoningInput
from common.observability import get_logger
from common.metrics import JustNewsMetrics

# Configure centralized logging
logger = get_logger(__name__)

ready = False

# Environment variables
REASONING_AGENT_PORT = int(os.environ.get("REASONING_AGENT_PORT", 8008))
MCP_BUS_URL = os.environ.get("MCP_BUS_URL", "http://localhost:8000")

class MCPBusClient:
    def __init__(self, base_url: str = MCP_BUS_URL):
        self.base_url = base_url

    def register_agent(self, agent_name: str, agent_address: str, tools: list):
        registration_data = {
            "name": agent_name,
            "address": agent_address,
        }
        try:
            response = requests.post(f"{self.base_url}/register", json=registration_data, timeout=(2, 5))
            response.raise_for_status()
            logger.info(f"Successfully registered {agent_name} with MCP Bus.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to register {agent_name} with MCP Bus: {e}")
            raise

class SimpleNucleoidImplementation:
    """Simple fallback implementation of Nucleoid for basic reasoning."""

    def __init__(self):
        self.facts = {}  # Store as key-value pairs
        self.rules = []

    def execute(self, statement: str) -> dict[str, Any]:
        """Execute a Nucleoid statement."""
        statement = statement.strip()

        # Handle variable assignments (facts) - simple assignments only
        if "=" in statement and "==" not in statement and not any(op in statement for op in ["+", "-", "*", "/", "if", "then"]):
            parts = statement.split("=")
            if len(parts) == 2:
                var_name = parts[0].strip()
                value = parts[1].strip()

                # Try to convert to number if possible
                try:
                    if "." in value:
                        value = float(value)
                    else:
                        value = int(value)
                except ValueError:
                    # Keep as string if not a number
                    value = value.strip("\"'")

                self.facts[var_name] = value
                return {"success": True, "message": f"Variable {var_name} set to {value}"}

        # Handle rule definitions (y = x + 10, if-then statements)
        if "=" in statement and (any(op in statement for op in ["+", "-", "*", "/"]) or "if" in statement or "then" in statement):
            self.rules.append(statement)
            return {"success": True, "message": "Rule added"}

        # Handle queries (single variable)
        if statement.isalpha() or statement.replace("_", "").isalpha():
            # Check if it's a direct fact
            if statement in self.facts:
                return self.facts[statement]

            # Try to evaluate using rules
            for rule in self.rules:
                if "=" in rule and rule.split("=")[0].strip() == statement:
                    right_side = rule.split("=")[1].strip()
                    try:
                        # Simple expression evaluation
                        result = self._evaluate_expression(right_side)
                        if result is not None:
                            return result
                    except Exception:
                        pass

            return {"success": False, "message": f"Unknown variable: {statement}"}

        # Handle boolean queries (==, !=, etc.)
        if any(op in statement for op in ["==", "!=", ">", "<", ">=", "<="]):
            try:
                return self._evaluate_boolean(statement)
            except Exception:
                return {"success": False, "message": "Could not evaluate boolean expression"}

        return {"success": False, "message": "Unknown statement type"}

    def _evaluate_expression(self, expression: str) -> Any:
        """Evaluate a simple mathematical expression."""
        try:
            # Replace variables with their values
            for var, val in self.facts.items():
                expression = expression.replace(var, str(val))

            # Simple evaluation (be careful in production!)
            result = eval(expression)
            return result
        except Exception:
            return None

    def _evaluate_boolean(self, statement: str) -> bool:
        """Evaluate a boolean statement."""
        try:
            # Replace variables with their values
            for var, val in self.facts.items():
                if isinstance(val, str):
                    statement = statement.replace(var, f"'{val}'")
                else:
                    statement = statement.replace(var, str(val))

            # Evaluate the boolean expression
            result = eval(statement)
            return result
        except Exception:
            return False

    def run(self, statement: str) -> dict[str, Any]:
        """Alias for execute method to match expected interface."""
        return self.execute(statement)

    def clear(self) -> dict[str, Any]:
        """Clear all facts and rules."""
        self.facts = {}
        self.rules = []
        return {"success": True, "message": "Knowledge base cleared"}
# Define the lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Reasoning agent is starting up.")

    # Initialize engines during application startup instead of at import time
    global engine, enhanced_engine
    engine = None
    enhanced_engine = None

    try:
        engine = NucleoidEngine()
        logger.info("✅ Reasoning Agent initialized successfully")

        try:
            from .enhanced_reasoning_architecture import EnhancedReasoningEngine
            enhanced_engine = EnhancedReasoningEngine(nucleoid_engine=engine)
            logger.info("✅ EnhancedReasoningEngine initialized and rules loaded")
        except Exception as ee:
            logger.warning(f"Could not initialize EnhancedReasoningEngine: {ee}")

    except Exception as e:
        logger.error(f"❌ Failed to initialize Reasoning Agent: {e}")
        engine = None
        enhanced_engine = None

    # MCP Bus registration with configurable retries and backoff
    mcp_bus_client = MCPBusClient()
    retries = int(os.environ.get("MCP_REGISTER_RETRIES", "3"))
    backoff = float(os.environ.get("MCP_REGISTER_BACKOFF", "2.0"))
    for attempt in range(1, retries + 1):
        try:
            mcp_bus_client.register_agent(
                agent_name="reasoning",
                agent_address=f"http://localhost:{REASONING_AGENT_PORT}",
                tools=["validate_fact", "detect_contradiction", "symbolic_reasoning"]
            )
            logger.info("Registered tools with MCP Bus.")
            break
        except Exception as e:
            logger.warning(f"MCP registration attempt {attempt} failed: {e}")
            if attempt < retries:
                sleep_time = backoff * attempt
                logger.info(f"Retrying MCP registration in {sleep_time}s...")
                await asyncio.sleep(sleep_time)
            else:
                logger.warning("MCP registration failed after retries; running in standalone mode.")

    # Load preload rules if provided (after engine initialization)
    preload_file = os.environ.get("REASONING_AGENT_PRELOAD")
    if preload_file and Path(preload_file).exists():
        if engine is None:
            logger.warning("Preload rules present but engine not initialized; skipping preload")
        else:
            logger.info(f"Loading preloaded rules from {preload_file}")
            try:
                with open(preload_file) as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("RULE:"):
                            engine.add_rule(line[5:].strip())
                        elif line.startswith("FACT:"):
                            try:
                                fact_data = json.loads(line[5:].strip())
                            except Exception:
                                fact_data = {"statement": line[5:].strip()}
                            engine.add_fact(fact_data)
                logger.info("✅ Preloaded rules and facts loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load preloaded rules: {e}")

    # Domain rules are loaded by EnhancedReasoningEngine if available

    global ready
    ready = True
    logger.info("✅ Reasoning Agent startup complete")

    yield

    # Shutdown logic (save state if engine available)
    logger.info("Reasoning agent is shutting down.")
    if engine is not None:
        try:
            state_file = Path(__file__).parent / "reasoning_state.json"
            state_data = {
                "facts": engine.get_facts() if engine else {},
                "rules": engine.get_rules() if engine else [],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            with open(state_file, "w") as f:
                json.dump(state_data, f, indent=2)
            logger.info(f"✅ Reasoning state saved to {state_file}")
        except Exception as e:
            logger.warning(f"Failed to save reasoning state: {e}")

    logger.info("✅ Reasoning Agent shutdown complete")

app = FastAPI(title="JustNews V4 Reasoning Agent (Nucleoid)", lifespan=lifespan)

# Initialize metrics
metrics = JustNewsMetrics("reasoning")
app.middleware("http")(metrics.request_middleware)

# Register shutdown endpoint if available
try:
    from agents.common.shutdown import register_shutdown_endpoint
    register_shutdown_endpoint(app)
except Exception:
    logger.debug("shutdown endpoint not registered for reasoning")

# Register reload endpoint if available
try:
    from agents.common.reload import register_reload_endpoint
    register_reload_endpoint(app)
except Exception:
    logger.debug("reload endpoint not registered for reasoning")
# --- Nucleoid GitHub Integration ---
class NucleoidEngine:
    """Wrapper for Nucleoid GitHub Python implementation."""

    def __init__(self):
        self.nucleoid: Any | None = None
        self.facts_store = {}  # Store facts for retrieval
        self.rules_store = []  # Store rules for retrieval
        self.session_id = "reasoning"
        self._setup_nucleoid()

    def _setup_nucleoid(self) -> None:
        """Setup Nucleoid Python implementation from our local implementation."""
        try:
            # Try to use our complete local implementation first
            from nucleoid_implementation import Nucleoid
            self.nucleoid = Nucleoid()
            logger.info("✅ Complete Nucleoid implementation loaded successfully")
            return

        except ImportError as e:
            logger.warning(f"Local implementation failed: {e}, trying GitHub repository...")

            # Fallback to GitHub repository approach
            nucleoid_dir = Path(__file__).parent / "nucleoid_repo"

            if not nucleoid_dir.exists():
                logger.info("Cloning Nucleoid repository...")
                subprocess.run([
                    "git", "clone",
                    "https://github.com/nucleoidai/nucleoid.git",
                    str(nucleoid_dir)
                ], check=True, capture_output=True)
                logger.info("✅ Nucleoid repository cloned successfully")

            # Add Python path for the nucleoid module
            python_path = str(nucleoid_dir / "python")
            if python_path not in sys.path:
                sys.path.insert(0, python_path)

                # Attempt a file-based import first to avoid static-analysis issues
                module_file = None
                candidate = Path(python_path) / "nucleoid" / "nucleoid.py"
                if candidate.exists():
                    module_file = candidate
                else:
                    # Try to find any matching file under the python path
                    matches = list(Path(python_path).rglob("nucleoid.py"))
                    if matches:
                        module_file = matches[0]

                if module_file:
                    try:
                        spec = importlib.util.spec_from_file_location("nucleoid_runtime_nucleoid", str(module_file))
                        if spec is not None:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)  # type: ignore[attr-defined]
                            NucleoidClass = getattr(module, "Nucleoid", None)
                            if NucleoidClass:
                                self.nucleoid = NucleoidClass()
                                logger.info("✅ Nucleoid GitHub implementation loaded successfully (file import)")
                                return
                    except Exception as e:
                        logger.warning(f"File-based import of Nucleoid failed: {e}")

                # As a last resort try package import (may still raise ImportError)
                try:
                    module = importlib.import_module("nucleoid.nucleoid")
                    NucleoidClass = getattr(module, "Nucleoid", None)
                    if NucleoidClass:
                        self.nucleoid = NucleoidClass()
                        logger.info("✅ Nucleoid GitHub implementation loaded successfully (package import)")
                        return
                except Exception as e:
                    logger.warning(f"Package import of nucleoid.nucleoid failed: {e}, using fallback...")

                # Final fallback
                self.nucleoid = SimpleNucleoidImplementation()
                logger.info("✅ Simple Nucleoid fallback implementation loaded")

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone Nucleoid repository: {e}")
            # Use fallback implementation
            self.nucleoid = SimpleNucleoidImplementation()
            logger.warning("Using fallback simple implementation")
        except Exception as e:
            logger.error(f"Unexpected error setting up Nucleoid: {e}")
            # Use fallback implementation
            self.nucleoid = SimpleNucleoidImplementation()
            logger.warning("Using fallback simple implementation")

    def add_fact(self, fact_data: dict[str, Any]) -> Any:
        """Add a fact to the reasoning system."""
        if self.nucleoid is None:
            raise RuntimeError("Nucleoid engine not initialized")
        try:
            # Convert fact to Nucleoid statement
            fact_id = f"fact_{len(self.facts_store)}"

            # Store fact for retrieval
            self.facts_store[fact_id] = fact_data

            # Create Nucleoid statement
            if "statement" in fact_data:
                # Direct statement execution
                result = self.nucleoid.run(fact_data["statement"])
            else:
                # Convert dict to variable assignments
                statements = []
                for key, value in fact_data.items():
                    if isinstance(value, str):
                        statements.append(f'{key} = "{value}"')
                    else:
                        statements.append(f'{key} = {value}')

                result = None
                for statement in statements:
                    result = self.nucleoid.run(statement)

            logger.info(f"Added fact {fact_id}: {fact_data}")
            return result

        except Exception as e:
            logger.error(f"Error adding fact: {e}")
            raise

    def add_rule(self, rule: str) -> Any:
        """Add a logical rule."""
        if self.nucleoid is None:
            raise RuntimeError("Nucleoid engine not initialized")
        try:
            # Store rule for retrieval
            self.rules_store.append(rule)

            # Execute rule in Nucleoid
            result = self.nucleoid.run(rule)

            logger.info(f"Added rule: {rule}")
            return result

        except Exception as e:
            logger.error(f"Error adding rule: {e}")
            raise

    def query(self, query_str: str) -> Any:
        """Execute a symbolic reasoning query."""
        if self.nucleoid is None:
            raise RuntimeError("Nucleoid engine not initialized")
        try:
            result = self.nucleoid.run(query_str)
            logger.info(f"Executed query: {query_str} -> {result}")
            return result

        except Exception as e:
            logger.error(f"Error executing query: {e}")
            raise

    def get_facts(self) -> dict[str, Any]:
        """Retrieve all stored facts."""
        return self.facts_store

    def get_rules(self) -> list[str]:
        """Retrieve all stored rules."""
        return self.rules_store

    def evaluate_contradiction(self, statements: list[str]) -> dict[str, Any]:
        """Check for logical contradictions between statements."""
        try:
            contradictions = []

            # Extract variable assignments and check for direct contradictions
            variable_assignments = {}

            for stmt in statements:
                # Check for direct variable assignments (x = 5, x = 10)
                if "=" in stmt and "==" not in stmt and not any(op in stmt for op in ["+", "-", "*", "/", "if", "then", ">", "<"]):
                    parts = stmt.split("=")
                    if len(parts) == 2:
                        var_name = parts[0].strip()
                        value = parts[1].strip()

                        # Try to convert to number for comparison
                        try:
                            if "." in value:
                                value = float(value)
                            else:
                                value = int(value)
                        except ValueError:
                            value = value.strip("\"'")

                        if var_name in variable_assignments:
                            if variable_assignments[var_name] != value:
                                contradictions.append({
                                    "statement1": f"{var_name} = {variable_assignments[var_name]}",
                                    "statement2": f"{var_name} = {value}",
                                    "conflict": "variable_reassignment_contradiction"
                                })
                        else:
                            variable_assignments[var_name] = value

            # Check for boolean contradictions (x == 5 vs x == 10)
            boolean_statements = [stmt for stmt in statements if any(op in stmt for op in ["==", "!=", ">", "<", ">=", "<="])]

            for i, stmt1 in enumerate(boolean_statements):
                for j, stmt2 in enumerate(boolean_statements[i+1:], i+1):
                    # Extract variable and values from boolean statements
                    try:
                        if self._are_contradictory_booleans(stmt1, stmt2):
                            contradictions.append({
                                "statement1": stmt1,
                                "statement2": stmt2,
                                "conflict": "boolean_contradiction"
                            })
                    except Exception:
                        pass  # Skip if can't parse

            return {
                "has_contradictions": len(contradictions) > 0,
                "contradictions": contradictions,
                "total_statements": len(statements)
            }

        except Exception as e:
            logger.error(f"Error evaluating contradictions: {e}")
            return {
                "has_contradictions": False,
                "contradictions": [],
                "total_statements": len(statements)
            }

    @staticmethod
    def _are_contradictory_booleans(stmt1: str, stmt2: str) -> bool:
        """Check if two boolean statements are contradictory."""
        # Simple check for directly contradictory statements
        # e.g., "temperature == 25" vs "temperature == 30"

        # Extract variable and operator for each statement
        for op in ["==", "!=", ">=", "<=", ">", "<"]:
            if op in stmt1 and op in stmt2:
                parts1 = stmt1.split(op)
                parts2 = stmt2.split(op)

                if len(parts1) == 2 and len(parts2) == 2:
                    var1, val1 = parts1[0].strip(), parts1[1].strip()
                    var2, val2 = parts2[0].strip(), parts2[1].strip()

                    # Same variable, same operator, different values
                    if var1 == var2 and op == "==" and val1 != val2:
                        return True

        return False

# Initialize Nucleoid engine (deferred to the FastAPI lifespan startup)
# Use runtime-safe accessors so other modules can obtain the engine without
# causing heavy import-time initialization.
engine: Any | None = None
enhanced_engine: Any | None = None


def get_engine(block: bool = False, timeout: float | None = None) -> Any | None:
    """Return the global Nucleoid engine instance if available.

    Args:
        block: If True, block until the engine is available or timeout is reached.
        timeout: Maximum seconds to wait when blocking. None means wait indefinitely.

    Returns:
        The engine instance or None if not available / timed out.
    """
    global engine
    if engine is not None:
        return engine
    if not block:
        return None

    import time
    start = time.time()
    while True:
        if engine is not None:
            return engine
        if timeout is not None and (time.time() - start) >= float(timeout):
            return None
        time.sleep(0.1)


def get_enhanced_engine(block: bool = False, timeout: float | None = None) -> Any | None:
    """Return the global EnhancedReasoningEngine if available.

    Same semantics as get_engine().
    """
    global enhanced_engine
    if enhanced_engine is not None:
        return enhanced_engine
    if not block:
        return None

    import time
    start = time.time()
    while True:
        if enhanced_engine is not None:
            return enhanced_engine
        if timeout is not None and (time.time() - start) >= float(timeout):
            return None
        time.sleep(0.1)

# --- Pydantic Models ---
class ToolCall(BaseModel):
    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    model_config = ConfigDict(arbitrary_types_allowed=True)

class Fact(BaseModel):
    data: dict[str, Any]

    model_config = ConfigDict(arbitrary_types_allowed=True)

class Facts(BaseModel):
    facts: list[dict[str, Any]]

    model_config = ConfigDict(arbitrary_types_allowed=True)

class Rule(BaseModel):
    rule: str

class Query(BaseModel):
    query: str

class Evaluate(BaseModel):
    expression: str

class ContradictionCheck(BaseModel):
    statements: list[str]

class FactValidation(BaseModel):
    claim: str
    context: dict[str, Any] | None = None

# --- Utility Functions ---
def log_feedback(event: str, details: dict[str, Any]):
    """Log feedback for debugging and improvement."""
    feedback_log = Path(__file__).parent / "feedback_reasoning.log"
    try:
        with open(feedback_log, "a", encoding="utf-8") as f:
            timestamp = datetime.now(timezone.utc).isoformat()
            f.write(f"{timestamp}\t{event}\t{json.dumps(details)}\n")
    except Exception as e:
        logger.warning(f"Failed to log feedback: {e}")


def _ingest_neural_assessment(assessment: NeuralAssessment) -> list[str]:
    """Convert a NeuralAssessment into a list of statements/facts for Nucleoid.

    This centralizes mapping logic so it's easy to test and evolve.
    """
    stmts: list[str] = []
    # Map extracted claims directly as statements
    for claim in assessment.extracted_claims:
        stmts.append(str(claim))

    # Map evidence matches as facts (simple representation)
    for em in assessment.evidence_matches:
        # Each evidence match may include {source, match_score, snippet}
        src = em.get("source") or em.get("source_url") or "unknown_source"
        score = em.get("score", em.get("match_score", 0.0))
        stmts.append(f'evidence_from_{src} = {score}')

    # Add source credibility and confidence as facts
    if assessment.source_credibility is not None:
        stmts.append(f'source_credibility = {float(assessment.source_credibility)}')
    stmts.append(f'fact_checker_confidence = {float(assessment.confidence)}')

    return stmts


@app.post("/pipeline/validate")
def pipeline_validate(payload: ReasoningInput) -> dict[str, Any]:
    """Run the three-stage pipeline: fact checker (neural) -> reasoning -> integrated decision.

    This endpoint accepts a standardized NeuralAssessment payload so other agents
    (or tests) can call the pipeline deterministically.
    """
    eng = get_engine()
    if not eng:
        raise HTTPException(status_code=503, detail="Nucleoid engine not available")

    try:
        assessment = payload.assessment

        # Stage 1 (ingest) - convert neural assessment to statements
        statements = _ingest_neural_assessment(assessment)

        # Temporarily add statements to the engine (do not persist them long-term)
        for stmt in statements:
            try:
                eng.add_fact({"statement": stmt})
            except Exception:
                # best-effort, continue
                pass

        # Stage 2 - reasoning validation
        # Prefer enhanced engine when available for richer validation
        eeng = get_enhanced_engine()
        if eeng is not None:
            try:
                logic_res = eeng.validate_news_claim_with_context(
                    claim=assessment.extracted_claims[0] if assessment.extracted_claims else "",
                    article_metadata=payload.article_metadata or {}
                )
            except Exception:
                logic_res = None
        else:
            logic_res = None

        if logic_res is None:
            # Fallback: aggregate evaluate on current facts + rules
            test_statements = list(eng.facts_store.values()) + eng.rules_store
            contradiction_res = eng.evaluate_contradiction([str(s) for s in test_statements])
            logic_res = {
                "logical_validation": {
                    "consistency_check": "PASS" if not contradiction_res.get("has_contradictions") else "FAIL",
                    "rule_compliance": "UNKNOWN",
                    "temporal_validity": True
                },
                "orchestration_decision": {
                    "consensus_confidence": assessment.confidence,
                    "escalation_required": False,
                    "recommended_action": "REVIEW" if contradiction_res.get("has_contradictions") else "APPROVE"
                }
            }

        # Stage 3 - integrated decision
        overall_confidence = float(assessment.confidence) * 0.6 + float(logic_res.get("orchestration_decision", {}).get("consensus_confidence", 0.0)) * 0.4
        final = {
            "version": "1.0",
            "overall_confidence": overall_confidence,
            "verification_status": logic_res.get("orchestration_decision", {}).get("recommended_action", "UNKNOWN"),
            "explanation": logic_res.get("logical_validation", {}),
            # Use model_dump() for Pydantic v2 compatibility; fall back to dict() when unavailable
            "neural_assessment": (assessment.model_dump() if hasattr(assessment, "model_dump") else assessment.dict()),
            "logical_validation": logic_res.get("logical_validation", {}),
            "processing_summary": {
                "fact_checker_confidence": assessment.confidence,
                "reasoning_validation": logic_res.get("orchestration_decision", {}).get("consensus_confidence", 0.0),
                "final_recommendation": logic_res.get("orchestration_decision", {}).get("recommended_action", "UNKNOWN")
            }
        }

        # Log pipeline outcome
        log_feedback("pipeline_run", {
            "final_overall_confidence": final["overall_confidence"],
            "verification_status": final["verification_status"]
        })

        return {"success": True, "result": final}

    except Exception as e:
        log_feedback("pipeline_error", {"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))


# --- API Endpoints ---
@app.post("/add_fact")
def add_fact_endpoint(call: ToolCall):
    """Add a fact to the reasoning system."""
    eng = get_engine()
    if not eng:
        raise HTTPException(status_code=503, detail="Nucleoid engine not available")
    try:
        # Extract fact from args or kwargs
        if call.args:
            fact_data = call.args[0] if isinstance(call.args[0], dict) else {"statement": str(call.args[0])}
        else:
            fact_data = call.kwargs.get("fact", call.kwargs.get("data", {}))

        result = eng.add_fact(fact_data)

        # Log feedback
        log_feedback("add_fact", {
            "fact_data": fact_data,
            "result": str(result),
            "success": True
        })

        return {"success": True, "result": result, "fact_id": len(eng.facts_store)}

    except Exception as e:
        error_msg = str(e)
        log_feedback("add_fact_error", {
            "fact_data": call.args if call.args else call.kwargs,
            "error": error_msg
        })
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/add_facts")
def add_facts_endpoint(call: ToolCall):
    """Add multiple facts to the reasoning system."""
    eng = get_engine()
    if not eng:
        raise HTTPException(status_code=503, detail="Nucleoid engine not available")
    try:
        # Extract facts from args or kwargs
        if call.args and isinstance(call.args[0], list):
            facts_list = call.args[0]
        else:
            facts_list = call.kwargs.get("facts", [])

        results = []
        for fact_data in facts_list:
            if isinstance(fact_data, dict):
                result = eng.add_fact(fact_data)
                results.append(result)
            else:
                result = eng.add_fact({"statement": str(fact_data)})
                results.append(result)

        # Log feedback
        log_feedback("add_facts", {
            "facts_count": len(facts_list),
            "results": [str(r) for r in results],
            "success": True
        })

        return {"success": True, "count": len(results), "results": results}

    except Exception as e:
        error_msg = str(e)
        log_feedback("add_facts_error", {
            "facts_data": call.args if call.args else call.kwargs,
            "error": error_msg
        })
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/add_rule")
def add_rule_endpoint(call: ToolCall):
    """Add a logical rule."""
    eng = get_engine()
    if not eng:
        raise HTTPException(status_code=503, detail="Nucleoid engine not available")
    try:
        # Extract rule from args or kwargs
        if call.args:
            rule = str(call.args[0])
        else:
            rule = call.kwargs.get("rule", "")

        if not rule:
            raise ValueError("Rule cannot be empty")

        result = eng.add_rule(rule)

        # Log feedback
        log_feedback("add_rule", {
            "rule": rule,
            "result": str(result),
            "success": True
        })

        return {"success": True, "result": result, "rule_count": len(eng.rules_store)}

    except Exception as e:
        error_msg = str(e)
        log_feedback("add_rule_error", {
            "rule_data": call.args if call.args else call.kwargs,
            "error": error_msg
        })
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/query")
def query_endpoint(call: ToolCall):
    """Execute a symbolic reasoning query."""
    eng = get_engine()
    if not eng:
        raise HTTPException(status_code=503, detail="Nucleoid engine not available")
    try:
        # Extract query from args or kwargs
        if call.args:
            query = str(call.args[0])
        else:
            query = call.kwargs.get("query", "")

        if not query:
            raise ValueError("Query cannot be empty")

        result = eng.query(query)

        # Log feedback
        log_feedback("query", {
            "query": query,
            "result": str(result),
            "success": True
        })

        return {"success": True, "result": result, "query": query}

    except Exception as e:
        error_msg = str(e)
        log_feedback("query_error", {
            "query_data": call.args if call.args else call.kwargs,
            "error": error_msg
        })
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/evaluate")
def evaluate_endpoint(call: ToolCall):
    """Evaluate contradictions and logical consistency."""
    eng = get_engine()
    if not eng:
        raise HTTPException(status_code=503, detail="Nucleoid engine not available")
    try:
        # Extract evaluation request
        if call.args and isinstance(call.args[0], list):
            statements = call.args[0]
        elif call.args:
            statements = [str(call.args[0])]
        else:
            statements = call.kwargs.get("statements", [])
            if not statements:
                # Evaluate all current facts and rules
                statements = list(eng.facts_store.values()) + eng.rules_store

        if not statements:
            return {"success": True, "result": "No statements to evaluate"}

        # Convert non-string statements to strings
        str_statements = []
        for stmt in statements:
            if isinstance(stmt, dict):
                if "statement" in stmt:
                    str_statements.append(stmt["statement"])
                else:
                    str_statements.append(json.dumps(stmt))
            else:
                str_statements.append(str(stmt))

        result = eng.evaluate_contradiction(str_statements)

        # Log feedback
        log_feedback("evaluate", {
            "statements_count": len(str_statements),
            "has_contradictions": result.get("has_contradictions", False),
            "contradictions_count": len(result.get("contradictions", [])),
            "success": True
        })

        return {"success": True, "result": result}

    except Exception as e:
        error_msg = str(e)
        log_feedback("evaluate_error", {
            "evaluation_data": call.args if call.args else call.kwargs,
            "error": error_msg
        })
        raise HTTPException(status_code=500, detail=error_msg)

@app.get("/facts")
def get_facts() -> dict[str, Any]:
    """Retrieve all stored facts."""
    eng = get_engine()
    if not eng:
        raise HTTPException(status_code=503, detail="Nucleoid engine not available")

    return {"facts": eng.get_facts(), "count": len(eng.facts_store)}

@app.get("/rules")
def get_rules() -> dict[str, Any]:
    """Retrieve all stored rules."""
    eng = get_engine()
    if not eng:
        raise HTTPException(status_code=503, detail="Nucleoid engine not available")

    return {"rules": eng.get_rules(), "count": len(eng.rules_store)}

@app.get("/status")
def get_status() -> dict[str, Any]:
    """Get reasoning engine status."""
    eng = get_engine()
    if not eng:
        return {
            "status": "unavailable",
            "nucleoid_available": False,
            "facts_count": 0,
            "rules_count": 0
        }

    return {
        "status": "ok",
        "nucleoid_available": True,
        "facts_count": len(eng.facts_store),
        "rules_count": len(eng.rules_store),
        "session_id": eng.session_id
    }

@app.get("/health")
def health() -> dict[str, Any]:
    """Health check endpoint."""
    eng = get_engine()
    status = "ok" if eng else "unavailable"
    return {"status": status, "nucleoid_available": eng is not None}

@app.get("/ready")
def ready_endpoint() -> dict[str, Any]:
    """Readiness endpoint."""
    return {"ready": ready}

# Metrics endpoint
@app.get("/metrics")
def get_metrics():
    """Prometheus metrics endpoint."""
    from fastapi import Response
    return Response(content=metrics.get_metrics(), media_type="text/plain")

# --- MCP Bus Integration ---
@app.post("/call")
def call_tool(request: dict[str, Any]):
    """MCP bus integration - handles tool calls from other agents."""
    try:
        tool = request.get("tool", "")
        args = request.get("args", [])
        kwargs = request.get("kwargs", {})

        # Create ToolCall object
        call = ToolCall(args=args, kwargs=kwargs)

        # Route to appropriate endpoint
        if tool == "add_fact":
            return add_fact_endpoint(call)
        elif tool == "add_facts":
            return add_facts_endpoint(call)
        elif tool == "add_rule":
            return add_rule_endpoint(call)
        elif tool == "query":
            return query_endpoint(call)
        elif tool == "evaluate":
            return evaluate_endpoint(call)
        else:
            available_tools = ["add_fact", "add_facts", "add_rule", "query", "evaluate"]
            raise HTTPException(
                status_code=400,
                detail=f"Unknown tool: {tool}. Available tools: {available_tools}"
            )

    except Exception as e:
        log_feedback("mcp_call_error", {
            "request": request,
            "error": str(e)
        })
        raise HTTPException(status_code=500, detail=str(e))

# --- News Analysis Specific Functions ---
@app.post("/validate_claim")
def validate_claim(call: ToolCall):
    """Validate a news claim against known facts and rules."""
    eng = get_engine()
    if not eng:
        raise HTTPException(status_code=503, detail="Nucleoid engine not available")

    try:
        # Extract claim
        if call.args:
            claim = str(call.args[0])
            context = call.args[1] if len(call.args) > 1 else {}
        else:
            claim = call.kwargs.get("claim", "")
            context = call.kwargs.get("context", {})

        if not claim:
            raise ValueError("Claim cannot be empty")

        # Add claim as temporary fact and check for contradictions
        # Get existing statements
        existing_statements = []
        for fact in eng.facts_store.values():
            if isinstance(fact, dict) and "statement" in fact:
                existing_statements.append(fact["statement"])
        existing_statements.extend(eng.rules_store)

        # Prefer the enhanced engine for validation if available
        eeng = get_enhanced_engine()
        if eeng is not None:
            try:
                validation_result = eeng.validate_news_claim_with_context(claim, context)
            except Exception:
                # Fallback to legacy contradiction evaluation below
                validation_result = None

        if eeng is None or validation_result is None:
            # Add the claim and check for contradictions using legacy engine
            test_statements = existing_statements + [claim]
            contradiction_result = eng.evaluate_contradiction(test_statements)

            # Determine validation result
            validation_result = {
                "claim": claim,
                "context": context,
                "valid": not contradiction_result["has_contradictions"],
                "contradictions": contradiction_result["contradictions"],
                "confidence": 1.0 - (len(contradiction_result["contradictions"]) * 0.2)
            }

        # Log feedback
        log_feedback("validate_claim", {
            "claim": claim,
            "valid": validation_result["valid"],
            "contradictions_count": len(contradiction_result["contradictions"]),
            "confidence": validation_result["confidence"]
        })

        return {"success": True, "result": validation_result}

    except Exception as e:
        error_msg = str(e)
        log_feedback("validate_claim_error", {
            "claim_data": call.args if call.args else call.kwargs,
            "error": error_msg
        })
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/explain_reasoning")
def explain_reasoning(call: ToolCall):
    """Provide explainable reasoning for a query or validation."""
    eng = get_engine()
    if not eng:
        raise HTTPException(status_code=503, detail="Nucleoid engine not available")

    try:
        # Extract query
        if call.args:
            query = str(call.args[0])
        else:
            query = call.kwargs.get("query", "")

        if not query:
            raise ValueError("Query cannot be empty")

        # Execute query and provide explanation; prefer enhanced_engine context if available
        result = eng.query(query)

        # Generate explanation (include enhanced_engine cues when present)
        eeng = get_enhanced_engine()
        explanation = {
            "query": query,
            "result": result,
            "reasoning_steps": [
                f"1. Executed query: '{query}'",
                f"2. Applied {len(eng.rules_store)} logical rules",
                f"3. Checked against {len(eng.facts_store)} known facts",
                f"4. Result: {result}"
            ],
            "facts_used": list(eng.facts_store.keys()),
            "rules_applied": eng.rules_store,
            "confidence": 0.8 if result else 0.2,
            "enhanced_available": eeng is not None
        }

        # Log feedback
        log_feedback("explain_reasoning", {
            "query": query,
            "result": str(result),
            "explanation_provided": True
        })

        return {"success": True, "result": explanation}

    except Exception as e:
        error_msg = str(e)
        log_feedback("explain_reasoning_error", {
            "query_data": call.args if call.args else call.kwargs,
            "error": error_msg
        })
        raise HTTPException(status_code=500, detail=error_msg)

# Startup/shutdown logic is handled by the lifespan context manager above.

# --- Main Entry Point ---
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("REASONING_AGENT_PORT", 8008))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
