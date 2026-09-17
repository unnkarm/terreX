# TerreX ML Models Report

Based on the codebase analysis, TerreX uses a modular machine learning architecture where models are loaded from the `models/` directory. The system is designed to gracefully fall back to "placeholder" or mock logic if the actual model weights are not staged locally.

Here are the specific models currently integrated into the system:

## 1. RemoteCLIP
- **Purpose**: Used as the core text and image embedding service. It enables multimodal search and indexing by mapping satellite imagery patches and text queries into the same vector space.
- **Model Type**: Vision-Language Model (specifically `RemoteCLIP-ViT-B-32`).
- **Where it is defined/loaded**:
  - [`backend/services/embeddings.py`](file:///c:/Users/SUBHAM%20NABIK/Desktop/terreX/backend/services/embeddings.py): The `_RealRemoteCLIP` class loads the checkpoint via the `open_clip` library.
- **Where it is used**:
  - [`backend/services/ingestion.py`](file:///c:/Users/SUBHAM%20NABIK/Desktop/terreX/backend/services/ingestion.py): Generates vector embeddings for ingested satellite data before storing them in the vector database (like Qdrant).
  - [`backend/services/ranking.py`](file:///c:/Users/SUBHAM%20NABIK/Desktop/terreX/backend/services/ranking.py): Calibrates the raw RemoteCLIP cosine similarities into a standardized 0..1 scale.
- **Current Status**: **Staged & Active**. The actual weights file `RemoteCLIP-ViT-B-32.pt` (~605MB) is successfully staged in the `models/remoteclip/` directory.

## 2. Prithvi-EO
- **Purpose**: Earth Observation feature extraction. Used as a core backbone to extract dense, meaningful feature maps directly from satellite imagery.
- **Model Type**: Vision Transformer (`prithvi-eo-v1`).
- **Where it is defined/loaded**:
  - [`backend/services/prithvi.py`](file:///c:/Users/SUBHAM%20NABIK/Desktop/terreX/backend/services/prithvi.py): The `_RealPrithvi` class loads the model using `terratorch` (HuggingFace format).
- **Where it is used**:
  - [`backend/services/change_detection.py`](file:///c:/Users/SUBHAM%20NABIK/Desktop/terreX/backend/services/change_detection.py): Prithvi feature maps are extracted from "before" and "after" image patches to compute a per-patch feature-difference map, identifying areas of change.
- **Current Status**: **Architecture & Config Staged**. The official architecture implementation (`prithvi_mae.py`) and configuration (`config.json`) are integrated in `models/prithvi/`. Feature extraction will use the ViT backbone once model weights (`Prithvi_EO_V1_100M.pt` / `prithvi_int8.onnx`) are placed into this folder, with fallback to statistical patch features in the interim.

## 3. Dedicated Change-Detection Head (Optional / Future Work)
- **Purpose**: A trained network (e.g., a Siamese difference network or full bi-temporal segmentation model) to replace the simple feature-difference approach currently used.
- **Where it is defined**: Outlined in [`models/change/README.md`](file:///c:/Users/SUBHAM%20NABIK/Desktop/terreX/models/change/README.md).
- **Where it would be used**: If implemented, it will replace the `_difference_to_change_map` function in [`backend/services/change_detection.py`](file:///c:/Users/SUBHAM%20NABIK/Desktop/terreX/backend/services/change_detection.py).
- **Current Status**: **Not Implemented**. The system deliberately relies on a simple, explainable feature-difference approach for the MVP.
