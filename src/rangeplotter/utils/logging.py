import logging
import os
from typing import Dict
from pathlib import Path

def setup_logging(cfg: Dict, verbose: int = 0):
    level = getattr(logging, cfg.get("level", "INFO"))
    
    # Console handler levels:
    # 0 (Standard): WARNING
    # 1 (-v): INFO
    # 2 (-vv): DEBUG
    if verbose == 0:
        console_level = logging.WARNING
    elif verbose == 1:
        console_level = logging.INFO
    else:
        console_level = logging.DEBUG
        
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(console_level)
    
    handlers = [stream_handler]
    
    log_file = cfg.get("file")
    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path)
        file_handler.setLevel(level) # File always gets the configured level
        handlers.append(file_handler)
        
    logging.basicConfig(
        level=logging.NOTSET, # Let handlers filter
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
        force=True # Ensure we override any existing config
    )
    return logging.getLogger("rangeplotter")

def log_memory_usage(logger: logging.Logger, context: str = ""):
    try:
        import psutil
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        logger.info(f"Memory Usage [{context}]: RSS={mem_info.rss / 1024 / 1024:.1f} MB, VMS={mem_info.vms / 1024 / 1024:.1f} MB")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Failed to log memory usage: {e}")

__all__ = ["setup_logging", "log_memory_usage"]
