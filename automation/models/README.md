# Local model configuration

Large model weights are not distributed or silently downloaded. No old local configuration or weight path is inherited.

`resources.json` records the baseline trained weight's SHA256 and byte size for comparison. It is provenance, not a runtime source-directory link. An independently installed copy must match the checksum pinned in your own Job configuration.

OpenCV repair is available with the base dependencies. For LaMa, install `.[lama]`, obtain an appropriately licensed TorchScript model through your own approved distribution, place it in an independent directory, and calculate its SHA256:

```powershell
Get-FileHash -Algorithm SHA256 C:/your-models/big-lama.pt
```

Provide `lama_model_path` (absolute) and `lama_model_sha256` in an image-options JSON together with `rights` and `max_mask_area`. JobManager pins the model bytes; mismatch must fail. A missing model does not become a successful LaMa execution. The adapter accepts the established two-tensor and dictionary contracts, tested using synthetic TorchScript, not a redistributed trained model.

External image editing remains an explicitly configured adapter with model allowlist, usage ledger and quality gate. It is NOT_RUN here. No model licensing grant is implied by extraction. Historical photographic fixtures retain their original provenance and are for local regression only; external redistribution requires rights review.
