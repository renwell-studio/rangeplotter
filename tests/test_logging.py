
import logging
import pytest
from unittest.mock import MagicMock, patch
from rangeplotter.utils.logging import setup_logging, log_memory_usage
from rich.console import Console
from rich.logging import RichHandler

def test_setup_logging_defaults():
    cfg = {}
    logger = setup_logging(cfg)
    assert logger.name == "rangeplotter"
    # setup_logging configures the root logger via basicConfig
    root_logger = logging.getLogger()
    assert len(root_logger.handlers) > 0

def test_setup_logging_verbose():
    cfg = {}
    # verbose=2 -> DEBUG
    with patch("rangeplotter.utils.logging.RichHandler") as mock_handler:
        setup_logging(cfg, verbose=2)
        # Check if RichHandler was initialized with DEBUG level
        args, kwargs = mock_handler.call_args
        assert kwargs['level'] == logging.DEBUG

def test_setup_logging_file(tmp_path):
    log_file = tmp_path / "test.log"
    cfg = {"file": str(log_file), "level": "DEBUG"}
    
    logger = setup_logging(cfg)
    
    # Verify file handler is added
    file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == str(log_file)
    
    logger.debug("Test message")
    # Force flush/close might be needed depending on buffering, but usually basicConfig handles it.
    # Let's check if file was created.
    assert log_file.exists()

def test_log_memory_usage():
    logger = MagicMock()
    
    with patch("psutil.Process") as mock_process:
        mock_mem = MagicMock()
        mock_mem.rss = 1024 * 1024 * 10 # 10 MB
        mock_mem.vms = 1024 * 1024 * 20 # 20 MB
        mock_process.return_value.memory_info.return_value = mock_mem
        
        log_memory_usage(logger, "test")
        
        logger.info.assert_called_once()
        args = logger.info.call_args[0][0]
        assert "RSS=10.0 MB" in args
        assert "VMS=20.0 MB" in args
        assert "[test]" in args

def test_log_memory_usage_error():
    logger = MagicMock()
    with patch("psutil.Process", side_effect=Exception("Error")):
        log_memory_usage(logger)
        logger.warning.assert_called_once()

def test_setup_logging_verbose():
    cfg = {}
    setup_logging(cfg, verbose=1)
    root_logger = logging.getLogger()
    rich_handlers = [h for h in root_logger.handlers if isinstance(h, RichHandler)]
    assert rich_handlers[0].level == logging.INFO

    setup_logging(cfg, verbose=2)
    rich_handlers = [h for h in logging.getLogger().handlers if isinstance(h, RichHandler)]
    assert rich_handlers[0].level == logging.DEBUG

def test_setup_logging_file(tmp_path):
    log_file = tmp_path / "test.log"
    cfg = {"file": str(log_file), "level": "DEBUG"}
    
    logger = setup_logging(cfg, verbose=0)
    logger.debug("Test debug message")
    
    # Force flush
    for h in logging.getLogger().handlers:
        h.flush()
        
    assert log_file.exists()
    content = log_file.read_text()
    assert "Test debug message" in content

def test_log_memory_usage():
    logger = MagicMock()
    
    with patch("psutil.Process") as mock_process:
        mock_mem = MagicMock()
        mock_mem.rss = 1024 * 1024 * 10 # 10 MB
        mock_mem.vms = 1024 * 1024 * 20 # 20 MB
        mock_process.return_value.memory_info.return_value = mock_mem
        
        log_memory_usage(logger, "test_context")
        
        logger.info.assert_called_once()
        args = logger.info.call_args[0][0]
        assert "Memory Usage [test_context]" in args
        assert "RSS=10.0 MB" in args

def test_log_memory_usage_import_error():
    logger = MagicMock()
    with patch.dict("sys.modules", {"psutil": None}):
        log_memory_usage(logger)
        logger.info.assert_not_called()
        logger.warning.assert_not_called()

def test_log_memory_usage_exception():
    logger = MagicMock()
    with patch("psutil.Process", side_effect=Exception("Boom")):
        log_memory_usage(logger)
        logger.warning.assert_called_once()
