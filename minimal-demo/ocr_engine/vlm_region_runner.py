"""Isolated, warm local VLM workers. Only crop pixels and task settings cross IPC.

No OCR text, reference label, page metadata, or confidence is accepted by the
worker protocol. Native inference timeouts terminate the process, not a thread.
"""
from __future__ import annotations

import atexit
import base64
from collections import OrderedDict
from contextlib import contextmanager, suppress
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time

PREFIX = "__REGION_VLM_RESULT__"
PROMPT_VERSION = "engineering-region-native-v1"
MODEL_IDS = {"glm-ocr": "zai-org/GLM-OCR",
             "mineru": "opendatalab/MinerU2.5-Pro-2604-1.2B",
             "formulanet": "PaddlePaddle/PP-FormulaNet_plus-L"}


def crop_png(image_crop):
    """PIL inputs are RGB; ndarray inputs follow the application's BGR convention."""
    from PIL import Image
    if not isinstance(image_crop, Image.Image):
        import numpy as np
        value = np.asarray(image_crop)
        if value.ndim == 3 and value.shape[2] == 3:
            value = value[:, :, ::-1]
        elif value.ndim == 3 and value.shape[2] == 4:
            value = value[:, :, [2, 1, 0, 3]]
        image_crop = Image.fromarray(value)
    image_crop = image_crop.convert("RGB")
    if min(image_crop.size) < 1:
        raise ValueError("Empty crop")
    stream = io.BytesIO()
    image_crop.save(stream, format="PNG")
    return stream.getvalue(), list(image_crop.size)


class _Worker:
    def __init__(self, engine, config, log_dir):
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log = (log_dir / (engine + ".log")).open("a", encoding="utf-8")
        script = Path(__file__).resolve().parents[1] / "scripts" / "engineering_region_vlm_worker.py"
        command = [str(config.get("python") or sys.executable), "-u", str(script),
                   "--engine", engine, "--model-dir", str(config["model_dir"]),
                   "--pixel-cap", str(config.get("pixel_cap", 1048576))]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=self.log, text=True, encoding="utf-8", bufsize=1,
            env={**os.environ, "PYTHONIOENCODING": "utf-8", "TOKENIZERS_PARALLELISM": "false",
                 "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"})
        self.messages = queue.Queue()
        self.thread = threading.Thread(target=self._drain, daemon=True)
        self.thread.start()
        self.identity = None

    def _drain(self):
        try:
            for line in self.process.stdout:
                if line.startswith(PREFIX):
                    try:
                        self.messages.put(json.loads(line[len(PREFIX):]))
                    except ValueError:
                        self.messages.put({"status": "error", "error": "worker_protocol_error"})
                else:
                    self.log.write(line)
                    self.log.flush()
        finally:
            self.messages.put({"status": "error", "error": "worker_exited"})

    def receive(self, timeout):
        try:
            return self.messages.get(timeout=max(0.001, timeout))
        except queue.Empty:
            self.close()
            return {"status": "timeout", "error": "hard_worker_timeout"}

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
        with suppress(subprocess.TimeoutExpired):
            self.process.wait(timeout=2)
        self.thread.join(timeout=2)
        for stream in (self.process.stdin, self.process.stdout, self.log):
            with suppress(Exception):
                stream.close()


class RegionVLMRunner:
    """Serialize inference and retain per-model workers across pages.

    Successful cache entries include the actual loaded model's weight identity;
    failed requests are retained by callers, not silently replaced by retries.
    """
    def __init__(self, configs, *, log_dir=None, load_timeout=600, cache_size=2048):
        self.configs = copy.deepcopy(configs)
        self.log_dir = Path(log_dir or Path(tempfile.gettempdir()) / "engineering-region-vlm")
        self.load_timeout = min(600., max(1., float(load_timeout)))
        self.cache_size = max(0, int(cache_size))
        self.workers = {}
        self.failures = {}
        self.cache = OrderedDict()
        self.lock = threading.RLock()

    def close(self):
        with self.lock:
            for worker in self.workers.values():
                worker.close()
            self.workers.clear()

    def reset_failure(self, model):
        """Explicit retry boundary; never called automatically by page inference."""
        with self.lock:
            worker = self.workers.pop(model, None)
            if worker:
                worker.close()
            self.failures.pop(model, None)

    @contextmanager
    def _request_lock(self, timeout):
        acquired = self.lock.acquire(timeout=max(.001, float(timeout)))
        try:
            yield acquired
        finally:
            if acquired:
                self.lock.release()

    def __call__(self, image_crop, *, model, task, max_new_tokens, timeout_seconds):
        wall_started = time.perf_counter()
        if model not in MODEL_IDS or task not in {"text", "formula"}:
            return {"status": "error", "error": "unsupported_model_or_task", "text": "",
                    "elapsed_seconds": 0., "load_seconds": 0., "inference_executed": False}
        config = self.configs.get(model)
        if not config or not config.get("model_dir"):
            return {"status": "error", "error": "model_not_configured", "text": "",
                    "model": {"id": MODEL_IDS[model]}, "elapsed_seconds": 0., "load_seconds": 0., "inference_executed": False}
        if model == "formulanet" and task != "formula":
            return {"status": "error", "error": "formula_only_model", "text": "",
                    "elapsed_seconds": 0., "load_seconds": 0., "inference_executed": False}
        try:
            png, source_size = crop_png(image_crop)
        except Exception as error:
            return {"status": "error", "error": "invalid_crop: " + str(error), "text": "",
                    "elapsed_seconds": 0., "load_seconds": 0., "inference_executed": False}
        limit = min(1024 if task == "formula" else 256, max(1, int(max_new_tokens)))
        request_limit = min(15., max(.001, float(timeout_seconds)))
        queued = time.perf_counter()
        with self._request_lock(request_limit) as acquired:
            queue_seconds = time.perf_counter() - queued
            if not acquired:
                return {"status": "timeout", "error": "queue_budget_exhausted", "text": "",
                        "elapsed_seconds": queue_seconds, "load_seconds": 0.,
                        "queue_seconds": queue_seconds, "inference_executed": False}
            if model in self.failures:
                return {**copy.deepcopy(self.failures[model]), "elapsed_seconds": queue_seconds,
                        "load_seconds": 0., "inference_executed": False,
                        "circuit_open": True, "retry_requires_explicit_reset": True}
            load_seconds = 0.
            worker = self.workers.get(model)
            if worker is None:
                started = time.perf_counter()
                try:
                    worker = _Worker(model, config, self.log_dir)
                    ready = worker.receive(self.load_timeout)
                except Exception as error:
                    ready = {"status": "error", "error": str(error)}
                load_seconds = time.perf_counter() - started
                if ready.get("event") != "ready":
                    if worker:
                        worker.close()
                    result = {"status": "error", "error": "model_load_failed", "load_failure": ready,
                            "text": "", "elapsed_seconds": 0., "load_seconds": load_seconds, "inference_executed": False,
                            "wall_seconds": time.perf_counter() - wall_started}
                    self.failures[model] = copy.deepcopy(result)
                    return result
                worker.identity = ready["identity"]
                worker.load_gpu_memory = ready.get("load_gpu_memory", {})
                self.workers[model] = worker
            image_hash = hashlib.sha256(png).hexdigest()
            cache_key = (model, worker.identity["weight_identity"],
                         worker.identity.get("configuration_fingerprint"), image_hash,
                         task, limit, PROMPT_VERSION, config.get("pixel_cap", 1048576))
            if cache_key in self.cache:
                result = copy.deepcopy(self.cache[cache_key])
                self.cache.move_to_end(cache_key)
                result.update(cache_hit=True, elapsed_seconds=queue_seconds, load_seconds=load_seconds,
                              wall_seconds=time.perf_counter() - wall_started, inference_executed=False)
                return result
            request = {"image_png": base64.b64encode(png).decode("ascii"), "task": task,
                       "max_new_tokens": limit}
            started = time.perf_counter()
            try:
                worker.process.stdin.write(json.dumps(request) + "\n")
                worker.process.stdin.flush()
                result = worker.receive(max(.001, request_limit - queue_seconds))
            except (BrokenPipeError, OSError, ValueError) as error:
                result = {"status": "error", "error": "worker_io_error", "detail": str(error)}
            result.update(model=worker.identity, prompt_version=PROMPT_VERSION,
                          elapsed_seconds=time.perf_counter() - started + queue_seconds, load_seconds=load_seconds,
                          wall_seconds=time.perf_counter() - wall_started,
                          image_sha256=image_hash, source_size=source_size, cache_hit=False,
                          queue_seconds=queue_seconds, inference_executed=True,
                          load_gpu_memory=worker.load_gpu_memory if load_seconds else None)
            result.setdefault("text", "")
            if result.get("status") in {"timeout", "error"}:
                worker.close()
                self.workers.pop(model, None)
                self.failures[model] = copy.deepcopy(result)
            elif result.get("status") == "ok" and self.cache_size:
                self.cache[cache_key] = copy.deepcopy(result)
                while len(self.cache) > self.cache_size:
                    self.cache.popitem(last=False)
            return result


_POOLS = {}
_POOL_LOCK = threading.Lock()


def build_region_vlm_runner(settings):
    """Application factory, keyed by immutable configuration rather than page state."""
    def get(name, default=None):
        return settings.get(name, default) if isinstance(settings, dict) else getattr(settings, name, default)
    explicit = get("OCR_ENGINEERING_VLM_CONFIGS", None)
    configs = copy.deepcopy(explicit) if explicit else {}
    for model, prefix in (("glm-ocr", "GLM"), ("mineru", "MINERU"), ("formulanet", "FORMULANET")):
        directory = get("OCR_ENGINEERING_VLM_" + prefix + "_MODEL_DIR", None)
        if directory and model not in configs:
            configs[model] = {"model_dir": str(directory),
                             "python": get("OCR_ENGINEERING_VLM_" + prefix + "_PYTHON", sys.executable)}
    log_dir = get("OCR_ENGINEERING_VLM_LOG_DIR", None)
    key = json.dumps({"configs": configs, "log_dir": str(log_dir or "")}, sort_keys=True, default=str)
    with _POOL_LOCK:
        if key not in _POOLS:
            _POOLS[key] = RegionVLMRunner(configs, log_dir=log_dir)
        return _POOLS[key]


def _close_pools():
    for pool in tuple(_POOLS.values()):
        pool.close()


atexit.register(_close_pools)
