import numpy as np
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import torch
    import torchvision.transforms as T
    from torchvision.models import resnet50, ResNet50_Weights
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

class WildlifeEmbeddingModel:
    """
    Provides deep embeddings for wildlife re-identification.
    Uses a pretrained ResNet-50 backbone to generate a 2048-d feature vector.
    """
    def __init__(self, device=None):
        self.device = device or ("cuda" if TORCH_AVAILABLE and torch.cuda.is_available() else "cpu")
        self.model = None
        self.transform = None
        
        if TORCH_AVAILABLE:
            try:
                # Use ResNet50 pretrained on ImageNet as a feature extractor
                weights = ResNet50_Weights.DEFAULT
                self.model = resnet50(weights=weights)
                self.model.fc = torch.nn.Identity()  # Remove classification layer
                self.model.to(self.device)
                self.model.eval()
                
                self.transform = weights.transforms()
                logger.info(f"WildlifeEmbeddingModel loaded on {self.device}")
            except Exception as e:
                logger.error(f"Failed to load torch model: {e}")
                self.model = None

    def extract(self, image_bgr: np.ndarray) -> np.ndarray | None:
        """Extracts a normalized embedding from a BGR image."""
        if not TORCH_AVAILABLE or self.model is None:
            # Fallback: Generate a deterministic pseudo-embedding based on image hash
            # This keeps the pipeline running during development/setup.
            return self._generate_fallback_embedding(image_bgr)

        try:
            # Convert BGR (OpenCV) to RGB (PyTorch)
            img_rgb = image_bgr[:, :, ::-1]
            from PIL import Image
            img_pil = Image.fromarray(img_rgb)
            
            tensor = self.transform(img_pil).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                embedding = self.model(tensor).cpu().numpy().flatten()
            
            # Normalize to unit length for Cosine Similarity
            norm = np.linalg.norm(embedding)
            return embedding / norm if norm > 0 else embedding
        except Exception as e:
            logger.warning(f"Embedding extraction failed: {e}")
            return None

    def _generate_fallback_embedding(self, image_bgr: np.ndarray) -> np.ndarray:
        """Generates a stable, deterministic pseudo-embedding for local development."""
        # Use a simple resized average to create a unique-ish vector
        small = np.resize(image_bgr, (16, 16, 3))
        vector = small.flatten().astype(np.float32)
        norm = np.linalg.norm(vector)
        return vector / norm if norm > 0 else vector

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculates the cosine similarity between two unit vectors."""
    return float(np.dot(a, b))

# Singleton instance
embedding_engine = WildlifeEmbeddingModel()
