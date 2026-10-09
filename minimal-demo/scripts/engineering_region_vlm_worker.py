"""GPU-only crop workers for GLM-OCR, MinerU and the FormulaNet control.

Run with a model-specific interpreter. A parent process imposes hard deadlines.
Models and processors must already exist locally; no model substitution is made.
"""
import argparse
import base64
from contextlib import redirect_stdout
import hashlib
import importlib.metadata
import io
import json
import math
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ocr_engine.vlm_region_runner import MODEL_IDS, PREFIX, PROMPT_VERSION


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def file_hash(path):
    result = hashlib.sha256()
    with path.open("rb") as source:
        for data in iter(lambda: source.read(8 * 1024 * 1024), b""):
            result.update(data)
    return result.hexdigest()


def model_identity(directory, engine):
    weights = [p for p in sorted(directory.rglob("*")) if p.is_file()
               and p.suffix in {".safetensors", ".pdiparams", ".pdparams", ".bin"}]
    if not weights:
        raise ValueError("No local model weights found")
    files = [{"path": str(p.relative_to(directory)), "bytes": p.stat().st_size,
              "sha256": file_hash(p)} for p in weights]
    configs = [{"path": p.name, "sha256": file_hash(p)} for p in sorted(directory.iterdir())
               if p.is_file() and p.suffix in {".json", ".yml", ".yaml", ".jinja"}]
    versions = {}
    for name in ("torch", "torchvision", "transformers", "mineru-vl-utils", "paddleocr",
                 "paddlex", "paddlepaddle-gpu", "Pillow", "accelerate", "safetensors"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            pass
    content_identity = sorted(({"sha256": item["sha256"], "bytes": item["bytes"]} for item in files),
                              key=lambda item: (item["sha256"], item["bytes"]))
    return {"id": MODEL_IDS[engine], "model_path": str(directory.resolve()),
            "weight_identity": digest(content_identity), "weight_files": files,
            "configuration_fingerprint": digest(configs), "configuration_files": configs,
            "versions": versions}


def jsonable(value):
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items() if k not in {"input_img", "output_img"}}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "tolist"):
        return value.tolist()
    return str(value)


def generation_status(tokens, eos, limit):
    eos = eos if isinstance(eos, (list, tuple, set)) else [eos]
    end = next((index for index, token in enumerate(tokens) if int(token) in eos), None)
    seen = end is not None
    length = end + 1 if seen else len(tokens)
    return {"output_tokens": length, "raw_sequence_tokens": len(tokens), "eos_observed": seen,
            "truncation_checked": True,
            "status": "truncated" if length > limit or (length >= limit and not seen) else "ok"}


class HFTrace:
    """Observe generate inputs/outputs without changing native MinerU processing."""
    def __init__(self, model, processor):
        self.rows = []
        original = model.generate

        def observed(*args, **kwargs):
            result = original(*args, **kwargs)
            inputs = kwargs["input_ids"]
            tokens = result[0, inputs.shape[-1]:].tolist()
            row = generation_status(tokens, model.generation_config.eos_token_id,
                                    kwargs["max_new_tokens"])
            row.update(input_tokens=int(inputs.shape[-1]), output_token_ids=tokens,
                       processor_image_grid_thw=jsonable(kwargs.get("image_grid_thw")),
                       pixel_values_shape=list(kwargs["pixel_values"].shape),
                       raw_text=processor.decode(tokens, skip_special_tokens=True,
                                                 clean_up_tokenization_spaces=False),
                       generation_settings={k: jsonable(v) for k, v in kwargs.items()
                                            if k in {"max_new_tokens", "do_sample", "temperature",
                                                     "top_p", "top_k", "repetition_penalty",
                                                     "no_repeat_ngram_size", "use_cache"}})
            self.rows.append(row)
            return result

        model.generate = observed


class FormulaTrace:
    def __init__(self, predictor):
        self.rows = []
        post_op = predictor.post_op
        self.eos = post_op.eos_token_id

        def observed(tokens, *args, **kwargs):
            self.rows.extend([jsonable(row) for row in tokens])
            return post_op(tokens, *args, **kwargs)

        predictor.post_op = observed


def run(args):
    output_stream = sys.stdout

    def emit(value):
        output_stream.write(PREFIX + json.dumps(value, ensure_ascii=False) + "\n")
        output_stream.flush()

    with redirect_stdout(sys.stderr):
        started = time.perf_counter()
        try:
            from PIL import Image
            identity = model_identity(args.model_dir, args.engine)
            if args.engine in {"glm-ocr", "mineru"}:
                import torch
                from transformers import AutoProcessor
                if not torch.cuda.is_available():
                    raise RuntimeError("CUDA required; CPU fallback is disabled")
                if args.engine == "glm-ocr":
                    from transformers import GlmOcrForConditionalGeneration as Model
                else:
                    from transformers import Qwen2VLForConditionalGeneration as Model
                model = Model.from_pretrained(str(args.model_dir), dtype=torch.bfloat16,
                    device_map="cuda:0", attn_implementation="sdpa", local_files_only=True).eval()
                processor = AutoProcessor.from_pretrained(str(args.model_dir), local_files_only=True)
                trace = HFTrace(model, processor)
                identity.update(precision=str(model.dtype), device=str(model.device),
                    architecture=type(model).__name__, attention="sdpa",
                    gpu_name=torch.cuda.get_device_name(0),
                    gpu_total_memory_bytes=torch.cuda.get_device_properties(0).total_memory,
                    compute_capability=list(torch.cuda.get_device_capability(0)),
                    torch_cuda_version=torch.version.cuda,
                    generation_configuration=jsonable(model.generation_config.to_dict()))
                if args.engine == "mineru":
                    from mineru_vl_utils import MinerUClient
                    from mineru_vl_utils.mineru_client import DEFAULT_PROMPTS, MinerUSamplingParams
                    client = MinerUClient(backend="transformers", model=model, processor=processor,
                        image_analysis=False, batch_size=1, max_concurrency=1)
            else:
                from paddleocr import FormulaRecognition
                import paddle
                if not paddle.is_compiled_with_cuda():
                    raise RuntimeError("CUDA required; CPU fallback is disabled")
                model = FormulaRecognition(model_name="PP-FormulaNet_plus-L",
                    model_dir=str(args.model_dir), device="gpu:0")
                predictor = model.paddlex_predictor
                trace = FormulaTrace(predictor)
                identity.update(precision="native_static_configuration", device="gpu:0",
                    architecture=type(model).__name__, configuration=jsonable(predictor.config),
                    native_token_ceiling=2560, dynamic_token_limit_supported=False)
            load_memory = ({"peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                            "peak_reserved_bytes": torch.cuda.max_memory_reserved()}
                           if args.engine in {"glm-ocr", "mineru"} else {"status": "native_allocator_unavailable"})
            emit({"event": "ready", "identity": identity, "load_gpu_memory": load_memory,
                  "load_seconds": time.perf_counter() - started})
        except Exception as error:
            emit({"status": "error", "error": "model_load_failed", "error_type": type(error).__name__,
                  "detail": str(error)[:1500], "load_seconds": time.perf_counter() - started})
            return

        for raw_request in sys.stdin:
            try:
                request = json.loads(raw_request)
                if set(request) != {"image_png", "task", "max_new_tokens"}:
                    raise ValueError("Unexpected worker request fields")
                task, limit = request["task"], int(request["max_new_tokens"])
                if task not in {"text", "formula"} or not 1 <= limit <= (1024 if task == "formula" else 256):
                    raise ValueError("Invalid task or token limit")
                image = Image.open(io.BytesIO(base64.b64decode(request["image_png"], validate=True))).convert("RGB")
                source_size = list(image.size)
                factor = min(1., math.sqrt(args.pixel_cap / (image.width * image.height)))
                if factor < 1.:
                    image = image.resize((max(1, int(image.width * factor)),
                                          max(1, int(image.height * factor))), Image.Resampling.LANCZOS)
                result = {"status": "ok", "task": task, "source_size": source_size,
                          "input_size": list(image.size), "pixel_cap": args.pixel_cap,
                          "output_token_limit": limit, "prompt_version": PROMPT_VERSION}
                started = time.perf_counter()
                trace.rows.clear()
                if args.engine in {"glm-ocr", "mineru"}:
                    torch.cuda.reset_peak_memory_stats()
                    prompt = "Formula Recognition:" if task == "formula" else "Text Recognition:"
                    with torch.inference_mode():
                        if args.engine == "glm-ocr":
                            messages = [{"role": "user", "content": [{"type": "image", "image": image},
                                         {"type": "text", "text": prompt}]}]
                            batch = processor.apply_chat_template(messages, tokenize=True,
                                add_generation_prompt=True, return_dict=True, return_tensors="pt").to(model.device)
                            model.generate(**batch, max_new_tokens=limit, do_sample=False)
                            native_text = trace.rows[-1]["raw_text"]
                        else:
                            prompt = DEFAULT_PROMPTS["equation" if task == "formula" else "[default]"]
                            image = client.helper.resize_by_need(image)
                            result["native_input_size"] = list(image.size)
                            native_text = client.client.predict(image, prompt=prompt,
                                sampling_params=MinerUSamplingParams(temperature=0., top_p=1., top_k=1,
                                    max_new_tokens=limit, presence_penalty=0., frequency_penalty=0.))
                        torch.cuda.synchronize()
                    result.update(trace.rows[-1])
                    result.update(text=native_text.strip(), raw_output={"text": native_text, "trace": trace.rows},
                        gpu_memory={"peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                                    "peak_reserved_bytes": torch.cuda.max_memory_reserved()})
                else:
                    if task != "formula":
                        raise ValueError("FormulaNet supports formula tasks only")
                    import numpy as np
                    prompt = "native_formula_recognition"
                    records = []
                    for item in model.predict(np.asarray(image)[:, :, ::-1].copy(), batch_size=1):
                        value = item.json
                        records.append(jsonable(value() if callable(value) else value))
                    native_text = " ".join(item.get("res", item).get("rec_formula", "") for item in records)
                    token_rows = [generation_status(row, trace.eos, limit) for row in trace.rows]
                    # Fixed exported graph cannot accept a dynamic token cap. Reject over-limit
                    # evidence explicitly instead of clipping and claiming a complete result.
                    excessive = any(row["output_tokens"] > limit for row in token_rows)
                    result.update(text=native_text.strip(), raw_output=records,
                        native_generation_trace=token_rows, output_token_limit_enforced=False,
                        native_token_ceiling=2560, truncation_checked=bool(token_rows),
                        status="truncated" if excessive or any(r["status"] == "truncated" for r in token_rows) else "ok")
                    if not token_rows:
                        result.update(status="error", error="native_token_trace_unavailable")
                result.update(prompt=prompt, prompt_sha256=digest(prompt),
                              inference_seconds=time.perf_counter() - started)
                if result["status"] == "ok" and not result["text"]:
                    result["empty_output"] = True  # Crop-level failure, not a broken model.
                emit(result)
            except Exception as error:
                emit({"status": "error", "error": "inference_failed", "error_type": type(error).__name__,
                      "detail": str(error)[:1500], "text": ""})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=tuple(MODEL_IDS), required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--pixel-cap", type=int, default=1048576)
    args = parser.parse_args()
    if args.pixel_cap <= 0:
        parser.error("--pixel-cap must be positive")
    run(args)
