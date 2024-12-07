from pathlib import Path
import shutil
import logging
from datetime import datetime

def setup_logger(log_folder: Path) -> logging.Logger:
    log_folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ProjectLogger")
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        current_time = datetime.now()
        log_filename = f"project_{current_time.strftime('%Y-%m-%d_%H')}.log"
        log_file_path = log_folder / log_filename
        fh = logging.FileHandler(log_file_path, encoding='utf-8', mode='a')
        fh.setLevel(logging.DEBUG)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
        fh.setFormatter(formatter)
        ch.setFormatter(formatter)
        logger.addHandler(fh)
        logger.addHandler(ch)
        logger.debug(f"Logger initialized. Logs are being written to {log_file_path}")

    return logger

class ProjectManager:
    def __init__(
        self,
        project_path: Path,
        ignored_dirs: list = None,
        ignored_files: list = None,
        ignored_path_substrings: list = None
    ):
        self.project_path = project_path.resolve()
        self.workspace_folder = Path('./workspace').resolve()
        self.analysis_folder = self.workspace_folder / self.project_path.name
        self.code_summary_folder = self.analysis_folder / "code_summaries"
        self.ignored_dirs = ignored_dirs if ignored_dirs else []
        self.ignored_files = ignored_files if ignored_files else []
        self.ignored_path_substrings = ignored_path_substrings if ignored_path_substrings else []
        self.logger = None

    def initialize_logger(self):
        self.logger = setup_logger(self.analysis_folder)
        self.logger.info(f"ProjectManager initialized for project: {self.project_path}")

    def close_logger(self):
        if self.logger:
            handlers = self.logger.handlers[:]
            for handler in handlers:
                handler.close()
                self.logger.removeHandler(handler)

    def setup_workspace(self, clean_existing: bool = False):
        self.logger.info("Setting up workspace...")

        if self.workspace_folder.exists():
            self.logger.info(f"Workspace folder already exists at {self.workspace_folder}")
            if clean_existing:
                self.logger.info(f"Cleaning existing analysis folder at {self.analysis_folder}")
                self.close_logger()
                shutil.rmtree(self.analysis_folder, ignore_errors=True)
                self.logger.info(f"Removed existing analysis folder at {self.analysis_folder}")
        else:
            self.logger.info(f"Creating workspace folder at {self.workspace_folder}")
            self.workspace_folder.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Created workspace folder at {self.workspace_folder}")

        if not self.analysis_folder.exists():
            self.logger.info(f"Creating analysis folder at {self.analysis_folder}")
            self.analysis_folder.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Created analysis folder at {self.analysis_folder}")
        else:
            self.logger.info(f"Analysis folder already exists at {self.analysis_folder}")

        if not self.code_summary_folder.exists():
            self.logger.info(f"Creating code summaries folder at {self.code_summary_folder}")
            self.code_summary_folder.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Created code summaries folder at {self.code_summary_folder}")
        else:
            self.logger.info(f"Code summaries folder already exists at {self.code_summary_folder}")

    def get_project_folder(self) -> Path:
        return self.project_path

    def get_analysis_folder(self) -> Path:
        return self.analysis_folder
