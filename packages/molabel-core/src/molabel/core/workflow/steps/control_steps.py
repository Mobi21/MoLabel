"""Control step executors: loop, conditional, parallel, gate.

WF-021 through WF-034. Control steps orchestrate other steps rather than
performing data operations directly. They manage branching, iteration,
concurrency, and explicit approval gates.
"""

from __future__ import annotations

import ast
import logging
import operator as op
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Any

from molabel.core.workflow.context import StepOutput, WorkflowContext
from molabel.core.workflow.steps.base import StepExecutor, StepResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Predicate evaluator for conditional steps (WF-028, WF-029)
# ---------------------------------------------------------------------------

# Allowed names in predicate expressions (no builtins, no function calls)
_SAFE_NAMES = frozenset(
    {
        "True",
        "False",
        "None",
        "and",
        "or",
        "not",
        "in",
    }
)

# AST node types that are allowed in predicate expressions
_ALLOWED_AST_NODES = frozenset(
    {
        ast.Expression,
        ast.Compare,
        ast.BoolOp,
        ast.BinOp,
        ast.UnaryOp,
        ast.Subscript,
        ast.Attribute,
        ast.Name,
        ast.Constant,
        ast.List,
        ast.Tuple,
        ast.Dict,
        ast.Load,
        ast.Store,
        ast.Del,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.Eq,
        ast.NotEq,
        ast.Lt,
        ast.LtE,
        ast.Gt,
        ast.GtE,
        ast.Is,
        ast.IsNot,
        ast.In,
        ast.NotIn,
        ast.USub,
        ast.UAdd,
        ast.Index,
    }
)

# AST node types that are explicitly rejected (dangerous)
_REJECTED_AST_NODES = frozenset(
    {
        ast.Call,
        ast.Lambda,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
        ast.JoinedStr,
        ast.Starred,
        ast.FormattedValue,
    }
)

# Comparison operators for AST evaluation
_AST_CMP_OPS: dict[type, Any] = {
    ast.Eq: op.eq,
    ast.NotEq: op.ne,
    ast.Lt: op.lt,
    ast.LtE: op.le,
    ast.Gt: op.gt,
    ast.GtE: op.ge,
    ast.Is: op.is_,
    ast.IsNot: op.is_not,
}

# Binary operators for AST evaluation
_AST_BIN_OPS: dict[type, Any] = {
    ast.Add: op.add,
    ast.Sub: op.sub,
    ast.Mult: op.mul,
    ast.Div: op.truediv,
    ast.FloorDiv: op.floordiv,
    ast.Mod: op.mod,
    ast.Pow: op.pow,
}

# Unary operators for AST evaluation
_AST_UNARY_OPS: dict[type, Any] = {
    ast.USub: op.neg,
    ast.UAdd: op.pos,
    ast.Not: op.not_,
}


def _validate_ast(node: ast.AST) -> str | None:
    """Walk an AST and reject disallowed node types.

    Returns an error message if a disallowed node is found, or None if safe.
    """
    for child in ast.walk(node):
        child_type = type(child)
        if child_type in _REJECTED_AST_NODES:
            return f"Disallowed expression type: {child_type.__name__}"
        if child_type not in _ALLOWED_AST_NODES:
            return f"Unsupported expression type: {child_type.__name__}"
    return None


def _eval_node(node: ast.AST, namespace: dict[str, Any]) -> Any:
    """Recursively evaluate an AST node against the namespace."""
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, namespace)

    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        if node.id in namespace:
            return namespace[node.id]
        raise NameError(f"Unknown name: {node.id!r}")

    if isinstance(node, ast.Subscript):
        value = _eval_node(node.value, namespace)
        slice_val = _eval_node(node.slice, namespace)
        return value[slice_val]

    if isinstance(node, ast.Attribute):
        value = _eval_node(node.value, namespace)
        return getattr(value, node.attr)

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            result = True
            for val in node.values:
                result = _eval_node(val, namespace)
                if not result:
                    return result
            return result
        elif isinstance(node.op, ast.Or):
            result = False
            for val in node.values:
                result = _eval_node(val, namespace)
                if result:
                    return result
            return result

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, namespace)
        for cmp_op, comparator in zip(node.ops, node.comparators, strict=True):
            right = _eval_node(comparator, namespace)
            if isinstance(cmp_op, ast.In):
                if left not in right:
                    return False
            elif isinstance(cmp_op, ast.NotIn):
                if left in right:
                    return False
            else:
                fn = _AST_CMP_OPS.get(type(cmp_op))
                if fn is None:
                    raise ValueError(f"Unsupported comparison: {type(cmp_op).__name__}")
                if not fn(left, right):
                    return False
            left = right
        return True

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, namespace)
        right = _eval_node(node.right, namespace)
        fn = _AST_BIN_OPS.get(type(node.op))
        if fn is None:
            raise ValueError(f"Unsupported binary op: {type(node.op).__name__}")
        return fn(left, right)

    if isinstance(node, ast.UnaryOp):
        operand = _eval_node(node.operand, namespace)
        fn = _AST_UNARY_OPS.get(type(node.op))
        if fn is None:
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        return fn(operand)

    if isinstance(node, ast.List):
        return [_eval_node(elt, namespace) for elt in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(elt, namespace) for elt in node.elts)

    if isinstance(node, ast.Dict):
        keys = [_eval_node(k, namespace) for k in node.keys if k is not None]
        values = [_eval_node(v, namespace) for v in node.values]
        return dict(zip(keys, values, strict=True))

    # Handle ast.Index (Python 3.8 compat, though 3.12+ doesn't emit it)
    if isinstance(node, ast.Index):  # type: ignore[attr-defined]
        return _eval_node(node.value, namespace)  # type: ignore[attr-defined]

    raise ValueError(f"Cannot evaluate AST node: {type(node).__name__}")


def evaluate_predicate(
    expression: str,
    context: WorkflowContext,
) -> bool:
    """Evaluate a predicate expression against the WorkflowContext.

    Uses an AST-based evaluator that only allows safe node types:
    comparisons, boolean operations, arithmetic, subscript access,
    attribute access, and literals. Function calls, lambdas,
    comprehensions, f-strings, and other potentially dangerous
    constructs are rejected.

    Args:
        expression: A simple predicate expression string.
        context: The current workflow context.

    Returns:
        True if the predicate is satisfied, False otherwise.
    """
    if not expression or not expression.strip():
        logger.warning("Empty predicate expression; evaluating to False")
        return False

    # Build safe evaluation namespace
    namespace: dict[str, Any] = {
        "metrics": _SafeDict(context.metrics),
        "variables": _SafeDict(context.variables),
        "step_outputs": _SafeStepOutputDict(context.step_outputs),
        "True": True,
        "False": False,
        "None": None,
    }

    try:
        # Parse the expression into an AST
        tree = ast.parse(expression, mode="eval")

        # Validate that only safe node types are present
        error = _validate_ast(tree)
        if error is not None:
            logger.warning(
                "Predicate rejected for '%s': %s; evaluating to False",
                expression,
                error,
            )
            return False

        # Evaluate the safe AST
        result = _eval_node(tree, namespace)
        return bool(result)
    except Exception as e:
        logger.warning(
            "Predicate evaluation failed for '%s': %s; evaluating to False",
            expression,
            e,
        )
        return False


class _SafeDict:
    """Dict wrapper that returns 0.0/False/None for missing keys."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        if key not in self._data:
            logger.warning(
                "Predicate references missing key '%s'; using default",
                key,
            )
            return 0.0
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data


class _SafeStepOutputDict:
    """Wrapper for step_outputs that returns proxy objects for attribute access."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        if key not in self._data:
            logger.warning("Predicate references missing step_output '%s'", key)
            return _StepOutputProxy()
        output = self._data[key]
        return _StepOutputProxy(output)


class _StepOutputProxy:
    """Proxy for StepOutput attribute access in predicates."""

    def __init__(self, output: Any = None) -> None:
        self._output = output

    @property
    def status(self) -> str:
        if self._output is not None:
            return getattr(self._output, "status", "unknown")
        return "unknown"


# ---------------------------------------------------------------------------
# Loop executor (WF-021 through WF-027)
# ---------------------------------------------------------------------------


class LoopExecutor(StepExecutor):
    """Executor for loop steps (WF-021 through WF-027).

    Orchestrates repeated execution of body steps until a termination
    condition is met or max_iterations is reached. Supports 4 termination
    strategies: count, metric, coverage, manual.

    The loop executor does not directly execute body steps -- it returns
    metadata that the engine uses to manage iteration. The engine calls
    check_termination() after each iteration.
    """

    VALID_TERMINATION_TYPES = {"count", "metric", "coverage", "manual"}

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        if not config.get("steps"):
            errors.append("loop requires 'steps' list in config")
        termination = config.get("termination", {})
        term_type = termination.get("type", "count")
        if term_type not in self.VALID_TERMINATION_TYPES:
            errors.append(
                f"Invalid termination type '{term_type}'. "
                f"Valid: {sorted(self.VALID_TERMINATION_TYPES)}"
            )
        if term_type == "metric":
            if not termination.get("metric"):
                errors.append("Metric termination requires 'metric' field")
            if not termination.get("threshold") and termination.get("threshold") != 0:
                errors.append("Metric termination requires 'threshold' field")
        if term_type == "coverage" and not termination.get("target_coverage"):
            errors.append("Coverage termination requires 'target_coverage' field")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        """Initialize the loop. The engine manages actual iteration.

        The loop executor sets up iteration tracking in the context. The
        engine reads the loop config and calls check_termination() after
        each body execution cycle.
        """
        termination = config.get("termination", {})
        max_iterations = termination.get(
            "max_iterations",
            termination.get("count", 10),
        )
        body_steps = config.get("steps", [])

        context.variables[f"loop.{step_id}.iteration"] = 0
        context.variables[f"loop.{step_id}.max_iterations"] = max_iterations
        context.variables[f"loop.{step_id}.body_steps"] = body_steps

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="loop",
                summary={
                    "body_steps": body_steps,
                    "termination_type": termination.get("type", "count"),
                    "max_iterations": max_iterations,
                    "current_iteration": 0,
                },
            ),
        )

    def check_termination(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        current_iteration: int,
    ) -> tuple[bool, str]:
        """Check if the loop should terminate after the current iteration.

        Args:
            step_id: The loop step ID.
            config: The loop step config.
            context: Current workflow context.
            current_iteration: 0-indexed iteration that just completed.

        Returns:
            Tuple of (should_terminate, reason).
        """
        termination = config.get("termination", {})
        term_type = termination.get("type", "count")
        max_iterations = termination.get(
            "max_iterations",
            termination.get("count", 10),
        )

        # Safety limit
        if current_iteration + 1 >= max_iterations:
            return True, "max_iterations_reached"

        if term_type == "count":
            count = termination.get("count", max_iterations)
            if current_iteration + 1 >= count:
                return True, "count_reached"

        elif term_type == "metric":
            metric_name = termination.get("metric", "")
            operator = termination.get("operator", ">=")
            threshold = float(termination.get("threshold", 0))
            current_value = context.metrics.get(metric_name)

            if current_value is not None:
                if _compare(current_value, operator, threshold):
                    return True, "metric_threshold_met"
            else:
                logger.warning(
                    "Loop '%s': metric '%s' not found in context",
                    step_id,
                    metric_name,
                )

        elif term_type == "coverage":
            target_coverage = float(termination.get("target_coverage", 1.0))
            # coverage_scope is stored in config for the engine to use
            coverage_key = f"loop.{step_id}.coverage"

            current_coverage = context.metrics.get(
                coverage_key,
                context.metrics.get("review.coverage", 0.0),
            )
            context.metrics[coverage_key] = current_coverage

            if current_coverage >= target_coverage:
                return True, "coverage_target_met"

        elif term_type == "manual":
            # Manual loops wait for operator; the engine handles the gate
            return False, "waiting_for_operator"

        return False, ""

    def reset_body_steps(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        iteration: int,
    ) -> None:
        """Reset loop body steps for the next iteration (WF-025).

        Previous iteration outputs are preserved with iteration-suffixed
        keys. Metrics and variables accumulate (NOT reset).
        """
        body_steps = config.get("steps", [])

        for body_step_id in body_steps:
            # Archive previous iteration output with suffix
            if body_step_id in context.step_outputs:
                suffixed_key = f"{body_step_id}__iter_{iteration - 1}"
                context.step_outputs[suffixed_key] = context.step_outputs[body_step_id]

            # Archive previous record set with suffix
            if body_step_id in context.record_sets:
                suffixed_key = f"{body_step_id}__iter_{iteration - 1}"
                context.record_sets[suffixed_key] = context.record_sets[body_step_id]

        # Update iteration counter
        context.variables[f"loop.{step_id}.iteration"] = iteration


_OPERATORS: dict[str, Any] = {
    ">=": op.ge,
    "<=": op.le,
    ">": op.gt,
    "<": op.lt,
    "==": op.eq,
    "!=": op.ne,
}


def _compare(value: float, operator: str, threshold: float) -> bool:
    """Compare a value against a threshold using the given operator."""
    fn = _OPERATORS.get(operator)
    if fn is None:
        return False
    return bool(fn(value, threshold))


# ---------------------------------------------------------------------------
# Conditional executor (WF-028 through WF-030)
# ---------------------------------------------------------------------------


class ConditionalExecutor(StepExecutor):
    """Executor for conditional steps (WF-028, WF-029, WF-030).

    Evaluates a predicate against the WorkflowContext and selects the
    then or else branch. Non-taken branch steps are marked skipped with
    transitive skip propagation.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        if not config.get("predicate"):
            errors.append("conditional requires 'predicate' in config")
        if config.get("then_steps") is None:
            errors.append("conditional requires 'then_steps' in config")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        predicate = config.get("predicate", "")
        then_steps = config.get("then_steps", [])
        else_steps = config.get("else_steps", [])

        # Evaluate predicate
        result = evaluate_predicate(predicate, context)
        branch_taken = "then" if result else "else"
        taken_steps = then_steps if result else else_steps
        skipped_steps = else_steps if result else then_steps

        context.variables[f"conditional.{step_id}.branch"] = branch_taken

        return StepResult(
            success=True,
            output=StepOutput(
                step_id=step_id,
                step_type="conditional",
                summary={
                    "predicate": predicate,
                    "predicate_result": result,
                    "branch_taken": branch_taken,
                    "taken_steps": taken_steps,
                    "skipped_steps": skipped_steps,
                },
            ),
            updated_context={
                "taken_steps": taken_steps,
                "skipped_steps": skipped_steps,
                "branch_taken": branch_taken,
            },
        )


# ---------------------------------------------------------------------------
# Parallel executor (WF-031 through WF-033)
# ---------------------------------------------------------------------------


class ParallelExecutor(StepExecutor):
    """Executor for parallel steps (WF-031, WF-032, WF-033).

    Runs multiple child steps concurrently using ThreadPoolExecutor.
    Supports fail-fast mode (cancel remaining on first failure) and
    default mode (wait for all, report partially_failed if any child failed).
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        errors: list[str] = []
        if not config.get("steps"):
            errors.append("parallel requires 'steps' list in config")
        return errors

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        """Execute child steps concurrently using ThreadPoolExecutor.

        Child executors and their configs are provided via the services dict
        under the key ``child_executors``. Each entry maps a child step ID to
        a dict with ``executor`` (StepExecutor) and ``config`` (dict) keys.

        If no ``child_executors`` key is present in services, falls back to
        returning metadata for the engine to handle.
        """
        services = services or {}
        child_steps = config.get("steps", [])
        fail_fast = config.get("fail_fast", False)

        child_executors: dict[str, dict[str, Any]] | None = services.get(
            "child_executors"
        )

        # If no child executors provided, return metadata for engine
        if child_executors is None:
            return StepResult(
                success=True,
                output=StepOutput(
                    step_id=step_id,
                    step_type="parallel",
                    summary={
                        "child_steps": child_steps,
                        "fail_fast": fail_fast,
                    },
                ),
                updated_context={
                    "child_steps": child_steps,
                    "fail_fast": fail_fast,
                },
            )

        # Run children concurrently
        child_results: dict[str, StepResult] = {}
        child_errors: list[str] = []
        futures: dict[Future[StepResult], str] = {}

        max_workers = min(len(child_steps), config.get("max_workers", 4))

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            for child_id in child_steps:
                child_info = child_executors.get(child_id)
                if child_info is None:
                    child_errors.append(
                        f"No executor provided for child step '{child_id}'"
                    )
                    continue
                executor = child_info["executor"]
                child_config = child_info["config"]
                child_services = child_info.get("services")
                fut = pool.submit(
                    executor.execute,
                    child_id,
                    child_config,
                    context,
                    child_services,
                )
                futures[fut] = child_id

            for fut in as_completed(futures):
                child_id = futures[fut]
                try:
                    result = fut.result()
                    child_results[child_id] = result
                    if not result.success and fail_fast:
                        # Cancel remaining futures
                        for pending_fut in futures:
                            pending_fut.cancel()
                        child_errors.append(
                            f"Child step '{child_id}' failed (fail-fast): "
                            f"{result.error}"
                        )
                        break
                    elif not result.success:
                        child_errors.append(
                            f"Child step '{child_id}' failed: {result.error}"
                        )
                except Exception as e:
                    child_errors.append(
                        f"Child step '{child_id}' raised exception: {e}"
                    )
                    if fail_fast:
                        for pending_fut in futures:
                            pending_fut.cancel()
                        break

        # Merge child outputs into context
        child_outputs: dict[str, StepOutput] = {}
        for child_id, result in child_results.items():
            if result.output:
                child_outputs[child_id] = result.output

        merge_warnings = self.merge_child_contexts(context, child_outputs)

        all_success = len(child_errors) == 0
        any_success = len(child_results) > len(child_errors)
        is_partial = not all_success and any_success

        return StepResult(
            success=all_success,
            is_partial=is_partial,
            output=StepOutput(
                step_id=step_id,
                step_type="parallel",
                summary={
                    "child_steps": child_steps,
                    "fail_fast": fail_fast,
                    "child_results": {
                        cid: r.success for cid, r in child_results.items()
                    },
                    "errors": child_errors,
                    "merge_warnings": merge_warnings,
                },
            ),
            error="; ".join(child_errors) if child_errors else "",
            updated_context={
                "child_steps": child_steps,
                "fail_fast": fail_fast,
            },
        )

    def merge_child_contexts(
        self,
        parent_context: WorkflowContext,
        child_outputs: dict[str, StepOutput],
    ) -> list[str]:
        """Merge child step outputs into the parent context (WF-033).

        Merge strategy:
        - record_sets: union (all child record sets added)
        - agent_run_ids: union (all child agent runs added)
        - metrics: last-write-wins with conflict warnings
        - variables: merge (child values overwrite parent)

        Returns a list of warnings (e.g. metric key conflicts).
        """
        warnings: list[str] = []
        seen_metric_keys: dict[str, str] = {}  # key -> last writer step_id

        for child_id, output in child_outputs.items():
            parent_context.step_outputs[child_id] = output

            # Check for metric conflicts
            summary = output.summary
            for key in summary.get("metrics_written", []):
                if key in seen_metric_keys:
                    warnings.append(
                        f"Metric '{key}' written by both "
                        f"'{seen_metric_keys[key]}' and '{child_id}' "
                        f"(last-write-wins)"
                    )
                seen_metric_keys[key] = child_id

        # After parallel, active_record_set_id is cleared
        parent_context.active_record_set_id = None

        return warnings


# ---------------------------------------------------------------------------
# Gate executor (WF-034)
# ---------------------------------------------------------------------------


class GateExecutor(StepExecutor):
    """Executor for gate steps (WF-034).

    An explicit pause point that requires operator approval. Always
    transitions to waiting_for_gate.
    """

    def validate(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
    ) -> list[str]:
        return []

    def execute(
        self,
        step_id: str,
        config: dict[str, Any],
        context: WorkflowContext,
        services: dict[str, Any] | None = None,
    ) -> StepResult:
        message = config.get("message", f"Gate '{step_id}': Approve to continue")
        require_reason = config.get("require_reason", False)

        return StepResult(
            success=True,
            waiting_for_gate=True,
            output=StepOutput(
                step_id=step_id,
                step_type="gate",
                summary={
                    "message": message,
                    "require_reason": require_reason,
                    "status": "waiting",
                },
            ),
        )
