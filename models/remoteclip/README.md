# Staging RemoteCLIP

TerreX's `backend/services/embeddings.py` looks for a checkpoint in this
directory at startup. If none is found, it **transparently falls back** to a
deterministic, non-AI placeholder embedder (visual/lexical hashing) so the
rest of the pipeline is exercisable — every embedding it produces is tagged
`is_placeholder=True` and the UI surfaces a warning badge whenever placeholder
results are shown.

## What to place here

One of:
- `RemoteCLIP-ViT-B-32.pt`
- `RemoteCLIP-RN50.pt`
- `remoteclip.pt` (any `.pt` file — the first one found is used)

## Where to get it (must be downloaded on a machine with internet, then
copied into this folder — TerreX itself never fetches it at runtime)

- **Model**: RemoteCLIP
- **Authors**: Fan Liu, Delong Chen, Zhangqingyun Guan, Xiaocong Zhou, Jiale Zhu, Jun Zhou (2023)
- **Paper**: "RemoteCLIP: A Vision Language Foundation Model for Remote Sensing"
- **Weights**: released on Hugging Face at `chendelong/RemoteCLIP` (safetensors/.pt
  checkpoints fine-tuned from OpenCLIP ViT-B-32 / RN50 / ViT-L-14 on remote-sensing
  image-text pairs)
- **License**: check the current Hugging Face model card — RemoteCLIP weights
  are released for research use; confirm license terms before any non-research
  deployment.

## Staging steps

1. On a machine with internet access, download the checkpoint file(s) from
   the RemoteCLIP release (Hugging Face repo `chendelong/RemoteCLIP`).
2. Copy the `.pt` file into this directory (`models/remoteclip/`).
3. Install the optional heavy dependency in `backend/requirements.txt`:
   uncomment `torch` and `open_clip_torch`, rebuild the backend image.
4. Restart the backend. Check `GET /api/system/status` — `models.remoteclip.staged`
   should become `true` and `active_model` should show `remoteclip-vit-b-32`
   (or similar) instead of `placeholder-visual-hash`.

## Architecture note

RemoteCLIP is distributed as a fine-tune of standard OpenCLIP architectures
(ViT-B-32 / RN50 / ViT-L-14), so it loads via `open_clip.create_model_and_transforms`
with `pretrained=None` followed by `model.load_state_dict(torch.load(path))` —
see `_RealRemoteCLIP` in `backend/services/embeddings.py`.
