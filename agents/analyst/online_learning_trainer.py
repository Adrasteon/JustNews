"""
from common.observability import get_logger
Online Learning Integration for justnewsagent
Demonstrates practical "training on the fly" implementation
"""

import json
from collections import deque
from datetime import datetime
from typing import Any

import numpy as np
import torch

logger = get_logger(__name__)

class OnlineNERTrainer:
    """
    Online learning system for Named Entity Recognition
    Integrates with justnewsagent agent pipeline
    """

    def __init__(self, model, config: dict[str, Any] = None):
        self.model = model
        self.config = config or self.default_config()

        # Training buffer for accumulating examples
        self.training_buffer = deque(maxlen=self.config['buffer_size'])
        self.examples_processed = 0

        # Performance tracking
        self.baseline_metrics = {}
        self.current_metrics = {}

        # Model versioning
        self.model_version = 1
        self.checkpoint_dir = "model_checkpoints"

        logger.info(f"🚀 OnlineNERTrainer initialized with buffer size {self.config['buffer_size']}")

    def default_config(self) -> dict[str, Any]:
        """Default configuration for online learning"""
        return {
            'buffer_size': 1000,
            'update_frequency': 50,  # Update every 50 high-quality examples
            'learning_rate': 1e-5,   # Small LR for stability
            'quality_threshold': 0.7,
            'uncertainty_threshold': 0.6,
            'performance_threshold': 0.05,  # 5% degradation limit
            'validation_size': 100
        }

    def should_use_for_training(self, article_data: dict, agent_predictions: dict) -> tuple[bool, str]:
        """
        Determine if this article should be used for online learning
        Uses active learning principles to select most valuable examples
        """

        # 1. Quality filter (Scout V2 integration)
        scout_quality = agent_predictions.get('scout', {}).get('quality_score', 0)
        if scout_quality < self.config['quality_threshold']:
            return False, "low_quality"

        # 2. Model uncertainty (high uncertainty = valuable for learning)
        entities = agent_predictions.get('analyst', {}).get('entities', [])
        if entities:
            avg_confidence = np.mean([e.get('confidence', 1.0) for e in entities])
            if avg_confidence < self.config['uncertainty_threshold']:
                return True, "high_uncertainty"

        # 3. Rare or new entity types
        entity_labels = [e.get('label', '') for e in entities]
        rare_labels = {'POLICY_TERM', 'FINANCIAL_METRIC', 'NEWS_ORG', 'CRYPTO', 'REGULATION'}
        if any(label in rare_labels for label in entity_labels):
            return True, "rare_entities"

        # 4. Agent disagreement (indicates challenging example)
        if self.detect_agent_disagreement(agent_predictions):
            return True, "agent_disagreement"

        # 5. High-value financial or political content
        if self.is_high_value_content(article_data):
            return True, "high_value_content"

        # 6. Random sampling for diversity (10% of remaining)
        if np.random.random() < 0.1:
            return True, "diversity_sampling"

        return False, "standard_processing"

    def add_training_example(self, article_data: dict, agent_predictions: dict,
                           ground_truth: dict | None = None):
        """
        Add a new training example to the buffer
        """
        should_train, reason = self.should_use_for_training(article_data, agent_predictions)

        if not should_train and not ground_truth:
            return  # Skip this example

        # Create training example
        training_example = {
            'id': f"{article_data.get('id', '')}_{datetime.now().isoformat()}",
            'text': article_data.get('content', ''),
            'url': article_data.get('url', ''),
            'entities': ground_truth or agent_predictions.get('analyst', {}).get('entities', []),
            'quality_score': agent_predictions.get('scout', {}).get('quality_score', 0.5),
            'selection_reason': reason,
            'timestamp': datetime.now().isoformat(),
            'priority': 'high' if ground_truth else 'normal'  # User corrections get priority
        }

        self.training_buffer.append(training_example)
        self.examples_processed += 1

        logger.info(f"📚 Added training example (reason: {reason})")

        # Check if we should trigger an update
        if self.should_trigger_update():
            self.incremental_update()

    def should_trigger_update(self) -> bool:
        """Determine when to trigger model update"""
        buffer_ready = len(self.training_buffer) >= self.config['update_frequency']
        high_priority_ready = any(ex['priority'] == 'high' for ex in list(self.training_buffer)[-10:])

        return buffer_ready or high_priority_ready

    def incremental_update(self):
        """
        Perform incremental model update with recent examples
        """
        if len(self.training_buffer) < 10:  # Minimum batch size
            return

        logger.info(f"🔄 Starting incremental update with {len(self.training_buffer)} examples")

        # Prepare training batch
        batch = list(self.training_buffer)
        training_data = self.prepare_training_batch(batch)

        # Save current model state for potential rollback
        self.save_checkpoint(f"pre_update_v{self.model_version}")

        # Perform update
        old_metrics = self.evaluate_model()
        self.update_model(training_data)
        new_metrics = self.evaluate_model()

        # Check if update improved performance
        if self.validate_update(old_metrics, new_metrics):
            self.model_version += 1
            self.save_checkpoint(f"updated_v{self.model_version}")
            logger.info(f"✅ Model updated successfully to v{self.model_version}")

            # Clear buffer (keep some for validation)
            keep_examples = list(self.training_buffer)[-self.config['validation_size']:]
            self.training_buffer.clear()
            self.training_buffer.extend(keep_examples)

        else:
            # Rollback model
            self.rollback_model()
            logger.warning("❌ Update degraded performance, rolled back")

    def update_model(self, training_data: list[dict]):
        """
        Update the model with new training data
        """
        self.model.train()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=self.config['learning_rate'])

        # Convert to model format (simplified)
        for example in training_data:
            # This would depend on your specific model architecture
            # For spaCy: use nlp.update()
            # For HuggingFace: prepare inputs and run training step

            inputs = self.prepare_model_inputs(example)
            outputs = self.model(**inputs)
            loss = outputs.loss if hasattr(outputs, 'loss') else self.compute_loss(outputs, inputs)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    def detect_agent_disagreement(self, agent_predictions: dict) -> bool:
        """
        Detect if different agents disagree on the content
        Indicates challenging example worth learning from
        """
        # Compare entity extraction confidence across agents
        analyst_entities = agent_predictions.get('analyst', {}).get('entities', [])
        scout_quality = agent_predictions.get('scout', {}).get('quality_score', 0.5)

        # If analyst found many entities but scout rated quality low
        if len(analyst_entities) > 5 and scout_quality < 0.4:
            return True

        # Other disagreement patterns...
        return False

    def is_high_value_content(self, article_data: dict) -> bool:
        """Check if content is high-value (financial, political, etc.)"""
        content = article_data.get('content', '').lower()
        high_value_terms = {
            'billion', 'million', 'investment', 'earnings', 'revenue',
            'government', 'policy', 'regulation', 'parliament', 'minister',
            'cryptocurrency', 'bitcoin', 'stock market', 'fed', 'central bank'
        }

        return any(term in content for term in high_value_terms)

    def prepare_training_batch(self, examples: list[dict]) -> list[dict]:
        """Convert buffer examples to model training format"""
        # This would depend on your model architecture
        # Simplified version here
        return [{
            'text': ex['text'],
            'entities': ex['entities'],
            'quality_score': ex['quality_score']
        } for ex in examples]

    def prepare_model_inputs(self, example: dict) -> dict:
        """Prepare single example for model input"""
        # Simplified - would need proper tokenization, etc.
        return {
            'input_text': example['text'],
            'target_entities': example['entities']
        }

    def evaluate_model(self) -> dict[str, float]:
        """Evaluate model performance on validation set"""
        # Simplified metrics
        return {
            'entity_f1': 0.85,  # Would compute actual F1
            'precision': 0.87,
            'recall': 0.83
        }

    def validate_update(self, old_metrics: dict, new_metrics: dict) -> bool:
        """Check if model update improved performance"""
        for metric_name, old_value in old_metrics.items():
            new_value = new_metrics.get(metric_name, 0)
            degradation = old_value - new_value

            if degradation > self.config['performance_threshold']:
                logger.warning(f"Performance degraded in {metric_name}: {degradation:.3f}")
                return False

        return True

    def save_checkpoint(self, checkpoint_name: str):
        """Save model checkpoint"""
        # Implementation would save actual model state
        logger.info(f"💾 Saved checkpoint: {checkpoint_name}")

    def rollback_model(self):
        """Rollback to previous model version"""
        # Implementation would restore previous model state
        logger.info(f"🔄 Rolled back to model v{self.model_version}")

    def get_training_stats(self) -> dict[str, Any]:
        """Get statistics about the online learning process"""
        return {
            'examples_processed': self.examples_processed,
            'buffer_size': len(self.training_buffer),
            'model_version': self.model_version,
            'buffer_composition': self.analyze_buffer_composition(),
            'recent_updates': self.examples_processed // self.config['update_frequency']
        }

    def analyze_buffer_composition(self) -> dict[str, int]:
        """Analyze what types of examples are in the buffer"""
        composition = {}
        for example in self.training_buffer:
            reason = example['selection_reason']
            composition[reason] = composition.get(reason, 0) + 1
        return composition


# Integration with JustNewsAgentic Pipeline
class EnhancedAnalystWithOnlineLearning:
    """
    Enhanced Analyst agent with online learning capabilities
    """

    def __init__(self):
        # Load existing models
        self.ner_model = self.load_ner_model()
        self.online_trainer = OnlineNERTrainer(self.ner_model)

        # Statistics tracking
        self.processed_articles = 0
        self.training_examples_added = 0

    def analyze_content(self, article_data: dict) -> dict[str, Any]:
        """
        Enhanced content analysis with online learning integration
        """
        # Perform standard analysis
        predictions = {
            'entities': self.extract_entities(article_data['content']),
            'statistics': self.analyze_statistics(article_data['content']),
            'metrics': self.extract_metrics(article_data['content'])
        }

        # Get predictions from other agents (would be actual MCP calls)
        scout_predictions = self.get_scout_predictions(article_data)

        # Combine all agent predictions
        all_predictions = {
            'analyst': predictions,
            'scout': scout_predictions
        }

        # Add to online learning pipeline
        self.online_trainer.add_training_example(article_data, all_predictions)

        self.processed_articles += 1

        return predictions

    def handle_user_correction(self, article_data: dict, corrected_entities: list[dict]):
        """
        Handle user corrections for immediate learning
        High-priority training examples
        """
        # Create ground truth from user correction
        ground_truth = {
            'entities': corrected_entities,
            'source': 'user_feedback',
            'confidence': 1.0  # User corrections are 100% confident
        }

        # Force immediate learning from correction
        self.online_trainer.add_training_example(
            article_data,
            {'analyst': ground_truth},
            ground_truth=ground_truth
        )

        logger.info("📝 User correction processed for immediate learning")

    def get_training_statistics(self) -> dict[str, Any]:
        """Get comprehensive training statistics"""
        online_stats = self.online_trainer.get_training_stats()

        return {
            'articles_processed': self.processed_articles,
            'online_learning': online_stats,
            'learning_efficiency': (online_stats['examples_processed'] / max(self.processed_articles, 1)) * 100,
            'model_evolution': f"v{online_stats['model_version']} (updated {online_stats['recent_updates']} times)"
        }

    # Placeholder methods (would be actual implementations)
    def load_ner_model(self): return None
    def extract_entities(self, text): return []
    def analyze_statistics(self, text): return {}
    def extract_metrics(self, text): return {}
    def get_scout_predictions(self, article): return {'quality_score': 0.8}


if __name__ == "__main__":
    # Example usage
    enhanced_analyst = EnhancedAnalystWithOnlineLearning()

    # Process an article (would normally come from BBC crawler)
    article = {
        'id': 'bbc_001',
        'content': 'Apple Inc. reported $95.3 billion in quarterly revenue, with CEO Tim Cook announcing plans for renewable energy investments.',
        'url': 'https://bbc.com/news/example'
    }

    # Analyze with online learning
    results = enhanced_analyst.analyze_content(article)

    # Check training statistics
    stats = enhanced_analyst.get_training_statistics()
    print(f"Training Statistics: {json.dumps(stats, indent=2)}")
