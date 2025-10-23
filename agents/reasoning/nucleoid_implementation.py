"""
from common.observability import get_logger
Complete Nucleoid Implementation for JustNews V4 Reasoning Agent
Based on the official Nucleoid GitHub repository with adaptations for production use.
Repository: https://github.com/nucleoidai/nucleoid
"""

import ast
from typing import Any

import networkx as nx

logger = get_logger(__name__)

class NucleoidState:
    """Global state management for variables and their values."""

    def __init__(self):
        self.variable_state: dict[str, Any] = {}

    def get(self, name: str, default=None):
        return self.variable_state.get(name, default)

    def set(self, name: str, value: Any):
        self.variable_state[name] = value

    def clear(self):
        self.variable_state.clear()

class NucleoidGraph:
    """Dependency graph management using NetworkX."""

    def __init__(self):
        self.maingraph = nx.MultiDiGraph()

    def add_node(self, node_name: str):
        self.maingraph.add_node(node_name)

    def add_edge(self, from_node: str, to_node: str):
        self.maingraph.add_edge(from_node, to_node)

    def clear(self):
        self.maingraph.clear()

class ExpressionHandler:
    """Handles expression evaluation with AST parsing."""

    def __init__(self, state: NucleoidState):
        self.state = state

    def evaluate(self, node):
        """
        Evaluates an AST node and returns its value based on the variable_state dictionary.
        """
        if isinstance(node, ast.Name):
            if node.id in self.state.variable_state:
                return self.state.variable_state[node.id]
            else:
                raise NameError(f"Variable {node.id} is not defined")
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.BinOp):
            left = self.evaluate(node.left)
            right = self.evaluate(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                return left * right
            elif isinstance(node.op, ast.Div):
                return left / right
            else:
                raise NotImplementedError(f"Operator {type(node.op)} not supported")
        elif isinstance(node, ast.Compare):
            left = self.evaluate(node.left)
            right = self.evaluate(node.comparators[0])
            if isinstance(node.ops[0], ast.Eq):
                return left == right
            elif isinstance(node.ops[0], ast.NotEq):
                return left != right
            elif isinstance(node.ops[0], ast.Lt):
                return left < right
            elif isinstance(node.ops[0], ast.LtE):
                return left <= right
            elif isinstance(node.ops[0], ast.Gt):
                return left > right
            elif isinstance(node.ops[0], ast.GtE):
                return left >= right
            else:
                raise NotImplementedError(f"Comparison operator {type(node.ops[0])} not supported")
        else:
            raise NotImplementedError(f"Node type {type(node)} not supported")

class AssignmentHandler:
    """Handles variable assignments."""

    def __init__(self, state: NucleoidState, graph: NucleoidGraph):
        self.state = state
        self.graph = graph

    def handle(self, node):
        """Handle variable assignment from AST node."""
        # Extract the variable name from the target
        target = node.targets[0]
        if isinstance(target, ast.Name):
            var_name = target.id

            # Extract and evaluate the value using expression handler
            if isinstance(node.value, ast.Constant):
                var_value = node.value.value
            elif isinstance(node.value, ast.Name):
                # Handle variable references
                var_value = self.state.get(node.value.id)
                if var_value is None:
                    raise NameError(f"Variable {node.value.id} is not defined")
            else:
                # Handle complex expressions (e.g., x + 10)
                try:
                    var_value = ExpressionHandler(self.state).evaluate(node.value)
                except Exception as e:
                    logger.warning(f"Could not evaluate expression for {var_name}: {e}")
                    var_value = None

            # Store the variable and its value
            self.state.set(var_name, var_value)
            # Add the variable as a node in the graph
            self.graph.add_node(var_name)

            # Add dependency edges if the value depends on other variables
            self._add_dependencies(var_name, node.value)

            return var_value

    def _add_dependencies(self, var_name: str, value_node):
        """Add dependency edges for variables that depend on other variables."""
        # Find all variable names in the value expression
        for node in ast.walk(value_node):
            if isinstance(node, ast.Name) and node.id != var_name:
                # Add edge from dependency to this variable
                self.graph.add_edge(node.id, var_name)
                logger.debug(f"Added dependency: {node.id} -> {var_name}")

class NucleoidParser:
    """Parser for Nucleoid statements using Python AST."""

    def parse(self, statement: str):
        """Parse a statement into an AST."""
        try:
            tree = ast.parse(statement)
            return tree
        except SyntaxError as e:
            raise ValueError(f"Invalid syntax in statement: {statement}. Error: {e}")

class Nucleoid:
    """
    Main Nucleoid class - complete implementation based on GitHub repository.
    """

    def __init__(self):
        logger.info("Nucleoid object created")

        # Initialize components
        self.state = NucleoidState()
        self.graph = NucleoidGraph()
        self.parser = NucleoidParser()
        self.expression_handler = ExpressionHandler(self.state)
        self.assignment_handler = AssignmentHandler(self.state, self.graph)

    def run(self, statement: str):
        """
        Execute a Nucleoid statement.
        
        Args:
            statement: The statement to execute
            
        Returns:
            The result of the statement execution
        """
        if not isinstance(statement, str):
            raise ValueError("Statement must be a string")

        logger.debug(f"Running statement: {statement}")

        try:
            # Parse the statement
            parsed_tree = self.parser.parse(statement)

            # Process the parsed AST
            result = self._process(parsed_tree)
            return result

        except Exception as e:
            logger.error(f"Error executing statement '{statement}': {e}")
            raise

    def _process(self, parsed_tree):
        """Process a parsed AST tree."""
        if not parsed_tree.body:
            return None

        node = parsed_tree.body[0]

        # Handle expressions (queries, comparisons)
        if isinstance(node, ast.Expr):
            return self.expression_handler.evaluate(node.value)

        # Handle assignments (variable definitions)
        elif isinstance(node, ast.Assign):
            return self.assignment_handler.handle(node)

        else:
            raise NotImplementedError(f"Statement type {type(node)} not supported")

    def clear(self):
        """Clear all state and graph data."""
        self.state.clear()
        self.graph.clear()
        logger.info("Nucleoid state and graph cleared")

    def get_state(self):
        """Get current variable state."""
        return self.state.variable_state.copy()

    def get_graph(self):
        """Get current dependency graph."""
        return self.graph.maingraph

    def set_variable(self, name: str, value: Any):
        """Directly set a variable value."""
        self.state.set(name, value)
        self.graph.add_node(name)
        logger.debug(f"Set variable {name} = {value}")

    def get_variable(self, name: str):
        """Get a variable value."""
        return self.state.get(name)

    def has_variable(self, name: str):
        """Check if a variable exists."""
        return name in self.state.variable_state

# Export for easy importing
__all__ = ['Nucleoid', 'NucleoidState', 'NucleoidGraph', 'ExpressionHandler', 'AssignmentHandler', 'NucleoidParser']
